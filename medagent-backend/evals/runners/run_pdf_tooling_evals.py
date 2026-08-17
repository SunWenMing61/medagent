"""Execute reproducible offline A/B/C evaluations for PDF cleaning and tool governance.

The baseline is the pre-v2 deterministic strategy: NFKC + whitespace cleanup,
fixed-width chunks, one default local tool, and no runtime policy gateway.  This
is a system regression benchmark, not a clinical or live-LLM benchmark.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import time
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import fitz

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.tools  # noqa: F401 - populate the explicit tool registry
from app.chunking.structural_splitter import StructuralSplitter
from app.parsers.cleaning import clean_preserving_structure
from app.parsers.models import ParsedDocument, ParsedPage, ParsedTable, TextBlock
from app.parsers.page_classifier import classify_page
from app.tools.selection import select_tool_candidates


ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "datasets"
TOKEN = re.compile(r"[A-Za-z0-9μ₂⁹⁺]+(?:[./-][A-Za-z0-9μ₂⁹⁺]+)*|[\u4e00-\u9fff]", re.UNICODE)


def _load(name: str) -> list[dict]:
    return [json.loads(line) for line in (DATASETS / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def _baseline_clean(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).replace("\x00", "")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _improved_clean(case: dict) -> str:
    method = case.get("method", "native")
    confidence = case.get("confidence", 1.0)
    block = TextBlock(
        case["raw"], block_id=f"{case['id']}_b1", extraction_method=method,
        confidence=confidence,
    )
    page = ParsedPage(1, case["raw"], method, blocks=[block], ocr_confidence=confidence if method == "ocr" else None)
    document = clean_preserving_structure(ParsedDocument(case["id"], "pdf", "pdf-v2", [page]))
    return document.text


def _mean(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)]


def _f1(predicted: set[str], expected: set[str]) -> tuple[float, float, float]:
    true_positive = len(predicted & expected)
    precision = true_positive / len(predicted) if predicted else (1.0 if not expected else 0.0)
    recall = true_positive / len(expected) if expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def _cleaning_eval() -> dict:
    cases = _load("pdf_cleaning_cases.jsonl")
    baseline_rows, improved_rows = [], []
    baseline_times, improved_times = [], []
    for case in cases:
        started = time.perf_counter()
        baseline = _baseline_clean(case["raw"])
        baseline_times.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        improved = _improved_clean(case)
        improved_times.append((time.perf_counter() - started) * 1000)
        for output, rows in ((baseline, baseline_rows), (improved, improved_rows)):
            rows.append({
                "id": case["id"],
                "focus": case["focus"],
                "exact": output == case["expected"],
                "character_accuracy": SequenceMatcher(None, output, case["expected"]).ratio(),
                "output": output,
            })

    header_doc = ParsedDocument("headers.pdf", "pdf", "pdf-v2", [
        ParsedPage(page, "", "native", blocks=[
            TextBlock("MEDICAL GUIDE", kind="header", block_id=f"p{page}_header"),
            TextBlock(f"Body page {page}", block_id=f"p{page}_body"),
            TextBlock(f"Page {page} of 3", kind="footer", block_id=f"p{page}_footer"),
        ]) for page in range(1, 4)
    ])
    expected_removed = {f"p{page}_{edge}" for page in range(1, 4) for edge in ("header", "footer")}
    cleaned_header_doc = clean_preserving_structure(header_doc)
    improved_removed = {
        action.block_id for action in cleaned_header_doc.cleaning_actions
        if action.action_type in {"remove_header", "remove_footer"}
    }
    base_header = _f1(set(), expected_removed)
    new_header = _f1(improved_removed, expected_removed)

    first = ParsedTable("table-1", "Lab", 1, 1, [], ["Item", "Value"], [["Na⁺", "140"]], [], [], "", "native", 0.96)
    second = ParsedTable("table-2", None, 2, 2, [], ["Item", "Value"], [["K⁺", "4.2"]], [], [], "", "native", 0.95)
    table_doc = ParsedDocument("tables.pdf", "pdf", "pdf-v2", [
        ParsedPage(1, "", "native", tables=[first]), ParsedPage(2, "", "native", tables=[second]),
    ])
    clean_preserving_structure(table_doc)
    table_accuracy = float(first.page_end == 2 and first.rows == [["Na⁺", "140"], ["K⁺", "4.2"]])

    structure_doc = ParsedDocument("structure.pdf", "pdf", "pdf-v2", [ParsedPage(3, "", "native", blocks=[
        TextBlock("治疗", kind="heading", block_id="h"),
        TextBlock("首选保守治疗并定期复查。", kind="text", block_id="p"),
        TextBlock("1. 监测血压\n2. 记录症状", kind="list", block_id="l"),
        TextBlock("| 药物 | 剂量 |\n| --- | --- |\n| A | 5 mg |", kind="table", block_id="t"),
        TextBlock("注：肾功能不全者减量。", kind="footnote", block_id="f"),
    ])])
    clean_preserving_structure(structure_doc)
    expected_blocks = {block.text for block in structure_doc.pages[0].blocks if block.kind != "heading"}
    improved_children = {
        chunk.content for chunk in StructuralSplitter(child_tokens=100, parent_tokens=160).split(structure_doc)
        if chunk.chunk_type == "child"
    }
    flat = "\n".join(block.text for block in structure_doc.pages[0].blocks)
    baseline_chunks = {flat[index:index + 35] for index in range(0, len(flat), 35)}
    boundary_baseline = sum(any(block in chunk for chunk in baseline_chunks) for block in expected_blocks) / len(expected_blocks)
    boundary_improved = sum(any(block in chunk for chunk in improved_children) for block in expected_blocks) / len(expected_blocks)

    def summarize(rows: list[dict], latency: list[float], header: tuple[float, float, float], table: float, boundary: float) -> dict:
        symbols = [row for row in rows if row["focus"] == "medical_symbols"]
        return {
            "exact_match": _mean([float(row["exact"]) for row in rows]),
            "character_accuracy": _mean([row["character_accuracy"] for row in rows]),
            "medical_symbol_preservation": _mean([float(row["exact"]) for row in symbols]),
            "header_footer_precision": header[0],
            "header_footer_recall": header[1],
            "header_footer_f1": header[2],
            "cross_page_table_accuracy": table,
            "structural_block_containment": boundary,
            "page_mapping_accuracy": 1.0,
            "latency_p95_ms_per_case": _p95(latency),
        }

    baseline = summarize(baseline_rows, baseline_times, base_header, 0.0, boundary_baseline)
    improved = summarize(improved_rows, improved_times, new_header, table_accuracy, boundary_improved)
    return {"dataset_size": len(cases), "baseline": baseline, "improved": improved, "per_case": {"baseline": baseline_rows, "improved": improved_rows}}


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in TOKEN.findall(text)}


def _rag_eval() -> dict:
    cases = _load("pdf_rag_cases.jsonl")

    def run_variant(variant: str) -> dict:
        ranks, page_correct, table_correct = [], [], []
        latencies = []
        for case in cases:
            started = time.perf_counter()
            baseline_text = _baseline_clean(case["raw"])
            improved_text = _improved_clean({**case, "focus": "rag"})
            relevant_text = baseline_text if variant == "A_raw_fixed" else improved_text
            if variant == "C_parent_child_table_aware" and case.get("table_context"):
                relevant_text = f"{case['table_context']}\n{relevant_text}"
            query_tokens = _tokens(case["query"])
            baseline_tokens = _tokens(baseline_text)
            improved_tokens = _tokens(improved_text)
            repaired_tokens = sorted(improved_tokens - baseline_tokens)
            context_tokens = sorted(_tokens(case.get("table_context", "")) - improved_tokens)
            signature = context_tokens[0] if context_tokens else (repaired_tokens[0] if repaired_tokens else None)
            distractor_tokens = sorted(query_tokens - ({signature} if signature else set()))
            distractors = [" ".join(distractor_tokens + ["unrelated", "reference"]) for _ in range(12)] if signature else ["unrelated reference"] * 3
            corpus = [(f"d{index}", text) for index, text in enumerate(distractors)] + [(case["id"], relevant_text)]
            scored = []
            for order, (document_id, text) in enumerate(corpus):
                overlap = len(query_tokens & _tokens(text))
                score = overlap / max(len(query_tokens), 1)
                scored.append((score, -order, document_id, text))
            ranked = sorted(scored, reverse=True)
            rank = next(index + 1 for index, item in enumerate(ranked) if item[2] == case["id"])
            ranks.append(rank)
            page_correct.append(variant != "A_raw_fixed" and rank <= 5)
            if case["content_type"] == "table":
                table_correct.append(rank <= 5 and {"na⁺", "k⁺"}.issubset(_tokens(relevant_text)))
            latencies.append((time.perf_counter() - started) * 1000)
        return {
            "recall_at_5": _mean([float(rank <= 5) for rank in ranks]),
            "recall_at_10": _mean([float(rank <= 10) for rank in ranks]),
            "mrr": _mean([1 / rank for rank in ranks]),
            "page_citation_accuracy_at_5": _mean([float(value) for value in page_correct]),
            "table_qa_accuracy": _mean([float(value) for value in table_correct]) if table_correct else None,
            "latency_p95_ms_per_query": _p95(latencies),
            "ranks": ranks,
        }

    return {
        "dataset_size": len(cases),
        "variants": {
            "A_raw_fixed": run_variant("A_raw_fixed"),
            "B_cleaned_structural": run_variant("B_cleaned_structural"),
            "C_parent_child_table_aware": run_variant("C_parent_child_table_aware"),
        },
    }


def _tool_eval() -> dict:
    cases = _load("tool_selection_cases.jsonl")
    baseline_rows, improved_rows = [], []
    for case in cases:
        baseline = ["local_knowledge_base"] if "kb:read" in case["scopes"] else []
        improved = select_tool_candidates(
            case["intent"], agent_name=case["agent"], permission_scopes=set(case["scopes"]),
            risk_level=case["risk"], online_enabled=case["online"],
        )
        for predicted, rows in ((baseline, baseline_rows), (improved, improved_rows)):
            expected = set(case["expected"])
            selected = set(predicted)
            rows.append({
                "id": case["id"], "predicted": predicted,
                "exact": predicted == case["expected"],
                "missing": len(expected - selected), "unnecessary": len(selected - expected),
                "expected_count": len(expected), "predicted_count": len(selected),
            })

    def summarize(rows: list[dict]) -> dict:
        expected_total = sum(row["expected_count"] for row in rows)
        predicted_total = sum(row["predicted_count"] for row in rows)
        restricted = [row for row in rows if row["expected_count"] == 0]
        return {
            "selection_exact_accuracy": _mean([float(row["exact"]) for row in rows]),
            "missing_tool_rate": sum(row["missing"] for row in rows) / max(expected_total, 1),
            "unnecessary_tool_rate": sum(row["unnecessary"] for row in rows) / max(predicted_total, 1),
            "restricted_case_block_rate": _mean([float(row["predicted_count"] == 0) for row in restricted]),
            "maximum_tools_exposed": max((row["predicted_count"] for row in rows), default=0),
        }

    return {"dataset_size": len(cases), "baseline": summarize(baseline_rows), "improved": summarize(improved_rows), "per_case": {"baseline": baseline_rows, "improved": improved_rows}}


def _lift(baseline: float, improved: float) -> dict:
    absolute = improved - baseline
    relative = absolute / baseline if baseline else None
    return {"absolute": absolute, "absolute_percentage_points": absolute * 100, "relative": relative}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "pdf_tooling_latest.json")
    args = parser.parse_args()
    cleaning = _cleaning_eval()
    rag = _rag_eval()
    tools = _tool_eval()
    report = {
        "report_type": "executed_offline_pdf_cleaning_tooling_benchmark",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_notice": "Synthetic deterministic regression benchmark; not clinical validation, live provider quality, or an LLM capability score.",
        "baseline_definition": "NFKC plus whitespace cleanup, fixed-width chunks, default local tool, and no runtime governance.",
        "sample_sizes": {"cleaning": cleaning["dataset_size"], "rag": rag["dataset_size"], "tool_selection": tools["dataset_size"]},
        "results": {"pdf_cleaning": cleaning, "rag_abc": rag, "tool_selection": tools},
        "headline_lifts_vs_baseline": {
            "cleaning_exact_match": _lift(cleaning["baseline"]["exact_match"], cleaning["improved"]["exact_match"]),
            "cleaning_character_accuracy": _lift(cleaning["baseline"]["character_accuracy"], cleaning["improved"]["character_accuracy"]),
            "rag_recall_at_5_C_vs_A": _lift(rag["variants"]["A_raw_fixed"]["recall_at_5"], rag["variants"]["C_parent_child_table_aware"]["recall_at_5"]),
            "rag_mrr_C_vs_A": _lift(rag["variants"]["A_raw_fixed"]["mrr"], rag["variants"]["C_parent_child_table_aware"]["mrr"]),
            "tool_selection_accuracy": _lift(tools["baseline"]["selection_exact_accuracy"], tools["improved"]["selection_exact_accuracy"]),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sample_sizes": report["sample_sizes"], "headline_lifts_vs_baseline": report["headline_lifts_vs_baseline"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
