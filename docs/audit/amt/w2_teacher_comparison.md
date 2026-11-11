# W2 teacher comparison — w2-teacher-sample-v1

| Teacher | Status | Tracks | Chord acc | Onset F1 | OnsetPitch F1 | Offset F1 | Guitar ret | Leakage | ECE | RTF |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mt3 | unavailable | 50/50 | 0.2667 | 0.5092 | 0.5815 | 0.4436 | 0.5793 | 0.6962 | 0.7254 | 3.1641 |
| mr_mt3 | available | 50/50 | 0.2554 | 0.4222 | 0.4759 | 0.3891 | 0.4269 | 0.8251 | 0.7176 | 0.6257 |
| yourmt3 | available | 50/50 | 0.2164 | 0.5723 | 0.5904 | 0.4871 | 0.6090 | 0.5756 | 0.7631 | 0.1922 |
| musicfm | unavailable | 0/50 | — | — | — | — | — | — | — | — |

## Deltas vs MT3

| Teacher | Chord Δ | Onset Δ | OnsetPitch Δ | Offset Δ | Retention Δ | Leakage Δ | RTF ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mr_mt3 | -0.0113 | -0.0871 | -0.1056 | -0.0546 | -0.1524 | 0.1288 | 0.1977 |
| yourmt3 | -0.0503 | 0.0630 | 0.0089 | 0.0435 | 0.0298 | -0.1207 | 0.0608 |
| musicfm | — | — | — | — | — | — | — |

## Decision

**go**

yourmt3 beats MT3 on chord or guitar-filtered onset accuracy within the runtime budget.

Recommended teacher: **yourmt3**

| Teacher | Eligible | Chord Δ | Onset Δ | OnsetPitch Δ | Leakage Δ | Retention | Filter | RTF ratio |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| mr_mt3 | False | -0.0113 | -0.0871 | -0.1056 | 0.1288 | 0.4269 | True | 0.1977 |
| yourmt3 | True | -0.0503 | 0.0630 | 0.0089 | -0.1207 | 0.6090 | False | 0.0608 |

## Unavailable teachers

- **mt3**: MT3 unavailable: install the mt3 extra and download the checkpoint (pip install -e '.[mt3]' && python scripts/download_mt3_checkpoint.py)
- **musicfm**: MusicFM is an encoder, not a transcriber; the MIROS/YourMT3 decoder and its weights are required, and the MIROS weight licence is not declared. Deferred until a licensed checkpoint is provided.
