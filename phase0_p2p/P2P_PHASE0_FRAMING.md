# Phase 0 Framing — P2P Transfers
**Role: Product Manager (#11) | Status: FRAMING DRAFT for owner review — no decisions locked**
Per D-002/D-003: P2P runs its own Phase 0 in parallel with card-payments execution and
unlocks its own Phase 1 independently.

## Why P2P is not "card payments with different plumbing"
The defining problem inverts. In card fraud, the fraudster transacts and the victim doesn't
know. In the dominant P2P fraud — **authorized push payment (APP) / scam-induced transfers**
— the *victim themselves* authorizes the payment, with valid credentials, on their own
device, with normal behavioral biometrics, because they've been socially engineered
(romance scams, fake invoices, impersonated bank staff, purchase scams). Nearly every
signal our card stack leans on (device mismatch, behavior score, credential anomalies)
reads **clean** on an APP fraud transaction. The fraud signal lives elsewhere:
- **Recipient-side reputation**: mule accounts receiving from many first-time senders,
  rapid onward transfers, freshly created accounts
- **Relationship novelty**: first-ever payment to this recipient, especially large
- **Context anomalies**: amount far above the sender's P2P norm, unusual hour, payment
  immediately following an inbound call/message (where observable)
- **Coaching indicators**: hesitation patterns, retries after limit warnings

## Draft fraud taxonomy for P2P v1
1. `p2p_app_scam` — victim-authorized transfer induced by deception (largest loss category;
   the hard one)
2. `p2p_ato_transfer` — classic account takeover pushing funds out (our card ATO signals
   DO transfer here: device/behavior mismatch works)
3. `p2p_mule_receipt` — receiving-side detection of mule/laundering patterns (first
   channel where network/graph features become first-class, not deferred)
Out of scope for P2P v1: merchant QR fraud, request-money spoofing (parked, documented).

## Success-criteria deltas vs card payments
| Dimension | Cards (locked) | P2P (draft — needs owner decision) |
|---|---|---|
| Cost asymmetry | 5:1 FN:FP | Likely **higher** (10:1-ish): APP fraud is usually unrecoverable once funds move, and P2P has no chargeback safety net |
| Latency | 100ms p99 | Softer: P2P UX tolerates 200–500ms and even deliberate friction (confirmation screens are a *feature* here) |
| Autonomy boundary | soft + hard block per txn | Same floor, plus a P2P-specific tool: **delayed settlement** (hold funds N hours on high-risk first-time transfers) — needs owner ruling on whether this counts as "transaction-level" autonomy |
| Alert capacity | shared 200/day cap? | Needs owner ruling: shared pool vs separate P2P lane |
| Explainability | top-features | Same format works; recipient-side features must be phrased carefully (we'd be explaining *someone else's* account behavior to an investigator) |

## Guardrail deltas
- **Recipient privacy**: scoring a transfer using the *recipient's* pattern data is new
  territory vs cards — data-minimization review needed before any recipient-reputation
  feature ships (GDPR-grade baseline applies; the recipient never consented to being scored)
- **AML adjacency**: `p2p_mule_receipt` detection borders regulated AML/SAR territory in
  most jurisdictions — flag: this likely triggers reporting obligations that card fraud
  alerts do not. Legal-review gate (D-009) applies with extra force here.
- **Vulnerable-user bias**: APP scam victims skew elderly; friction targeted "for their
  protection" can shade into discriminatory service degradation. Bias review must add an
  age-proxy check when P2P features are built.

## Open questions for owner (decision needed before P2P Phase 1)
1. Cost ratio for APP fraud (draft: ~10:1 given unrecoverability) — confirm or set
2. Delayed-settlement as an autonomous action: inside or outside the D-005 boundary?
3. Alert capacity: shared 200/day pool or separate P2P lane?
4. Is recipient-reputation scoring approved in principle (with data-minimization review),
   or excluded from P2P v1?
5. Mule detection (`p2p_mule_receipt`): in v1, or deferred to its own AML-focused phase
   given the regulatory adjacency?

## Reuse from the card stack (so P2P Phase 1 starts warm)
- Feature-store pattern, hold-state mechanism, alert queue/disposition loop, experiment
  registry, harness structure — all channel-agnostic
- ATO signal set transfers directly to `p2p_ato_transfer`
- Institution-scoped keys already enforce the federated-ready rule
