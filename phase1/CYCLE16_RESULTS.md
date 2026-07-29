# Cycle 16 Results — Sleeper-Device Counter-Feature
**To: Owner | D-051 | Date: 2026-07-23** | Team Lead solo (no agent spend — efficiency directive)

## Goal
Close the C15 red-team gap: `sleeper_device` (a device with 20–40 days of genuine
history that then pivots to defraud other cards) beat tenure-based trust at 61.5% recall.

## What worked, what didn't (ablation on identical red-team-2 data, model-only)
| Feature config | Overall recall | sleeper | low_slow | evasive |
|---|---|---|---|---|
| Baseline (26) | 71.2% | 65.4% | 68.9% | 76.7% |
| **+ pair_device_life_ratio (27)** | **74.5%** | **69.2%** | **75.6%** | **86.7%** |
| + device_new_cards_7d (28) | 70.8% | 61.5% | 62.2% | 60.0% |

**Kept one feature, rejected one.** `pair_device_life_ratio` (share of a device's
observed life it has known this specific card) is time-stationary — legit card+device
grow up together (ratio ≈1 at any point in the stream); a sleeper pivot is an old
device on a brand-new pair (ratio ≈0). It lifts sleeper +3.8pts and helps two other
cells for free. The companion `device_new_cards_7d` **measurably hurt** (sleeper back to
61.5%) and was dropped — no sentimentality, ablation decides.

Note recorded for reuse: the first attempt used raw pair-*age* (not the ratio) and it
made things worse — time-confounded, since every legit pair is young early in the
stream. The ratio removes that confound.

## Honest read
This is a **modest, real** improvement, not a knockout: sleeper devices remain the
hardest card cell (69% vs 88% for blatant CNP) because a device with genuine history is
genuinely trusted — the ratio catches the *pivot moment* but not every subsequent
fraud once the new pair itself ages. That is the honest ceiling of a feature-only
defense here, consistent with the cross-channel lesson (sleeper mules, slow-
establishment): tenure alone is not trust, and process controls carry what features
can't. No further ML chasing recommended for this cell.

Feature count 27 (was 26). All 14 tests pass. Phase 0 gates hold (latency, cap, beats-
naive, explanations). No new owner decisions.
