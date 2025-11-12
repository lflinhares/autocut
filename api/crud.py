from sqlalchemy.orm import Session
from . import models, schemas, security
from typing import Optional

# --- User CRUD ---
def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.email == email).first()

def create_user(db: Session, user: schemas.UserCreate) -> models.User:
    hashed_password = security.get_password_hash(user.password)
    db_user = models.User(email=user.email, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def authenticate_user(db: Session, email: str, password: str) -> Optional[models.User]:
    user = get_user_by_email(db, email)
    if not user or not security.verify_password(password, user.hashed_password):
        return None
    return user

# --- Job CRUD ---
def create_user_job(db: Session, job: schemas.JobCreate, user_id: int) -> models.Job:
    db_job = models.Job(**job.dict(), owner_id=user_id)
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job

def get_jobs_by_user(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> list[models.Job]:
    return db.query(models.Job).filter(models.Job.owner_id == user_id).offset(skip).limit(limit).all()