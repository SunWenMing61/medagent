"""Run the fixed dense-vs-hybrid retrieval A/B suite and persist a JSON report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.evaluation.hybrid_retrieval_comparison import run_hybrid_retrieval_comparison


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=None)
    parser.add_argument(
        "--output",
        default="evals/reports/hybrid_retrieval_comparison_latest.json",
    )
    args = parser.parse_args()
    report = run_hybrid_retrieval_comparison(args.dataset) if args.dataset else run_hybrid_retrieval_comparison()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
