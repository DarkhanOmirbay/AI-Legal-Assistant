from fastapi import APIRouter, Depends, HTTPException, status, Request, Form,BackgroundTasks,Response
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Annotated
from pydantic import BaseModel,EmailStr,SecretStr

from database import get_db
from models.models import User
from services.auth_service import authenticate_user, create_access_token, get_password_hash,get_user_by_email,create_password_reset_token,send_password_reset_email
from services.auth_service import get_reset_token,update_user_password,use_reset_token
from config import settings

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="templates")

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

class RegisterRequest(BaseModel):
    email:EmailStr
    username:str
    password:str
    
@router.post("/register")
async def register(
    register_data:RegisterRequest,
    db: Session = Depends(get_db)
):
    
    existing_user = db.query(User).filter(User.email == register_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    existing_username = db.query(User).filter(User.username == register_data.username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    
    hashed_password = get_password_hash(register_data.password)
    new_user = User(email=register_data.email, username=register_data.username, hashed_password=hashed_password)
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    response = JSONResponse(
        {
            "message":"Registered succesfully!",
            "redirect_url":"/login"
        }
    )
    return response

@router.post("/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

class LoginRequest(BaseModel):
    email:EmailStr
    password:str
@router.post("/login")
async def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, login_data.email, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    
    response = JSONResponse({
        "message": "Login successful",
        "redirect_url": "/chat"
    })
    
    response.set_cookie(
        key="access_token", 
        value=f"Bearer {access_token}", 
        httponly=True
    )
    
    return response

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    return response
@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot-password.html", {"request": request})

@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request):
    return templates.TemplateResponse("reset-password.html", {"request": request})

class ForgotPasswordRequest(BaseModel):
    email:EmailStr
    
@router.post("/forgot-password")
async def forgot_password(
    # email:Annotated[str,Form()],
    forgot_password_data:ForgotPasswordRequest,
    bg:BackgroundTasks,
    db:Session = Depends(get_db)
):
    user = get_user_by_email(db,forgot_password_data.email)
    
    if user:
        reset_token = create_password_reset_token(db,forgot_password_data.email)
        
        bg.add_task(
            send_password_reset_email,
            reset_token,
            forgot_password_data.email,
        )
    return {
        "message": "If the email exists, a password reset link has been sent"
    }

    
@router.post("/reset-password")
async def reset_password(
    request:ResetPasswordRequest,
    db:Session = Depends(get_db)
):
    token_record = get_reset_token(db,request.token)
    
    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail = "Invalid or expired reset token"
        )
    
    user = update_user_password(db,token_record.email,request.new_password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found"
        )
    
    use_reset_token(db,token_record)
    return {"message": "Password reset successfully"}

    
    