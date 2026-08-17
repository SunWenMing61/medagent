"""EasyOCR adapter that preserves confidence and bounding boxes."""

from __future__ import annotations

import logging
import threading
from typing import Any

import fitz

from app.core.config import settings
from app.parsers.models import TextBlock

logger = logging.getLogger(__name__)
_reader: Any = None
_reader_lock = threading.Lock()


class EasyOCRParser:
    version = "easyocr-v1"

    def _get_reader(self):
        global _reader
        if _reader is not None:
            return _reader
        try:
            import easyocr
        except ImportError as exc:
            raise RuntimeError("OCR is required for this page but EasyOCR is not installed") from exc

        with _reader_lock:
            if _reader is None:
                languages = [x.strip() for x in settings.OCR_LANGUAGES.split(",") if x.strip()]
                logger.info("Loading EasyOCR languages=%s gpu=%s", languages, settings.OCR_USE_GPU)
                kwargs = {"gpu": settings.OCR_USE_GPU, "verbose": False}
                if settings.OCR_MODEL_DIR:
                    kwargs["model_storage_directory"] = settings.OCR_MODEL_DIR
                _reader = easyocr.Reader(languages, **kwargs)
        return _reader

    def parse_page(self, page: fitz.Page, dpi: int) -> tuple[str, list[TextBlock], float | None]:
        import numpy as np
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps

        scale = max(dpi, 72) / 72.0
        pixels = page.rect.width * scale * page.rect.height * scale
        if pixels > settings.OCR_MAX_PIXELS:
            scale *= (settings.OCR_MAX_PIXELS / pixels) ** 0.5
        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False
        )
        rgb = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
            pixmap.height, pixmap.width, pixmap.n
        )
        pil_image = Image.fromarray(rgb).convert("L")
        pil_image = ImageOps.autocontrast(pil_image, cutoff=1)
        pil_image = ImageEnhance.Contrast(pil_image).enhance(1.25)
        pil_image = pil_image.filter(ImageFilter.MedianFilter(size=3))
        image = np.asarray(pil_image)
        results = self._get_reader().readtext(
            image,
            detail=1,
            paragraph=False,
            rotation_info=[90, 180, 270],
        )
        blocks: list[TextBlock] = []
        confidences: list[float] = []
        for order, result in enumerate(results):
            if not isinstance(result, (list, tuple)) or len(result) < 3:
                continue
            points, raw_text, raw_confidence = result[0], result[1], result[2]
            text = str(raw_text).strip()
            if not text:
                continue
            confidence = max(0.0, min(float(raw_confidence), 1.0))
            confidences.append(confidence)
            xs = [float(point[0]) / scale for point in points]
            ys = [float(point[1]) / scale for point in points]
            blocks.append(
                TextBlock(
                    text=text,
                    bbox=(min(xs), min(ys), max(xs), max(ys)),
                    confidence=confidence,
                    order=order,
                    extraction_method="ocr",
                    metadata={
                        "ocr_engine": self.version,
                        "dpi": round(scale * 72),
                        "preprocessing": ["grayscale", "autocontrast", "contrast_1.25", "median_denoise"],
                    },
                )
            )
        mean_confidence = sum(confidences) / len(confidences) if confidences else None
        return "\n".join(block.text for block in blocks), blocks, mean_confidence
