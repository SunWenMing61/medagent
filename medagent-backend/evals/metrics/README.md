# Metric definitions

- Triage: intent/risk accuracy, emergency recall and precision, clarification accuracy.
- Planning: exact route accuracy and preservation of numeric/abbreviation terms.
- Evidence: sufficiency accuracy and unsupported/unauthorized rejection accuracy.
- Answer: citation correctness and completeness for structured claims.
- Safety: expected safety disposition accuracy.
- End-to-end: task success and average bounded Agent/Tool calls.
- Medical retrieval: Accuracy@1, Precision/Recall/F1@K, Hit Rate@K, MRR,
  nDCG@K and MAP@K. Retrieval labels may contain multiple relevant evidence
  items with graded relevance; metrics are macro-averaged across cases and are
  also reported per medical category.

`Hit Rate@K` is the fraction of questions whose first K results contain at
least one relevant evidence item. `MRR` is the mean reciprocal rank of the
first relevant item. `nDCG@K` rewards placing highly relevant evidence earlier,
while `MAP@K` rewards retrieving all labelled evidence in a useful order.

Clinical benchmarking additionally requires expert-labelled, representative
data and confidence intervals; the included synthetic cases must not be used as
a clinical performance claim.
