from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt

from app.db import crud, models
from app.db.database import get_db
from app.auth import schemas as auth_schemas
from app.core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> models.User:
    """
    Retrieve the current authenticated user based on the provided JWT token.

    Args:
        token (str): JWT access token extracted from the request.
        db (Session): SQLAlchemy database session.

    Returns:
        models.User: The authenticated user object.

    Raises:
        HTTPException: If the credentials are invalid or user does not exist.

    TODO:
        - Add support for token expiration handling.
        - Implement user role/permission checks if needed.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload: dict = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = auth_schemas.TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user: models.User | None = crud.get_user_by_username(db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user