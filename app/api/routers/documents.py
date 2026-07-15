from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile

from app.api.auth_deps import get_current_user
from app.api.deps import get_document_repository, get_upload_document_use_case
from app.application.upload_document import UploadDocumentUseCase
from app.domain.entities import AuthenticatedUser, DocumentMetadata
from app.infrastructure.document_repository import SqlAlchemyDocumentRepository

router = APIRouter(tags=["documents"])


@router.post("/documents", response_model=DocumentMetadata)
async def upload_document(
    file: UploadFile,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    use_case: Annotated[UploadDocumentUseCase, Depends(get_upload_document_use_case)],
) -> DocumentMetadata:
    content = await file.read()
    return await use_case.execute(user_oid=user.oid, filename=file.filename or "untitled", content=content)


@router.get("/documents", response_model=list[DocumentMetadata])
async def list_documents(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    repository: Annotated[SqlAlchemyDocumentRepository, Depends(get_document_repository)],
) -> list[DocumentMetadata]:
    return await repository.list_documents(user.oid)
