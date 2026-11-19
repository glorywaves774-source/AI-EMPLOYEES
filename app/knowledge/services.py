"""Document extraction, chunking and permission-aware keyword retrieval."""
from collections import Counter
from io import BytesIO
import re
import zipfile

from app.extensions import db
from app.models import (AIEmployee, AIEmployeeKnowledgePermission, AuditLog, KnowledgeChunk,
                        KnowledgeDocument, KnowledgeRepository)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv"}
MAX_EXTRACTED_CHARS = 300_000
CHUNK_SIZE = 1_500
CHUNK_OVERLAP = 180


def extract_document_text(filename, raw_bytes):
    """Validate a small allowlisted document and extract text without writing it to disk."""
    from pathlib import PurePath
    suffix = PurePath(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Supported file types are PDF, DOCX, TXT, Markdown and CSV.")
    if not raw_bytes:
        raise ValueError("The uploaded document is empty.")

    if suffix == ".pdf":
        if not raw_bytes.startswith(b"%PDF-"):
            raise ValueError("The file does not have a valid PDF signature.")
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(raw_bytes), strict=True)
        if len(reader.pages) > 200:
            raise ValueError("PDF files are limited to 200 pages.")
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        mime = "application/pdf"
    elif suffix == ".docx":
        if not raw_bytes.startswith(b"PK\x03\x04"):
            raise ValueError("The file does not have a valid DOCX signature.")
        with zipfile.ZipFile(BytesIO(raw_bytes)) as archive:
            entries = archive.infolist()
            if len(entries) > 1000 or sum(item.file_size for item in entries) > 20_000_000:
                raise ValueError("The DOCX package exceeds safe extraction limits.")
            if "word/document.xml" not in archive.namelist():
                raise ValueError("The uploaded ZIP is not a valid DOCX document.")
        from docx import Document
        document = Document(BytesIO(raw_bytes))
        parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        text = "\n".join(parts)
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        if b"\x00" in raw_bytes:
            raise ValueError("Binary content is not accepted as a text document.")
        try:
            text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Text files must use UTF-8 encoding.") from exc
        mime = {".txt": "text/plain", ".md": "text/markdown", ".csv": "text/csv"}[suffix]

    text = text.replace("\x00", "").strip()
    if not text:
        raise ValueError("No selectable text was found. Scanned PDFs and image-only documents need OCR, which is not included in this milestone.")
    if len(text) > MAX_EXTRACTED_CHARS:
        text = text[:MAX_EXTRACTED_CHARS]
    return mime, text


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    text = (text or "").strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text) and len(chunks) < 250:
        end = min(len(text), start + size)
        if end < len(text):
            boundary = text.rfind("\n", start + size // 2, end)
            if boundary > start:
                end = boundary
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _terms(value):
    return [word for word in re.findall(r"[a-z0-9]{3,}", (value or "").lower())]


def _rank_rows(query, rows, limit):
    query_terms = Counter(_terms(query))
    if not query_terms:
        return []
    ranked = []
    for chunk, document, repository in rows:
        counts = Counter(_terms(chunk.content))
        score = sum(min(counts[term], 4) * weight for term, weight in query_terms.items())
        if score:
            ranked.append((score, chunk, document, repository))
    ranked.sort(key=lambda item: (-item[0], item[2].id, item[1].chunk_index))
    return ranked[:limit]


def search_tenant_knowledge(tenant_id, query, limit=25):
    rows = (db.session.query(KnowledgeChunk, KnowledgeDocument, KnowledgeRepository)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .join(KnowledgeRepository, KnowledgeRepository.id == KnowledgeDocument.repository_id)
            .filter(KnowledgeChunk.tenant_id == tenant_id,
                    KnowledgeDocument.tenant_id == tenant_id,
                    KnowledgeRepository.tenant_id == tenant_id,
                    KnowledgeDocument.status == "ready").limit(5000).all())
    return _rank_rows(query, rows, limit)


def retrieve_employee_knowledge(tenant_id, employee_id, query, limit=4, task_id=None, actor_user_id=None):
    """Return only chunks from repositories explicitly assigned to this employee."""
    permitted_ids = [row[0] for row in db.session.query(AIEmployeeKnowledgePermission.repository_id)
                     .join(AIEmployee, AIEmployee.id == AIEmployeeKnowledgePermission.employee_id)
                     .filter(AIEmployeeKnowledgePermission.tenant_id == tenant_id,
                             AIEmployeeKnowledgePermission.employee_id == employee_id,
                             AIEmployee.tenant_id == tenant_id).all()]
    if not permitted_ids:
        return ""
    rows = (db.session.query(KnowledgeChunk, KnowledgeDocument, KnowledgeRepository)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .join(KnowledgeRepository, KnowledgeRepository.id == KnowledgeDocument.repository_id)
            .filter(KnowledgeChunk.tenant_id == tenant_id,
                    KnowledgeDocument.tenant_id == tenant_id,
                    KnowledgeRepository.tenant_id == tenant_id,
                    KnowledgeDocument.repository_id.in_(permitted_ids),
                    KnowledgeDocument.status == "ready").limit(2000).all())
    selected = _rank_rows(query, rows, limit)
    if not selected:
        return ""
    doc_ids = sorted({item[2].id for item in selected})
    for doc_id in doc_ids:
        db.session.add(AuditLog(tenant_id=tenant_id, actor_user_id=actor_user_id, action="knowledge.retrieved",
            target_type="knowledge_document", target_id=str(doc_id),
            details_json={"employee_id": employee_id, "task_id": task_id,
                          "chunk_count": sum(1 for item in selected if item[2].id == doc_id)}))
    parts = []
    for score, chunk, document, repository in selected:
        parts.append(f"[Source: {document.original_filename}; repository: {repository.name}; section {chunk.chunk_index + 1}]\n{chunk.content}")
    return "\n\n".join(parts)[:12_000]
