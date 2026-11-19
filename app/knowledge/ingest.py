"""One path for every document that enters the knowledge library (upload or Google Drive):
size check, safe text extraction, encrypted storage, chunking and an audit entry."""
import hashlib
import uuid

from flask import current_app
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import AuditLog, KnowledgeChunk, KnowledgeDocument
from app.knowledge.services import chunk_text, extract_document_text
from app.knowledge.storage import delete_file, store_file

MAX_UPLOAD_BYTES = 12 * 1024 * 1024


class IngestError(Exception):
    """A user-facing reason the document was not added."""


def ingest_document(tenant_id, repository, user_id, filename, data, source="upload", source_ref=None):
    """Store and index one document. Returns the KnowledgeDocument; raises IngestError."""
    original = secure_filename(filename or "")[:255]
    if not original:
        raise IngestError("The document needs a file name.")
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise IngestError("The document must be between 1 byte and 12 MB.")
    try:
        mime_type, extracted = extract_document_text(original, data)
    except ValueError as exc:
        raise IngestError(str(exc)) from exc
    except Exception as exc:
        current_app.logger.exception("Business document could not be parsed")
        raise IngestError("The document is damaged, password-protected or could not be safely read.") from exc
    key = uuid.uuid4().hex
    try:
        store_file(key, data)
    except Exception as exc:
        current_app.logger.exception("Private document storage failed")
        raise IngestError("Encrypted document storage is not configured or is unavailable. Ask the administrator to configure it.") from exc
    doc = KnowledgeDocument(tenant_id=tenant_id, repository_id=repository.id, uploaded_by_user_id=user_id,
                            original_filename=original, storage_key=key, mime_type=mime_type, file_size=len(data),
                            sha256=hashlib.sha256(data).hexdigest(), status="ready", extracted_chars=len(extracted))
    db.session.add(doc)
    try:
        db.session.flush()
        pieces = chunk_text(extracted)
        for index, piece in enumerate(pieces):
            db.session.add(KnowledgeChunk(tenant_id=tenant_id, document_id=doc.id, chunk_index=index, content=piece))
        details = {"filename": original, "size_bytes": len(data), "sha256": doc.sha256,
                   "repository_id": repository.id, "chunks": len(pieces), "source": source}
        if source_ref:
            details["source_ref"] = source_ref
        db.session.add(AuditLog(tenant_id=tenant_id, actor_user_id=user_id, action="knowledge.document_uploaded",
                                target_type="knowledge_document", target_id=str(doc.id), details_json=details))
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        try:
            delete_file(key)
        except Exception:
            current_app.logger.exception("Could not clean up failed document upload")
        raise IngestError("The document could not be indexed. Please try again.") from exc
    return doc
