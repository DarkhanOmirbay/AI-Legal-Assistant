from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from datetime import timedelta

from database import get_db
from services.auth_service import create_access_token
from services.oauth_service import GoogleOAuth, create_or_get_oauth_user
from config import settings
from services.auth_service import get_current_user
from models.models import User

oauth_router = APIRouter(tags=["oauth"])

@oauth_router.get("/auth/google")
async def google_auth(request: Request):
    """Initiate Google OAuth flow"""
    google_oauth = GoogleOAuth()
    auth_url, state = google_oauth.get_auth_url()
    return RedirectResponse(url=auth_url)

@oauth_router.get("/auth/google/callback")
async def google_callback(
    code: str = None,
    state: str = None,
    error: str = None,
    db: Session = Depends(get_db)
):
    """Handle Google OAuth callback"""
    
    if error:
        return RedirectResponse(url="/login?error=oauth_cancelled")
    
    if not code:
        return RedirectResponse(url="/login?error=oauth_failed")
    
    google_oauth = GoogleOAuth()
    
    try:
        token_data = await google_oauth.exchange_code_for_token(code)
        if not token_data:
            return RedirectResponse(url="/login?error=oauth_failed")
        
        user_info = await google_oauth.get_user_info(token_data["access_token"])
        if not user_info:
            return RedirectResponse(url="/login?error=oauth_failed")
        
        user = create_or_get_oauth_user(db, user_info, "google")
        
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email}, expires_delta=access_token_expires
        )
        
        response = RedirectResponse(url="/chat", status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key="access_token",
            value=f"Bearer {access_token}",
            httponly=True,
            secure=settings.ENVIRONMENT == "production", 
            samesite="lax"
        )
        
        return response
        
    except Exception as e:
        print(f"OAuth error: {str(e)}")
        return RedirectResponse(url="/login?error=oauth_failed")

@oauth_router.post("/auth/unlink-google")
async def unlink_google_account(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Unlink Google account from user profile"""
    
    user = db.query(User).filter(User.email == current_user.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    

    if not user.hashed_password and user.oauth_provider == "google":
        raise HTTPException(
            status_code=400, 
            detail="Cannot unlink Google account. Please set a password first."
        )

    user.google_id = None
    if user.oauth_provider == "google":
        user.oauth_provider = None
    
    db.commit()
    
    return {"message": "Google account unlinked successfully"}