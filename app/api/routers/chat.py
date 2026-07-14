from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.auth_deps import get_current_user
from app.api.deps import get_send_chat_message_use_case
from app.application.chat import SendChatMessageUseCase
from app.domain.entities import AuthenticatedUser, ChatMessage

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@router.post("/chat")
async def post_chat(
    request: ChatRequest,
    _user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    use_case: Annotated[SendChatMessageUseCase, Depends(get_send_chat_message_use_case)],
) -> StreamingResponse:
    async def event_stream():
        async for chunk in use_case.execute(request.messages):
            yield chunk

    return StreamingResponse(event_stream(), media_type="text/plain")
