# Sanctions Feed Authentication Requirements Spec
**Role: Cybersecurity Engineer | Cycle 12, D-037 | Spec now, build at integration**

## Context and scope

Per D-030, sanctions/AML screening stays out of scope for FinGuard's wire model — an
existing upstream bank/vendor system owns the screen, and we consume only its verdict
as one input feature, `sanctions_verdict_pass` (`finguard/wire.py:50`). Today that
feature is a hardcoded stub (`= 1`, `finguard/wire.py:338`) with no feed behind it.
Cycle 11 review (F7, `phase1/CYCLE11_RESULTS.md`) flagged that once a real feed is
wired in, the model will trust whatever value arrives on that field with no
verification — a spoofed "pass" is currently indistinguishable from a real one. This
spec defines what the feed integration must satisfy before the stub is replaced. It is
vendor-neutral: no specific screening provider or transport is assumed. Build is
deferred to integration time per D-037; this document is the acceptance bar for that
build.

## Threat model

**Asset:** the `sanctions_verdict_pass` boolean and its freshness/provenance, which the
wire model treats as ground truth for one of its dozen features and which downstream
compliance processes may also rely on for OFAC/sanctions-list obligations.

**Attackers and what a forged/suppressed verdict buys them:**

| Attacker | Capability | Path | Impact |
|---|---|---|---|
| Network-position attacker (MITM, compromised link/proxy between the sanctions vendor and FinGuard) | Intercept/modify traffic on the feed path | Rewrite an in-flight `fail` verdict to `pass`, or replay an old `pass` for a new (now-listed) counterparty | A sanctioned or newly-listed beneficiary clears screening; the wire model sees `sanctions_verdict_pass=1` and treats the wire as materially safer than it is — the one feature designed to catch this exact class of risk is silently defeated |
| Malicious/compromised upstream integration (a system or account with legitimate write access to whatever channel carries the verdict into FinGuard, e.g. a compromised ETL job or message queue producer) | Inject arbitrary verdicts | Push fabricated `pass` verdicts for arbitrary payer/beneficiary pairs, or suppress `fail` verdicts entirely | Same as above, at higher volume and lower detection likelihood since it doesn't require breaking transport crypto |
| Insider (analyst, integration engineer, or vendor-side operator with access to the feed pipeline) | Modify or replay stored/queued verdicts before they reach the model | Doctor a specific wire's verdict ahead of a targeted BEC/ATO strike they know is coming, or replay a stale `pass` for a beneficiary account that has since become sanctioned | Same impact as above, but targeted and harder to distinguish from legitimate feed behavior since it uses the trusted path, not an external exploit — this is the same class of concern as the label-loop poisoning surface (Cycle 4 backlog item), applied to an upstream feed instead of analyst dispositions |
| Availability attacker (DoS against the vendor feed or the network path to it) | Degrade or cut feed availability | Force FinGuard into whatever fail-posture is configured | If fail-open: attacker gets free `pass` verdicts for the duration of the outage, timed to a strike. If fail-closed: attacker forces false holds / throughput loss — a lower-severity but real availability cost |

**Severity ranking:**
1. **Critical** — spoofed/replayed `pass` for a real BEC/ATO strike (network MITM or
   compromised producer): directly defeats the control, financial loss, and is silent
   (no operator signal that anything is wrong).
2. **High** — insider-doctored verdict on a targeted wire: same defeat, harder to
   detect because it looks like normal feed traffic; the audit trail (below) is the
   primary detective control since prevention alone can't fully close an insider path.
3. **Medium** — forced fail-open via feed outage timed to a strike: requires the
   attacker to also control or predict outage timing, but costs nothing to attempt.
4. **Low** — forced fail-closed via DoS: no fraud loss, but a throughput/friction cost
   and a plausible nuisance-DoS vector if the fail-posture is naively fail-closed with
   no rate limiting on how much of the wire queue it can freeze.

The common thread: today, all four rows above are **free** — there is no transport
authentication, no verdict signing, no freshness check, and no audit trail, so a
`pass` value on the wire has exactly as much trust as a stub constant, because that is
literally what it is.

## Authentication requirements for the feed

1. **Mutual TLS on the transport.** The feed connection (whatever transport is chosen
   at integration — REST callback, message queue, file drop) must use mTLS with
   certificate pinning to the vendor's known CA/cert, not just server-side TLS. This
   closes the network-MITM row of the threat model at the transport layer.
2. **Per-verdict signing, independent of transport.** Transport security alone is not
   sufficient — it protects the pipe, not the payload once it's inside FinGuard's own
   systems (queues, logs, retries). Each verdict record must carry a vendor-signed
   payload (verdict, subject identifiers, timestamp, nonce) so that verdict integrity
   can be checked at the point of consumption, not just at the wire. This is what
   distinguishes a legitimate replay-from-cache from a forged or stale record, and it's
   the control that also covers the insider-on-the-trusted-path row, since an insider
   with pipeline access still cannot forge the vendor's signature.
3. **Replay protection.** Each signed verdict must bind to a nonce or monotonic
   sequence number plus a short validity window, checked at consumption time. A
   correctly-signed but stale `pass` (e.g., from before a beneficiary was added to a
   list) must be rejected, not accepted on the strength of a valid signature alone.
   Signature validity and freshness validity are two separate checks — do not
   conflate them.
4. **Freshness window tied to screening semantics, not a generic TTL.** Sanctions
   lists update on their own cadence (routine batch updates, but also emergency
   designations that can land intraday). The freshness window should be short enough
   that a verdict is not trusted across a list-update boundary — recommend the
   integration-time spec pull the vendor's actual list-update SLA and set the window
   at most that wide, rather than picking a round number in isolation. If the vendor
   cannot state an update SLA, treat that as a vendor-selection blocker, not a spec
   detail to work around.
5. **Verdict scoped to the specific transaction, not cached per-beneficiary.** The
   signed payload should bind to the wire being screened (payer, beneficiary, amount,
   timestamp), not just the beneficiary identity. A beneficiary-level cache is exactly
   what a slow-establishment attacker (the same tradecraft flagged in Cycle 11's
   81.3%-recall frontier cell — legitimacy manufactured over time) would probe for: get
   one clean verdict early, then reuse it. Binding to the transaction forces a fresh
   check per wire, at the cost of more calls to the vendor.
6. **Least-privilege on the consuming side.** Only the wire-scoring path should be able
   to read the verdict feed; write/inject access must be restricted to the vendor's
   authenticated producer identity, with no generic internal service account able to
   post verdicts.

## Fail-posture: fail-closed, with a scoped exception

**Recommendation: fail-closed** — if the feed is unavailable, stale beyond its
freshness window, or fails signature/replay verification, the wire is treated as
`sanctions_verdict_pass=0` (fail), not `=1`.

Rationale: D-030 puts sanctions/AML screening upstream because the bank's existing
systems own the compliance obligation; FinGuard consuming a *known-bad-or-unknown*
verdict as `pass` would mean the fraud model actively launders a screening failure
into a false assurance signal, and a fail-open posture converts every feed outage
into a routable "sanctions screening is off" window for anyone who can either predict
the outage or trigger one via the availability-attacker row above. This is also
consistent with the existing autonomy posture in this system: D-005 lets the system
hard-block/hold autonomously but never lets it authorize something a human hasn't
signed off on, and D-028 already inverts wire autonomy so that holding is the
low-friction default action. Fail-closed on this one feature is directionally the same
choice, at feature-granularity rather than decision-granularity — it degrades one
input rather than overriding the whole model's action.

**What fail-closed should NOT mean:** it should not silently convert into a system-wide
autonomous hard-block. `sanctions_verdict_pass=0` is one input among the wire feature
set; per D-027/D-028 it feeds the amount-dependent cost threshold like any other
feature and can push a wire into HOLD, which routes to the existing human-release
queue above $100k, or into ordinary review below it. That routing, not a bespake
sanctions-specific block path, is what should trigger — the point is to remove the
false-assurance signal, not to add a new autonomous action class outside D-005/D-028.

**Scoped exception — flagged as owner-gated, not decided here:** if the vendor feed's
observed availability is poor enough that fail-closed materially raises false-hold
volume during ordinary outages (as opposed to attacker-timed ones), the owner may want
a bounded fail-open exception (e.g., only for wires below a small dollar threshold, or
only for a short grace period before escalating to fail-closed). That is a
friction-vs-risk tradeoff on compliance-adjacent functionality, which sits squarely in
owner-gated territory per the team charter — this spec's default is fail-closed with
no exception, and any relaxation should be an explicit, logged decision at integration
time, not a config default nobody chose.

## Audit logging

Every verdict consumed by the wire scorer must be logged, independent of and in
addition to the scoring feature itself, with at minimum:
- Vendor-signed payload as received (raw, for later re-verification/dispute)
- Signature/replay verification result (pass/fail and which check failed, if any)
- Freshness check result and the computed age against the window
- The wire/transaction identifiers the verdict was bound to
- What the scorer actually did with it (value consumed: real verdict, or fail-closed
  substitution — and if substitution, why: unavailable / stale / signature-invalid /
  replay-detected)

This log is the primary detective control against the insider row of the threat model
(row 3 above) — prevention via signing closes most of that path, but an insider with
legitimate pipeline access is the hardest case to fully prevent, and this is the same
posture already required for the label-loop poisoning surface (Cycle 4 backlog):
audit trail + role auth as the compensating control when prevention alone isn't
sufficient. Retention should follow the existing behavioral/session-data bar (90 days,
D-008) at minimum, extended to match whatever retention the compliance/AML side of the
business needs for its own dispute and regulator-inquiry windows — that duration is a
compliance question, not a security one, and should be confirmed with whoever owns the
AML relationship before integration, not assumed here.

## Verification requirements at integration time

Before the stub is replaced with a live feed, the integration must demonstrate, not
just claim:
1. **mTLS enforcement** — a connection attempt with an unpinned/self-signed cert is
   rejected.
2. **Signature verification** — a tampered payload (verdict flipped, subject changed)
   with a transport-valid connection is rejected and logged as a signature failure,
   not silently accepted.
3. **Replay rejection** — a previously-seen, correctly-signed verdict replayed outside
   its freshness window is rejected and logged, not treated as fresh.
4. **Fail-closed behavior under outage** — simulated feed unavailability (timeout,
   connection refused, stale-beyond-window) results in `sanctions_verdict_pass=0`
   reaching the model, verified end-to-end through `finguard/wire.py`'s feature
   pipeline, not just at the feed client.
5. **Audit log completeness** — every one of the above test cases produces the audit
   record described above, and the record is queryable by wire ID.
6. **Least-privilege check** — confirm no internal service identity other than the
   vendor-authenticated producer can write to the verdict channel.

None of this should be taken as license to build screening logic in-house — D-030
holds: the verdict's correctness is the vendor/upstream system's responsibility. This
spec only covers whether FinGuard can trust that the verdict it received is the one
the vendor actually sent, current, and for the right transaction.

## Needs-owner

- **Fail-open exception scope** (see Fail-posture section above): whether any bounded
  fail-open carve-out is acceptable for ordinary (non-attacker-timed) vendor outages,
  and if so, its dollar/duration bounds. Default in this spec is no exception.
- **Audit log retention duration** for the compliance/AML side specifically (security
  baseline is D-008's 90 days; actual regulator/dispute-window needs may require
  longer and should come from whoever owns the AML relationship).
- **Vendor selection criteria should include** a stated list-update SLA (see
  Requirement 4) — if no vendor under consideration can state one, that's a
  vendor-selection question for whoever owns that relationship, not a spec gap here.
