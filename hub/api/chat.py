import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from hub.models.database import get_db
from hub.models.user import User
from hub.auth.dependencies import get_current_user
from hub.core.orchestrator import Orchestrator

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    device: str = "web"


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@router.post("/", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # always ensure session_id is a valid UUID
    if payload.session_id:
        try:
            session_id = str(uuid.UUID(payload.session_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session_id format — must be a UUID")
    else:
        session_id = str(uuid.uuid4())

    orchestrator = Orchestrator(db=db, user_id=str(current_user.id))

    reply = await orchestrator.run(
        user_message=payload.message,
        session_id=session_id,
        device=payload.device
    )

    return ChatResponse(reply=reply, session_id=session_id)