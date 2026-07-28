from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth_deps import AuthContext, get_auth_context
from app.api.deps import get_send_email_use_case
from app.application.send_email import AttachmentNotFoundError, SendEmailUseCase
from app.domain.entities import EmailSendProposal, EmailSendResult

router = APIRouter(tags=["email"])


@router.post("/email/send", response_model=EmailSendResult)
async def confirm_send_email(
    proposal: EmailSendProposal,
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    use_case: Annotated[SendEmailUseCase, Depends(get_send_email_use_case)],
) -> EmailSendResult:
    """The only path that actually sends an email via Graph. Called
    directly by the frontend after the user reviews a proposal the
    assistant surfaced in chat — never triggered by the model itself,
    same pattern as /calendar/events."""
    try:
        await use_case.execute(
            user_oid=auth_context.user.oid,
            user_assertion=auth_context.raw_token,
            proposal=proposal,
        )
    except AttachmentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No ready document named '{exc}' found for this user",
        ) from exc

    return EmailSendResult()
