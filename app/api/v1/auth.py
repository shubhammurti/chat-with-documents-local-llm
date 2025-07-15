from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from httpx_oauth.oauth2 import GetAccessTokenError

from app.auth import jwt
from app.db import crud
from app.db.database import get_db
from app.db.schemas import UserCreate, User, Token
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.db import models
import logging

from jose import jwt as jose_jwt, JWTError
from httpx_oauth.clients.google import GoogleOAuth2


router = APIRouter()
logger = logging.getLogger(__name__)

google_client = GoogleOAuth2(
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
)

@router.post("/signup", response_model=User, status_code=status.HTTP_201_CREATED)
def signup(user: UserCreate, db: Session = Depends(get_db)) -> models.User:
    db_user = crud.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    if crud.get_user_by_email(db, email=user.email):
         raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db=db, user=user)

@router.post("/token", response_model=Token)
def login_for_access_token(
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> dict:
    user = crud.get_user_by_username(db, username=form_data.username)
    if not user or not user.hashed_password or not jwt.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = jwt.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


# === Google OAuth2 Authentication ===
@router.get("/login/google", name="auth:google_login")
async def login_google(request: Request):
    redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI
    if not redirect_uri:
        logger.error("GOOGLE_OAUTH_REDIRECT_URI is not configured.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth is not configured correctly."
        )
    authorization_url = await google_client.get_authorization_url(
        redirect_uri=redirect_uri,
        scope=["email", "profile"],
    )
    return RedirectResponse(url=authorization_url)


@router.get("/callback/google", name="auth:google_callback", include_in_schema=False)
async def callback_google(request: Request, db: Session = Depends(get_db)):
    try:
        redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI
        code = request.query_params.get("code")
        if not code:
            raise HTTPException(status_code=400, detail="Missing authorization code from Google")

        token_data = await google_client.get_access_token(code, redirect_uri)
        
        id_token_jwt = token_data.get("id_token")
        if not id_token_jwt:
            raise HTTPException(status_code=400, detail="ID token not found in Google response")

        try:
            id_token_payload = jose_jwt.decode(
                id_token_jwt, 
                key=None, 
                options={
                    "verify_signature": False, 
                    "verify_aud": False,
                    "verify_iss": False,
                    "verify_at_hash": False 
                }
            )
        except JWTError as e:
            logger.error(f"JWT decoding error: {e}")
            raise HTTPException(status_code=401, detail="Could not validate credentials from token")

        email = id_token_payload["email"]
        social_id = id_token_payload["sub"]
        full_name = id_token_payload.get("name", "")

        db_user = crud.get_user_by_social_id(db, provider="google", social_id=social_id)
        if not db_user:
            existing_user_by_email = crud.get_user_by_email(db, email=email)
            if existing_user_by_email:
                error_url = f"{settings.FRONTEND_URL}?error=email_exists_local"
                return RedirectResponse(url=error_url)

            username = email
            if crud.get_user_by_username(db, username=username):
                 username = f"{email.split('@')[0]}_{social_id[:6]}"

            db_user = crud.create_oauth_user(db, email=email, username=username, full_name=full_name, provider="google", social_id=social_id)
        
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = jwt.create_access_token(
            data={"sub": db_user.username}, expires_delta=access_token_expires
        )

        redirect_url = f"{settings.FRONTEND_URL}?token={access_token}"
        return RedirectResponse(url=redirect_url)

    except GetAccessTokenError as e:
        logger.error(f"Error getting access token from Google: {e}")
        error_detail = "oauth_token_failed"
        if e.response:
            logger.error(f"Google's detailed response: {e.response.json()}")
            error_detail = e.response.json().get('error', 'oauth_token_failed')
        error_url = f"{settings.FRONTEND_URL}?error={error_detail}"
        return RedirectResponse(url=error_url)

    except Exception as e:
        logger.error(f"An unexpected error occurred during Google authentication: {e}", exc_info=True)
        error_url = f"{settings.FRONTEND_URL}?error=oauth_server_error"
        return RedirectResponse(url=error_url)


@router.get("/users/me", response_model=User)
def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user

@router.delete("/users/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    logger.info(f"User '{current_user.username}' (ID: {current_user.id}) has requested account deletion.")
    crud.delete_user(db, user_id=current_user.id)
    logger.info(f"Successfully deleted account for user '{current_user.username}'.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)