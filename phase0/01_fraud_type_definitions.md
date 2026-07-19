# Fraud-Type Definitions — Card Payments
**Roles: Product Manager (#11) + Fraud Analyst (#10) | Phase 0, Deliverable 1**

## Purpose
Testable, unambiguous definitions of what counts as fraud for the card-payments channel.
These definitions are the labeling standard Fraud Analysts use to mark historical/simulated
data, and the target classes AI/ML Engineer trains against in Phase 1.

## In-scope fraud types (card payments channel)

### 1. Stolen-credential / Card-Not-Present (CNP) fraud
**Definition:** A transaction is authorized using valid card credentials (number, expiry, CVV)
by a party who is not the legitimate cardholder and has no authorization from them, where the
transaction is not physically card-present.
**Positive label criteria:** confirmed via chargeback with reason code indicating unauthorized
use, cardholder-reported "I did not make this transaction," or confirmed credential breach
correlation.
**Explicitly excluded from this label:** cardholder disputes where the cardholder authorized
the transaction but disputes the merchant/goods (this is a merchant dispute, not fraud —
routed differently).

### 2. Account-takeover-driven card fraud
**Definition:** A transaction made using a compromised customer account/session (e.g. stolen
login, hijacked session, SIM-swap-enabled OTP interception) where the card itself was not
stolen but access to it was gained through account compromise.
**Positive label criteria:** confirmed unauthorized login/session activity immediately
preceding the transaction, cardholder confirms they did not initiate the session, or device/
behavioral fingerprint mismatch confirmed against account history at time of transaction.
**Distinction from #1:** ATO fraud implicates the authentication/session layer, not just the
card credential — this affects which signals matter most (session/device/behavioral vs. pure
card-data velocity).

### 3. Synthetic card fraud (cloned/counterfeit card data used in CNP context)
**Definition:** Card data obtained via skimming, breach, or generation (e.g. BIN attacks) and
used in a CNP transaction without a genuine cardholder relationship.
**Positive label criteria:** card confirmed compromised via issuer breach notification, or BIN-
attack pattern confirmed (sequential card number testing across a merchant).
**Note:** treated as a sub-case of #1 for modeling purposes (same signal profile: valid-looking
credentials, illegitimate use) but tracked separately for reporting since detection method
(velocity/testing-pattern detection) differs from typical stolen-credential fraud.

## Explicitly out of scope for this channel/phase
- **First-party/friendly fraud** (legitimate cardholder disputes a legitimate charge) — not
  technical fraud detection, requires different dispute-resolution workflow
- **Merchant-side fraud** (fraudulent merchants, not fraudulent cardholders) — different
  detection surface entirely
- **Synthetic identity fraud** (fabricated identity opening a new account over time) — long-
  horizon pattern, deferred per Phase 0 scope
- **Money laundering / mule activity via card payments** — network-level pattern, deferred

## Labeling standard for Fraud Analyst
Every flagged/reviewed transaction gets one of: `confirmed_fraud_cnp`, `confirmed_fraud_ato`,
`confirmed_fraud_synthetic_card`, `confirmed_legitimate`, `friendly_fraud_dispute` (routed out),
or `unresolved` (insufficient evidence — excluded from training data, not treated as negative).

## Open question flagged for your input
None blocking — these definitions are ready for use. If real chargeback/dispute data becomes
available in Phase 1, these definitions should be revisited against actual reason-code
taxonomies from card networks (Visa/Mastercard use specific reason codes that may warrant
finer-grained sub-labels).
