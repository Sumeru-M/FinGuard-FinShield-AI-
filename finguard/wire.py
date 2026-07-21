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
DISCOVERY_LATENCY = pd.Timedelta(days=5)   # C13/F4: BEC is discovered days after the loss;
# an establishment TEST payment isn't known to be fraud until its STRIKE is investigated.
NEW_BENEFICIARY_CAP = 50_000.0    # D-040: cumulative $ to a new/changed beneficiary
# allowed while UNVERIFIED, pending callback/CoP verification (raised from $25k — median
# invoice ~$13k, so $25k held two normal invoices to a legit new supplier)
VERIFY_DELAY_DAYS = (2.0, 7.0)    # D-041: a callback takes this long to complete
CONFIRM_PROB_LEGIT = 0.97         # a real supplier answers an independent callback
CONFIRM_PROB_FRAUD = 0.05         # a fraud "supplier" rarely does (residual: social engineering)

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
    # C10 counter-features (D-032):
    "payer_new_accounts_7d",       # distinct new beneficiary accounts lately (structuring/fake-vendor)
    "payer_wire_sum_24h",          # dollar aggregate regardless of per-wire sizing
    "amount_over_account_max",     # vs the account's OWN history (establishment: strike >> test)
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
    "payer_new_accounts_7d": "New beneficiary accounts this week (payer)",
    "payer_wire_sum_24h": "Payer's total wired in 24h",
    "amount_over_account_max": "Amount vs largest ever paid to this account",
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
        # C10 analyst-review fix: legit suppliers get onboarded MID-stream and change
        # bank details — the honest false-positive population BEC hides inside.
        for s in range(int(rng.integers(1, 4))):     # late-onboarded new suppliers
            sups.append({
                "supplier": f"sup_{o:04d}_new{s:02d}",
                "account": f"acct_{rng.integers(0, 10**8):08d}",
                "country": str(rng.choice(["US", "GB", "DE", "IN", "CN", "SG"])),
                "amount_mu": float(rng.normal(9.5, 1.2)),
                "cycle_days": int(rng.choice([14, 30, 30, 60])),
                "phase": int(rng.integers(30, n_days - 10)),   # first payment mid-window
            })
        for sup in sups:                              # ~15% legitimately change accounts
            sup["change_day"] = int(rng.integers(40, n_days)) if rng.random() < 0.15 else None
            sup["new_account"] = f"acct_{rng.integers(0, 10**8):08d}"
        org_suppliers[org] = sups
        for sup in sups:
            day = sup["phase"]
            while day < n_days:
                jitter = int(rng.integers(-2, 3))
                if 0 <= day + jitter < n_days:
                    changed = sup["change_day"] is not None and day + jitter >= sup["change_day"]
                    rows.append(dict(
                        timestamp=start + pd.Timedelta(days=day + jitter,
                                                       hours=int(rng.integers(9, 17))),
                        payer=org, supplier=sup["supplier"],
                        beneficiary_account=sup["new_account"] if changed else sup["account"],
                        beneficiary_country=sup["country"],
                        amount=round(float(rng.lognormal(sup["amount_mu"], 0.25)), 2),
                        # analyst-review fix: most legit corporate wires ALSO trace to
                        # emailed invoices — email-initiated must not be a fraud tell
                        is_email_initiated=int(rng.random() < 0.55),
                        device_mismatch=0,
                        session_behavior_score=float(np.clip(rng.normal(0.85, 0.07), 0, 1)),
                        label="legit", variant="none",
                    ))
                day += sup["cycle_days"]

    orgs = list(org_suppliers)
    # BEC: attacker impersonates a KNOWN supplier; payment goes to a NEW account.
    # (C11: count grown for cell size.)
    for bi in range(120):
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

    # C11 (D-034): window attacks — evasions aimed at the counter-features' fixed
    # 7d/24h windows and the amount-over-account-max ratio.
    # Slow establishment: MULTIPLE test payments spaced >7d apart, shrinking the
    # strike ratio and never tripping payer_new_accounts_7d twice in a window.
    for _ in range(30):
        org = str(rng.choice(orgs))
        sup = org_suppliers[org][rng.integers(0, len(org_suppliers[org]))]
        t0 = start + pd.Timedelta(days=int(rng.integers(45, n_days - 40)),
                                  hours=int(rng.integers(9, 17)))
        acct = f"acct_{rng.integers(0, 10**8):08d}"
        n_tests = int(rng.integers(2, 4))
        for k in range(n_tests):   # escalating test payments, 8-12 days apart
            rows.append(dict(
                timestamp=t0 + pd.Timedelta(days=k * int(rng.integers(8, 13))),
                payer=org, supplier=sup["supplier"],
                beneficiary_account=acct, beneficiary_country=sup["country"],
                amount=round(float(rng.lognormal(sup["amount_mu"] - 1.0 + 0.4 * k, 0.3)), 2),
                is_email_initiated=int(rng.random() < 0.55),
                device_mismatch=0,
                session_behavior_score=float(np.clip(rng.normal(0.85, 0.07), 0, 1)),
                label="wire_bec", variant="bec_establish_slow_test",
            ))
        rows.append(dict(   # the strike: only ~2-3x the last test payment
            timestamp=t0 + pd.Timedelta(days=n_tests * 10 + int(rng.integers(5, 10))),
            payer=org, supplier=sup["supplier"],
            beneficiary_account=acct, beneficiary_country=sup["country"],
            amount=round(float(rng.lognormal(sup["amount_mu"] + 0.3, 0.25)), 2),
            is_email_initiated=int(rng.random() < 0.55),
            device_mismatch=0,
            session_behavior_score=float(np.clip(rng.normal(0.85, 0.07), 0, 1)),
            label="wire_bec", variant="bec_establish_slow_strike",
        ))

    # Slow structuring: sub-$100k wires spread >24h apart over several days
    for _ in range(20):
        org = str(rng.choice(orgs))
        t0 = start + pd.Timedelta(days=int(rng.integers(45, n_days - 8)),
                                  hours=int(rng.integers(9, 17)))
        for k in range(int(rng.integers(3, 6))):
            rows.append(dict(
                timestamp=t0 + pd.Timedelta(days=k, hours=int(rng.integers(1, 8))),
                payer=org, supplier=f"unknown_{rng.integers(0, 10**4):04d}",
                beneficiary_account=f"acct_{rng.integers(0, 10**8):08d}",
                beneficiary_country="US",
                amount=round(float(rng.uniform(88_000, 99_000)), 2),
                is_email_initiated=0, device_mismatch=0,
                session_behavior_score=float(np.clip(rng.normal(0.62, 0.10), 0, 1)),
                label="wire_ato", variant="ato_structuring_slow",
            ))

    # C10 (D-032): account-establishment BEC — attacker "verifies" the fake account
    # with a small on-cycle test invoice, waits ~1 cycle, then hits the real one.
    # By the big payment, the account has observed history and isn't "new".
    # C11: counts grown for cell size; test/strike split per analyst backlog.
    for _ in range(60):
        org = str(rng.choice(orgs))
        sup = org_suppliers[org][rng.integers(0, len(org_suppliers[org]))]
        t0 = start + pd.Timedelta(days=int(rng.integers(45, n_days - 35)),
                                  hours=int(rng.integers(9, 17)))
        acct = f"acct_{rng.integers(0, 10**8):08d}"
        rows.append(dict(   # the establishment payment: small, plausible, on-pattern
            timestamp=t0, payer=org, supplier=sup["supplier"],
            beneficiary_account=acct, beneficiary_country=sup["country"],
            amount=round(float(rng.lognormal(sup["amount_mu"] - 1.0, 0.3)), 2),
            is_email_initiated=1, device_mismatch=0,
            session_behavior_score=float(np.clip(rng.normal(0.85, 0.07), 0, 1)),
            label="wire_bec", variant="bec_establish_test",
        ))
        rows.append(dict(   # the strike: full invoice amount, ~one cycle later
            timestamp=t0 + pd.Timedelta(days=int(sup["cycle_days"]) + int(rng.integers(-2, 3)),
                                        hours=int(rng.integers(9, 17))),
            payer=org, supplier=sup["supplier"],
            beneficiary_account=acct, beneficiary_country=sup["country"],
            amount=round(float(rng.lognormal(sup["amount_mu"] + 0.2, 0.25)), 2),
            is_email_initiated=1, device_mismatch=0,
            session_behavior_score=float(np.clip(rng.normal(0.85, 0.07), 0, 1)),
            label="wire_bec", variant="bec_establish_strike",
        ))

    # C10: fake-vendor onboarding — a wholly new "supplier" that never existed.
    # Hides inside the legitimate new-supplier false-hold population. (C11: count grown.)
    for _ in range(50):
        org = str(rng.choice(orgs))
        rows.append(dict(
            timestamp=start + pd.Timedelta(days=int(rng.integers(45, n_days)),
                                           hours=int(rng.integers(9, 17))),
            payer=org, supplier=f"fakevendor_{rng.integers(0, 10**4):04d}",
            beneficiary_account=f"acct_{rng.integers(0, 10**8):08d}",
            beneficiary_country=str(rng.choice(["US", "GB", "DE"])),   # unremarkable
            amount=round(float(rng.lognormal(9.2, 0.4)), 2),           # mid-size invoice
            is_email_initiated=1, device_mismatch=0,
            session_behavior_score=float(np.clip(rng.normal(0.85, 0.07), 0, 1)),
            label="wire_bec", variant="bec_fake_vendor",
        ))

    # ATO wires — blatant, plus C10 structuring variant: several wires each sized
    # BELOW the $100k human-release line, spread over hours, to distinct accounts.
    # (C11: count grown for cell size.)
    for ai in range(70):
        org = str(rng.choice(orgs))
        ts = start + pd.Timedelta(days=int(rng.integers(45, n_days)),
                                  hours=int(rng.integers(0, 24)))
        if ai % 2 == 0:
            rows.append(dict(
                timestamp=ts, payer=org, supplier=f"unknown_{rng.integers(0, 10**4):04d}",
                beneficiary_account=f"acct_{rng.integers(0, 10**8):08d}",
                beneficiary_country=str(rng.choice(["NG", "HK", "AE", "CY", "US"])),
                amount=round(float(rng.lognormal(10.5, 0.5)), 2),
                is_email_initiated=0, device_mismatch=int(rng.random() < 0.7),
                session_behavior_score=float(np.clip(rng.normal(0.45, 0.15), 0, 1)),
                label="wire_ato", variant="ato_blatant",
            ))
        else:
            for k in range(int(rng.integers(3, 6))):
                rows.append(dict(
                    timestamp=ts + pd.Timedelta(hours=k * int(rng.integers(1, 4)),
                                                minutes=int(rng.integers(0, 60))),
                    payer=org, supplier=f"unknown_{rng.integers(0, 10**4):04d}",
                    beneficiary_account=f"acct_{rng.integers(0, 10**8):08d}",
                    beneficiary_country="US",
                    # analyst-review fix: real structuring clusters TIGHT under the line
                    amount=round(float(rng.uniform(88_000, 99_000)), 2),
                    is_email_initiated=0, device_mismatch=0,              # hijacked session
                    session_behavior_score=float(np.clip(rng.normal(0.62, 0.10), 0, 1)),
                    label="wire_ato", variant="ato_structuring",
                ))

    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    df.insert(0, "wire_id", [f"wire_{i:06d}" for i in range(len(df))])

    # C13/F4: honest label-availability timing. A fraud row is only usable as a TRAINING
    # positive once it has been discovered. Ordinary fraud is discovered DISCOVERY_LATENCY
    # after the loss; an establishment TEST payment is not recognized as fraud until its
    # own STRIKE is investigated — so it inherits the strike's discovery time.
    df["discovered_at"] = pd.NaT
    fraud = df["label"] != "legit"
    df.loc[fraud, "discovered_at"] = df.loc[fraud, "timestamp"] + DISCOVERY_LATENCY
    test_v = ["bec_establish_test", "bec_establish_slow_test"]
    strike_v = ["bec_establish_strike", "bec_establish_slow_strike"]
    strike_ts = (df[df["variant"].isin(strike_v)]
                 .groupby("beneficiary_account")["timestamp"].max())
    for acct, s_ts in strike_ts.items():
        m = (df["beneficiary_account"] == acct) & df["variant"].isin(test_v)
        df.loc[m, "discovered_at"] = s_ts + DISCOVERY_LATENCY

    # C14/D-041: callback-verification-completion. Each beneficiary account gets an
    # INDEPENDENT callback outcome — a real supplier confirms (a genuine contact answers
    # a number sourced independently of the invoice); a fraud "supplier" structurally
    # does not. Modeled with realistic imperfection both ways (unreachable legit
    # suppliers; socially-engineered fraud callbacks). This is a business-process
    # control, NOT a model feature — verified_at is never in WIRE_FEATURES.
    rng_v = np.random.default_rng(seed + 1)
    acct_first = df.groupby("beneficiary_account")["timestamp"].min()
    acct_fraud = df.groupby("beneficiary_account")["label"].apply(lambda s: (s != "legit").any())
    verified = {}
    for acct, first_ts in acct_first.items():
        p = CONFIRM_PROB_FRAUD if bool(acct_fraud[acct]) else CONFIRM_PROB_LEGIT
        verified[acct] = (first_ts + pd.Timedelta(days=float(rng_v.uniform(*VERIFY_DELAY_DAYS)))
                          if rng_v.random() < p else pd.NaT)
    df["verified_at"] = df["beneficiary_account"].map(verified)
    return df


def build_features(df):
    pair_hist = defaultdict(list)       # (payer,supplier) -> (ts, amount)
    pair_accounts = defaultdict(dict)   # (payer,supplier) -> {account: first_seen}
    pair_country = {}                   # (payer,supplier) -> historical country
    payer_wires = defaultdict(list)
    payer_new_accts = defaultdict(list)  # payer -> ts of first-payments to new accounts
    payer_amounts = defaultdict(list)    # payer -> (ts, amount)
    account_amounts = defaultdict(list)  # (payer, account) -> amounts paid before

    account_first_seen = {}             # (payer, account) -> first-payment ts
    rows = []
    controls = []   # D-035 control signals — business rules, NOT model features
    for t in df.itertuples(index=False):
        ts, key = t.timestamp, (t.payer, t.supplier)
        akey = (t.payer, t.beneficiary_account)
        prior_to_acct = account_amounts[akey]
        first_seen = account_first_seen.get(akey, ts)   # this ts if brand new
        acct_age_days = (ts - first_seen).days
        cum_to_acct = float(sum(prior_to_acct)) + t.amount   # cumulative incl. this wire
        controls.append({"benef_account_age_days": float(acct_age_days),
                         "cumulative_to_account": cum_to_acct})
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
            "payer_new_accounts_7d": sum(1 for x in payer_new_accts[t.payer]
                                         if x >= ts - pd.Timedelta(days=7)),
            "payer_wire_sum_24h": float(sum(a for x, a in payer_amounts[t.payer]
                                            if x >= ts - pd.Timedelta(hours=24))),
            "amount_over_account_max":
                float(min(t.amount / max(max(account_amounts[(t.payer, t.beneficiary_account)],
                                             default=t.amount), 1.0), 50.0)),
        })
        pair_hist[key].append((ts, t.amount))
        seen.setdefault(t.beneficiary_account, ts)
        pair_country.setdefault(key, t.beneficiary_country)
        payer_wires[t.payer].append(ts)
        if new_acct:
            payer_new_accts[t.payer].append(ts)
        payer_amounts[t.payer].append((ts, t.amount))
        account_amounts[akey].append(t.amount)
        account_first_seen.setdefault(akey, ts)

    ff = pd.DataFrame(rows, columns=WIRE_FEATURES)
    ctrl = pd.DataFrame(controls)
    meta = df[["wire_id", "timestamp", "amount", "label", "variant",
               "discovered_at", "verified_at"]] \
        .rename(columns={"amount": "amt"}).reset_index(drop=True)
    return pd.concat([meta, ctrl, ff], axis=1)


VARIANTS = ["bec_blatant", "bec_evasive", "bec_establish_test", "bec_establish_strike",
            "bec_establish_slow_test", "bec_establish_slow_strike", "bec_fake_vendor",
            "ato_blatant", "ato_structuring", "ato_structuring_slow"]


def hold_threshold(amount: np.ndarray) -> np.ndarray:
    """D-027 amount-dependent threshold: hold when p > (D·A + REVIEW) / ((1-R+D)·A)."""
    return (D_FRAC * amount + REVIEW_COST) / ((1 - R_FRAC + D_FRAC) * amount)


def decide(p, amt, unverified, cum_to_acct):
    """C14 decision layer: model score + D-041 verification control, D-028 routing.
      - model_held: amount-dependent cost-model threshold (D-027)
      - control_held (D-040/D-041): while a beneficiary account is UNVERIFIED (its
        independent callback has not confirmed), cumulative $ to it is capped at
        NEW_BENEFICIARY_CAP; any wire crossing that is held. Release is tied to
        verification-COMPLETION, not a clock — so a patient attacker cannot outwait it
        (a fraud account never verifies), closing the slow-establishment frontier.
    Returns (held, control_held, human_queue, dual_control)."""
    model_held = p > hold_threshold(amt)
    control_held = unverified & (cum_to_acct >= NEW_BENEFICIARY_CAP)
    held = model_held | control_held
    human_queue = held & (amt > HUMAN_RELEASE_ABOVE)          # D-028: human sign-off
    dual_control = held & (amt <= HUMAN_RELEASE_ABOVE)        # D-036: 2nd-analyst co-sign
    return held, control_held, human_queue, dual_control


def main():
    df = generate()
    ff = build_features(df)
    ff["y"] = (ff["label"] != "legit").astype(int)
    days = ff["timestamp"].dt.normalize()
    cutoff = days.unique()[int(len(days.unique()) * 0.7)]
    cutoff_ts = pd.Timestamp(cutoff)
    tr, te = ff[days < cutoff], ff[days >= cutoff]

    from finguard.core import score_calibrated, train_calibrated
    X = tr[WIRE_FEATURES]
    # F4 (D-039): honest training labels — a fraud row is a positive ONLY if it was
    # DISCOVERED before the training cutoff. Fraud not yet discovered trains as 0, the
    # true production condition (establishment test-payments no longer leak their label).
    y = ((tr["label"] != "legit") & (tr["discovered_at"] < cutoff_ts)).astype(int).values
    model, cal, _ = train_calibrated(X, y, scale_pos_weight=20)

    p = score_calibrated(model, cal, te[WIRE_FEATURES])
    amt = te["amt"].values
    yb = te["y"].values.astype(bool)
    n_days_te = te["timestamp"].dt.normalize().nunique()

    # model-only baseline (D-027 threshold, no business control)
    held_m = p > hold_threshold(amt)
    # model + D-035/D-036 controls
    # D-041: an account is unverified at wire time if its callback never confirmed,
    # or confirmed only later than this wire
    unverified = (te["verified_at"].isna() | (te["timestamp"] < te["verified_at"])).values
    held, control_held, human_queue, dual_control = decide(
        p, amt, unverified, te["cumulative_to_account"].values)

    loss_naive = float((amt * yb).sum())          # release everything
    loss = float((amt * (yb & ~held)).sum() + R_FRAC * (amt * (yb & held)).sum()
                 + D_FRAC * (amt * (~yb & held)).sum() + REVIEW_COST * held.sum())

    report = {
        "test_rows": int(len(te)), "test_days": int(n_days_te),
        "fraud_rows": int(yb.sum()),
        "fraud_dollars": round(float((amt * yb).sum()), 2),
        "train_positives_labeled": int(y.sum()),   # F4: fewer than raw fraud rows
        "train_fraud_rows_raw": int((tr["label"] != "legit").sum()),
        "recall_by_count": round(float((yb & held).sum() / yb.sum()), 4),
        "recall_by_value": round(float((amt * (yb & held)).sum() / (amt * yb).sum()), 4),
        "recall_model_only_by_count": round(float((yb & held_m).sum() / yb.sum()), 4),
        "precision": round(float((yb & held).sum() / max(held.sum(), 1)), 4),
        "holds_per_day": round(float(held.sum() / n_days_te), 1),
        "control_only_holds_per_day": round(float((control_held & ~held_m).sum() / n_days_te), 1),
        "human_release_queue_per_day": round(float(human_queue.sum() / n_days_te), 1),
        # analyst-review: this is wires ROUTED to the dual-control queue awaiting a
        # second-analyst disposition — NOT auto-releases (most are correctly-held fraud)
        "dual_control_queue_per_day": round(float(dual_control.sum() / n_days_te), 1),
        "false_holds_per_day": round(float((~yb & held).sum() / n_days_te), 1),
        "expected_loss_vs_naive": round(loss / loss_naive, 4),
        # F4: n=0 cells reported explicitly, never silently omitted
        "recall_by_variant": {
            v: {"recall": round(float((te[te.variant == v].index.isin(te.index[held])).mean()), 4)
                if (te.variant == v).any() else None,
                "n": int((te.variant == v).sum())}
            for v in VARIANTS
        },
        "largest_missed_wire": round(float((amt * (yb & ~held)).max()), 2) if (yb & ~held).any() else 0.0,
        # analyst-review: attribute the worst miss to its variant so it can be dispositioned
        "largest_missed_variant": (te.loc[(yb & ~held), "variant"]
                                   .iloc[np.argmax(amt[(yb & ~held)])] if (yb & ~held).any() else None),
        "largest_caught_wire": round(float((amt * (yb & held)).max()), 2) if (yb & held).any() else 0.0,
    }
    # C11 ablation (analyst backlog #1): how much recall depends on the two suspected
    # lab tells — email initiation and the behavioral score?
    # Security-review F1: device_mismatch is also a synthetic separator — ablate all 3
    ABLATED = [f for f in WIRE_FEATURES
               if f not in ("is_email_initiated", "session_behavior_score",
                            "device_mismatch")]
    model_a, cal_a, _ = train_calibrated(tr[ABLATED], y, scale_pos_weight=20)
    p_a = score_calibrated(model_a, cal_a, te[ABLATED])
    held_a = p_a > hold_threshold(amt)
    report["ablation_no_email_behavior_device"] = {
        "recall_by_count": round(float((yb & held_a).sum() / yb.sum()), 4),
        "recall_by_value": round(float((amt * (yb & held_a)).sum() / (amt * yb).sum()), 4),
        "false_holds_per_day": round(float((~yb & held_a).sum() / n_days_te), 1),
        # F1: per-variant ablation recall so frontier-cell sensitivity is visible
        "recall_by_variant": {
            v: {"recall": round(float((te[te.variant == v].index.isin(te.index[held_a])).mean()), 4)
                if (te.variant == v).any() else None,
                "n": int((te.variant == v).sum())}
            for v in VARIANTS
        },
    }

    print(json.dumps(report, indent=2))
    with open("data/wire_report.json", "w") as f:
        json.dump(report, f, indent=2)
    from finguard.experiments import log_run
    # F5: tag/params must distinguish generator + ablation code versions
    log_run("wire_train", params={"features": WIRE_FEATURES, "r_frac": R_FRAC,
                                  "d_frac": D_FRAC, "review_cost": REVIEW_COST,
                                  "variants": VARIANTS, "ablated": ABLATED},
            metrics=report, tag="cycle13")


if __name__ == "__main__":
    main()
