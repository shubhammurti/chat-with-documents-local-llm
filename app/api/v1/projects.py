from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid

from app.db import crud, models, schemas
from app.db.database import get_db
from app.core.dependencies import get_current_user

router = APIRouter()

@router.post("/", response_model=schemas.Project)
def create_project(
    project: schemas.ProjectCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> schemas.Project:
    """
    Create a new project for the current user.

    Args:
        project (schemas.ProjectCreate): Project creation data.
        db (Session): Database session.
        current_user (models.User): The authenticated user.

    Returns:
        schemas.Project: The created project.
    """
    # TODO: Add validation for duplicate project names per user
    return crud.create_project(db=db, project=project, user_id=current_user.id)

@router.get("/", response_model=List[schemas.Project])
def read_projects(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> List[schemas.Project]:
    """
    Retrieve all projects for the current user.

    Args:
        db (Session): Database session.
        current_user (models.User): The authenticated user.

    Returns:
        List[schemas.Project]: List of projects.
    """
    # TODO: Add pagination support
    projects = crud.get_projects_for_user(db, user_id=current_user.id)
    return projects

@router.get("/{project_id}", response_model=schemas.Project)
def read_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
) -> schemas.Project:
    """
    Retrieve a specific project by its ID for the current user.

    Args:
        project_id (uuid.UUID): The project ID.
        db (Session): Database session.
        current_user (models.User): The authenticated user.

    Returns:
        schemas.Project: The requested project.

    Raises:
        HTTPException: If the project is not found.
    """
    # TODO: Add permission checks for shared projects
    db_project = crud.get_project(db, project_id=project_id, user_id=current_user.id)
    if db_project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return db_project