import base64

import httpx

from app.domain.entities import EmailDraft, EmailMessage, EmailSendProposal, EmailSummary
from app.infrastructure.resilience import retry_graph_call

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _auth_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


class HttpxGraphMailClient:
    """Concrete implementation of domain.GraphMailClient backed by direct
    calls to Microsoft Graph."""

    @retry_graph_call
    async def list_recent_emails(
        self, access_token: str, top: int, unread_only: bool
    ) -> list[EmailSummary]:
        params: dict[str, str | int] = {
            "$top": top,
            "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview",
            "$orderby": "receivedDateTime desc",
        }
        if unread_only:
            params["$filter"] = "isRead eq false"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_GRAPH_BASE}/me/messages",
                params=params,
                headers=_auth_header(access_token),
            )
            response.raise_for_status()
            data = response.json()

        return [self._to_summary(item) for item in data.get("value", [])]

    @retry_graph_call
    async def search_emails(self, access_token: str, query: str, top: int) -> list[EmailSummary]:
        # $search (full-text, across subject/body/from — unlike $filter,
        # which only matches exact field values) requires this header per
        # Graph's docs, plus $orderby is not supported alongside $search.
        headers = _auth_header(access_token) | {"ConsistencyLevel": "eventual"}
        params: dict[str, str | int] = {
            "$search": f'"{query}"',
            "$top": top,
            "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{_GRAPH_BASE}/me/messages", params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

        return [self._to_summary(item) for item in data.get("value", [])]

    @retry_graph_call
    async def get_email(self, access_token: str, message_id: str) -> EmailMessage:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_GRAPH_BASE}/me/messages/{message_id}",
                headers=_auth_header(access_token),
            )
            response.raise_for_status()
            data = response.json()

        return EmailMessage(
            id=data["id"],
            subject=data.get("subject", ""),
            from_address=self._extract_address(data.get("from")),
            received_at=data.get("receivedDateTime"),
            body=data.get("body", {}).get("content", ""),
        )

    # Deliberately not retried: this is two sequential writes (create then
    # patch), and retrying the whole method after a transient failure on
    # the second call would re-run the first one too, creating a duplicate
    # draft — unlike the read-only calls above, this isn't idempotent.
    async def create_draft_reply(self, access_token: str, message_id: str, body: str) -> EmailDraft:
        async with httpx.AsyncClient() as client:
            create_response = await client.post(
                f"{_GRAPH_BASE}/me/messages/{message_id}/createReply",
                headers=_auth_header(access_token),
            )
            create_response.raise_for_status()
            draft_id = create_response.json()["id"]

            patch_response = await client.patch(
                f"{_GRAPH_BASE}/me/messages/{draft_id}",
                headers=_auth_header(access_token),
                json={"body": {"contentType": "Text", "content": body}},
            )
            patch_response.raise_for_status()

        return EmailDraft(id=draft_id)

    # Deliberately not retried, same reasoning as HttpxGraphCalendarClient.
    # create_event: a lost response after Graph already sent the mail would
    # retry into a real duplicate landing in the recipient's inbox.
    async def send_email(
        self,
        access_token: str,
        proposal: EmailSendProposal,
        attachment_content: bytes | None,
    ) -> None:
        message: dict = {
            "subject": proposal.subject,
            "body": {"contentType": "Text", "content": proposal.body},
            "toRecipients": [{"emailAddress": {"address": proposal.to}}],
        }
        if attachment_content is not None and proposal.attachment_filename:
            message["attachments"] = [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": proposal.attachment_filename,
                    "contentBytes": base64.b64encode(attachment_content).decode("ascii"),
                }
            ]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_GRAPH_BASE}/me/sendMail",
                headers=_auth_header(access_token),
                json={"message": message, "saveToSentItems": True},
            )
            response.raise_for_status()

    @staticmethod
    def _extract_address(from_field: dict | None) -> str | None:
        if not from_field:
            return None
        return from_field.get("emailAddress", {}).get("address")

    @classmethod
    def _to_summary(cls, item: dict) -> EmailSummary:
        return EmailSummary(
            id=item["id"],
            subject=item.get("subject", ""),
            from_address=cls._extract_address(item.get("from")),
            received_at=item.get("receivedDateTime"),
            is_read=item.get("isRead", False),
            preview=item.get("bodyPreview", ""),
        )
