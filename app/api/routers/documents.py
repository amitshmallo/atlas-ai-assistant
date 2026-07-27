from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status

from app.api.auth_deps import get_current_user
from app.api.deps import get_delete_document_use_case, get_document_repository, get_upload_document_use_case
from app.application.delete_document import DeleteDocumentUseCase, DocumentNotFoundError
from app.application.upload_document import UploadDocumentUseCase
from app.domain.entities import AuthenticatedUser, DocumentMetadata
from app.infrastructure.document_repository import SqlAlchemyDocumentRepository
from app.infrastructure.rate_limiter import limiter

router = APIRouter(tags=["documents"])


@router.post("/documents", response_model=DocumentMetadata)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
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


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    use_case: Annotated[DeleteDocumentUseCase, Depends(get_delete_document_use_case)],
) -> None:
    try:
        await use_case.execute(user_oid=user.oid, document_id=document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found") from exc
