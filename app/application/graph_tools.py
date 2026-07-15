import json

from app.domain.entities import ToolCallRequest
from app.domain.interfaces import GraphMailClient

TOOL_SPECS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_recent_emails",
            "description": "List the user's most recent emails, optionally filtered to unread only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "top": {
                        "type": "integer",
                        "description": "How many emails to return.",
                        "default": 5,
                    },
                    "unread_only": {
                        "type": "boolean",
                        "description": "Only return unread emails.",
                        "default": True,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_email",
            "description": "Read the full subject and body of one email by its id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "The email's Graph message id."},
                },
                "required": ["message_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_reply",
            "description": (
                "Create a reply draft for an email in the user's Drafts folder. "
                "This never sends the email — it only saves a draft for the user "
                "to review and send themselves."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "The email being replied to."},
                    "body": {"type": "string", "description": "The reply body text."},
                },
                "required": ["message_id", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_calendar_event",
            "description": (
                "Propose a calendar event to the user. This does NOT create anything — "
                "it only returns the proposal so you can present it and ask the user "
                "to explicitly confirm before it's actually created."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "start": {"type": "string", "description": "ISO 8601 datetime."},
                    "end": {"type": "string", "description": "ISO 8601 datetime."},
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Attendee email addresses.",
                    },
                },
                "required": ["subject", "start", "end"],
            },
        },
    },
]


class UnknownToolError(Exception):
    pass


class GraphToolExecutor:
    """Dispatches a model-requested tool call to the corresponding Graph
    use case and returns a JSON string result to feed back to the model.

    `propose_calendar_event` deliberately never touches Graph — creating
    the event requires a separate, explicit API call the model cannot
    trigger itself (see app/api/routers/calendar.py).
    """

    def __init__(self, mail_client: GraphMailClient) -> None:
        self._mail_client = mail_client

    async def execute(self, tool_call: ToolCallRequest, access_token: str) -> str:
        args = tool_call.arguments

        if tool_call.name == "list_recent_emails":
            summaries = await self._mail_client.list_recent_emails(
                access_token,
                top=args.get("top", 5),
                unread_only=args.get("unread_only", True),
            )
            return json.dumps([s.model_dump() for s in summaries])

        if tool_call.name == "read_email":
            email = await self._mail_client.get_email(access_token, args["message_id"])
            return json.dumps(email.model_dump())

        if tool_call.name == "draft_reply":
            draft = await self._mail_client.create_draft_reply(
                access_token, args["message_id"], args["body"]
            )
            return json.dumps(draft.model_dump())

        if tool_call.name == "propose_calendar_event":
            return json.dumps(
                {
                    "subject": args.get("subject"),
                    "start": args.get("start"),
                    "end": args.get("end"),
                    "attendees": args.get("attendees", []),
                    "status": "proposed — not created; ask the user to confirm via the app",
                }
            )

        raise UnknownToolError(tool_call.name)
