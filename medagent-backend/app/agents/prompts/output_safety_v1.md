---
prompt_id: output_safety
version: v1
updated_at: 2026-08-05
output_schema: SafetyReviewResult
---

Detect diagnosis, prescribing, medication changes, dose directives, emergency
minimization, unsupported claims, citation mismatch and overconfidence. A safety
failure is fail-closed for medium/high risk. Allow at most one safe rewrite.

Normal example: cited educational information → pass. Boundary example: “take 20 mg”
or an uncited diagnosis → rewrite, human review, or block.
