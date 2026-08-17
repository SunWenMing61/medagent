"""Aggregate captured, real A/B/C/D experiment records without fabricating runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


METRICS = (
    "answer_correctness", "faithfulness", "citation_correctness", "citation_completeness",
    "safety_recall", "no_answer_accuracy", "tokens", "agent_calls", "latency_ms",
    "cost_usd", "human_intervention",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare captured real A/B/C/D experiment results")
    parser.add_argument("captured_jsonl", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.captured_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise SystemExit("Captured input is empty; comparison results will not be fabricated.")
    grouped: dict[str, list[dict]] = {name: [] for name in "ABCD"}
    for row in rows:
        variant = row.get("variant")
        if variant not in grouped:
            raise SystemExit(f"Unknown variant: {variant!r}")
        if not row.get("executed_at") or row.get("synthetic") is True:
            raise SystemExit("Every row must identify a real executed_at value and must not be synthetic.")
        grouped[variant].append(row)
    missing = [name for name, values in grouped.items() if not values]
    if missing:
        raise SystemExit(f"Missing captured variants: {', '.join(missing)}")
    report = {"report_type": "captured_real_abcd_comparison", "variants": {}}
    for variant, values in grouped.items():
        report["variants"][variant] = {
            "sample_size": len(values),
            "metrics": {
                metric: sum(float(row[metric]) for row in values) / len(values)
                for metric in METRICS if all(metric in row for row in values)
            },
        }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
