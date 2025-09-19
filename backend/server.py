from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import requests
import aiofiles
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
import json
from datetime import datetime, timezone, timedelta
import asyncio
from dataclasses import dataclass

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create uploads directory
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Discord webhook URL
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1418619476328448090/hTnqGtvx3JAbFPULeC51QL5IgPGXgd4cjABYBpnr5orgeTe5WecRwvJHk_Z937GdnmSH"

# Blocked file extensions
BLOCKED_EXTENSIONS = {'.php', '.phtml', '.sh'}

# Create the main app
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Models
class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    username: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_seconds: Optional[int] = 3600  # Default 1 hour TTL
    expires_at: Optional[datetime] = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None

class MessageCreate(BaseModel):
    content: str
    username: str
    ttl_seconds: Optional[int] = 3600
    send_to_discord: bool = False

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # Remove broken connections
                self.active_connections.remove(connection)

manager = ConnectionManager()

# Background task to cleanup expired messages
async def cleanup_expired_messages():
    while True:
        try:
            current_time = datetime.now(timezone.utc)
            logging.info(f"Running cleanup task at {current_time}")
            
            # Delete expired messages
            result = await db.messages.delete_many({
                "expires_at": {"$lt": current_time}
            })
            if result.deleted_count > 0:
                logging.info(f"Cleaned up {result.deleted_count} expired messages")
                # Broadcast cleanup notification to all connected clients
                cleanup_data = {
                    "type": "cleanup",
                    "deleted_count": result.deleted_count
                }
                await manager.broadcast(json.dumps(cleanup_data))
            
            # Also delete old files for expired messages
            expired_messages = await db.messages.find({
                "expires_at": {"$lt": current_time},
                "file_path": {"$ne": None}
            }).to_list(None)
            
            for msg in expired_messages:
                file_path = Path(msg.get('file_path', ''))
                if file_path.exists():
                    file_path.unlink()
                    logging.info(f"Deleted expired file: {file_path}")
                    
        except Exception as e:
            logging.error(f"Error in cleanup task: {e}")
        
        await asyncio.sleep(10)  # Check every 10 seconds for better TTL accuracy

# Background task to auto-clear all messages every hour
async def auto_clear_all_messages():
    while True:
        try:
            await asyncio.sleep(3600)  # Wait 1 hour
            current_time = datetime.now(timezone.utc)
            logging.info(f"Auto-clearing all messages at {current_time}")
            
            # Delete all messages
            result = await db.messages.delete_many({})
            logging.info(f"Auto-cleared {result.deleted_count} messages")
            
            # Delete all uploaded files
            if UPLOAD_DIR.exists():
                for file_path in UPLOAD_DIR.glob("*"):
                    if file_path.is_file():
                        file_path.unlink()
                        
            # Broadcast auto-clear notification to all connected clients
            clear_data = {
                "type": "auto_clear",
                "message": "All messages have been automatically cleared (1-hour cleanup)"
            }
            await manager.broadcast(json.dumps(clear_data))
                    
        except Exception as e:
            logging.error(f"Error in auto-clear task: {e}")

# Start cleanup task
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_expired_messages())
    asyncio.create_task(auto_clear_all_messages())

def is_file_allowed(filename: str) -> bool:
    """Check if file extension is allowed"""
    file_ext = Path(filename).suffix.lower()
    return file_ext not in BLOCKED_EXTENSIONS

def send_to_discord_webhook(content: str, file_path: Optional[str] = None, file_name: Optional[str] = None):
    """Send message/file to Discord webhook"""
    try:
        logging.info(f"Sending to Discord: content='{content}', file_path='{file_path}', file_name='{file_name}'")
        
        if file_path and Path(file_path).exists():
            # Send file to Discord
            with open(file_path, 'rb') as f:
                files = {'file': (file_name or Path(file_path).name, f)}
                data = {'content': content} if content.strip() else {}
                logging.info(f"Sending file to Discord webhook: {DISCORD_WEBHOOK_URL}")
                response = requests.post(DISCORD_WEBHOOK_URL, files=files, data=data, timeout=10)
        else:
            # Send text message to Discord
            data = {'content': content}
            logging.info(f"Sending text to Discord webhook: {DISCORD_WEBHOOK_URL}")
            response = requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=10)
        
        logging.info(f"Discord response: {response.status_code} - {response.text}")
        
        if response.status_code not in [200, 204]:
            logging.error(f"Discord webhook error: {response.status_code} - {response.text}")
            return False
        return True
    except Exception as e:
        logging.error(f"Error sending to Discord: {e}")
        return False

@api_router.websocket("/ws/chat/SUAI")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle WebSocket messages if needed
            pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@api_router.post("/messages")
async def create_message(
    content: str = Form(...),
    username: str = Form(...),
    ttl_seconds: int = Form(3600),
    send_to_discord: bool = Form(False),
    file: Optional[UploadFile] = File(None)
):
    # Validate file if provided
    if file and file.filename:
        if not is_file_allowed(file.filename):
            raise HTTPException(status_code=400, detail="File type not allowed")
    
    # Calculate expiration time
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    
    # Handle file upload
    file_path = None
    file_name = None
    file_size = None
    
    if file and file.filename:
        file_id = str(uuid.uuid4())
        file_extension = Path(file.filename).suffix
        file_path = UPLOAD_DIR / f"{file_id}{file_extension}"
        file_name = file.filename
        file_size = 0
        
        async with aiofiles.open(file_path, 'wb') as f:
            file_content = await file.read()
            await f.write(file_content)
            file_size = len(file_content)
    
    # Create message
    message = Message(
        content=content,
        username=username,
        ttl_seconds=ttl_seconds,
        expires_at=expires_at,
        file_path=str(file_path) if file_path else None,
        file_name=file_name,
        file_size=file_size
    )
    
    # Save to database
    await db.messages.insert_one(message.dict())
    
    # Send to Discord if requested
    if send_to_discord:
        discord_content = f"**{username}**: {content}"
        try:
            discord_success = send_to_discord_webhook(discord_content, str(file_path) if file_path else None, file_name)
            logging.info(f"Discord send result: {discord_success}")
        except Exception as e:
            logging.error(f"Error calling Discord webhook: {e}")
    
    # Broadcast to all connected WebSocket clients
    message_data = {
        "type": "new_message",
        "message": message.dict()
    }
    await manager.broadcast(json.dumps(message_data, default=str))
    
    return message

@api_router.get("/messages")
async def get_messages():
    # Get non-expired messages
    current_time = datetime.now(timezone.utc)
    messages = await db.messages.find({
        "$or": [
            {"expires_at": {"$gt": current_time}},
            {"expires_at": None}
        ]
    }).sort("timestamp", 1).to_list(1000)
    
    return [Message(**msg) for msg in messages]

@api_router.get("/files/{file_id}")
async def download_file(file_id: str):
    # Find message with this file
    message = await db.messages.find_one({"file_path": {"$regex": file_id}})
    if not message:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_path = Path(message['file_path'])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    return FileResponse(
        path=file_path,
        filename=message.get('file_name', file_path.name),
        media_type='application/octet-stream'
    )

# Serve uploaded files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Include the router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()