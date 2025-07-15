import uuid
from sqlalchemy import Column, String, ForeignKey, DateTime, Text, UniqueConstraint, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import enum

from .database import Base

class User(Base):
    """
    Represents a user in the system.
    Supports both local password-based and OAuth authentication.
    """
    __tablename__ = "users"
    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # For local auth, this is username. For Google, this is the email.
    username: str = Column(String, unique=True, index=True, nullable=False)
    email: str = Column(String, unique=True, index=True, nullable=True)
    full_name: str = Column(String, nullable=True)

    # --- NEW COLUMN ---
    # Stores the unique ID from the OAuth provider (e.g., Google's 'sub' field)
    social_id: str = Column(String, nullable=True, index=True)

    provider: str = Column(String, nullable=False, default="local") # 'local' or 'google'
    # Password can be null for users who signed up via OAuth
    hashed_password: str = Column(String, nullable=True)

    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")
    
    # This constraint now works because the 'social_id' column exists.
    __table_args__ = (UniqueConstraint('provider', 'social_id', name='_provider_social_id_uc'),)

# ... (rest of the file remains the same)


class Project(Base):
    """
    Represents a project owned by a user.
    """
    __tablename__ = "projects"
    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: str = Column(String, index=True, nullable=False)
    llm_provider: str = Column(String, nullable=False, default="groq") 
    llm_model_name: str = Column(String, nullable=True) 
    owner_id: uuid.UUID = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    owner = relationship("User", back_populates="projects")
    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="project", cascade="all, delete-orphan")

class DocumentStatus(enum.Enum):
    """
    Enum for document processing status.
    """
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Document(Base):
    """
    Represents a document uploaded to a project.
    """
    __tablename__ = "documents"
    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_name: str = Column(String, nullable=False)
    file_type: str = Column(String, nullable=False)
    storage_key: str = Column(String, unique=True, nullable=False) # e.g., user_id/project_id/file_uuid.pdf
    status: DocumentStatus = Column(SAEnum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False)
    project_id: uuid.UUID = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    project = relationship("Project", back_populates="documents")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ChatSession(Base):
    """
    Represents a chat session within a project.
    """
    __tablename__ = "chat_sessions"
    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: str = Column(String, nullable=False, default="New Chat")
    project_id: uuid.UUID = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    project = relationship("Project", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ChatMessage(Base):
    """
    Represents a message in a chat session.
    """
    __tablename__ = "chat_messages"
    id: uuid.UUID = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: uuid.UUID = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False)
    session = relationship("ChatSession", back_populates="messages")
    role: str = Column(String, nullable=False)  # 'user' or 'assistant'
    content: str = Column(Text, nullable=False)
    sources: str = Column(Text, nullable=True) # JSON string of source chunks
    created_at = Column(DateTime(timezone=True), server_default=func.now())
