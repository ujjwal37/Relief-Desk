# Relief Desk Benchmark Results (BUILD_BRIEF.md Section 9.3)

- **Dataset**: `data\synthetic\flood_v1`
- **Split**: Test split (70% = 168 messages)
- **Seed**: 42
- **Generated At**: 2026-10-11T10:52:50.096317+00:00
- **Note**: Evaluated on synthetic dataset

## Comparative Metrics Table

| Metric | Relief Desk | Baseline | Target |
|---|---|---|---|
| **Type Accuracy (%)** | **56.1** | 16.3 | >= 90% |
| **Place Ward Accuracy (%)** | **16.3** | 13.3 | >= 85% |
| **People Count Exact (%)** | **79.5** | 65.4 | Reported |
| **People Count Pm1 (%)** | **80.8** | 71.8 | Reported |
| **Vulnerable Flag Macro F1 (%)** | **59.0** | 39.4 | Reported |
| **Duplicate Precision (%)** | **71.4** | 10.0 | Beat hash clearly |
| **Duplicate Recall (%)** | **11.1** | 4.4 | Beat hash clearly |
| **Duplicate F1 (%)** | **19.2** | 6.2 | Beat hash clearly |
| **Duplicate Vs Update 3Way Accuracy (%)** | **43.9** | N/A (cannot detect updates) | Reported |
| **False Merge Rate (%)** | **0.0** | N/A | As low as possible |
| **Critical Case Top5 Share (%)** | **60.0** | N/A | Clearly above FCFS |
| **Critical Case Top10 Share (%)** | **50.0** | 20.0 | Clearly above FCFS |
| **Critical Case Mean Rank** | **10.5** | 13.5 | Lower is better |
| **Hoax Catch Rate (%)** | **100.0** | 0.0% | Reported |
| **Hoax False Flag Rate (%)** | **0.0** | 0.0% | Reported |
| **Latency P50 (Ms)** | **19.0** | < 1 ms | Reported |
| **Latency P95 (Ms)** | **25.1** | < 1 ms | Reported |
| **Cost Per 1000 (Ms)Gs Usd** | **$0.0467** | N/A | Reported |

## Failure Analysis Examples

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
