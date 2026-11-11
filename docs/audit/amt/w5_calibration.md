# W5 calibration & recording-quality evaluation — amt-eval-v1

Tier: `mt3` · tracks: 526

## Chord-confidence calibration

Samples: 15204 · duration: 14524.2925 s · ECE: 0.7281 · accuracy: 0.2026 · mean confidence: 0.9307

| Bin | Events | Duration (s) | Avg confidence | Accuracy | Gap |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0.0–0.1 | 12 | 6.7338 | 0.0000 | 0.0000 | 0.0000 |
| 0.1–0.2 | 69 | 39.3346 | 0.1177 | 0.0000 | 0.1177 |
| 0.2–0.3 | 267 | 150.0938 | 0.3000 | 0.0000 | 0.3000 |
| 0.3–0.4 | 2 | 0.9752 | 0.3750 | 0.0000 | 0.3750 |
| 0.4–0.5 | 34 | 19.5280 | 0.4000 | 0.0000 | 0.4000 |
| 0.5–0.6 | 2019 | 1470.3804 | 0.5366 | 0.0000 | 0.5366 |
| 0.6–0.7 | 9 | 4.7833 | 0.6667 | 0.0000 | 0.6667 |
| 0.7–0.8 | 809 | 429.7781 | 0.7494 | 0.3135 | 0.4359 |
| 0.8–0.9 | 549 | 291.9677 | 0.8068 | 0.5441 | 0.2628 |
| 0.9–1.0 | 11434 | 12110.7175 | 1.0000 | 0.2188 | 0.7812 |

### By source

| Source | Events | ECE | Accuracy | Mean confidence |
| --- | ---: | ---: | ---: | ---: |
| egset12 | 150 | 0.8456 | 0.1493 | 0.9856 |
| guitar_techs | 566 | 0.6098 | 0.3829 | 0.9927 |
| guitarset | 7299 | 0.7337 | 0.1934 | 0.9271 |
| idmt_smt_guitar | 3086 | 0.7547 | 0.1944 | 0.9489 |
| rwc_p | 4103 | 0.7280 | 0.1654 | 0.8935 |

## Recording-quality gate

Tracks evaluated: 513 · accuracy threshold: 0.5000

| | High accuracy | Low accuracy | Total |
| --- | ---: | ---: | ---: |
| Accepted | 18 | 495 | 513 |
| Rejected | 0 | 0 | 0 |

Accepted mean accuracy: 0.1456 · rejected mean accuracy: —

Recommendation: **insufficient rejected or accepted tracks to evaluate the gate**

| Metric | Threshold | Accepted | Rejected | Accepted acc | Rejected acc | Separation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| score | 0.6500 | 510 | 3 | 0.1448 | 0.2696 | -0.1248 |
| score | 0.7000 | 498 | 15 | 0.1400 | 0.3304 | -0.1904 |
| score | 0.7500 | 481 | 32 | 0.1363 | 0.2839 | -0.1476 |
| score | 0.8000 | 462 | 51 | 0.1321 | 0.2676 | -0.1356 |
| score | 0.8500 | 438 | 75 | 0.1279 | 0.2484 | -0.1204 |
| score | 0.9000 | 408 | 105 | 0.1287 | 0.2109 | -0.0821 |
| score | 0.9500 | 378 | 135 | 0.1278 | 0.1952 | -0.0674 |
| score | 1.0000 | 181 | 332 | 0.0707 | 0.1863 | -0.1156 |
| snr_db | 6.0000 | 510 | 3 | 0.1448 | 0.2696 | -0.1248 |
| snr_db | 10.0000 | 481 | 32 | 0.1363 | 0.2839 | -0.1476 |
| snr_db | 15.0000 | 420 | 93 | 0.1298 | 0.2169 | -0.0871 |
| snr_db | 20.0000 | 359 | 154 | 0.1271 | 0.1886 | -0.0615 |
| clipping_ratio | 0.0000 | 418 | 95 | 0.1495 | 0.1280 | 0.0215 |
