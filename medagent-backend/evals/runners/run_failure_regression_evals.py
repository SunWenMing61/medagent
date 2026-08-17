"""Score captured fixed-suite runs and compare them with a baseline report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.evaluation.failure_taxonomy import (
    EvaluationDataError,
    compare_reports,
    evaluate_run,
    load_captured_run,
    load_fixed_dataset,
    read_report,
)

DEFAULT_DATASET = BACKEND_ROOT / "evals" / "datasets" / "failure_taxonomy_v1.jsonl"


def _write_or_print(value: dict, output: Path | None) -> None:
    rendered = json.dumps(value, ensure_ascii=False, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic MedAgent failure taxonomy regression evaluator"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate and fingerprint the fixed dataset")
    validate.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)

    score = sub.add_parser("score", help="score a captured JSONL execution")
    score.add_argument("captured_jsonl", type=Path)
    score.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    score.add_argument("--run-id", required=True)
    score.add_argument("--config", type=Path, help="JSON metadata: prompt/model/retrieval versions")
    score.add_argument("--output", type=Path)

    compare = sub.add_parser("compare", help="compare candidate report to a saved baseline")
    compare.add_argument("baseline_json", type=Path)
    compare.add_argument("candidate_json", type=Path)
    compare.add_argument("--output", type=Path)
    compare.add_argument("--fail-on-regression", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "validate":
            bundle = load_fixed_dataset(args.dataset)
            _write_or_print({
                "valid": True,
                "dataset_version": bundle.dataset_version,
                "dataset_sha256": bundle.dataset_sha256,
                "case_count": len(bundle.cases),
            }, None)
            return
        if args.command == "score":
            configuration = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
            report = evaluate_run(
                load_fixed_dataset(args.dataset),
                load_captured_run(args.captured_jsonl),
                run_id=args.run_id,
                configuration=configuration,
            )
            _write_or_print(report, args.output)
            return
        comparison = compare_reports(read_report(args.baseline_json), read_report(args.candidate_json))
        _write_or_print(comparison, args.output)
        if args.fail_on_regression and comparison["regression"]:
            raise SystemExit(2)
    except EvaluationDataError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()

