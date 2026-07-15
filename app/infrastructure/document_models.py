import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class DocumentModel(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_oid: Mapped[str] = mapped_column(index=True)
    filename: Mapped[str]
    blob_path: Mapped[str]
    # processing -> ready | failed, updated by the blob-triggered Azure
    # Function once OCR/chunk/embed/index finishes — the API only ever
    # writes "processing" at upload time.
    status: Mapped[str] = mapped_column(default="processing")
    error_message: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
