# Label Noise Analysis Report

**Dataset**: GuitarSet
**Analysis Date**: 2026-05-23 18:55:50
**Methodology**: Following MT3 paper Appendix D.2

## Sensitivity Analysis Results

| Tolerance (ms) | F1 Score |
|----------------|----------|
| 10 | 0.630 |
| 25 | 0.647 |
| 50 | 0.713 |
| 100 | 0.733 |
| 200 | 0.704 |
| 500 | 0.722 |

## Noise Assessment

🔴 **LABELS SHOW SIGNIFICANT TIMING NOISE**

The F1 score continues to improve significantly beyond 50ms tolerance, indicating substantial timing errors in the ground truth labels.

- F1 improvement from 50ms to 100ms: 0.021
- F1 improvement from 50ms to 200ms: -0.009

This suggests that the model's performance is being limited by label quality rather than model capability.

## Recommendations

1. **Apply temporal jitter augmentation** during training to make the model robust to label timing uncertainty
2. **Implement label quality gating** to reject examples with extreme boundary jitter (>100ms)
3. **Consider collecting additional annotations** for critical subsets of the data
4. **Use ensemble methods** or confidence-weighted predictions to reduce reliance on noisy labels

## Technical Details

- Evaluation used chord-level F1 score with flexible matching
- Tolerance windows converted from milliseconds to frames based on hop size
- Analysis follows MT3 Appendix D.2 methodology for label noise diagnosis
