import uuid
from sqlalchemy.orm import Session
from . import models, schemas
from app.auth.jwt import get_password_hash
from typing import Dict, Any

def get_user(db: Session, user_id: uuid.UUID) -> models.User | None:
    """Retrieve a user by their UUID."""
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_user_by_username(db: Session, username: str) -> models.User | None:
    """Retrieve a user by their username."""
    return db.query(models.User).filter(models.User.username == username).first()

def get_user_by_email(db: Session, email: str) -> models.User | None:
    """Retrieve a user by their email address."""
    return db.query(models.User).filter(models.User.email == email).first()

def create_user(db: Session, user: schemas.UserCreate) -> models.User:
    """
    Create a new user with hashed password (for local auth).
    """
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        username=user.username,
        email=user.email,
        # **FIX**: Use the username as the full_name by default for local signups.
        full_name=user.username,
        hashed_password=hashed_password,
        provider="local"
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_user_by_social_id(db: Session, provider: str, social_id: str) -> models.User | None:
    """Retrieve a user by their OAuth provider and social ID."""
    return db.query(models.User).filter(
        models.User.provider == provider,
        models.User.social_id == social_id
    ).first()

def create_oauth_user(db: Session, email: str, username: str, full_name: str, provider: str, social_id: str) -> models.User:
    """
    Create a new user from OAuth provider data.
    """
    db_user = models.User(
        username=username,
        email=email,
        # **FIX**: Provide a fallback if the name from Google is empty.
        full_name=full_name or email.split('@')[0],
        provider=provider,
        social_id=social_id,
        hashed_password=None
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user
    
def get_project(db: Session, project_id: uuid.UUID, user_id: uuid.UUID) -> models.Project | None:
    return db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.owner_id == user_id
    ).first()

def get_projects_for_user(db: Session, user_id: uuid.UUID) -> list[models.Project]:
    return db.query(models.Project).filter(models.Project.owner_id == user_id).all()

def create_project(db: Session, project: schemas.ProjectCreate, user_id: uuid.UUID) -> models.Project:
    db_project = models.Project(**project.dict(), owner_id=user_id)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

def create_document(db: Session, doc: schemas.DocumentCreate) -> models.Document:
    db_doc = models.Document(**doc.dict())
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc

def get_documents_for_project(db: Session, project_id: uuid.UUID) -> list[models.Document]:
    return db.query(models.Document).filter(models.Document.project_id == project_id).all()

def update_document_status(db: Session, document_id: uuid.UUID, status: models.DocumentStatus) -> models.Document | None:
    db_doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if db_doc:
        db_doc.status = status
        db.commit()
        db.refresh(db_doc)
    return db_doc

def create_chat_session(db: Session, project_id: uuid.UUID, first_message: str) -> models.ChatSession:
    title = f"Chat about: {first_message[:30]}..."
    db_session = models.ChatSession(project_id=project_id, title=title)
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session

def get_chat_sessions_for_project(db: Session, project_id: uuid.UUID) -> list[models.ChatSession]:
    return db.query(models.ChatSession).filter(
        models.ChatSession.project_id == project_id
    ).order_by(models.ChatSession.created_at.desc()).all()

def get_chat_session(db: Session, session_id: uuid.UUID, project_id: uuid.UUID) -> models.ChatSession | None:
    return db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id,
        models.ChatSession.project_id == project_id
    ).first()

def add_chat_message(db: Session, session_id: uuid.UUID, message: schemas.ChatMessageCreate) -> models.ChatMessage:
    db_message = models.ChatMessage(session_id=session_id, **message.dict())
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message

def delete_document(db: Session, document_id: uuid.UUID) -> models.Document | None:
    db_doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if db_doc:
        db.delete(db_doc)
        db.commit()
    return db_doc

def delete_chat_session(db: Session, session_id: uuid.UUID) -> models.ChatSession | None:
    db_session = db.query(models.ChatSession).filter(models.ChatSession.id == session_id).first()
    if db_session:
        db.delete(db_session)
        db.commit()
    return db_session

def delete_user(db: Session, user_id: uuid.UUID) -> models.User | None:
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user:
        db.delete(db_user)
        db.commit()
    return db_user