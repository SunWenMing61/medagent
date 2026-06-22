import os       # 操作系统接口,用于文件路径处理
import fitz     # PyMuPDF 库,用于解析 PDF 文件
from docx import Document as DocxDocument  # python-docx 库,用于解析 DOCX 文件


def extract_text_from_pdf(file_path: str) -> list:
    """从 PDF 文件中提取文本。

    Args:
        file_path: PDF 文件的完整路径

    Returns:
        (page_num, text) 元组列表,每个元组包含页码和对应的文本内容
    """
    results = []  # 存储 (页码, 文本) 元组
    try:
        doc = fitz.open(file_path)  # 使用 PyMuPDF 打开 PDF 文件
        for page_num, page in enumerate(doc, start=1):  # 从第 1 页开始遍历
            text = page.get_text()   # 提取当前页的文本
            if text.strip():         # 跳过空白页
                results.append((page_num, text.strip()))  # 添加 (页码, 清洗后文本)
        doc.close()  # 关闭文档释放资源
    except Exception as e:
        raise ValueError(f"PDF parse error: {e}")  # 解析失败时抛出异常
    return results


def extract_text_from_docx(file_path: str) -> list:
    """从 DOCX 文件中提取文本。

    Args:
        file_path: DOCX 文件的完整路径

    Returns:
        [(1, text)] 列表,所有文本合并后作为一页(页码为 1)
    """
    results = []  # 存储结果
    try:
        doc = DocxDocument(file_path)  # 使用 python-docx 打开 DOCX 文件
        # 提取所有段落文本,过滤空白段落,用换行符连接
        text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        if text.strip():
            results.append((1, text.strip()))  # DOCX 无分页概念,统一作为第 1 页
    except Exception as e:
        raise ValueError(f"DOCX parse error: {e}")
    return results


def extract_text_from_txt(file_path: str) -> list:
    """从纯文本文件中提取文本。

    Args:
        file_path: TXT 文件的完整路径

    Returns:
        [(1, text)] 列表,内容作为一页(页码为 1)
    """
    results = []  # 存储结果
    try:
        # 以 UTF-8 编码打开文件,errors='replace' 表示遇到无法解码的字符时用替换符替代
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()  # 读取全部文本
        if text.strip():
            results.append((1, text.strip()))  # TXT 无分页概念,统一作为第 1 页
    except Exception as e:
        raise ValueError(f"TXT parse error: {e}")
    return results


def extract_text(file_path: str, file_type: str) -> list:
    """根据文件类型提取文本内容。

    Args:
        file_path: 文件的完整路径
        file_type: 文件类型(小写,如 'pdf', 'docx', 'txt')

    Returns:
        (page_num, text) 元组列表

    Raises:
        ValueError: 如果文件类型不支持
    """
    ext = file_type.lower()  # 统一转为小写进行比较
    if ext == "pdf":
        return extract_text_from_pdf(file_path)   # PDF 文件处理
    elif ext == "docx":
        return extract_text_from_docx(file_path)   # DOCX 文件处理
    elif ext in ("txt", "md", "markdown"):
        return extract_text_from_txt(file_path)    # 纯文本/Markdown 文件处理
    else:
        raise ValueError(f"Unsupported file type: {file_type}")  # 不支持的文件类型
