import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base


class ConversationModel(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_oid: Mapped[str] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    messages: Mapped[list["MessageModel"]] = relationship(
        back_populates="conversation", order_by="MessageModel.created_at"
    )


class MessageModel(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str]
    content: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    conversation: Mapped[ConversationModel] = relationship(back_populates="messages")
