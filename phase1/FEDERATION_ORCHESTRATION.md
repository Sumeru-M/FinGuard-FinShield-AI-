# Federation Orchestration Protocol — Design Doc (Cycle 14, D-046 track b)

**Author: Distributed Systems Engineer | Status: design only, no code | Scope: what
runs `finguard/federation.py` (and its DP-mitigated sibling `federation_dp.py`) as a
real multi-institution service instead of a single-process simulation.**

## Constraint that shapes every decision

D-006 is absolute: no raw data, no features, no feature-store state ever crosses an
institution boundary. The only object this protocol ever moves is a **signed model
artifact** (or, per `federation_dp.py`, a distilled surrogate + noised probe
predictions) — never in the 100ms scoring path (D-004), always out-of-band.
Everything below is scoped to that one artifact's lifecycle: produce, sign, publish,
fetch, verify, aggregate, retire.

## 1. Artifact format and signing

Each round, each institution produces one **round artifact**:

```
{
  "institution_id": "inst_002",
  "round_id": "r-2026-07-21-014",
  "artifact_kind": "surrogate_v1",       // never "raw_model" in production
  "schema_version": "1.0",
  "probe_set_hash": "sha256:...",         // which shared probe set this was scored against
  "payload": { ... surrogate model bytes + noised probe scores ... },
  "epsilon": 20.0,                        // DP budget spent on this release
  "created_at": "...",
  "signature": "ed25519:..."
}
```

- **Signing**: each institution holds an Ed25519 keypair; the round artifact is
  signed over its content hash. Peers verify the signature against a public-key
  registry (out of scope here — assume a consortium-operated key directory, same
  trust model as the sanctions-feed integration in D-037) before ever loading the
  payload. An unsigned or bad-signature artifact is dropped, never aggregated,
  and logged as a security event (Cybersecurity's lane).
- **Why sign, not just TLS**: TLS protects the transport; signing protects the
  artifact itself through storage/relay/caching — a compromised object store or a
  malicious relay can't inject an artifact that impersonates a peer.
- **Artifact kind is not optional metadata** — it's the D-006 enforcement point. The
  publishing pipeline (not the receiving side) must refuse to serialize
  `artifact_kind: raw_model` at all in production; `federation_dp.py`'s surrogate +
  noised-probe format is the only kind this design allows to leave an institution.

## 2. Versioning

- `schema_version` on the artifact format itself (so institutions can upgrade the
  wire format without a flag day — receivers reject versions they don't understand
  rather than guessing).
- `round_id` is monotonic per round, globally agreed (see scheduling below), not
  institution-chosen — prevents an institution from silently re-submitting a stale
  round under a new label.
- `probe_set_hash` pins which shared probe set (see `federation_dp.PROBE_CFG`) the
  surrogate was distilled against. A consortium-agreed probe set rotates
  periodically (stale probe sets are themselves a minor leakage vector if reused
  forever); every artifact must declare which version it used so aggregation
  never mixes surrogates fit against different probes.
- Aggregators keep the last N rounds per institution (config, default N=3) so a
  straggler or a bad round can be rolled back to the last known-good ensemble
  member without re-running the whole federation.

## 3. Round scheduling

- **Fixed cadence, not event-triggered.** Real institutions retrain on their own
  schedule; forcing synchronous rounds couples availability across organizations
  we don't control. Proposal: weekly rounds, a published `round_open` /
  `round_close` timestamp pair (e.g. 48h submission window), and the aggregator
  builds the ensemble from whatever valid, signed artifacts arrived in that
  window.
- **Aggregator role**: a neutral (consortium-operated, not any single
  institution's) coordination service that: (a) publishes the shared probe set
  and its hash for the round, (b) collects signed artifacts, (c) verifies
  signatures + schema + probe_set_hash match, (d) publishes the resulting
  ensemble manifest (list of verified artifact hashes + round_id) for every
  institution to pull. The aggregator never sees raw model internals in a
  meaningful sense beyond what the artifact already exposes (surrogate +ε-noised
  probe scores) — it is a router/verifier, not a data-holder, consistent with
  D-006 applying to it too.
- Each institution pulls the round manifest and locally builds its ensemble
  exactly as `federation_dp.fed_score_dp` does today — evaluating peer surrogates
  against its own local features, which never leave the institution.

## 4. Stragglers and failures

- **Late artifact**: if an institution's artifact misses `round_close`, that
  institution is simply excluded from that round's ensemble for everyone —
  finguard's per-institution local model keeps scoring alone in the meantime
  (never blocks the 100ms scoring path, per D-004; federation is always an
  enrichment, never a hard dependency of the hot path).
- **Malformed / unsigned / wrong-probe-hash artifact**: dropped at verification,
  logged, does not crash the round for other participants. Repeated failures
  from one institution raise an operational alert (something is broken on their
  side) rather than silently degrading everyone's ensemble.
- **Aggregator failure**: since the aggregator only routes and verifies (no
  institution-specific state it uniquely holds beyond the current round's
  manifest), it can be stateless/replicated behind a standard load balancer;
  worst case on aggregator downtime is "this round doesn't happen," which
  degrades gracefully to local-only scoring everywhere, not an outage.
- **Byzantine/poisoned artifact from a signed, legitimate-looking institution**:
  out of this design's scope to fully solve, but two structural mitigations are
  already implied by the surrogate approach: (a) a poisoned surrogate can only
  ever be *as wrong as* the shared probe set lets it be — it's a bounded-capacity
  regressor fit on public data, not an arbitrary payload — and (b) each
  institution's own local model is never overwritten, only ensembled with peers
  at a fixed 1/(N+1) weight, capping any one peer's influence. Anomaly detection
  on submitted surrogates (e.g. flag one whose predictions on the probe set
  diverge wildly from the rest) is future work, explicitly not built here.

## 5. What this design deliberately does not do yet

- No dynamic per-institution trust weighting (all peers currently get equal
  ensemble weight, same as `federation.py`/`federation_dp.py` today).
- No formal composed privacy budget across rounds (see the honesty note in
  `finguard/federation_dp.py` — epsilon here is a per-round dial, not a tracked
  lifetime budget; a real deployment needs a privacy accountant before rounds run
  indefinitely).
- No cross-institution SLA/incentive design (why would an institution keep
  submitting artifacts?) — that's a product/business question for the Team
  Lead/owner, not an engineering one.

## Privacy budget (Cycle 15, D-049 track b)

`finguard/privacy_accountant.py` closes the gap flagged above and in
`federation_dp.py`'s honesty note. Implements two composition methods over `k`
per-round Laplace releases spending `eps_total` lifetime budget: **basic**
(linear, `eps0 = eps_total / k`, exact, always valid) and **advanced/strong**
composition (Dwork-Rothblum-Vadhan 2010, inverted numerically at `delta=1e-5`).

**Measured finding — weekly cadence does not survive any realistic lifetime
budget.** For `eps_total` in {10, 50, 100} spent over 52 weekly rounds (1
year), the composed per-round epsilon is 0.10-1.92 under either method. Rerunning
the Cycle 14 pipeline (`federation_dp.run_round`) at every one of those exact
values — not extrapolated, actually measured — collapses precision to
0.0009-0.0014 and inflates `cost_vs_naive` to 44x-68x across all three
institutions, at every budget tested. This matches (and confirms, at the
composed values rather than Cycle 14's uncomposed sweep) Cycle 14's finding
that utility collapses below eps~10 per round; composition pushes weekly
per-round epsilon an order of magnitude below that floor even at the most
generous budget tested.

**A second finding, not obvious in advance: "advanced" composition is not
uniformly better here.** The DRV10 bound's `k*eps0*(exp(eps0)-1)` term is
negligible only for small eps0 (roughly `eps0 << 1/sqrt(k)`); at the
utility-relevant eps0 range (10-20) that term explodes (`exp(10)~22000`) and
the bound is *worse* than basic composition — degenerate to ~0 affordable
rounds even at k=1. Basic composition is therefore the only usable accounting
tool for the cadence-viability question below; this only strengthens the
conclusion (there is no favorable-but-untried composition method hiding a
better answer).

**What cadence or budget would make it viable, quantified via basic
composition** (using Cycle 14's own reference points: eps0=20 preserves
near-baseline precision, eps0=10 is already visibly degraded but usable):

| lifetime budget | target eps0/round | total rounds affordable, ever | quarterly cadence buys | semi-annual cadence buys |
|---|---|---|---|---|
| 10  | 20 (preserving) | 0.5  | ~1.5 months | ~3 months |
| 10  | 10 (marginal)   | 1    | ~3 months   | ~6 months |
| 50  | 20 (preserving) | 2.5  | ~7.5 months | ~1.25 years |
| 50  | 10 (marginal)   | 5    | ~1.25 years | ~2.5 years |
| 100 | 20 (preserving) | 5    | ~1.25 years | ~2.5 years |
| 100 | 10 (marginal)   | 10   | ~2.5 years  | ~5 years |

Honest conclusion: at a genuinely meaningful lifetime epsilon (10-100 is
already generous by DP-literature norms — many production deployments target
single-digit lifetime epsilon), **weekly federation rounds are not viable
under this mechanism.** The fix is not a better composition formula — it's
one or more of: (a) **slow the cadence to quarterly or semi-annual**, which
this table shows buys 1-5 years of runway at usable per-round epsilon
depending on budget; (b) **change the mechanism** (subsampling amplification,
a tighter Renyi-DP/moments accountant, or a fundamentally different
output-perturbation scheme with lower per-release sensitivity) rather than
composition accounting alone, which is future work explicitly not attempted
here; or (c) accept a much larger, and harder to justify as "private," lifetime
budget. This is an engineering/privacy-policy tradeoff for the Team
Lead/owner to weigh, not a decision this role makes.

Measured numbers: `data/privacy_accountant_report.json`; run logged to the
experiment registry (`tag=cycle15_privacy`).

## Open question for the owner (flagging, not deciding)

Whether the "neutral aggregator" is consortium-operated infrastructure, a rotating
institution, or a third-party vendor is a governance/cost decision outside this
role's authority — flagged here so it's visible before any real pilot is scoped.
