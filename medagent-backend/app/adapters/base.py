"""在线知识源的基类适配器接口。"""
from abc import ABC, abstractmethod  # 抽象基类和抽象方法装饰器
from dataclasses import dataclass, field  # 数据类装饰器和字段工具
from typing import AsyncGenerator, Optional  # 异步生成器和可选类型
from datetime import datetime  # 日期时间类型


@dataclass
class SourceDocument:
    """表示从在线来源获取的单个内容条目。

    这是所有适配器返回的通用数据结构。
    SourceService 消费这些数据并存储为 Document + Chunk。

    Attributes:
        title: 文档标题
        content: 文档正文内容
        source_url: 来源 URL
        source_id_field: 来源的唯一标识符
        authors: 作者列表
        publication_date: 发布日期
        metadata: 附加元数据字典
    """
    title: str  # 文档标题
    content: str  # 文档正文内容
    source_url: str = ""  # 来源页面的 URL
    source_id_field: str = ""  # 来源的唯一标识符(如 PMID、批准文号)
    authors: list = field(default_factory=list)  # 作者列表,默认空列表
    publication_date: Optional[datetime] = None  # 发布日期,可选
    metadata: dict = field(default_factory=dict)  # 额外的元数据字典


class BaseSourceAdapter(ABC):
    """在线知识源适配器的抽象基类。

    每个适配器实现一种在线来源类型的获取逻辑
    (如 PubMed、默沙东诊疗手册、药品说明书 API 等)。

    Attributes:
        source_type: 来源类型标识符(如 "pubmed", "msd_manual")
        display_name: 来源的人类可读名称(如 "PubMed", "默沙东诊疗手册")
    """

    source_type: str = ""  # 适配器对应的来源类型标识
    display_name: str = ""  # 适配器对应的显示名称

    @abstractmethod
    def validate_config(self, config: dict) -> tuple[bool, Optional[str]]:
        """验证适配器的配置是否有效。

        Args:
            config: 用户提供的配置字典

        Returns:
            (is_valid, error_message) 元组,分别表示配置是否有效和错误信息
        """
        ...  # 抽象方法,子类必须实现

    @abstractmethod
    def get_config_schema(self) -> dict:
        """返回描述预期配置结构的 JSON Schema。

        用于前端渲染动态配置表单。
        必须至少包含: type、properties、required。

        Returns:
            符合 JSON Schema 标准的字典
        """
        ...  # 抽象方法,子类必须实现

    @abstractmethod
    async def fetch_content(
        self, config: dict,
    ) -> AsyncGenerator[SourceDocument, None]:
        """从在线来源获取内容。

        异步生成器,逐个产出 SourceDocument 对象。
        子类必须在内部处理频率限制。

        Args:
            config: 适配器配置字典

        Yields:
            SourceDocument 对象,每次一个
        """
        ...  # 抽象方法,子类必须实现

        # 使 Python < 3.12 对空抽象生成器保持兼容
        if False:  # pragma: no cover  # 永远不会执行的分支,仅用于语法兼容
            yield

    def get_default_config(self) -> dict:
        """返回默认的配置值。

        Returns:
            包含默认配置的字典
        """
        return {}  # 子类可选择性覆盖
