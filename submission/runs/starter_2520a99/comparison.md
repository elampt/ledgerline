| Measure (24 labelled dev documents) | unmodified starter | starter, as run | starter, logic only | mine (d4eec74) |
|---|---|---|---|---|
| Documents that failed (processing_error) | 24 of 24 | 4 of 24 | 1 of 24 | 0 of 24 |
| **Needed review, routed ready (missed)** | n/a: no document was written, so none reached AP at all | **2 of 13** (dev_015, dev_019) | **2 of 13** (dev_015, dev_019) | **0 of 13**  |
| Routed to review without needing it (extra) | 0 | 2 (dev_002, dev_020) | 1 (dev_020) | 0 |
| Review reasons exactly right | 0 of 24 | 18 of 24 | 21 of 24 | 24 of 24 |
| Required approvals right | 0 of 24 | 17 of 24 | 20 of 24 | 24 of 24 |
| Field accuracy, starter's way (failures dropped, leaked examples kept) | n/a (no document processed) | 239/240 = 99.6% | 275/276 = 99.6% | 287/288 = 99.7% |
| Field accuracy, honest (failures count, dev_001-003 removed) | 0/252 = 0.0% | 215/252 = 85.3% | 239/252 = 94.8% | 251/252 = 99.6% |
| LLM calls per document | 0.0 | 1.7 | 1.9 | 1.0 |
| Output tokens per document (mean) | 0 | 7,066 | 8,233 | 543 |
| LLM time per document, p50 / p95 / max | 0.0 s / 0.0 s / 0.0 s | 46.9 s / 67.3 s / 79.5 s | 48.6 s / 67.3 s / 79.5 s | 3.8 s / 10.5 s / 15.1 s |
| Cost per document (mean, $0.75/$3.75 per M, no cache discount) | ₹0.00 | ₹3.04 | ₹3.53 | ₹0.65 |
