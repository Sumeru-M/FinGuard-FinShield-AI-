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

## Open question for the owner (flagging, not deciding)

Whether the "neutral aggregator" is consortium-operated infrastructure, a rotating
institution, or a third-party vendor is a governance/cost decision outside this
role's authority — flagged here so it's visible before any real pilot is scoped.
