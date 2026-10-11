# Relief Desk Benchmark Results (BUILD_BRIEF.md Section 9.3)

- **Dataset**: `data\synthetic\flood_v1`
- **Split**: Test split (70% = 168 messages)
- **Seed**: 42
- **Generated At**: 2026-10-11T12:20:25.901707+00:00
- **Status**: Verified on synthetic test set

## Comparative Metrics Table

| Metric | Relief Desk | Baseline | Target |
|---|---|---|---|
| **Type accuracy** | **56.1%** | Keyword: 16.3% | >= 90% |
| **Place (ward) accuracy** | **16.3%** | Keyword: 13.3% | >= 85% |
| **People-count exact accuracy** | **79.5%** | Keyword: 65.4% | Reported |
| **People-count within +/- 1** | **80.8%** | Keyword: 71.8% | Reported |
| **Vulnerable-flag F1 (macro)** | **59.0%** | Keyword: 39.4% | Reported |
| **Duplicate Precision** | **92.9%** | Hash: 10.0% | Beat hash clearly |
| **Duplicate Recall** | **57.8%** | Hash: 4.4% | Beat hash clearly |
| **Duplicate F1 Score** | **71.2%** | Hash: 6.2% | Beat hash clearly |
| **Duplicate-vs-update accuracy (3-way)** | **66.3%** | N/A (cannot detect updates) | Reported |
| **False-merge rate** | **0.0%** | Hash: 0.0% | As low as possible |
| **Critical-case share in Top-5** | **80.0%** | FCFS: 0.0% | Clearly above FCFS |
| **Critical-case share in Top-10** | **60.0%** | FCFS: 20.0% | Clearly above FCFS |
| **Mean rank of critical cases** | **9.3** | FCFS: 13.5 | Lower is better |
| **Hoax/spam catch rate** | **100.0%** | 0.0% | Reported |
| **Hoax/spam false-flag rate** | **0.0%** | 0.0% | Reported |
| **Latency p50 / message** | **0.7 ms** | < 1 ms | Reported |
| **Latency p95 / message** | **1.1 ms** | < 1 ms | Reported |
| **Cost per 1,000 messages** | **$0.0467** | N/A | Reported |

## Captured Failure Analysis Examples

### Failure Case 1: Incident Type Misclassification (MSG-0073)
- **Message**: "Water level 3 feet and road blocked near civil lines metro station."
- **Ground Truth**: `type: info`
- **Relief Desk**: `type: rescue`
- **Analysis**: Under-specified phrasing led to 'rescue' instead of 'info'.

### Failure Case 2: Incident Type Misclassification (MSG-0075)
- **Message**: "गंगा दर्शन व्यूप्वाइंट के पास पानी 3 फीट भर गया है, रास्ता बंद है।"
- **Ground Truth**: `type: info`
- **Relief Desk**: `type: rescue`
- **Analysis**: Under-specified phrasing led to 'rescue' instead of 'info'.

### Failure Case 3: Incident Type Misclassification (MSG-0076)
- **Message**: "Water level 3 feet and road blocked near gandhi nagar metro station."
- **Ground Truth**: `type: info`
- **Relief Desk**: `type: rescue`
- **Analysis**: Under-specified phrasing led to 'rescue' instead of 'info'.

