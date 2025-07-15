import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response, status
from sqlalchemy.orm import Session
from typing import List

from app.db import crud, models, schemas
from app.db.database import get_db
from app.core.dependencies import get_current_user
from app.services import storage_service
from app.services.rag_service import RAGService
from app.tasks import process_document_task, rebuild_project_index_task
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

class URLPayload(BaseModel):
    url: str

@router.post("/upload/{project_id}", response_model=schemas.Document, status_code=status.HTTP_201_CREATED)
def upload_document(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> schemas.Document:
    """
    Upload a document file to a project, store it, and queue it for processing.
    """
    logger.info(f"User '{current_user.username}' attempting to upload document to project '{project_id}'")
    
    project = crud.get_project(db, project_id=project_id, user_id=current_user.id)
    if not project:
        logger.warning(f"Access denied or project not found for user '{current_user.username}' and project '{project_id}'")
        raise HTTPException(status_code=404, detail="Project not found or access denied")

    try:
        storage_key = f"{current_user.id}/{project_id}/{uuid.uuid4()}_{file.filename}"
        if not storage_service.upload_file_obj(file.file, storage_key):
            logger.error(f"Failed to upload file to storage for key: {storage_key}")
            raise HTTPException(status_code=503, detail="Could not upload file to storage service. Please try again later.")
    except Exception as e:
        logger.error(f"An unexpected error occurred during file upload for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred during file upload.")

    doc_create = schemas.DocumentCreate(
        file_name=file.filename,
        file_type=file.content_type,
        storage_key=storage_key,
        project_id=project_id
    )
    db_doc = crud.create_document(db, doc_create)

    process_document_task.delay(
        str(current_user.id),
        str(project_id),
        str(db_doc.id),
        storage_key,
        file.content_type,
        file.filename
    )
    
    logger.info(f"Successfully created document record '{db_doc.id}' and queued for processing.")
    return db_doc

@router.post("/upload_url/{project_id}", response_model=schemas.Document, status_code=status.HTTP_201_CREATED)
def upload_url(
    project_id: uuid.UUID,
    payload: URLPayload,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> schemas.Document:
    """
    Add a document from a URL to a project and queue it for processing.
    """
    logger.info(f"User '{current_user.username}' attempting to add URL to project '{project_id}'")
    
    project = crud.get_project(db, project_id=project_id, user_id=current_user.id)
    if not project:
        logger.warning(f"Access denied or project not found for user '{current_user.username}' and project '{project_id}'")
        raise HTTPException(status_code=404, detail="Project not found or access denied")

    file_name = payload.url
    storage_key = f"{current_user.id}/{project_id}/{uuid.uuid4()}_url"

    doc_create = schemas.DocumentCreate(
        file_name=file_name,
        file_type="text/html",
        storage_key=storage_key,
        project_id=project_id
    )
    db_doc = crud.create_document(db, doc_create)

    process_document_task.delay(
        str(current_user.id),
        str(project_id),
        str(db_doc.id),
        storage_key,
        "text/html",
        file_name,
        url=payload.url
    )

    logger.info(f"Successfully created URL document record '{db_doc.id}' and queued for processing.")
    return db_doc

@router.get("/{project_id}", response_model=List[schemas.Document])
def get_documents_for_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> List[schemas.Document]:
    """
    Retrieve all documents for a given project.
    """
    logger.debug(f"Fetching documents for project '{project_id}' for user '{current_user.username}'")
    project = crud.get_project(db, project_id=project_id, user_id=current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or access denied")
    return crud.get_documents_for_project(db, project_id=project_id)

@router.delete("/{project_id}/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> Response:
    """
    Delete a document, its stored file, its vector embeddings, and trigger an index rebuild.
    """
    logger.info(f"User '{current_user.username}' attempting to delete document '{document_id}' from project '{project_id}'")
    
    project = crud.get_project(db, project_id, current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or access denied.")
        
    doc_to_delete = db.query(models.Document).filter(
        models.Document.id == document_id, 
        models.Document.project_id == project_id
    ).first()

    if not doc_to_delete:
        raise HTTPException(status_code=404, detail="Document not found in this project.")

    try:
        # Step 1: Delete chunks from the vector store
        logger.info(f"Attempting to delete chunks for document {doc_to_delete.id}.")
        rag_service = RAGService(user=current_user, project=project)
        rag_service.delete_document_chunks(document_id=str(doc_to_delete.id))

        # Step 2: Delete the file from object storage
        if not doc_to_delete.file_type == 'text/html': # Don't delete file for URLs
            if not storage_service.delete_file(doc_to_delete.storage_key):
                logger.error(f"Could not delete file '{doc_to_delete.storage_key}' from storage. Continuing with DB deletion.")
            else:
                logger.info(f"Successfully deleted file '{doc_to_delete.storage_key}' from storage.")

        # Step 3: Delete the document record from the database
        db.delete(doc_to_delete)
        db.commit()
        logger.info(f"Successfully deleted document record '{doc_to_delete.id}' from database.")

        # Step 4: Trigger a background task to rebuild the persisted BM25 index
        rebuild_project_index_task.delay(str(current_user.id), str(project_id))
        logger.info(f"Queued BM25 index rebuild for project '{project_id}'.")

    except Exception as e:
        logger.error(f"Error during deletion of document {document_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="An internal error occurred while deleting the document.")
        
    return Response(status_code=status.HTTP_204_NO_CONTENT)