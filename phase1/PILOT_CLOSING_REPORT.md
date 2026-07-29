# FinGuard / FraudShield AI — Pilot Closing Report
**To: Owner | Cycle 17 (final) | Date: 2026-07-23**

The original goal: *a real-time, AI-powered fraud detection and prevention system for
digital payments — analyzing transaction patterns, device/behavioral signals and
geolocation to score risk in milliseconds, adapting via federated learning without
sharing raw data, with explainable alerts for investigators.* Every element is built,
measured, and red-teamed on synthetic data. This report is the final scorecard.

## Final scorecard — all channels, all controls active

| Channel | Recall | Precision | Volume | Latency | Cost vs naive |
|---|---|---|---|---|---|
| **Cards** | 89.4% system | 54.1% | 10.9 alerts/day (cap 200) | p99 0.77ms (budget 100ms) | 0 false blocks |
| **P2P** | 89.3% (w/ CoP friction) | 50.0% | 37.5 alerts/day (cap 100) | — | 0.203 |
| **Wire** | 99.9% by value | 26.6% | 16.2 false holds/day | minutes (rail-appropriate) | 0.107 (loss) |

**Every Phase 0 exit gate passes on every channel.** Latency, alert caps, beats-naive
cost, explainable alerts (frozen D-011 format), bias review clean.

## Goal-element coverage
- **Real-time millisecond scoring** — cards p99 0.77ms in-process / ~8ms HTTP under 2k
  rps load (D-004 100ms budget, 12x headroom).
- **Transaction / device / behavioral / geo signals** — 27 point-in-time-correct card
  features incl. behavioral-biometric score, device reputation, geo-mismatch, and the
  Cycle-16 pair-device-life-ratio; channel-specific feature sets for P2P and wire.
- **Adapts via federated learning, no raw-data sharing** — 3-institution simulation
  lifts recall at all three (65→92%, 44→100%, 33→83%); tree-leakage closed structurally
  (DP-noised probe predictions + surrogate distillation); quarterly cadence adopted
  (D-050) after the privacy accountant proved weekly rounds don't survive composition.
- **Explainable investigator alerts** — frozen top-features payload + transaction
  context + dual-lane dashboard, analyst-reviewed and format-frozen (D-011); every
  disposition identity-audited (D-049a).
- **Graduated, human-bounded prevention** — approve / challenge / block (+ hold_funds,
  delayed settlement, verification holds); no account-level action without a human
  (D-005/D-018/D-028); wire release dual-controlled (D-036).

## The honest limits (carried forward, not hidden)
Three structurally hard fraud cells survive pure ML — sleeper devices (cards, ~69%),
installment APP scams to sleeper mules (P2P, ~85% only *with* friction), slow-
establishment BEC (wire). The consistent, validated answer: **process controls carry
what features can't** — confirmation-of-payee, cooling-off + callback verification,
per-wire floors. All three are implemented. "Tenure alone is not trust" is the pilot's
central detection lesson.

## What is deliberately NOT in the pilot (external gates, not unfinished work)
- Real-data ingestion — blocked by the legal/compliance gate (D-009), by design.
- Kafka/Redis infra swap — environment-gated (no Docker daemon); interface-ready, ~1
  cycle when available.
- Sanctions-feed auth build — spec'd and ratified (D-037/D-042/D-044/D-045), builds at
  real integration.
- Real federation pilot — needs actual institutions + the D-048 third-party aggregator.
- AML/mule detection — carved out as its own regulatory-adjacent program (D-019/D-030).
- Cross-channel intelligence — explicitly out of pilot scope (D-051).

## Engineering state
Shared `core.py` training library; 14-test suite (Phase 0 gates, point-in-time
correctness, frozen alert contract, hold-state + audit regressions) green; every run
logged to the experiment registry; 51 owner decisions recorded in the decision log;
11-agent team with maker-checker review as standing practice.

**The pilot delivers the stated goal on synthetic data. Next steps are all external
gates — legal sign-off, real infrastructure, real institutions — not further build.**
