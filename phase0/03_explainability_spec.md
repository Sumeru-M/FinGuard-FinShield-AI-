# Explainability Spec — Card Payments
**Roles: AI/ML Engineer (#1) + Platform Engineer (#9) + Fraud Analyst (#10) | Phase 0, Deliverable 3**

## Format decision
**Working default: top-contributing-features format** (SHAP-style feature attribution),
presented as a ranked list with human-readable feature names and relative contribution weight.

**Why this default:** broadest compatibility across model families (works whether AI/ML
Engineer ultimately chooses gradient-boosted trees, a neural network, or an ensemble), fastest
to implement reliably, and gives Fraud Analysts a concrete, auditable basis for override
decisions without requiring a separate natural-language-generation step (which introduces its
own faithfulness risk — the generated sentence could misrepresent what the model actually
weighted).

**Deferred, not rejected:** natural-language rationale (a generated sentence summarizing the
alert) is a candidate for a later iteration, layered on top of the feature-attribution data
once the underlying attributions are trusted and stable. Counterfactual explanations
("would not have flagged if X") are also deferred — higher implementation complexity, revisit
if Fraud Analyst feedback indicates the top-features format isn't actionable enough.

## Alert payload spec

```json
{
  "alert_id": "string",
  "transaction_id": "string",
  "timestamp": "ISO8601",
  "risk_score": "float (0-1)",
  "decision": "enum: approve | soft_challenge | hard_block",
  "fraud_type_prediction": "enum: cnp | ato | synthetic_card | none",
  "top_features": [
    {
      "feature_name": "string (human-readable, e.g. 'New device for this account')",
      "contribution_weight": "float (0-1, relative contribution to risk score)",
      "feature_value": "string (actual observed value, e.g. 'first seen 2 minutes ago')"
    }
  ],
  "confidence": "float (0-1, model confidence distinct from risk score)"
}
```
- `top_features`: minimum 3, maximum 7 entries — enough for investigator context without
  overwhelming the alert view.
- `feature_name` must be human-readable at generation time (not a raw internal feature ID) —
  this is a requirement on AI/ML Engineer's feature-naming convention, not a Platform-side
  translation step, to avoid drift between internal names and displayed names.

## Requirement on AI/ML Engineer (Phase 1)
Model family selection must support feature-attribution methods compatible with the 100ms
latency budget (attribution computation, if not precomputed, adds to the scoring-path cost).
Tree-based models (SHAP TreeExplainer) and linear/logistic models are attribution-cheap;
deep neural approaches may require precomputed/approximate attribution to stay in budget —
flag this explicitly if a deep model is proposed in Phase 1.

## Requirement on Platform Engineer (Phase 1)
Investigator dashboard must render `top_features` as a ranked, readable list per alert, with
the transaction's raw decision and risk score visible alongside it — not a separate lookup.

## Open question for Fraud Analyst validation (deferred to Phase 1 kickoff)
This spec is a working default based on general best-practice, not validated against an actual
Fraud Analyst's workflow (no analyst has reviewed a live example yet, since no data exists).
**Action item for Phase 1 kickoff:** first working prototype's alert output should be reviewed
by whoever fills the Fraud Analyst role before the format is finalized.
