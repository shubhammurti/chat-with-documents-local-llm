import uuid
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

from .models import DocumentStatus

from pydantic import BaseModel, Field
from typing import Optional
import uuid

class UserBase(BaseModel):
    """
    Base schema for user data.

    Attributes:
        username (str): The username of the user.
    """
    username: str

class UserCreate(UserBase):
    """
    Schema for creating a new user.

    Attributes:
        password (str): The user's password.
        email (str): The user's email address.
    """
    email: str # 
    password: str

class User(UserBase):
    """
    Schema representing a user.

    Attributes:
        id (uuid.UUID): The unique identifier of the user.
        username (str): The username of the user.
        full_name (Optional[str]): The user's full name, if available (e.g., from OAuth).
    """
    id: uuid.UUID
    full_name: Optional[str] = None 

    class Config:
        from_attributes = True

class Token(BaseModel):
    """
    Schema for authentication token.

    Attributes:
        access_token (str): The access token string.
        token_type (str): The type of the token.
    """
    access_token: str
    token_type: str

class TokenData(BaseModel):
    """
    Schema for token data.

    Attributes:
        username (Optional[str]): The username associated with the token, if any.
    """
    username: Optional[str] = None


class ProjectBase(BaseModel):
    """
    Base model for a project.
    """
    name: str = Field(..., min_length=1, max_length=100)
    llm_provider: Optional[str] = "groq"
    llm_model_name: Optional[str] = None

class DocumentBase(BaseModel):
    """
    Base model for a document.
    """
    file_name: str
    file_type: str


class ProjectCreate(ProjectBase):
    """
    Model for creating a project.
    """
    pass

class DocumentCreate(DocumentBase):
    """
    Model for creating a document.
    """
    storage_key: str
    project_id: uuid.UUID
    status: DocumentStatus = DocumentStatus.PENDING

class ChatMessageCreate(BaseModel):
    """
    Model for creating a chat message.
    """
    role: str
    content: str
    sources: Optional[str] = None

class Document(DocumentBase):
    """
    Model representing a document (read model).
    """
    id: uuid.UUID
    status: DocumentStatus
    created_at: datetime

    class Config:
        from_attributes = True

class Project(ProjectBase):
    """
    Model representing a project (read model).
    """
    id: uuid.UUID
    owner_id: uuid.UUID
    documents: List[Document] = []
    llm_provider: str
    llm_model_name: Optional[str] = None

    class Config:
        from_attributes = True

class ChatMessage(BaseModel):
    """
    Model representing a chat message (read model).
    """
    id: uuid.UUID
    role: str
    content: str
    sources: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ChatSession(BaseModel):
    """
    Model representing a chat session.
    """
    id: uuid.UUID
    title: str
    project_id: uuid.UUID
    created_at: datetime
    messages: List[ChatMessage] = []

    class Config:
        from_attributes = True