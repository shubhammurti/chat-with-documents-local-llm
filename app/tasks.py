import uuid
import logging
from typing import Optional
from app.core.celery_app import celery_app
from app.db.database import SessionLocal
from app.db import crud, schemas
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)

@celery_app.task
def process_document_task(
    user_id: str,
    project_id: str,
    document_id: str,
    storage_key: str,
    file_type: str,
    file_name: str,
    url: Optional[str] = None
) -> None:
    """
    Celery task to process a single document in the background.
    This includes chunking, embedding, and rebuilding the project's BM25 index.
    """
    logger.info(f"Starting document processing for document_id: {document_id}")
    db = SessionLocal()
    try:
        user_uuid = uuid.UUID(user_id)
        project_uuid = uuid.UUID(project_id)
        doc_uuid = uuid.UUID(document_id)

        crud.update_document_status(db, doc_uuid, schemas.DocumentStatus.PROCESSING)
        user = crud.get_user(db, user_uuid)
        project = crud.get_project(db, project_uuid, user_uuid)
        
        if not user or not project:
            logger.error(f"User or Project not found for doc_id {document_id}. Aborting.")
            crud.update_document_status(db, doc_uuid, schemas.DocumentStatus.FAILED)
            return

        rag_service = RAGService(user=user, project=project)
        rag_service.process_document(storage_key, file_type, file_name, document_id, url)
        
        # After processing, trigger a rebuild of the persisted BM25 index
        rag_service.rebuild_and_persist_bm25_index()

        crud.update_document_status(db, doc_uuid, schemas.DocumentStatus.COMPLETED)
        logger.info(f"Successfully processed document_id: {document_id} and rebuilt index.")
    except Exception as e:
        logger.error(f"Error processing document {document_id}: {e}", exc_info=True)
        crud.update_document_status(db, uuid.UUID(document_id), schemas.DocumentStatus.FAILED)
    finally:
        db.close()

@celery_app.task
def rebuild_project_index_task(user_id: str, project_id: str) -> None:
    """
    Celery task to rebuild and persist the BM25 index for a project.
    Typically called after a document is deleted.
    """
    logger.info(f"Starting BM25 index rebuild for project_id: {project_id}")
    db = SessionLocal()
    try:
        user_uuid = uuid.UUID(user_id)
        project_uuid = uuid.UUID(project_id)
        
        user = crud.get_user(db, user_uuid)
        project = crud.get_project(db, project_uuid, user_uuid)

        if not user or not project:
            logger.error(f"User or Project not found for index rebuild on project {project_id}. Aborting.")
            return

        rag_service = RAGService(user=user, project=project)
        rag_service.rebuild_and_persist_bm25_index()
        logger.info(f"Successfully rebuilt and persisted BM25 index for project {project_id}")

    except Exception as e:
        logger.error(f"Error rebuilding BM25 index for project {project_id}: {e}", exc_info=True)
    finally:
        db.close()