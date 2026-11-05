from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from db.database import get_db
from db.models import Document, Shareholder
from models.document import DocumentCreate, DocumentResponse, DocumentUpdate
from .auth import get_current_shareholder, require_admin

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(get_current_shareholder),
):
    return db.query(Document).order_by(Document.sort_order, Document.id).all()


@router.post("", response_model=DocumentResponse)
def create_document(
    doc: DocumentCreate,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_admin),
):
    max_order = db.query(func.max(Document.sort_order)).scalar() or 0
    db_doc = Document(
        title=doc.title,
        url=doc.url,
        description=doc.description,
        sort_order=max_order + 1,
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc


@router.put("/{doc_id}", response_model=DocumentResponse)
def update_document(
    doc_id: int,
    update: DocumentUpdate,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_admin),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if update.title is not None:
        doc.title = update.title
    if update.url is not None:
        doc.url = update.url
    if update.description is not None:
        doc.description = update.description
    if update.sort_order is not None:
        doc.sort_order = update.sort_order

    db.commit()
    db.refresh(doc)
    return doc


@router.delete("/{doc_id}")
def delete_document(
    doc_id: int,
    db: DBSession = Depends(get_db),
    _: Shareholder = Depends(require_admin),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    db.delete(doc)
    db.commit()
    return {"message": "Document deleted"}
