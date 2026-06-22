"""药品说明书适配器。

主要支持 CSV 导入方式。用户上传包含结构化药品信息的 CSV 文件,
系统解析后生成 SourceDocument 对象。

未来计划:接入第三方 API(如丁香园 API、摩熵数科 API)。
"""

import csv  # CSV 文件解析
import os   # 操作系统接口,用于文件路径检查
from typing import AsyncGenerator, Optional  # 异步生成器和可选类型

from app.adapters.base import BaseSourceAdapter, SourceDocument  # 基础适配器和文档类型
from app.adapters import register_adapter  # 适配器注册函数


# 适配器可识别的标准字段列名映射(key=英文字段名, value=中文显示名)
RECOGNIZED_COLUMNS = {
    "drug_name": "药品名称",         # 药品名称
    "generic_name": "通用名",         # 通用名
    "category": "类别",               # 类别
    "indications": "适应症",          # 适应症
    "dosage": "用法用量",             # 用法用量
    "side_effects": "不良反应",       # 不良反应
    "contraindications": "禁忌",      # 禁忌
    "precautions": "注意事项",        # 注意事项
    "interactions": "药物相互作用",   # 药物相互作用
    "pharmacology": "药理毒理",       # 药理毒理
    "storage": "贮藏",               # 贮藏
    "packaging": "包装",             # 包装
    "manufacturer": "生产企业",       # 生产企业
    "approval_number": "批准文号",    # 批准文号
    "ingredients": "主要成分",        # 主要成分
}

# 生成文档时各章节的顺序(key=英文字段名, value=中文显示名)
SECTION_ORDER = [
    ("category", "类别"),               # 类别
    ("generic_name", "通用名"),           # 通用名
    ("ingredients", "主要成分"),          # 主要成分
    ("indications", "适应症"),           # 适应症
    ("dosage", "用法用量"),              # 用法用量
    ("side_effects", "不良反应"),        # 不良反应
    ("contraindications", "禁忌"),       # 禁忌
    ("precautions", "注意事项"),         # 注意事项
    ("interactions", "药物相互作用"),    # 药物相互作用
    ("pharmacology", "药理毒理"),        # 药理毒理
    ("storage", "贮藏"),                # 贮藏
    ("packaging", "包装"),              # 包装
    ("manufacturer", "生产企业"),        # 生产企业
    ("approval_number", "批准文号"),     # 批准文号
]


class DrugLabelAdapter(BaseSourceAdapter):
    """药品说明书适配器,支持从 CSV 文件导入药品信息。"""
    source_type = "drug_label"  # 来源类型标识
    display_name = "药品说明书"  # 显示名称

    def validate_config(self, config: dict) -> tuple[bool, Optional[str]]:
        """验证适配器配置:检查 CSV 文件路径是否存在。

        Args:
            config: 配置字典,包含 source_type、file_path 等

        Returns:
            (is_valid, error_message) 元组
        """
        source = config.get("source_type", "csv_import")  # 来源类型,默认 CSV 导入
        if source == "csv_import":
            file_path = config.get("file_path", "")
            if not file_path:
                return True, None  # 文件路径为空视为有效(将在同步时通过上传设置)
            if not os.path.isfile(file_path):
                return False, f"文件不存在: {file_path}"  # 文件路径不存在则报错
        return True, None  # 默认通过验证

    def get_config_schema(self) -> dict:
        """返回前端渲染配置表单所需的 JSON Schema。

        Returns:
            配置表单的 JSON Schema 字典
        """
        return {
            "type": "object",
            "title": "药品说明书配置",
            "properties": {
                "source_type": {          # 数据来源选择
                    "type": "string",
                    "title": "数据来源",
                    "enum": ["csv_import"],  # 目前仅支持 CSV 导入
                    "enumNames": ["CSV 文件导入"],
                    "default": "csv_import",
                    "description": "目前支持 CSV 文件导入，后续将支持 API 接入",
                },
                "file_path": {             # CSV 文件路径
                    "type": "string",
                    "title": "CSV 文件路径",
                    "description": "上传 CSV 文件后自动填充",
                    "default": "",
                },
                "delimiter": {             # CSV 分隔符
                    "type": "string",
                    "title": "分隔符",
                    "enum": [",", ";", "\t", "|"],
                    "enumNames": ["逗号 (,)", "分号 (;)", "制表符 (Tab)", "竖线 (|)"],
                    "default": ",",
                },
                "encoding": {              # 文件编码
                    "type": "string",
                    "title": "文件编码",
                    "enum": ["utf-8", "gbk", "gb2312", "utf-8-sig"],
                    "enumNames": ["UTF-8", "GBK", "GB2312", "UTF-8 BOM"],
                    "default": "utf-8",
                },
                "column_mapping": {        # CSV 列名到标准字段的映射
                    "type": "object",
                    "title": "列映射",
                    "description": "将 CSV 列名映射为标准字段（不填则自动检测）",
                    "properties": {col: {"type": "string", "title": label} for col, label in RECOGNIZED_COLUMNS.items()},
                    "default": {},
                },
                "batch_name": {            # 本次导入的批次名称标识
                    "type": "string",
                    "title": "批次名称",
                    "description": "本次导入的名称标识",
                    "default": "",
                },
            },
            "required": ["source_type"],  # 必填字段
        }

    def get_default_config(self) -> dict:
        """返回默认配置值。

        Returns:
            包含默认值的配置字典
        """
        return {
            "source_type": "csv_import",  # 默认来源类型:CSV 导入
            "file_path": "",              # 默认文件路径为空
            "delimiter": ",",             # 默认分隔符:逗号
            "encoding": "utf-8",          # 默认编码:UTF-8
            "column_mapping": {},          # 默认无列映射
            "batch_name": "",             # 默认无批次名称
        }

    async def fetch_content(
        self, config: dict,
    ) -> AsyncGenerator[SourceDocument, None]:
        """根据配置获取药品说明书内容。

        目前仅支持 CSV 导入模式。

        Args:
            config: 配置字典

        Yields:
            SourceDocument 对象
        """
        source_type = config.get("source_type", "csv_import")
        if source_type == "csv_import":
            async for doc in self._fetch_from_csv(config):  # 从 CSV 获取数据
                yield doc

    async def _fetch_from_csv(
        self, config: dict,
    ) -> AsyncGenerator[SourceDocument, None]:
        """从 CSV 文件中逐行读取并生成 SourceDocument。

        Args:
            config: 配置字典,包含 file_path、delimiter、encoding、column_mapping、batch_name

        Yields:
            每行数据转换后的 SourceDocument 对象
        """
        file_path = config.get("file_path", "")
        if not file_path or not os.path.isfile(file_path):
            return  # 文件不存在则直接返回

        delimiter = config.get("delimiter", ",")           # 分隔符
        encoding = config.get("encoding", "utf-8")          # 文件编码
        column_mapping = config.get("column_mapping", {}) or {}  # 列映射(防止 None)
        batch_name = config.get("batch_name", "")           # 批次名称

        try:
            with open(file_path, "r", encoding=encoding) as f:
                reader = csv.DictReader(f, delimiter=delimiter)  # 创建 CSV 字典读取器
                if reader.fieldnames is None:
                    return  # 无列名则无法解析,直接返回

                # 如果用户未提供列映射,则自动检测
                fieldnames = [name.strip() for name in reader.fieldnames]  # 清洗列名
                col_map = self._build_column_mapping(fieldnames, column_mapping)  # 构建列映射

                for row in reader:
                    doc = self._row_to_document(row, col_map, batch_name)  # 行转文档
                    if doc is not None:
                        yield doc  # 产出 SourceDocument

        except (csv.Error, IOError, UnicodeDecodeError) as e:
            # 错误将由 SourceService 统一捕获处理
            raise RuntimeError(f"CSV 解析失败: {e}")

    def _build_column_mapping(self, fieldnames: list[str], user_mapping: dict) -> dict:
        """根据常见名称自动检测列映射关系。

        Args:
            fieldnames: CSV 文件中的列名列表
            user_mapping: 用户手动提供的列映射

        Returns:
            完整的列映射字典(CSV列名 -> 标准字段名)
        """
        mapping = dict(user_mapping)  # 以用户提供的映射为基础

        # 常见名称到标准字段名的映射表
        canonical_names = {
            "药品名称": "drug_name", "药名": "drug_name", "名称": "drug_name",
            "drug_name": "drug_name", "name": "drug_name",
            "通用名": "generic_name", "generic_name": "generic_name",
            "类别": "category", "分类": "category", "category": "category",
            "适应症": "indications", "主治": "indications", "功能主治": "indications",
            "indications": "indications",
            "用法": "dosage", "用量": "dosage", "用法用量": "dosage",
            "dosage": "dosage",
            "不良反应": "side_effects", "副作用": "side_effects",
            "side_effects": "side_effects",
            "禁忌": "contraindications", "contraindications": "contraindications",
            "注意事项": "precautions", "注意": "precautions",
            "precautions": "precautions",
            "相互作用": "interactions", "interactions": "interactions",
            "药理": "pharmacology", "药理毒理": "pharmacology",
            "pharmacology": "pharmacology",
            "贮藏": "storage", "storage": "storage",
            "包装": "packaging", "packaging": "packaging",
            "生产企业": "manufacturer", "生产厂家": "manufacturer",
            "manufacturer": "manufacturer",
            "批准文号": "approval_number", "批号": "approval_number",
            "approval_number": "approval_number",
            "成分": "ingredients", "主要成分": "ingredients",
            "ingredients": "ingredients",
        }

        for field in fieldnames:
            if field in mapping:
                continue  # 已在用户映射中,跳过
            stripped = field.strip()  # 清洗空格
            if stripped in canonical_names:
                mapping[field] = canonical_names[stripped]  # 自动匹配标准字段名

        return mapping

    def _row_to_document(
        self, row: dict, col_map: dict, batch_name: str,
    ) -> Optional[SourceDocument]:
        """将 CSV 的一行数据转换为 SourceDocument 对象。

        Args:
            row: CSV 行数据字典
            col_map: 列映射字典(CSV列名 -> 标准字段名)
            batch_name: 批次名称

        Returns:
            转换后的 SourceDocument 对象,如果无数据则返回 None
        """
        # 构建标准字段值字典
        values = {}  # 标准字段名 -> 值
        for csv_col, standard_col in col_map.items():
            val = row.get(csv_col, "").strip()  # 获取 CSV 列的值并清洗
            if val:
                values[standard_col] = val  # 非空值才加入

        if not values:
            return None  # 无有效数据则返回 None

        drug_name = values.get("drug_name", "")  # 获取药品名称
        if not drug_name:
            # 如果药品名称为空,尝试取第一个非空列的值作为名称
            for v in row.values():
                if v.strip():
                    drug_name = v.strip()
                    break
            if not drug_name:
                return None  # 仍然为空则返回 None

        category = values.get("category", "西药")  # 默认类别为西药

        # 构建结构化的文档内容
        content_parts = [f"===== {drug_name} ====="]  # 标题行
        if values.get("generic_name"):
            content_parts.append(f"通用名: {values['generic_name']}")  # 通用名

        content_parts.append(f"类别: {category}")  # 类别

        # 按照预定义顺序添加各章节内容
        for key, label in SECTION_ORDER:
            if key in ("drug_name", "category", "generic_name"):
                continue  # 已在前面的步骤处理过,跳过
            if key in values and values[key]:
                content_parts.append(f"\n【{label}】")  # 添加章节标题
                content_parts.append(values[key])        # 添加章节内容

        content = "\n".join(content_parts)  # 合并为完整文本

        metadata = dict(values)  # 将标准字段值复制为元数据
        metadata["batch_name"] = batch_name  # 添加批次名称到元数据

        return SourceDocument(
            title=drug_name,                                # 文档标题为药品名
            content=content,                                # 文档正文
            source_url=values.get("source_url", ""),        # 来源 URL
            source_id_field=values.get("approval_number", ""),  # 批准文号作为唯一标识
            metadata=metadata,                              # 元数据
        )


# 在模块加载时注册适配器,使其可被适配器工厂发现
register_adapter(DrugLabelAdapter)
