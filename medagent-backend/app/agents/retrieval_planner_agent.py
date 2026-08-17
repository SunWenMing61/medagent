"""Deterministic multi-turn query understanding and source planning."""

from __future__ import annotations

import re
from typing import Any

from app.agents.registry import AgentDefinition, agent_registry
from app.agents.schemas import InputTriageResult, MedicalEntity, RetrievalPlan
from app.schemas.retrieval import NumericConstraint, SubQuestion


VERSION = "2.0.0"
_RANGE = re.compile(r"(?P<low>\d+(?:\.\d+)?)\s*(?:-|–|至|到)\s*(?P<high>\d+(?:\.\d+)?)\s*(?P<unit>mg|g|μg|mL|ml|mmol/L|mmHg|岁|天|周|月|年|%)?", re.I)
_NUMBER = re.compile(r"(?P<prefix>不超过|不低于|至少|至多|大于|小于|高于|低于|>=|<=|≥|≤|>|<)?\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mg|g|μg|mL|ml|mmol/L|mmHg|岁|天|周|月|年|%)?", re.I)
_ABBREVIATION = re.compile(r"\b(?:PMID\s*:?)?[A-Z][A-Z0-9-]{1,12}\b|\bPMID\s*:?\s*\d{5,10}\b", re.I)
_POPULATION = re.compile(r"儿童|婴儿|青少年|成人|老年人?|孕妇|哺乳期|肾功能不全|肝功能不全|男性|女性|pediatric|elderly|pregnan\w*", re.I)
_TIME = re.compile(r"近\s*\d+\s*(?:天|周|月|年)|过去\s*\d+\s*(?:天|周|月|年)|\d+\s*(?:天|周|月|年)(?:内|后|前)|最新|近期|长期|短期|recent|latest|within\s+\d+\s+(?:days?|weeks?|months?|years?)", re.I)
_NEGATION = re.compile(r"无|没有|不伴|不包括|排除|非|禁止|禁忌|不要|not|without|exclude|contraindicat\w*", re.I)
_PRONOUN = re.compile(r"它|这个药|该药|这个疾病|这种情况|上述|前者|后者|\bit\b|\bthat\b|\bthis drug\b", re.I)
_SPLIT = re.compile(r"[；;]|(?:并且|以及|同时|另外|还要|\band\b)", re.I)

_KNOWN = {
    "阿司匹林": ("drug", "aspirin", ["乙酰水杨酸", "aspirin"]),
    "二甲双胍": ("drug", "metformin", ["metformin"]),
    "华法林": ("drug", "warfarin", ["warfarin"]),
    "高血压": ("disease", "hypertension", ["hypertension", "HTN"]),
    "糖尿病": ("disease", "diabetes mellitus", ["diabetes", "DM"]),
    "eGFR": ("lab_indicator", "estimated glomerular filtration rate", ["估算肾小球滤过率", "eGFR"]),
    "血压": ("lab_indicator", "blood pressure", ["BP", "blood pressure"]),
    "SpO₂": ("lab_indicator", "oxygen saturation", ["SpO2", "血氧饱和度"]),
}


class RetrievalPlannerAgent:
    name = "retrieval_planner"
    version = VERSION

    def run(
        self,
        query: str,
        triage: InputTriageResult,
        session_context: dict[str, Any] | None = None,
        memory_context: list[dict[str, Any]] | None = None,
    ) -> RetrievalPlan:
        original = (query or "").strip()
        standalone, referenced_memory_ids, rewrite_reason = self._standalone(
            original, session_context or {}, memory_context or [],
        )
        normalized = re.sub(r"\s+", " ", standalone).strip()
        numeric = self._numeric_constraints(original)
        populations = list(dict.fromkeys(match.group(0) for match in _POPULATION.finditer(original)))
        times = list(dict.fromkeys(match.group(0) for match in _TIME.finditer(original)))
        negations = list(dict.fromkeys(match.group(0) for match in _NEGATION.finditer(original)))
        entities, synonyms = self._entities(original, populations, times, numeric)

        routes: list[str] = []
        if "local_rag" in triage.required_routes or "document_summary" in triage.required_routes:
            routes.append("local_knowledge_base")
        if "online_web" in triage.required_routes:
            routes.append("web_search")
        if "online_medical_source" in triage.required_routes:
            if triage.intent == "literature_search":
                routes.append("pubmed")
            elif triage.intent == "drug_information":
                routes.extend(["fda_drug_label", "msd_manual"])
        sub_questions = self._sub_questions(standalone, entities, numeric, routes)
        exact = bool(entities or numeric) or triage.intent in {"drug_information", "literature_search"}
        return RetrievalPlan(
            original_query=original,
            standalone_query=standalone,
            normalized_query=normalized,
            intent=triage.intent,
            entities=entities,
            local_queries=[normalized] if "local_knowledge_base" in routes else [],
            online_queries=[normalized] if any(item in routes for item in ("web_search", "pubmed", "fda_drug_label", "msd_manual")) else [],
            retrieval_routes=routes,
            need_exact_match=exact,
            need_recency_filter=triage.intent == "literature_search" or bool(times),
            need_guideline_priority=triage.intent in {"medical_knowledge", "symptom_consultation"},
            max_candidates_per_route=40,
            reason=rewrite_reason or "Routes follow triage; entities and all numeric/population/time/negation constraints are preserved.",
            synonyms=synonyms,
            numeric_constraints=[item.model_dump(mode="json") for item in numeric],
            population_constraints=populations,
            time_constraints=times,
            negations=negations,
            referenced_memory_ids=referenced_memory_ids,
            sub_questions=[item.model_dump(mode="json") for item in sub_questions],
        )

    @staticmethod
    def _standalone(original: str, session: dict, memory: list[dict]) -> tuple[str, list[str], str | None]:
        if not _PRONOUN.search(original):
            return original, [], None
        entity = None
        active = session.get("active_entities") or session.get("referenced_entities") or []
        if active:
            entity = active[0].get("canonical_name") or active[0].get("original_text")
        entity = entity or session.get("active_topic")
        referenced: list[str] = []
        if not entity:
            for item in memory:
                if item.get("category") in {"project_context", "explicit_user_fact"} and item.get("subject"):
                    entity = str(item["subject"])
                    if item.get("memory_id"):
                        referenced.append(str(item["memory_id"]))
                    break
        if not entity:
            return original, [], "Pronoun remained unresolved; no memory fact was invented."
        standalone = _PRONOUN.sub(str(entity), original)
        return standalone, referenced, f"Resolved an explicit reference to '{entity}' using scoped session entity context only."

    @staticmethod
    def _numeric_constraints(query: str) -> list[NumericConstraint]:
        results: list[NumericConstraint] = []
        occupied: list[tuple[int, int]] = []
        for match in _RANGE.finditer(query):
            occupied.append(match.span())
            results.append(NumericConstraint(
                name=RetrievalPlannerAgent._constraint_name(query, match.start()), operator="range",
                value=[float(match.group("low")), float(match.group("high"))],
                unit=match.group("unit"), original_text=match.group(0),
            ))
        operators = {"不超过": "<=", "至多": "<=", "小于": "<", "低于": "<", "≤": "<=", "<=": "<=", "<": "<", "不低于": ">=", "至少": ">=", "大于": ">", "高于": ">", "≥": ">=", ">=": ">=", ">": ">"}
        for match in _NUMBER.finditer(query):
            if any(start <= match.start() < end for start, end in occupied):
                continue
            prefix = (match.group("prefix") or "").strip()
            results.append(NumericConstraint(
                name=RetrievalPlannerAgent._constraint_name(query, match.start()),
                operator=operators.get(prefix, "="), value=float(match.group("value")),
                unit=match.group("unit"), original_text=match.group(0).strip(),
            ))
        return results

    @staticmethod
    def _constraint_name(query: str, start: int) -> str:
        prefix = query[max(0, start - 16):start]
        for name in ("eGFR", "SpO₂", "SpO2", "血压", "剂量", "年龄", "疗程", "体重"):
            if name.lower() in prefix.lower():
                return name
        return "numeric_condition"

    @staticmethod
    def _entities(query: str, populations: list[str], times: list[str], numeric: list[NumericConstraint]) -> tuple[list[MedicalEntity], dict[str, list[str]]]:
        entities: list[MedicalEntity] = []
        synonyms: dict[str, list[str]] = {}
        lower = query.lower()
        for text, (kind, canonical, aliases) in _KNOWN.items():
            if text.lower() in lower or any(alias.lower() in lower for alias in aliases):
                entities.append(MedicalEntity(entity_type=kind, original_text=text, canonical_name=canonical, synonyms=aliases, aliases=aliases))
                synonyms[text] = aliases
        for match in _ABBREVIATION.finditer(query):
            value = match.group(0).strip()
            if not any(item.original_text.lower() == value.lower() for item in entities):
                kind = "medical_code" if re.search(r"PMID|ICD|[A-Z]\d{2}(?:\.\d+)?", value, re.I) else "other"
                entities.append(MedicalEntity(entity_type=kind, original_text=value, canonical_name=value))
        entities.extend(MedicalEntity(entity_type="population", original_text=value, canonical_name=value) for value in populations)
        entities.extend(MedicalEntity(entity_type="time", original_text=value, canonical_name=value) for value in times)
        entities.extend(MedicalEntity(entity_type="numeric_constraint", original_text=value.original_text, canonical_name=value.name, value=value.value[0] if isinstance(value.value, list) else value.value, unit=value.unit) for value in numeric)
        return entities, synonyms

    @staticmethod
    def _sub_questions(query: str, entities: list[MedicalEntity], numeric: list[NumericConstraint], routes: list[str]) -> list[SubQuestion]:
        parts = [part.strip(" ,，。?") for part in _SPLIT.split(query) if part.strip(" ,，。?")]
        if len(parts) <= 1:
            return []
        entity_names = [item.original_text for item in entities]
        constraints = [item.original_text for item in numeric]
        return [SubQuestion(
            sub_question_id=f"sq_{index + 1}", question=part,
            target_entities=[item for item in entity_names if item.lower() in part.lower()],
            required_sources=routes,
            required_constraints=[item for item in constraints if item in part],
        ) for index, part in enumerate(parts[:5])]


retrieval_planner_agent = RetrievalPlannerAgent()
agent_registry.register(
    AgentDefinition(
        name=retrieval_planner_agent.name,
        version=VERSION,
        prompt_id="retrieval_planner",
        prompt_version="retrieval_planner_v2",
        output_schema=RetrievalPlan,
        model_setting="TRIAGE_MODEL",
    ),
    retrieval_planner_agent,
)
