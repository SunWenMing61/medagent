"""聊天消息中文件/图片附件的处理工具。"""

import base64  # Base64 编解码,用于将图片数据转为文本格式
import logging  # 日志记录
import os      # 操作系统接口,用于文件和路径处理
import uuid    # UUID 生成,用于生成唯一的文件名
from typing import List, Optional  # 类型提示

from app.core.config import settings  # 应用配置
from app.utils.file_utils import extract_text  # 文件文本提取工具

logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器

# 允许上传的图片 MIME 类型集合
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
# 允许上传的文档 MIME 类型集合
ALLOWED_DOC_TYPES = {"application/pdf", "text/plain", "text/markdown"}
# 允许上传的文档文件扩展名集合
ALLOWED_DOC_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}
# 图片文件的扩展名集合
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def get_file_type(filename: str, content_type: str) -> str:
    """判断一个文件是图片、文档还是未知类型。

    Args:
        filename: 原始文件名
        content_type: 文件的 MIME 类型

    Returns:
        "image" 表示图片, "document" 表示文档, "unknown" 表示不支持的类型
    """
    ext = os.path.splitext(filename)[1].lower()  # 获取文件扩展名并转小写
    if ext in IMAGE_EXTENSIONS:
        return "image"      # 扩展名匹配图片格式
    if ext in ALLOWED_DOC_EXTENSIONS or content_type in ALLOWED_DOC_TYPES:
        return "document"   # 扩展名或 MIME 类型匹配文档格式
    return "unknown"        # 不支持的格式


def process_attachment(file_path: str, filename: str, content_type: str) -> Optional[dict]:
    """处理单个上传的聊天附件。

    Args:
        file_path: 文件在磁盘上的完整路径
        filename: 原始文件名
        content_type: 文件的 MIME 类型

    Returns:
        处理后的字典:
          - type: "image" 或 "document"
          - filename: 原始文件名
          - 图片: base64_data, mime_type
          - 文档: extracted_text
        如果文件类型不支持则返回 None
    """
    file_type = get_file_type(filename, content_type)  # 判断文件类型

    if file_type == "image":
        try:
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")  # 读取图片并编码为 Base64
            mime = content_type or "image/png"  # 使用提供的 MIME 类型或默认值
            return {
                "type": "image",
                "filename": filename,
                "base64_data": b64,   # Base64 编码的图片数据
                "mime_type": mime,    # 图片的 MIME 类型
            }
        except Exception as e:
            logger.error("Failed to read image %s: %s", filename, e)  # 读取图片失败
            return None

    elif file_type == "document":
        ext = os.path.splitext(filename)[1].lower().lstrip(".")  # 获取无点扩展名
        try:
            pages = extract_text(file_path, ext if ext else "txt")  # 提取文档文本
            text = "\n".join([t for _, t in pages])  # 合并所有页的文本
            if text.strip():
                return {
                    "type": "document",
                    "filename": filename,
                    "extracted_text": text,  # 提取的文档文本内容
                }
            return None  # 文档无文本则返回 None
        except Exception as e:
            logger.error("Failed to extract text from %s: %s", filename, e)  # 文本提取失败
            return None

    return None  # 不支持的文件类型


def save_uploaded_file(file_content: bytes, filename: str) -> str:
    """将上传的文件保存到聊天上传目录。

    Args:
        file_content: 文件的二进制内容
        filename: 原始文件名(仅用于提取扩展名)

    Returns:
        保存后的文件绝对路径
    """
    chat_upload_dir = os.path.join(settings.UPLOAD_DIR, "chat_uploads")  # 聊天上传目录路径
    os.makedirs(chat_upload_dir, exist_ok=True)  # 确保目录存在

    ext = os.path.splitext(filename)[1] or ""  # 提取文件扩展名
    saved_name = f"{uuid.uuid4().hex}{ext}"    # 用 UUID 生成唯一文件名(保留扩展名)
    file_path = os.path.join(chat_upload_dir, saved_name)  # 完整的保存路径

    with open(file_path, "wb") as f:
        f.write(file_content)  # 写入文件内容

    return file_path  # 返回保存后的路径


def cleanup_file(file_path: str):
    """删除临时文件。

    Args:
        file_path: 要删除的文件路径
    """
    try:
        if os.path.isfile(file_path):  # 检查文件是否存在
            os.remove(file_path)       # 删除文件
    except Exception as e:
        logger.warning("Failed to clean up %s: %s", file_path, e)  # 删除失败仅记录警告


def build_multimodal_content(
    question: str,
    attachments: List[dict],
) -> list:
    """从用户问题和附件构建 LLM 多模态内容数组。

    返回与 OpenAI 兼容 API 兼容的内容块列表:
      [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "data:...;base64,..."}}]

    Args:
        question: 用户的问题文本
        attachments: 附件处理结果列表(由 process_attachment 返回)

    Returns:
        多模态内容块列表,包含文本和可选的图片/文档内容
    """
    content: list = [{"type": "text", "text": question}]  # 将用户问题作为第一个文本块

    # 添加文档提取的文本作为额外的上下文
    doc_texts = []  # 存储文档文本片段
    for att in attachments:
        if att["type"] == "image":
            # 图片附件:添加为 image_url 类型的内容块
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{att['mime_type']};base64,{att['base64_data']}",
                },
            })
        elif att["type"] == "document":
            text = att.get("extracted_text", "")
            if text:
                # 截断超长文档以避免超出 token 限制
                if len(text) > 50000:
                    text = text[:50000] + "\n\n[... 文档过长，已截断 ...]"
                doc_texts.append(f"--- 文件: {att['filename']} ---\n{text}")

    if doc_texts:
        # 如果有文档文本,将它们合并为一个文本块追加到内容列表
        doc_section = "\n\n".join(doc_texts)
        content.append({
            "type": "text",
            "text": f"\n\n用户同时上传了以下文档作为参考:\n\n{doc_section}",
        })

    return content


def describe_attachments_for_prompt(attachments: List[dict]) -> str:
    """为非多模态提示构建附件的文本描述。

    Args:
        attachments: 附件处理结果列表

    Returns:
        格式化后的附件描述文本
    """
    parts = []  # 存储各附件的描述
    for att in attachments:
        if att["type"] == "image":
            parts.append(f"[图片: {att['filename']}]")  # 图片仅标注文件名
        elif att["type"] == "document":
            text = att.get("extracted_text", "")
            preview = text[:500] + "..." if len(text) > 500 else text  # 预览前 500 字符
            parts.append(f"[文档: {att['filename']}]\n{preview}")
    return "\n\n".join(parts)  # 用双换行连接各附件描述
