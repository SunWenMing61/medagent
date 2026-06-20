"""Drug label / 药品说明书 adapter.

Supports CSV import as the primary method. Users upload a CSV file with
structured drug information which gets parsed into SourceDocuments.

Future: Add third-party API integration (e.g. 丁香园 API, 摩熵数科 API).
"""

import csv
import os
from typing import AsyncGenerator, Optional

from app.adapters.base import BaseSourceAdapter, SourceDocument
from app.adapters import register_adapter


# Standard columns recognized by the adapter
RECOGNIZED_COLUMNS = {
    "drug_name": "药品名称",
    "generic_name": "通用名",
    "category": "类别",
    "indications": "适应症",
    "dosage": "用法用量",
    "side_effects": "不良反应",
    "contraindications": "禁忌",
    "precautions": "注意事项",
    "interactions": "药物相互作用",
    "pharmacology": "药理毒理",
    "storage": "贮藏",
    "packaging": "包装",
    "manufacturer": "生产企业",
    "approval_number": "批准文号",
    "ingredients": "主要成分",
}

# Standard sections in the generated document (in order)
SECTION_ORDER = [
    ("category", "类别"),
    ("generic_name", "通用名"),
    ("ingredients", "主要成分"),
    ("indications", "适应症"),
    ("dosage", "用法用量"),
    ("side_effects", "不良反应"),
    ("contraindications", "禁忌"),
    ("precautions", "注意事项"),
    ("interactions", "药物相互作用"),
    ("pharmacology", "药理毒理"),
    ("storage", "贮藏"),
    ("packaging", "包装"),
    ("manufacturer", "生产企业"),
    ("approval_number", "批准文号"),
]


class DrugLabelAdapter(BaseSourceAdapter):
    source_type = "drug_label"
    display_name = "药品说明书"

    def validate_config(self, config: dict) -> tuple[bool, Optional[str]]:
        source = config.get("source_type", "csv_import")
        if source == "csv_import":
            file_path = config.get("file_path", "")
            if not file_path:
                return True, None  # Will be set at sync time via upload
            if not os.path.isfile(file_path):
                return False, f"文件不存在: {file_path}"
        return True, None

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "title": "药品说明书配置",
            "properties": {
                "source_type": {
                    "type": "string",
                    "title": "数据来源",
                    "enum": ["csv_import"],
                    "enumNames": ["CSV 文件导入"],
                    "default": "csv_import",
                    "description": "目前支持 CSV 文件导入，后续将支持 API 接入",
                },
                "file_path": {
                    "type": "string",
                    "title": "CSV 文件路径",
                    "description": "上传 CSV 文件后自动填充",
                    "default": "",
                },
                "delimiter": {
                    "type": "string",
                    "title": "分隔符",
                    "enum": [",", ";", "\t", "|"],
                    "enumNames": ["逗号 (,)", "分号 (;)", "制表符 (Tab)", "竖线 (|)"],
                    "default": ",",
                },
                "encoding": {
                    "type": "string",
                    "title": "文件编码",
                    "enum": ["utf-8", "gbk", "gb2312", "utf-8-sig"],
                    "enumNames": ["UTF-8", "GBK", "GB2312", "UTF-8 BOM"],
                    "default": "utf-8",
                },
                "column_mapping": {
                    "type": "object",
                    "title": "列映射",
                    "description": "将 CSV 列名映射为标准字段（不填则自动检测）",
                    "properties": {col: {"type": "string", "title": label} for col, label in RECOGNIZED_COLUMNS.items()},
                    "default": {},
                },
                "batch_name": {
                    "type": "string",
                    "title": "批次名称",
                    "description": "本次导入的名称标识",
                    "default": "",
                },
            },
            "required": ["source_type"],
        }

    def get_default_config(self) -> dict:
        return {
            "source_type": "csv_import",
            "file_path": "",
            "delimiter": ",",
            "encoding": "utf-8",
            "column_mapping": {},
            "batch_name": "",
        }

    async def fetch_content(
        self, config: dict,
    ) -> AsyncGenerator[SourceDocument, None]:
        source_type = config.get("source_type", "csv_import")
        if source_type == "csv_import":
            async for doc in self._fetch_from_csv(config):
                yield doc

    async def _fetch_from_csv(
        self, config: dict,
    ) -> AsyncGenerator[SourceDocument, None]:
        file_path = config.get("file_path", "")
        if not file_path or not os.path.isfile(file_path):
            return

        delimiter = config.get("delimiter", ",")
        encoding = config.get("encoding", "utf-8")
        column_mapping = config.get("column_mapping", {}) or {}
        batch_name = config.get("batch_name", "")

        try:
            with open(file_path, "r", encoding=encoding) as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                if reader.fieldnames is None:
                    return

                # Auto-detect column mapping if not provided
                fieldnames = [name.strip() for name in reader.fieldnames]
                col_map = self._build_column_mapping(fieldnames, column_mapping)

                for row in reader:
                    doc = self._row_to_document(row, col_map, batch_name)
                    if doc is not None:
                        yield doc

        except (csv.Error, IOError, UnicodeDecodeError) as e:
            # Error will be caught by SourceService
            raise RuntimeError(f"CSV 解析失败: {e}")

    def _build_column_mapping(self, fieldnames: list[str], user_mapping: dict) -> dict:
        """Auto-detect column mapping based on common names."""
        # Start with user-provided mapping
        mapping = dict(user_mapping)

        # Auto-detect remaining unmapped fields
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
                continue  # Already mapped
            stripped = field.strip()
            if stripped in canonical_names:
                mapping[field] = canonical_names[stripped]

        return mapping

    def _row_to_document(
        self, row: dict, col_map: dict, batch_name: str,
    ) -> Optional[SourceDocument]:
        """Convert a CSV row to a SourceDocument."""
        # Build column value dict
        values = {}
        for csv_col, standard_col in col_map.items():
            val = row.get(csv_col, "").strip()
            if val:
                values[standard_col] = val

        if not values:
            return None

        drug_name = values.get("drug_name", "")
        if not drug_name:
            # Try first non-empty column
            for v in row.values():
                if v.strip():
                    drug_name = v.strip()
                    break
            if not drug_name:
                return None

        category = values.get("category", "西药")

        # Build structured content
        content_parts = [f"===== {drug_name} ====="]
        if values.get("generic_name"):
            content_parts.append(f"通用名: {values['generic_name']}")

        content_parts.append(f"类别: {category}")

        for key, label in SECTION_ORDER:
            if key in ("drug_name", "category", "generic_name"):
                continue
            if key in values and values[key]:
                content_parts.append(f"\n【{label}】")
                content_parts.append(values[key])

        content = "\n".join(content_parts)

        metadata = dict(values)
        metadata["batch_name"] = batch_name

        return SourceDocument(
            title=drug_name,
            content=content,
            source_url=values.get("source_url", ""),
            source_id_field=values.get("approval_number", ""),
            metadata=metadata,
        )


register_adapter(DrugLabelAdapter)
