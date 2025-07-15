import uuid
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Response, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any, AsyncGenerator
from sse_starlette.sse import EventSourceResponse

from app.db import crud, models, schemas
from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)
router = APIRouter()

class ChatRequest(BaseModel):
    """Request model for chat queries."""
    query: str
    chat_id: Optional[uuid.UUID] = None

class ChatResponse(BaseModel):
    """Response model for non-streaming chat queries."""
    answer: str
    sources: List[Dict[str, Any]]
    chat_id: uuid.UUID

@router.post("/{project_id}", response_model=ChatResponse, summary="Handle a standard chat query")
def handle_chat_query(
    project_id: uuid.UUID,
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> ChatResponse:
    """
    Handle a non-streaming chat query for a given project.
    """
    project = crud.get_project(db, project_id=project_id, user_id=current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or access denied")

    rag_service = RAGService(user=current_user, project=project)
    answer, sources = rag_service.query(request.query)

    chat_id: Optional[uuid.UUID] = request.chat_id
    if not chat_id:
        chat_session = crud.create_chat_session(db, project_id=project_id, first_message=request.query)
        chat_id = chat_session.id

    crud.add_chat_message(db, chat_id, schemas.ChatMessageCreate(role="user", content=request.query))
    crud.add_chat_message(db, chat_id, schemas.ChatMessageCreate(
        role="assistant", 
        content=answer, 
        sources=json.dumps(sources)
    ))

    return ChatResponse(answer=answer, sources=sources, chat_id=chat_id)

@router.post("/stream/{project_id}", summary="Handle a streaming chat query")
async def handle_streaming_chat_query(
    project_id: uuid.UUID,
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> EventSourceResponse:
    """
    Handle a streaming chat query for a given project using Server-Sent Events (SSE).
    """
    project = crud.get_project(db, project_id=project_id, user_id=current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or access denied")

    # Determine chat_id before starting the stream
    chat_id = request.chat_id
    if not chat_id:
        chat_session = crud.create_chat_session(db, project_id=project_id, first_message=request.query)
        chat_id = chat_session.id

    rag_service = RAGService(user=current_user, project=project)

    async def event_generator() -> AsyncGenerator[Dict[str, Any], None]:
        # Save user message before streaming assistant response
        crud.add_chat_message(db, chat_id, schemas.ChatMessageCreate(role="user", content=request.query))
        
        # Yield start event with chat_id
        yield {"event": "start", "data": json.dumps({"chat_id": str(chat_id)})}
        
        full_response = ""
        sources = []
        try:
            # The RAG service generator yields events for sources, tokens, and returns the full response
            response_generator, final_sources = await rag_service.stream_query(request.query)
            
            # Yield sources first
            sources = final_sources # store for db saving
            yield {"event": "sources", "data": json.dumps(sources)}

            # Yield LLM tokens
            async for token in response_generator:
                full_response += token
                # FIX: Wrap the token in json.dumps to make it a valid JSON string
                yield {"event": "token", "data": json.dumps(token)}

        except Exception as e:
            logger.error(f"Error during stream for project {project_id}: {e}", exc_info=True)
            # FIX: Wrap the error message in json.dumps
            yield {"event": "error", "data": json.dumps("An error occurred while generating the response.")}
        finally:
            # Save the complete assistant message to the database
            if full_response:
                crud.add_chat_message(db, chat_id, schemas.ChatMessageCreate(
                    role="assistant", 
                    content=full_response,
                    sources=json.dumps(sources)
                ))
            # Signal the end of the stream
            # FIX: Wrap the end message in json.dumps
            yield {"event": "end", "data": json.dumps("Stream ended")}

    return EventSourceResponse(event_generator())

@router.get("/sessions/{project_id}", response_model=List[schemas.ChatSession])
def get_chat_sessions(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> List[schemas.ChatSession]:
    """
    Retrieve all chat sessions for a given project.
    """
    project = crud.get_project(db, project_id=project_id, user_id=current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return crud.get_chat_sessions_for_project(db, project_id=project_id)

@router.get("/sessions/{project_id}/{session_id}", response_model=schemas.ChatSession)
def get_chat_session_messages(
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> schemas.ChatSession:
    """
    Retrieve messages for a specific chat session.
    """
    session = crud.get_chat_session(db, session_id=session_id, project_id=project_id)
    if not session or session.project.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session

@router.delete(
    "/sessions/{project_id}/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat session"
)
def delete_chat_session_endpoint(
    project_id: uuid.UUID,
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> Response:
    """
    Delete a specific chat session and all its associated messages for a given project.
    """
    logger.info(f"User '{current_user.username}' attempting to delete chat session '{session_id}' from project '{project_id}'")
    session_to_delete = crud.get_chat_session(db, session_id=session_id, project_id=project_id)

    if not session_to_delete:
        logger.warning(f"Chat session '{session_id}' not found for project '{project_id}'.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found.")

    if session_to_delete.project.owner_id != current_user.id:
        logger.warning(f"Access denied: User '{current_user.username}' does not own project for chat session '{session_id}'.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to delete this chat session.")

    crud.delete_chat_session(db, session_id=session_id)
    logger.info(f"Successfully deleted chat session '{session_id}'.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)