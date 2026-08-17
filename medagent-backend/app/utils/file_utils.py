"""文档文本提取工具，支持文字 PDF、混合 PDF 与扫描 PDF OCR。"""

import logging
import threading
from typing import Callable, List, Optional, Tuple

import fitz
from docx import Document as DocxDocument

from app.core.config import settings

logger = logging.getLogger(__name__)

PageText = Tuple[int, str]
PdfProgressCallback = Callable[[int, int, bool], None]

_ocr_reader = None
_ocr_reader_lock = threading.Lock()
_ocr_available: Optional[bool] = None


def is_ocr_available() -> bool:
    """返回 EasyOCR 及其必要运行依赖是否可导入。"""
    global _ocr_available
    if _ocr_available is None:
        try:
            import easyocr  # noqa: F401
            import numpy  # noqa: F401

            _ocr_available = True
        except ImportError:
            _ocr_available = False
            logger.warning(
                "[OCR] EasyOCR is not installed; scanned PDFs cannot be processed."
            )
    return _ocr_available


def _get_ocr_reader():
    """惰性初始化并复用 EasyOCR Reader，避免每一页重复加载模型。"""
    global _ocr_reader
    if _ocr_reader is not None:
        return _ocr_reader
    if not is_ocr_available():
        raise ValueError(
            "扫描型 PDF 需要 OCR 识别，但 EasyOCR 未安装。"
            "请安装项目 requirements.txt 中的 OCR 依赖后重启 worker。"
        )

    with _ocr_reader_lock:
        if _ocr_reader is None:
            import easyocr

            languages = [
                language.strip()
                for language in settings.OCR_LANGUAGES.split(",")
                if language.strip()
            ]
            logger.info("[OCR] Loading EasyOCR model for languages=%s", languages)
            _ocr_reader = easyocr.Reader(
                languages,
                gpu=settings.OCR_USE_GPU,
                verbose=False,
            )
    return _ocr_reader


def _ocr_pdf_page(page: fitz.Page, dpi: int) -> str:
    """把单页渲染为 RGB 图片并执行 OCR。"""
    import numpy as np

    scale = max(dpi, 72) / 72.0
    pixmap = page.get_pixmap(
        matrix=fitz.Matrix(scale, scale),
        colorspace=fitz.csRGB,
        alpha=False,
    )
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n
    )
    lines = _get_ocr_reader().readtext(
        image,
        detail=0,
        paragraph=True,
    )
    return "\n".join(str(line).strip() for line in lines if str(line).strip())


def extract_text_from_pdf(
    file_path: str,
    progress_callback: Optional[PdfProgressCallback] = None,
) -> List[PageText]:
    """逐页提取 PDF 文本，对无文字/少文字页面自动执行 OCR。

    与只在“整份 PDF 完全无文字”时触发 OCR 的实现不同，这里也能正确处理
    文字页与扫描页混排的 PDF。回调参数依次为已处理页数、总页数、该页是否 OCR。
    """
    results: List[PageText] = []
    min_native_chars = max(settings.OCR_MIN_NATIVE_TEXT_CHARS, 0)
    dpi = max(settings.OCR_DPI, 72)
    max_pages = max(settings.OCR_MAX_PAGES, 1)

    try:
        with fitz.open(file_path) as document:
            total_pages = document.page_count
            if total_pages == 0:
                raise ValueError("PDF 没有可处理的页面")
            ocr_pages = 0

            for page_index, page in enumerate(document, start=1):
                native_text = page.get_text("text").strip()
                used_ocr = len(native_text) < min_native_chars
                text = native_text

                if used_ocr:
                    ocr_pages += 1
                    if ocr_pages > max_pages:
                        raise ValueError(
                            f"需要 OCR 的页面超过 OCR_MAX_PAGES={max_pages} 的安全上限"
                        )
                    try:
                        ocr_text = _ocr_pdf_page(page, dpi=dpi).strip()
                    except Exception as exc:
                        raise ValueError(
                            f"PDF 第 {page_index}/{total_pages} 页 OCR 失败: {exc}"
                        ) from exc
                    # 少量原生文字可能是页码或隐藏层；OCR 有结果时以 OCR 为准。
                    if ocr_text:
                        text = ocr_text

                if text:
                    results.append((page_index, text))

                if progress_callback:
                    progress_callback(page_index, total_pages, used_ocr)

    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"PDF parse error: {exc}") from exc

    if not results:
        raise ValueError("PDF 文本提取和 OCR 均未识别到有效内容")
    return results


def extract_text_from_docx(file_path: str) -> List[PageText]:
    """从 DOCX 文件中提取文本。"""
    try:
        document = DocxDocument(file_path)
        text = "\n".join(p.text for p in document.paragraphs if p.text.strip()).strip()
        return [(1, text)] if text else []
    except Exception as exc:
        raise ValueError(f"DOCX parse error: {exc}") from exc


def extract_text_from_txt(file_path: str) -> List[PageText]:
    """从纯文本或 Markdown 文件中提取文本。"""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as file:
            text = file.read().strip()
        return [(1, text)] if text else []
    except Exception as exc:
        raise ValueError(f"TXT parse error: {exc}") from exc


def extract_text(
    file_path: str,
    file_type: str,
    progress_callback: Optional[PdfProgressCallback] = None,
) -> List[PageText]:
    """根据文件类型提取文本。"""
    extension = file_type.lower()
    if extension == "pdf":
        return extract_text_from_pdf(file_path, progress_callback=progress_callback)
    if extension == "docx":
        return extract_text_from_docx(file_path)
    if extension in ("txt", "md", "markdown"):
        return extract_text_from_txt(file_path)
    raise ValueError(f"Unsupported file type: {file_type}")
