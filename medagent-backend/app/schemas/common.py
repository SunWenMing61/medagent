# 从 pydantic 导入 BaseModel（数据模型基类）
from pydantic import BaseModel
# 从 typing 导入 Generic（泛型基类）、TypeVar（类型变量）、List（列表类型）、Optional（可选类型）
from typing import Generic, TypeVar, List, Optional

# 声明一个类型变量 T，用于泛型分页响应模型
T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    # 通用分页响应模型，使用泛型 T 支持任意数据类型的分页返回
    # 当前页的数据项列表，类型由泛型参数 T 决定
    items: List[T]
    # 数据总条数
    total: int
    # 当前页码，默认值为 1
    page: int = 1
    # 每页大小，默认值为 20
    page_size: int = 20


class MessageResponse(BaseModel):
    # 通用消息响应模型，用于返回简单的操作结果信息
    # 消息文本内容，例如 "操作成功" 或错误描述
    message: str
