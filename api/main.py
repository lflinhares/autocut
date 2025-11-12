# api/main.py

from typing import List
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from . import crud, models, schemas, security, auth
from .database import get_db, engine
from worker.celery_app import celery

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="YouTube Clipper API",
    description="An API to process YouTube videos and create clips.",
    version="1.0.0"
)

# --- AUTHENTICATION ---
@app.post("/token", response_model=schemas.Token)
def login_for_access_token(
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
):
    user = crud.authenticate_user(db, email=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = security.create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

# --- USERS ---
@app.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    print(f"!!! INSIDE create_user function. Password length: {len(user.password)}")
    
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db=db, user=user)

# --- JOBS ---
@app.post("/jobs/", response_model=schemas.Job)
def create_job_for_user(
    job: schemas.JobCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    print(f"API: Job creation requested for URL: {job.youtube_url} by user {current_user.email}")
    
    # Create the job in the database first
    db_job = crud.create_user_job(db=db, job=job, user_id=current_user.id)
    
    # Trigger the background task
    celery.send_task(
        "worker.tasks.process_video_task",
        kwargs={
            "job_id": db_job.id,
            "youtube_url": db_job.youtube_url
        }
    )
    
    print(f"API: Task for job {db_job.id} has been sent to the worker.")
    
    return db_job

@app.get("/jobs/", response_model=List[schemas.Job])
def read_user_jobs(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    jobs = crud.get_jobs_by_user(db, user_id=current_user.id, skip=skip, limit=limit)
    return jobs