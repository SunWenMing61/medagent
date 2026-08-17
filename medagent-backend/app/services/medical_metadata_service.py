"""Deterministic, dependency-free metadata extraction for exact medical retrieval.

This is deliberately conservative: extracted values improve candidate recall but never
become medical evidence by themselves. The original chunk remains the cited source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_CODE = re.compile(r"\b(?:ICD-?10[:： ]*)?[A-Z][0-9]{2}(?:\.[0-9A-Z]{1,4})?\b|\bNCT\d{8}\b|\bPMID[:： ]*\d{5,9}\b", re.I)
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9-]{2,}|[\u4e00-\u9fff]{2,8}")
_DRUG_SUFFIX = re.compile(r"(?:mab|nib|pril|sartan|statin|cillin|mycin|azole)$", re.I)
_DRUG_CN = re.compile(r"[\u4e00-\u9fff]{1,8}(?:单抗|西林|霉素|沙坦|普利|他汀|唑|胺|片|胶囊|注射液)")
_DISEASE_CN = re.compile(r"[\u4e00-\u9fff]{1,10}(?:病|癌|瘤|炎|综合征|感染|衰竭|高血压)")
_STOPWORDS = {
    "this", "that", "with", "from", "have", "were", "which", "进行", "可以", "以及", "患者",
    "治疗", "研究", "结果", "相关", "使用", "对于", "一种", "表明", "临床",
}


@dataclass(frozen=True, slots=True)
class MedicalMetadata:
    medical_entities: list[str]
    normalized_drug_names: list[str]
    disease_names: list[str]
    medical_codes: list[str]
    keywords: list[str]


def _unique(values, limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw).strip(" ,.;:：()[]{}")
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
        if len(result) >= limit:
            break
    return result


def extract_medical_metadata(content: str) -> MedicalMetadata:
    content = content or ""
    codes = _unique(_CODE.findall(content), 20)
    chinese_drugs = _DRUG_CN.findall(content)
    latin_drugs = [word for word in _WORD.findall(content) if _DRUG_SUFFIX.search(word)]
    drugs = _unique([*chinese_drugs, *latin_drugs], 20)
    diseases = _unique(_DISEASE_CN.findall(content), 20)
    keywords = _unique(
        (word for word in _WORD.findall(content) if word.casefold() not in _STOPWORDS),
        40,
    )
    entities = _unique([*drugs, *diseases, *codes], 40)
    return MedicalMetadata(entities, drugs, diseases, codes, keywords)
