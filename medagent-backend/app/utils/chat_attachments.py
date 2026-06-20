"""Utility for processing file/image attachments in chat messages."""

import base64
import logging
import os
import uuid
from typing import List, Optional

from app.core.config import settings
from app.utils.file_utils import extract_text

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_DOC_TYPES = {"application/pdf", "text/plain", "text/markdown"}
ALLOWED_DOC_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def get_file_type(filename: str, content_type: str) -> str:
    """Determine if a file is image, document, or unknown."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in ALLOWED_DOC_EXTENSIONS or content_type in ALLOWED_DOC_TYPES:
        return "document"
    return "unknown"


def process_attachment(file_path: str, filename: str, content_type: str) -> Optional[dict]:
    """Process a single uploaded chat attachment.

    Returns a dict with:
      - type: "image" | "document"
      - filename: original filename
      - For images: base64_data, mime_type
      - For documents: extracted_text

    Returns None if the file type is unsupported.
    """
    file_type = get_file_type(filename, content_type)

    if file_type == "image":
        try:
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            mime = content_type or "image/png"
            return {
                "type": "image",
                "filename": filename,
                "base64_data": b64,
                "mime_type": mime,
            }
        except Exception as e:
            logger.error("Failed to read image %s: %s", filename, e)
            return None

    elif file_type == "document":
        ext = os.path.splitext(filename)[1].lower().lstrip(".")
        try:
            pages = extract_text(file_path, ext if ext else "txt")
            text = "\n".join([t for _, t in pages])
            if text.strip():
                return {
                    "type": "document",
                    "filename": filename,
                    "extracted_text": text,
                }
            return None
        except Exception as e:
            logger.error("Failed to extract text from %s: %s", filename, e)
            return None

    return None


def save_uploaded_file(file_content: bytes, filename: str) -> str:
    """Save an uploaded file to the chat uploads directory.

    Returns the absolute file path.
    """
    chat_upload_dir = os.path.join(settings.UPLOAD_DIR, "chat_uploads")
    os.makedirs(chat_upload_dir, exist_ok=True)

    ext = os.path.splitext(filename)[1] or ""
    saved_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(chat_upload_dir, saved_name)

    with open(file_path, "wb") as f:
        f.write(file_content)

    return file_path


def cleanup_file(file_path: str):
    """Delete a temporary file."""
    try:
        if os.path.isfile(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.warning("Failed to clean up %s: %s", file_path, e)


def build_multimodal_content(
    question: str,
    attachments: List[dict],
) -> list:
    """Build an LLM content array (text + images) from question and attachments.

    Returns a list of content blocks compatible with OpenAI-compatible APIs:
      [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "data:...;base64,..."}}]
    """
    content: list = [{"type": "text", "text": question}]

    # Add document extracted text as additional context
    doc_texts = []
    for att in attachments:
        if att["type"] == "image":
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{att['mime_type']};base64,{att['base64_data']}",
                },
            })
        elif att["type"] == "document":
            text = att.get("extracted_text", "")
            if text:
                # Truncate very long documents to avoid token limits
                if len(text) > 50000:
                    text = text[:50000] + "\n\n[... 文档过长，已截断 ...]"
                doc_texts.append(f"--- 文件: {att['filename']} ---\n{text}")

    if doc_texts:
        doc_section = "\n\n".join(doc_texts)
        content.append({
            "type": "text",
            "text": f"\n\n用户同时上传了以下文档作为参考:\n\n{doc_section}",
        })

    return content


def describe_attachments_for_prompt(attachments: List[dict]) -> str:
    """Build a text description of attachments for non-multimodal prompts."""
    parts = []
    for att in attachments:
        if att["type"] == "image":
            parts.append(f"[图片: {att['filename']}]")
        elif att["type"] == "document":
            text = att.get("extracted_text", "")
            preview = text[:500] + "..." if len(text) > 500 else text
            parts.append(f"[文档: {att['filename']}]\n{preview}")
    return "\n\n".join(parts)
