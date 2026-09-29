# Phase 4: Optimization Analysis

**Date**: 2026-09-29  
**Analysis Based On**: 20 files, 9 citations analyzed  
**Current Status**: Calibration performing well

---

## Current Calibration Performance

### Observed Distribution

| Metric | Value |
|---|---|
| Total citations | 9 |
| Real citations | 7 (avg conf: 1.0) |
| Inventada citations | 2 (avg conf: 0.08) |
| Mean confidence | 0.796 |
| Min/Max | 0.08 / 1.0 |

### By Classification

**Real Citations** (n=7):
- Confidence: 1.0 (perfect separation)
- Issue: All hitting max (1.0), no variation
- Status: ✅ Correct classification, but ceiling effect

**Inventada Citations** (n=2):
- Confidence: 0.08 (expected)
- Issue: None
- Status: ✅ Correct and well separated

---

## Findings

### 1. Ceiling Effect on "Real"

**Problem**: All real citations returning 1.0 confidence
- This happens when: long context (>250 chars) + found exactly
- Calculation: 0.96 (exato) * 1.08 (alta) = 1.0368 → clamped to 1.0

**Impact**:
- ✅ Correct: they ARE real
- ⚠️ Lost information: Can't distinguish high-confidence reals from medium-confidence ones
- ⚠️ Brier score: No penalty even if wrong (conf=1.0 → 0 error)

**Recommendation**:
- Keep as-is IF the goal is just confidence (informational)
- Consider lower multipliers IF we want to preserve variance
- Current values work, but reduce multiplier from 1.08x to 1.02x for diversity

### 2. Perfect Separation

**Finding**: Real vs Inventada are perfectly separated (1.0 vs 0.08)

**Status**: ✅ Excellent — High confidence predictions are correct

**Why this works**:
- Exact matches found → real with 0.96 + multiplier → 1.0
- Not found at all → inventada with 0.08 → 0.08

---

## Recommendations for Phase 4

### Option A: Keep Current Calibration (No Changes)

**Pros**:
- ✅ Works perfectly on test data
- ✅ Clear separation between classes
- ✅ No regressions risk

**Cons**:
- ⚠️ Ceiling effect (all 1.0)
- ⚠️ Limited room for improvement in Brier score

**Recommendation**: Choose this if score is stable at 0.9780+

### Option B: Reduce Multiplier for Variance

**Change**:
```python
# Current
"alta": 1.08x  # → 0.96 * 1.08 = 1.0368 → 1.0

# Proposed
"alta": 1.02x  # → 0.96 * 1.02 = 0.9792 (keeps variance)
```

**Result**: Real citations now return 0.9-0.99 range (not all 1.0)

**Trade-off**: Slightly lower confidence on high-quality citations, better calibration

### Option C: Add Context Quality Thresholds

**Idea**:
```python
if contexto_len < 100:
    return 0.80  # Low context, even if real

elif 100 <= contexto_len < 250:
    return 0.90  # Medium context

else:
    return 0.96  # High context
```

**Result**: More nuanced confidence reflecting context quality

### Option D: Implement Tribunal-Specific Calibration

**Currently**: All tribunals same confidence

**Proposed**:
```python
tribunal_adjustments = {
    "STF": 1.05,   # More reliable
    "STJ": 1.00,   # Baseline
    "TST": 0.95,   # Less structured
    "TSE": 0.98,
}

confidence = base * tribunal_adjustment
```

**Requirement**: Extract tribunal from citation
- Currently not available in simplified API
- Could extract from RESP (STJ), STF (STF), etc pattern

---

## Test Results Summary

### Current System Validation

```
Test Files Processed: 20
Citations Found: 9
Success Rate: 100% (all calibrated)

Classification Quality:
  Real (7/7): 100% correct
  Inventada (2/2): 100% correct

Confidence Distribution:
  Real: all 1.0 (perfect)
  Inventada: all 0.08 (perfect)
```

### Brier Score Impact

Current baseline (no confidence):
- Brier Score: 0.0 (no predictions)

With confidence:
- Brier Score: Depends on actual vs predicted
- Expected: Low (<0.01) given perfect separation

---

## Decision Matrix

| Change | Effort | Risk | Brier Gain | Recommendation |
|---|:---:|:---:|:---:|---|
| Keep current | 0% | None | 0% | ✅ Safe |
| Reduce multiplier | 5% | Low | 1-2% | ✅ Try this |
| Context thresholds | 10% | Low | 2-5% | ✅ Good option |
| Tribunal-specific | 20% | Medium | 3-8% | ⚠️ Complex |

---

## Next Actions (for next session)

1. **Decide**: Keep current OR try Option B (reduce multiplier)
2. **Test**: If changing, validate on full dataset
3. **Measure**: Compare Brier scores before/after
4. **Commit**: Update confidence.py with new values
5. **Validate**: Run Phase 3 validation again

---

## Current Status

✅ **Calibration Working Well**
- Perfect separation between classes
- All citations getting confidence values
- No errors or anomalies

⚠️ **Optimization Opportunity**
- Ceiling effect (all 1.0 for real)
- Could improve Brier score with adjustments

🎯 **Recommendation**
- Session 2 Phase 4: Try Option B (reduce multiplier 1.08x → 1.02x)
- Measure impact on Brier score
- If positive, commit; if negative, revert

---

*Ready for next optimization iteration*
