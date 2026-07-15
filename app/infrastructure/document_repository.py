from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import DocumentMetadata
from app.infrastructure.document_models import DocumentModel


class SqlAlchemyDocumentRepository:
    """Concrete implementation of domain.DocumentRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_document(
        self, document_id: str, user_oid: str, filename: str, blob_path: str
    ) -> DocumentMetadata:
        document = DocumentModel(
            id=document_id, user_oid=user_oid, filename=filename, blob_path=blob_path, status="processing"
        )
        self._session.add(document)
        await self._session.commit()
        return DocumentMetadata(id=str(document.id), filename=document.filename, status=document.status)

    async def list_documents(self, user_oid: str) -> list[DocumentMetadata]:
        result = await self._session.execute(
            select(DocumentModel).where(DocumentModel.user_oid == user_oid).order_by(DocumentModel.created_at.desc())
        )
        return [
            DocumentMetadata(
                id=str(row.id), filename=row.filename, status=row.status, error_message=row.error_message
            )
            for row in result.scalars().all()
        ]

    async def get_owner(self, document_id: str) -> str | None:
        try:
            result = await self._session.execute(
                select(DocumentModel.user_oid).where(DocumentModel.id == document_id)
            )
        except ValueError:
            return None
        return result.scalar_one_or_none()
