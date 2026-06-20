import os
import fitz  # PyMuPDF
from docx import Document as DocxDocument


def extract_text_from_pdf(file_path: str) -> list:
    """Extract text from PDF, returns list of (page_num, text) tuples."""
    results = []
    try:
        doc = fitz.open(file_path)
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text()
            if text.strip():
                results.append((page_num, text.strip()))
        doc.close()
    except Exception as e:
        raise ValueError(f"PDF parse error: {e}")
    return results


def extract_text_from_docx(file_path: str) -> list:
    """Extract text from DOCX, returns list of [(1, text)]."""
    results = []
    try:
        doc = DocxDocument(file_path)
        text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        if text.strip():
            results.append((1, text.strip()))
    except Exception as e:
        raise ValueError(f"DOCX parse error: {e}")
    return results


def extract_text_from_txt(file_path: str) -> list:
    """Extract text from TXT file."""
    results = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        if text.strip():
            results.append((1, text.strip()))
    except Exception as e:
        raise ValueError(f"TXT parse error: {e}")
    return results


def extract_text(file_path: str, file_type: str) -> list:
    """Extract text from file based on type. Returns list of (page_num, text)."""
    ext = file_type.lower()
    if ext == "pdf":
        return extract_text_from_pdf(file_path)
    elif ext == "docx":
        return extract_text_from_docx(file_path)
    elif ext in ("txt", "md", "markdown"):
        return extract_text_from_txt(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")
