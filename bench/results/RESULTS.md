# Relief Desk Benchmark Results (BUILD_BRIEF.md Section 9.3)

- **Dataset**: `data/synthetic/flood_v1`
- **Split**: Test split (168 messages, frozen)
- **Seed**: 42
- **Generated At**: 2026-10-11T19:02:01.595650+00:00
- **Status**: Synthetic labels. The Gemini column is filled only when a live or cached model call is scored.

## Comparative Metrics Table

| Metric | Relief Desk | Baseline | Target |
|---|---|---|---|
| **Type accuracy** | **67.3%** | Keyword: 16.3% | >= 90% |
| **Place (ward) accuracy** | **100.0%** | Keyword: 13.3% | >= 85% |
| **People-count exact accuracy** | **79.5%** | Keyword: 65.4% | Reported |
| **People-count within +/- 1** | **80.8%** | Keyword: 71.8% | Reported |
| **Vulnerable-flag F1 (macro)** | **58.5%** | Keyword: 39.4% | Reported |
| **Duplicate Precision** | **95.5%** | Hash: 10.0% | Beat hash clearly |
| **Duplicate Recall** | **46.7%** | Hash: 4.4% | Beat hash clearly |
| **Duplicate F1 Score** | **62.7%** | Hash: 6.2% | Beat hash clearly |
| **Duplicate-vs-update accuracy (3-way)** | **61.2%** | N/A (cannot detect updates) | Reported |
| **False-merge rate** | **0.0%** | Hash: 0.0% | As low as possible |
| **Critical-case share in Top-5** | **60.0%** | FCFS: 0.0% | Clearly above FCFS |
| **Critical-case share in Top-10** | **60.0%** | FCFS: 20.0% | Clearly above FCFS |
| **Mean rank of critical cases** | **11.5** | FCFS: 13.5 | Lower is better |
| **Hoax/spam catch rate** | **100.0%** | 0.0% | Reported |
| **Hoax/spam false-flag rate** | **0.0%** | 0.0% | Reported |
| **Latency p50 / message** | **14.0 ms** | < 1 ms | Reported |
| **Latency p95 / message** | **27.9 ms** | < 1 ms | Reported |
| **Cost per 1,000 messages** | **$0.0465** | N/A | Reported |

## Captured Failure Analysis Examples

### Failure Case 1: Incident Type Misclassification (MSG-0102)
- **Message**: "Kainakary LP School में पानी भर गया है, तुरंत बचाव दल भेजो!"
- **Ground Truth**: `type: medical`
- **Relief Desk**: `type: rescue`
- **Analysis**: Under-specified phrasing led to 'rescue' instead of 'medical'.

### Failure Case 2: Incident Type Misclassification (MSG-0103)
- **Message**: "Champakulam School में पानी भर गया है, तुरंत बचाव दल भेजो!"
- **Ground Truth**: `type: medical`
- **Relief Desk**: `type: rescue`
- **Analysis**: Under-specified phrasing led to 'rescue' instead of 'medical'.

### Failure Case 3: Incident Type Misclassification (MSG-0106)
- **Message**: "Temple Road में पानी भर गया है, तुरंत बचाव दल भेजो!"
- **Ground Truth**: `type: medical`
- **Relief Desk**: `type: rescue`
- **Analysis**: Under-specified phrasing led to 'rescue' instead of 'medical'.

## Gemini and the keyword baseline

Gemini was not measured (no_api_key). Configured model gemini-3.8-flash, date 2026-10-11, n=168. Keyword baseline on this split: type 16.3%, ward 13.3%. Rule pipeline: type 67.3%, ward 100.0%.

Cache is on. Live calls are limited to 30 per minute. A run without an API key does not fill the Gemini column.

## Type error counts

- medical->rescue: 10
- food->rescue: 8
- shelter->rescue: 6
- info->rescue: 5
- rescue->shelter: 1
- food->medical: 1
- info->shelter: 1

Counts from this split only. Rules were not edited from these misses.

