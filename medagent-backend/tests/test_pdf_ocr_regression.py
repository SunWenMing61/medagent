"""文字、扫描与混合 PDF 提取的回归测试。"""

from unittest.mock import patch

import fitz

from app.utils.file_utils import extract_text_from_pdf


def test_mixed_pdf_only_ocr_low_text_pages(tmp_path):
    pdf_path = tmp_path / "mixed.pdf"
    document = fitz.open()
    text_page = document.new_page()
    text_page.insert_text((72, 72), "native text " * 10)
    document.new_page()  # 空白页用于模拟扫描页；OCR 本身在此测试中 mock。
    document.save(pdf_path)
    document.close()

    progress = []
    with patch("app.utils.file_utils._ocr_pdf_page", return_value="扫描识别结果") as ocr:
        pages = extract_text_from_pdf(
            str(pdf_path),
            progress_callback=lambda done, total, used_ocr: progress.append(
                (done, total, used_ocr)
            ),
        )

    assert [page_number for page_number, _ in pages] == [1, 2]
    assert pages[1][1] == "扫描识别结果"
    assert ocr.call_count == 1
    assert progress == [(1, 2, False), (2, 2, True)]

