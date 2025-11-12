# worker/tasks.py

from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

from .celery_app import celery
from api.models import Job 
from .logic import run_processing_pipeline

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@celery.task(bind=True)
def process_video_task(self, job_id: int, youtube_url: str):
    """
    The main background task to process a video.
    This now calls the real processing pipeline.
    """
    db = SessionLocal()
    try:
        print(f"WORKER [Job {job_id}]: Received task. Updating status to PROCESSING.")
        db.execute(
            update(Job).where(Job.id == job_id).values(status="PROCESSING")
        )
        db.commit()

        final_clip_paths = run_processing_pipeline(job_id=job_id, url=youtube_url)
        
        print(f"WORKER [Job {job_id}]: Pipeline finished. Updating status to COMPLETED.")
        db.execute(
            update(Job).where(Job.id == job_id).values(
                status="COMPLETED",
                result_urls=final_clip_paths
            )
        )
        db.commit()
        
        return {"status": "Completed", "job_id": job_id, "results": final_clip_paths}

    except Exception as e:
        error_message = f"An error occurred: {e}"
        print(f"WORKER [Job {job_id}]: {error_message}")
        import traceback
        traceback.print_exc()
        
        db.execute(
            update(Job).where(Job.id == job_id).values(
                status="FAILED",
                result_urls={"error": error_message}
            )
        )
        db.commit()
        # self.update_state(state='FAILURE', meta={'exc': error_message})
        # The above line is a more advanced way to report errors in Celery
        return {"status": "Failed", "job_id": job_id, "error": error_message}
    finally:
        db.close()