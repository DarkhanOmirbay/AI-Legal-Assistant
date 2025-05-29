from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Annotated, Optional, List, Dict
import json

from database import get_db
from models.models import User, Conversation, Message
from services.auth_service import get_current_user
from services.dify_service import DifyService

router = APIRouter(tags=["chat"])
templates = Jinja2Templates(directory="templates")
dify_service = DifyService()

@router.get("/chat", response_class=HTMLResponse)
async def chat_page(
    request: Request,
    access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    if not access_token:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    try:
        token = access_token.replace("Bearer ", "")
        user = await get_current_user(token=token, db=db)
        
        conversations = db.query(Conversation).filter(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()).all()
        
        return templates.TemplateResponse(
            "chat.html", 
            {
                "request": request, 
                "user": user, 
                "conversations": conversations
            }
        )
    except Exception as e:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/api/chat/new")
async def create_new_chat(
    access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        token = access_token.replace("Bearer ", "")
        user = await get_current_user(token=token, db=db)
        
        result = await dify_service.create_new_conversation("New Chat", user.username)
        
        conversation = Conversation(
            dify_conversation_id=result["conversation_id"],
            name="New Chat",
            user_id=user.id
        )
        
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        
        return {"conversation_id": conversation.id, "dify_conversation_id": conversation.dify_conversation_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/chat/message")
async def send_message(
    message: str = Form(...),
    conversation_id: int = Form(...),
    access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
    
):
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        token = access_token.replace("Bearer ", "")
        user = await get_current_user(token=token, db=db)
        
        conversation = db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.user_id == user.id).first()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        result = await dify_service.send_message(
            query=message,
            user_id=user.username,
            conversation_id=conversation.dify_conversation_id
        )
        
        new_message = Message(
            dify_message_id=result["message_id"],
            conversation_id=conversation.id,
            query=message,
            answer=result["answer"]
        )
        
        db.add(new_message)
        
        conversation.updated_at = new_message.created_at
        if conversation.name == "New Chat" and len(message) < 30:
            conversation.name = message
        
        db.commit()
        
        return {
            "message_id": new_message.id,
            "answer": result["answer"],
            "created_at": new_message.created_at.isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
@router.get("/api/chat/conversations")
async def get_conversations(
    access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        token = access_token.replace("Bearer ", "")
        user = await get_current_user(token=token, db=db)
        
        conversations = db.query(Conversation).filter(
            Conversation.user_id == user.id
        ).order_by(Conversation.updated_at.desc()).all()
        
        result = []
        for conversation in conversations:
            result.append({
                "id": conversation.id,
                "name": conversation.name,
                "created_at": conversation.created_at.isoformat(),
                "updated_at": conversation.updated_at.isoformat()
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/chat/history/{conversation_id}")
async def get_chat_history(
    conversation_id: int,
    access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        token = access_token.replace("Bearer ", "")
        user = await get_current_user(token=token, db=db)
        
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id, 
            Conversation.user_id == user.id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        messages = db.query(Message).filter(
            Message.conversation_id == conversation.id
        ).order_by(Message.created_at.asc()).all()
        
        result = []
        for message in messages:
            result.append({
                "id": message.id,
                "query": message.query,
                "answer": message.answer,
                "created_at": message.created_at.isoformat()
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/chat/delete/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)   
):
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        token = access_token.replace("Bearer ", "")
        user = await get_current_user(token=token, db=db)
        
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id, 
            Conversation.user_id == user.id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        
        db.query(Message).filter(Message.conversation_id == conversation.id).delete()
        
        db.delete(conversation)
        db.commit()
        
        return {"success": True}
    except Exception as e:
        print(str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/chat/rename/{conversation_id}")
async def rename_conversation(
    conversation_id: int,
    name: str = Form(...),
    access_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        token = access_token.replace("Bearer ", "")
        user = await get_current_user(token=token, db=db)
        
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id, 
            Conversation.user_id == user.id
        ).first()
        
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        await dify_service.rename_conversation(conversation.dify_conversation_id, user.username, name)
        
        conversation.name = name
        db.commit()
        
        return {"success": True, "name": name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    
    