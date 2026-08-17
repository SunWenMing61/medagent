"""Rule-first, zero-token complexity routing for the hybrid Agent runtime."""

from __future__ import annotations

import re
import time
from collections.abc import Mapping

from app.core.config import settings
from app.hybrid.contracts import ComplexityLevel, ExecutionMode, RouterDecision


class ComplexityRouter:
    """Route from observable signals without storing private model reasoning.

    High-confidence requests are decided entirely by rules.  Ambiguous requests
    stay on the bounded ReAct path with escalation enabled; a future small model
    can be inserted behind the same contract without changing callers.
    """

    _multi_connectors = re.compile(r"(?:并且|同时|分别|比较|对比|综合|权衡|以及|形成.+方案|and\s+then|compare|versus)", re.I)
    _rag_terms = re.compile(r"(?:指南|证据|文献|研究|知识库|出处|引用|共识|病历|最近.+次|guide|evidence|paper|source|record)", re.I)
    _private_terms = re.compile(r"(?:我的|患者|病历|检查结果|最近.+(?:血压|血糖|HbA1c)|既往|当前用药|my\s+(?:record|result)|patient)", re.I)
    _cross_domain = re.compile(r"(?:药物.+(?:检验|影像|疾病|手术)|疾病.+(?:药物|检查|治疗)|用药.+指南|drug.+(?:lab|disease)|disease.+drug)", re.I)
    _constraint_terms = re.compile(r"(?:孕妇|妊娠|儿童|老人|老年|肾|肝|过敏|剂量|疗程|禁忌|相互作用|既往史|合并用药|监测|pregnan|child|renal|hepatic|dose|contraind)", re.I)
    _safety_terms = re.compile(r"(?:急救|急诊|胸痛|呼吸困难|昏迷|自杀|大量服用|出血|中毒|停药|换药|加量|减量|emergency|suicid|overdose)", re.I)
    _tool_terms = re.compile(r"(?:搜索|检索|查询|计算|知识图谱|网页|查表|数据库|病历|检查结果|search|lookup|calculate|graph|database)", re.I)
    _dependency_terms = re.compile(r"(?:先.+再|根据.+结合|依赖|基于.+结果|趋势.+建议|then|depends?\s+on|based\s+on)", re.I)
    _simple_definition = re.compile(r"^(?:请)?(?:简单)?(?:解释|介绍|说明)?\s*(?:一下)?[^，；;,.!?！？]{1,36}(?:是什么|的定义|什么意思|有哪些常见表现)?[？?。]?$", re.I)

    def __init__(self, *, direct_threshold: float | None = None, multi_agent_threshold: float | None = None) -> None:
        self.direct_threshold = float(settings.HYBRID_DIRECT_THRESHOLD if direct_threshold is None else direct_threshold)
        self.multi_agent_threshold = float(settings.HYBRID_MULTI_AGENT_THRESHOLD if multi_agent_threshold is None else multi_agent_threshold)
        if not 0 <= self.direct_threshold < self.multi_agent_threshold <= 1:
            raise ValueError("Hybrid routing thresholds must satisfy 0 <= direct < multi_agent <= 1")

    def route(
        self,
        query: str,
        *,
        conversation_summary: str = "",
        metadata: Mapping[str, object] | None = None,
    ) -> RouterDecision:
        started = time.perf_counter()
        text = (query or "").strip()
        meta = dict(metadata or {})
        clauses = [item for item in re.split(r"[，。；;,.!?！？\n]+", text) if item.strip()]
        connector_count = len(self._multi_connectors.findall(text))
        constraint_count = len(self._constraint_terms.findall(text))
        tool_count = len(self._tool_terms.findall(text))
        requires_rag = bool(self._rag_terms.search(text) or meta.get("requires_rag"))
        requires_private = bool(self._private_terms.search(text) or meta.get("requires_private_data"))
        tool_dependency = bool(self._dependency_terms.search(text) or meta.get("tool_dependency"))
        cross_domain = bool(self._cross_domain.search(text) or meta.get("cross_domain"))
        safety = bool(self._safety_terms.search(text) or meta.get("safety_complexity"))
        subtask_count = max(1, len(clauses) + connector_count)
        intent_count = max(1, 1 + connector_count + int(cross_domain))
        estimated_tools = max(tool_count, int(requires_rag), int(requires_private))
        cross_agent = bool(meta.get("cross_agent_requirement") or (subtask_count >= 4 and (cross_domain or constraint_count >= 2)) or tool_dependency)
        context_complexity = min(1.0, (len(text) / 500) + (len(conversation_summary) / 1200))
        signal_values = {
            "intent_count": min(1.0, (intent_count - 1) / 3),
            "subtask_count": min(1.0, (subtask_count - 1) / 5),
            "estimated_tool_count": min(1.0, estimated_tools / 3),
            "tool_dependency": float(tool_dependency),
            "requires_rag": float(requires_rag),
            "requires_private_data": float(requires_private),
            "cross_domain": float(cross_domain),
            "cross_agent_requirement": float(cross_agent),
            "context_complexity": context_complexity,
            "constraint_count": min(1.0, constraint_count / 4),
            "multi_turn_dependency": 0.75 if conversation_summary.strip() else 0.0,
            "safety_complexity": float(safety),
        }
        weights = {
            "intent_count": .08, "subtask_count": .15, "estimated_tool_count": .08,
            "tool_dependency": .13, "requires_rag": .08, "requires_private_data": .08,
            "cross_domain": .10, "cross_agent_requirement": .13, "context_complexity": .04,
            "constraint_count": .07, "multi_turn_dependency": .03, "safety_complexity": .10,
        }
        score = min(1.0, sum(signal_values[name] * weight for name, weight in weights.items()))
        # A true definition request with no data/tool requirements should not be
        # pushed into ReAct solely because it contains medical terminology.
        simple_definition = bool(self._simple_definition.match(text)) and not any((requires_rag, requires_private, tool_count, tool_dependency, safety))
        if simple_definition:
            score = min(score, self.direct_threshold * .45)
        elif requires_rag or requires_private or estimated_tools:
            score = max(score, self.direct_threshold + .02)
        # Explicit dependent/cross-agent requests are never under-routed because
        # their text happens to be short.
        if cross_agent and (tool_dependency or subtask_count >= 4):
            score = max(score, self.multi_agent_threshold + .05)
        score = round(score, 4)
        if score < self.direct_threshold:
            mode, level = ExecutionMode.DIRECT, ComplexityLevel.VERY_SIMPLE if score < self.direct_threshold / 2 else ComplexityLevel.SIMPLE
        elif score < self.multi_agent_threshold:
            mode, level = ExecutionMode.REACT, ComplexityLevel.SIMPLE if score < (self.direct_threshold + self.multi_agent_threshold) / 2 else ComplexityLevel.MEDIUM
        else:
            mode, level = ExecutionMode.MULTI_AGENT, ComplexityLevel.COMPLEX if score < .75 else ComplexityLevel.VERY_COMPLEX
        nearest = min(abs(score - self.direct_threshold), abs(score - self.multi_agent_threshold))
        confidence = round(min(.99, .62 + nearest * 1.8 + (.12 if simple_definition or cross_agent else 0)), 4)
        active = [name for name, value in signal_values.items() if value >= .5]
        return RouterDecision(
            execution_mode=mode,
            complexity_level=level,
            score=score,
            confidence=confidence,
            signals={name: round(value, 4) for name, value in signal_values.items()},
            decision_summary=f"score={score:.2f}; active_signals={','.join(active) or 'none'}; selected={mode.value}",
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            input_tokens=0,
            output_tokens=0,
            escalation_enabled=bool(settings.REACT_ALLOW_ESCALATION and mode == ExecutionMode.REACT),
            route_source="rules" if confidence >= settings.HYBRID_ROUTER_LOW_CONFIDENCE else "rules_ambiguous_safe_react",
        )


complexity_router = ComplexityRouter()
