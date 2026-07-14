from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.auth_deps import get_current_user
from app.api.deps import get_conversation_repository, get_send_chat_message_use_case
from app.application.chat import ConversationNotFoundError, SendChatMessageUseCase
from app.domain.entities import AuthenticatedUser, ChatMessage
from app.infrastructure.conversation_repository import SqlAlchemyConversationRepository

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str


@router.post("/chat")
async def post_chat(
    request: ChatRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    use_case: Annotated[SendChatMessageUseCase, Depends(get_send_chat_message_use_case)],
) -> StreamingResponse:
    try:
        conversation_id, stream = await use_case.execute(
            user_oid=user.oid,
            conversation_id=request.conversation_id,
            user_message=request.message,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found") from exc

    response = StreamingResponse(stream, media_type="text/plain")
    response.headers["X-Conversation-Id"] = conversation_id
    return response


@router.get("/chat/{conversation_id}/messages", response_model=list[ChatMessage])
async def get_chat_history(
    conversation_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    repository: Annotated[SqlAlchemyConversationRepository, Depends(get_conversation_repository)],
) -> list[ChatMessage]:
    owner = await repository.get_owner(conversation_id)
    if owner != user.oid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    return await repository.get_recent_messages(conversation_id, limit=50)
