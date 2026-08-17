# Controlled multi-agent evaluations

The JSONL files in `datasets/` are synthetic regression examples. Run
`runners/run_agent_evals.py` for an actually executed offline report. This does
not measure clinical validity or live retrieval quality.

`runners/compare_abcd.py` accepts only captured, non-synthetic A/B/C/D execution
rows. The expected variants are documented in `experiment_configs.json` and in
the repository evaluation guide.

For the PDF-cleaning and governed-tool regression benchmark, run
`runners/run_pdf_tooling_evals.py`. It compares the declared legacy baseline,
cleaned structural retrieval, and parent/child table-aware retrieval, then
writes `reports/pdf_tooling_latest.json`. Its JSONL cases are synthetic and are
not a clinical or live-model benchmark.

For the layered Memory and Dense/Sparse/Exact retrieval regression benchmark,
run `runners/run_memory_retrieval_v2_evals.py`. It writes
`reports/memory_retrieval_v2_latest.json`; the cases are deterministic,
synthetic architecture regressions and do not claim clinical validity.

For the expanded medical RAG retrieval benchmark, run
`python evals/runners/run_hybrid_retrieval_comparison.py`. Version v3 contains
38 fixed multi-evidence cases across 19 medical settings, including emergency,
cardiovascular, respiratory, pediatrics, obstetrics, geriatrics, medication
safety, laboratory, imaging, oncology, infectious disease, mental health,
traditional medicine, rehabilitation, preventive care, rare disease, critical
care, nursing and clinical research. The report includes Accuracy@1,
Precision/Recall/F1@1/3/5, Hit Rate@1/3/5, MRR, nDCG@1/3/5 and MAP@1/3/5,
plus per-category results and Dense-vs-hybrid deltas. These are synthetic
engineering regression metrics, not clinical validity claims.

For prompt/model/retrieval regression decisions, use the versioned
`datasets/failure_taxonomy_v1.jsonl` suite and
`runners/run_failure_regression_evals.py`. It attributes failures to retrieval,
answer hallucination, invalid tool arguments, or incomplete tasks, fingerprints
the exact dataset, and compares a captured candidate run with a saved baseline.
See `../../docs/FAILURE_REGRESSION_EVALUATION.md` for the capture contract and CI
commands. The fixed cases are synthetic engineering regressions, not a clinical
validity benchmark.
