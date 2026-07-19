"""Cycle 9 (D-031): Wire transfers — Phase 1 vertical slice, corporate-first (D-029).

The channel where per-EVENT cost models break: a $2M wire is not a $10k wire.
Per D-027 the cost model is per-dollar expected loss with a fixed review cost:

    cost(release) = p · A                    (BEC loss ≈ unrecoverable full amount)
    cost(hold)    = p · R_frac · A  +  (1-p) · D_frac · A  +  REVIEW_COST

so holding beats releasing when  p > (D_frac·A + REVIEW_COST) / ((1 - R_frac + D_frac)·A)
— an AMOUNT-DEPENDENT threshold: a $5k wire needs meaningful suspicion to hold,
a $2M wire is held on a whisper. This is the analytic-threshold method from cards,
generalized to value-weighted stakes.

Decisions per D-028 (inverted autonomy): the machine may HOLD any wire autonomously;
a held wire above $100k enters a human-release queue — only a person can un-stop it.
Latency is not a constraint on this rail (minutes acceptable; in-line enrichment fine).

Scope per D-029/D-030: BEC/invoice-manipulation + ATO wires; sanctions/AML screening
is an upstream system whose verdict we consume as a feature (stubbed here as pass).
"""

from __future__ import annotations

import json
from collections import defaultdict

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import StratifiedKFold

R_FRAC = 0.10      # residual loss fraction if fraud is held (mostly recovered)
D_FRAC = 0.002     # friction cost fraction for delaying a legit wire
REVIEW_COST = 50.0   # fixed analyst cost per held wire
HUMAN_RELEASE_ABOVE = 100_000.0   # D-028

WIRE_FEATURES = [
    "amount", "log_amount",
    "amount_z_vs_supplier",        # vs this payer→supplier invoice history
    "is_new_beneficiary_account",  # THE BEC tell: account details changed/new
    "days_since_beneficiary_change",
    "beneficiary_country_mismatch",  # vs supplier's historical bank country
    "days_off_cycle",              # timing vs payer→supplier usual cadence
    "payer_wires_30d",
    "supplier_payment_count",      # depth of relationship history
    "is_email_initiated",          # request-channel metadata (BEC arrives by email)
    "device_mismatch",             # ATO tell
    "session_behavior_score",
    "sanctions_verdict_pass",      # upstream system's verdict (D-030), stub=1
]

WIRE_DISPLAY = {
    "amount": "Wire amount", "log_amount": "Wire amount (log)",
    "amount_z_vs_supplier": "Amount vs invoice history with this supplier",
    "is_new_beneficiary_account": "Beneficiary account is new/changed",
    "days_since_beneficiary_change": "Days since beneficiary details changed",
    "beneficiary_country_mismatch": "Beneficiary bank country changed",
    "days_off_cycle": "Off-schedule vs usual payment cadence",
    "payer_wires_30d": "Payer's wires in last 30d",
    "supplier_payment_count": "Payments made to this supplier before",
    "is_email_initiated": "Initiated via email request",
    "device_mismatch": "Unrecognized device/session",
    "session_behavior_score": "Operator behavior match score",
    "sanctions_verdict_pass": "Sanctions screening passed (upstream)",
}


def generate(n_orgs=400, n_days=120, seed=42):
    """Corporate payers on invoice cycles. Longer window than retail channels —
    wire cadences are monthly, and BEC needs history to hide against."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2026-03-01")
    rows = []
    org_suppliers = {}
    for o in range(n_orgs):
        org = f"org_{o:04d}"
        n_sup = int(rng.integers(3, 15))
        sups = []
        for s in range(n_sup):
            sups.append({
                "supplier": f"sup_{o:04d}_{s:02d}",
                "account": f"acct_{rng.integers(0, 10**8):08d}",
                "country": str(rng.choice(["US", "GB", "DE", "IN", "CN", "SG"])),
                "amount_mu": float(rng.normal(9.5, 1.2)),   # median ~$13k, tail to millions
                "cycle_days": int(rng.choice([7, 14, 30, 30, 30, 60])),
                "phase": int(rng.integers(0, 30)),
            })
        org_suppliers[org] = sups
        for sup in sups:
            day = sup["phase"]
            while day < n_days:
                jitter = int(rng.integers(-2, 3))
                if 0 <= day + jitter < n_days:
                    rows.append(dict(
                        timestamp=start + pd.Timedelta(days=day + jitter,
                                                       hours=int(rng.integers(9, 17))),
                        payer=org, supplier=sup["supplier"],
                        beneficiary_account=sup["account"],
                        beneficiary_country=sup["country"],
                        amount=round(float(rng.lognormal(sup["amount_mu"], 0.25)), 2),
                        is_email_initiated=int(rng.random() < 0.15),
                        device_mismatch=0,
                        session_behavior_score=float(np.clip(rng.normal(0.85, 0.07), 0, 1)),
                        label="legit", variant="none",
                    ))
                day += sup["cycle_days"]

    orgs = list(org_suppliers)
    # BEC: attacker impersonates a KNOWN supplier; payment goes to a NEW account.
    for bi in range(60):
        evasive = bi % 2 == 1
        org = str(rng.choice(orgs))
        sup = org_suppliers[org][rng.integers(0, len(org_suppliers[org]))]
        ts = start + pd.Timedelta(days=int(rng.integers(45, n_days)),
                                  hours=int(rng.integers(9, 17)))
        fake_acct = f"acct_{rng.integers(0, 10**8):08d}"
        if not evasive:
            # blatant: inflated amount, foreign account, off-cycle, email-initiated
            rows.append(dict(
                timestamp=ts, payer=org, supplier=sup["supplier"],
                beneficiary_account=fake_acct,
                beneficiary_country=str(rng.choice(["NG", "HK", "AE", "CY"])),
                amount=round(float(rng.lognormal(sup["amount_mu"] + 1.0, 0.3)), 2),
                is_email_initiated=1, device_mismatch=0,
                session_behavior_score=float(np.clip(rng.normal(0.84, 0.07), 0, 1)),
                label="wire_bec", variant="bec_blatant",
            ))
        else:
            # evasive: amount matches the real invoice, same country, timed ON-cycle
            # — only the account number changed (the classic supplier-detail-change scam)
            rows.append(dict(
                timestamp=ts, payer=org, supplier=sup["supplier"],
                beneficiary_account=fake_acct,
                beneficiary_country=sup["country"],
                amount=round(float(rng.lognormal(sup["amount_mu"], 0.25)), 2),
                is_email_initiated=1, device_mismatch=0,
                session_behavior_score=float(np.clip(rng.normal(0.85, 0.07), 0, 1)),
                label="wire_bec", variant="bec_evasive",
            ))

    # ATO wires: compromised banking session pushes to a mule account
    for ai in range(30):
        org = str(rng.choice(orgs))
        sup = org_suppliers[org][rng.integers(0, len(org_suppliers[org]))]
        rows.append(dict(
            timestamp=start + pd.Timedelta(days=int(rng.integers(45, n_days)),
                                           hours=int(rng.integers(0, 24))),
            payer=org, supplier=f"unknown_{rng.integers(0, 10**4):04d}",
            beneficiary_account=f"acct_{rng.integers(0, 10**8):08d}",
            beneficiary_country=str(rng.choice(["NG", "HK", "AE", "CY", "US"])),
            amount=round(float(rng.lognormal(10.5, 0.5)), 2),
            is_email_initiated=0, device_mismatch=int(rng.random() < 0.7),
            session_behavior_score=float(np.clip(rng.normal(0.45, 0.15), 0, 1)),
            label="wire_ato", variant="ato",
        ))

    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    df.insert(0, "wire_id", [f"wire_{i:06d}" for i in range(len(df))])
    return df


def build_features(df):
    pair_hist = defaultdict(list)       # (payer,supplier) -> (ts, amount)
    pair_accounts = defaultdict(dict)   # (payer,supplier) -> {account: first_seen}
    pair_country = {}                   # (payer,supplier) -> historical country
    payer_wires = defaultdict(list)

    rows = []
    for t in df.itertuples(index=False):
        ts, key = t.timestamp, (t.payer, t.supplier)
        hist = pair_hist[key]
        amts = [a for _, a in hist]
        mu, sd = (np.mean(amts), max(np.std(amts), 1.0)) if len(amts) >= 2 else (t.amount, 1.0)
        seen = pair_accounts[key]
        new_acct = t.beneficiary_account not in seen
        chg_days = 999.0 if new_acct else (ts - seen[t.beneficiary_account]).days
        if len(hist) >= 2:
            gaps = np.diff([x.value for x, _ in hist[-6:]]) / 86_400e9
            cadence = float(np.median(gaps)) if len(gaps) else 30.0
            off = abs((ts - hist[-1][0]).days - cadence)
        else:
            off = 0.0
        pw = [x for x in payer_wires[t.payer] if x >= ts - pd.Timedelta(days=30)]
        payer_wires[t.payer] = pw
        rows.append({
            "amount": t.amount, "log_amount": float(np.log1p(t.amount)),
            "amount_z_vs_supplier": float(min(abs(t.amount - mu) / sd, 20.0)) if len(amts) >= 2 else 0.0,
            "is_new_beneficiary_account": int(new_acct and len(hist) > 0),
            "days_since_beneficiary_change": float(min(chg_days, 999.0)),
            "beneficiary_country_mismatch": int(key in pair_country
                                                and t.beneficiary_country != pair_country[key]),
            "days_off_cycle": float(min(off, 60.0)),
            "payer_wires_30d": len(pw),
            "supplier_payment_count": len(hist),
            "is_email_initiated": t.is_email_initiated,
            "device_mismatch": t.device_mismatch,
            "session_behavior_score": t.session_behavior_score,
            "sanctions_verdict_pass": 1,   # upstream stub (D-030)
        })
        pair_hist[key].append((ts, t.amount))
        seen.setdefault(t.beneficiary_account, ts)
        pair_country.setdefault(key, t.beneficiary_country)
        payer_wires[t.payer].append(ts)

    ff = pd.DataFrame(rows, columns=WIRE_FEATURES)
    return pd.concat([df[["wire_id", "timestamp", "amount", "label", "variant"]]
                      .rename(columns={"amount": "amt"}).reset_index(drop=True),
                      ff], axis=1)


def hold_threshold(amount: np.ndarray) -> np.ndarray:
    """D-027 amount-dependent threshold: hold when p > (D·A + REVIEW) / ((1-R+D)·A)."""
    return (D_FRAC * amount + REVIEW_COST) / ((1 - R_FRAC + D_FRAC) * amount)


def main():
    df = generate()
    ff = build_features(df)
    ff["y"] = (ff["label"] != "legit").astype(int)
    days = ff["timestamp"].dt.normalize()
    cutoff = days.unique()[int(len(days.unique()) * 0.7)]
    tr, te = ff[days < cutoff], ff[days >= cutoff]

    X, y = tr[WIRE_FEATURES], tr["y"].values
    oof = np.zeros(len(tr))
    for a, b in StratifiedKFold(5, shuffle=True, random_state=42).split(X, y):
        m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
                               scale_pos_weight=20, random_state=42, verbose=-1)
        m.fit(X.iloc[a], y[a])
        oof[b] = m.predict_proba(X.iloc[b])[:, 1]
    cal = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(oof, y)
    model = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
                               scale_pos_weight=20, random_state=42, verbose=-1)
    model.fit(X, y)

    p = cal.predict(model.predict_proba(te[WIRE_FEATURES])[:, 1])
    amt = te["amt"].values
    yb = te["y"].values.astype(bool)
    held = p > hold_threshold(amt)
    human_queue = held & (amt > HUMAN_RELEASE_ABOVE)
    n_days_te = te["timestamp"].dt.normalize().nunique()

    loss_naive = float((amt * yb).sum())          # release everything
    loss = float((amt * (yb & ~held)).sum() + R_FRAC * (amt * (yb & held)).sum()
                 + D_FRAC * (amt * (~yb & held)).sum() + REVIEW_COST * held.sum())

    report = {
        "test_rows": int(len(te)), "test_days": int(n_days_te),
        "fraud_rows": int(yb.sum()),
        "fraud_dollars": round(float((amt * yb).sum()), 2),
        "recall_by_count": round(float((yb & held).sum() / yb.sum()), 4),
        "recall_by_value": round(float((amt * (yb & held)).sum() / (amt * yb).sum()), 4),
        "precision": round(float((yb & held).sum() / max(held.sum(), 1)), 4),
        "holds_per_day": round(float(held.sum() / n_days_te), 1),
        "human_release_queue_per_day": round(float(human_queue.sum() / n_days_te), 1),
        "false_holds_per_day": round(float((~yb & held).sum() / n_days_te), 1),
        "expected_loss_vs_naive": round(loss / loss_naive, 4),
        "recall_by_variant": {
            v: round(float((te[te.variant == v].index.isin(te.index[held])).mean()), 4)
            for v in ["bec_blatant", "bec_evasive", "ato"] if (te.variant == v).any()
        },
        "largest_missed_wire": round(float((amt * (yb & ~held)).max()), 2) if (yb & ~held).any() else 0.0,
        "largest_caught_wire": round(float((amt * (yb & held)).max()), 2) if (yb & held).any() else 0.0,
    }
    print(json.dumps(report, indent=2))
    with open("data/wire_report.json", "w") as f:
        json.dump(report, f, indent=2)
    from finguard.experiments import log_run
    log_run("wire_train", params={"features": WIRE_FEATURES, "r_frac": R_FRAC,
                                  "d_frac": D_FRAC, "review_cost": REVIEW_COST},
            metrics=report, tag="cycle9")


if __name__ == "__main__":
    main()
