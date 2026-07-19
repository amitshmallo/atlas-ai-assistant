import uuid
from datetime import datetime

from sqlalchemy import UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class PreferenceModel(Base):
    __tablename__ = "preferences"
    __table_args__ = (UniqueConstraint("user_oid", "key", name="uq_preferences_user_oid_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_oid: Mapped[str] = mapped_column(index=True)
    key: Mapped[str]
    value: Mapped[str]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
