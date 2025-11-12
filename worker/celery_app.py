from celery import Celery

broker_url = "redis://redis:6379/0"

result_backend = "redis://redis:6379/0" 

celery = Celery(
    __name__,
    broker=broker_url,
    backend=result_backend,
    include=['worker.tasks']
)

celery.conf.update(
    task_track_started=True,
)