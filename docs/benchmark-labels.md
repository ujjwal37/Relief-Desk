# Benchmark type labels: why test differs from dev and train

Written 2026-10-12. This analysis used only the generator (`scripts/generate_dataset.py`, `scripts/extend_bench_train.py`), `labels.jsonl` and `split.json`. No test predictions were read, and the intake prompt was **not** changed because of it.

## What the labels contain

| Split | Reports with a type label | single_incident | duplicate_of | not_duplicate (near miss) |
|---|---|---|---|---|
| dev | 72 | 72 | 0 | 0 |
| train | 200 | 192 | 4 | 0 (+4 update_of) |
| test | 98 | 28 | **45** | 25 |

## The convention

`generate_dataset.py` section 2 ("True Duplicates") writes each `duplicate_of` message from one of three generic templates:

- "Another report from {landmark}: roads completely submerged, people on second floor needing help."
- "same here near {landmark}, pani bohot zyada hai log phase hue hain"
- the Hindi equivalent

Its `ground_truth.type` is then copied from the incident it duplicates (`"type": inc["type"]`). The template is the same whether that incident was food, medical, shelter, info or rescue.

So for 45 of the 98 typed test reports, the right type cannot be read from the text. It is only known by linking the report to the earlier incident, which is the dedupe step's job, not intake's. dev has no duplicates at all, which is why dev scores 100% and test does not.

## Consequence

- **Text-only ceiling on test.** The 53 reports that state their need could all be right. For the 45 duplicates, the best text-only answer is a constant: "rescue" matches 14 of them. That gives (53 + 14) / 98 ≈ **68%**. The 85% target is not reachable for any reader of the text alone.
- **No precedence rule exists.** The generator spec has no primary-need precedence rule that the prompt fails to state, so there was nothing honest to add to the prompt.
- **Benchmark output now splits type accuracy.** `bench/gemini_eval.py` reports `type_by_label_type` and `type_accuracy_need_stated_pct`, which covers every label kind except `duplicate_of`. Read those next to the headline number.
- **Possible follow-up.** Score duplicates after dedupe, with each duplicate inheriting the type of the request it merges into. That would measure the pipeline as it really runs, but it has not been built yet.
