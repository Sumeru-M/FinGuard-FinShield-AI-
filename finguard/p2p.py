"""Cycle 7 (D-025): P2P transfers — Phase 1 vertical slice.

The channel that inverts card-fraud assumptions: in APP (authorized push payment)
scams the VICTIM authorizes the transfer on their own device with clean behavioral
biometrics. Device/session signals read normal; the fraud lives in the transfer's
CONTEXT (first-time recipient, amount far above the sender's norm, odd hour) and in
the RECIPIENT's pattern (mule accounts: young, fan-in from many first-time senders,
rapid pass-through). Recipient-reputation features approved under D-024 (gated on
data-minimization review before real data).

Decisions per D-018: approve / hold_funds (delayed settlement, auto-releases,
autonomous) / block. Cost model per D-017 (10:1 — APP losses are unrecoverable):
    approve fraud   = 10.0      hold fraud  = 1.0  (most recovered during hold)
    block legit     = 1.0       hold legit  = 0.2  (delay, mild friction)
Alert cap per D-023: separate P2P lane, 100/day.

Fraud taxonomy (D-019 scope: mule detection deferred to AML phase — recipient
reputation is used as a FEATURE here, mule accounts are not themselves flagged):
    p2p_app_scam      victim-authorized, scam-induced
    p2p_ato_transfer  account takeover pushing funds out
"""

from __future__ import annotations

import json
from collections import defaultdict

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import StratifiedKFold

# C18: values from finguard.config (defaults unchanged — byte-identical)
from finguard.config import cfg
COST_FN, COST_FRAUD_HOLD, COST_FP_BLOCK, COST_FP_HOLD = (
    cfg.p2p_cost_fn, cfg.p2p_cost_fraud_hold, cfg.p2p_cost_fp_block, cfg.p2p_cost_fp_hold)
ALERT_CAP_PER_DAY = cfg.p2p_alert_cap   # D-023: separate P2P lane

P2P_FEATURES = [
    "amount", "log_amount",
    "amount_over_sender_avg",       # vs sender's own P2P norm
    "is_first_time_recipient",      # sender has never paid this recipient
    "sender_transfer_count_30d",
    "sender_new_recipients_7d",     # how many NEW recipients recently (scam burst tell)
    "hour_is_odd",                  # 00:00–05:59 local
    "recipient_account_age_days",   # D-024 recipient-side features
    "recipient_inbound_30d",        # fan-in volume
    "recipient_unique_senders_30d",
    "recipient_first_time_sender_ratio",  # share of inbound from first-time senders
    "device_mismatch",              # ATO tell (clean for APP scams — that's the point)
    "session_behavior_score",
    # C8-1 counter-features for the red-team evasions:
    "pair_cum_amount_7d",           # installments to one recipient ACCUMULATE
    "pair_txn_count_7d",            # ...and repeat (coached payment cadence)
    "recipient_inbound_accel",      # sleeper activation: inbound now vs their own past
]

P2P_DISPLAY = {
    "amount": "Transfer amount", "log_amount": "Transfer amount (log)",
    "amount_over_sender_avg": "Amount vs sender's usual transfers",
    "is_first_time_recipient": "First payment to this recipient",
    "sender_transfer_count_30d": "Sender's transfers in last 30d",
    "sender_new_recipients_7d": "New recipients this week",
    "hour_is_odd": "Late-night transfer",
    "recipient_account_age_days": "Recipient account age",
    "recipient_inbound_30d": "Recipient's inbound transfers (30d)",
    "recipient_unique_senders_30d": "Distinct senders to recipient (30d)",
    "recipient_first_time_sender_ratio": "Recipient's share of first-time senders",
    "device_mismatch": "Unrecognized device for sender",
    "session_behavior_score": "Behavioral biometric match score",
    "pair_cum_amount_7d": "Total sent to this recipient in 7 days",
    "pair_txn_count_7d": "Payments to this recipient in 7 days",
    "recipient_inbound_accel": "Recipient's inbound surge vs their history",
}


def generate(n_users=3000, n_days=30, seed=42):
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2026-06-01")
    users = [f"u_{i:05d}" for i in range(n_users)]
    # each user has a small circle of regular payees
    circles = {u: list(rng.choice(users, size=rng.integers(2, 8), replace=False))
               for u in users}
    spend_mu = {u: float(rng.normal(3.2, 0.6)) for u in users}
    rate = {u: float(rng.uniform(0.05, 0.8)) for u in users}
    account_created = {u: start - pd.Timedelta(days=float(rng.uniform(30, 2000))) for u in users}

    rows = []
    for day in range(n_days):
        ts0 = start + pd.Timedelta(days=day)
        for u in users:
            for _ in range(rng.poisson(rate[u])):
                new_payee = rng.random() < 0.10
                to = str(rng.choice(users)) if new_payee else str(rng.choice(circles[u]))
                rows.append(dict(
                    timestamp=ts0 + pd.Timedelta(hours=int(rng.integers(7, 23)),
                                                 minutes=int(rng.integers(0, 60))),
                    sender=u, recipient=to,
                    amount=round(float(rng.lognormal(spend_mu[u], 0.7)), 2),
                    device_mismatch=0,
                    session_behavior_score=float(np.clip(rng.normal(0.85, 0.08), 0, 1)),
                    label="legit", variant="none",
                ))

    # Mule accounts: young accounts that will fan-in scam proceeds
    mules = [f"mule_{i:03d}" for i in range(30)]
    for m in mules:
        account_created[m] = start - pd.Timedelta(days=float(rng.uniform(1, 40)))

    # C8-1 (D-026): sleeper mules — accounts with months of ORDINARY personal use
    # before activation. They defeat account-age and clean-history heuristics.
    sleepers = [f"u_{i:05d}" for i in rng.choice(n_users, size=60, replace=False)]

    n_scams = 360   # C14: grown for a meaningful friction-effect measurement (was 120)
    for si in range(n_scams):                      # APP scams: THE VICTIM PAYS
        evasive = si % 2 == 1                      # 50/50 blatant / evasive
        victim = str(rng.choice(users))
        ts = start + pd.Timedelta(days=int(rng.integers(0, n_days)),
                                  hours=int(rng.integers(0, 24)))
        if not evasive:
            mule = str(rng.choice(mules))
            for k in range(int(rng.integers(1, 4))):
                rows.append(dict(
                    timestamp=ts + pd.Timedelta(hours=k * int(rng.integers(1, 12))),
                    sender=victim, recipient=mule,
                    # elevated vs victim's norm, but victim's own hand: clean device+behavior
                    amount=round(float(rng.lognormal(spend_mu[victim] + 1.5, 0.5)), 2),
                    device_mismatch=0,
                    session_behavior_score=float(np.clip(rng.normal(0.80, 0.10), 0, 1)),
                    label="p2p_app_scam", variant="app_blatant",
                ))
        else:
            # Evasive: installment coaching — several payments INSIDE the victim's
            # normal band, spread over days, to a sleeper mule with real history
            mule = str(rng.choice(sleepers))
            for k in range(int(rng.integers(3, 7))):
                rows.append(dict(
                    timestamp=ts + pd.Timedelta(days=k, hours=int(rng.integers(9, 21))),
                    sender=victim, recipient=mule,
                    amount=round(float(rng.lognormal(spend_mu[victim] + 0.3, 0.4)), 2),
                    device_mismatch=0,
                    session_behavior_score=float(np.clip(rng.normal(0.83, 0.09), 0, 1)),
                    label="p2p_app_scam", variant="app_evasive",
                ))

    n_ato = 120   # C14: grown alongside scams (was 40)
    for ai in range(n_ato):                        # ATO: attacker pushes funds out
        evasive = ai % 2 == 1
        victim = str(rng.choice(users))
        ts = start + pd.Timedelta(days=int(rng.integers(0, n_days)),
                                  hours=int(rng.integers(0, 24)))
        if not evasive:
            rows.append(dict(
                timestamp=ts, sender=victim, recipient=str(rng.choice(mules)),
                amount=round(float(rng.lognormal(spend_mu[victim] + 1.8, 0.4)), 2),
                device_mismatch=1,
                session_behavior_score=float(np.clip(rng.normal(0.35, 0.12), 0, 1)),
                label="p2p_ato_transfer", variant="ato_blatant",
            ))
        else:
            # Evasive ATO: session hijack (no device mismatch), moderate amounts,
            # paid to a sleeper mule, biometrics only mildly off
            rows.append(dict(
                timestamp=ts, sender=victim, recipient=str(rng.choice(sleepers)),
                amount=round(float(rng.lognormal(spend_mu[victim] + 0.9, 0.4)), 2),
                device_mismatch=0,
                session_behavior_score=float(np.clip(rng.normal(0.62, 0.10), 0, 1)),
                label="p2p_ato_transfer", variant="ato_evasive",
            ))

    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    df.insert(0, "transfer_id", [f"p2p_{i:07d}" for i in range(len(df))])
    return df, account_created


def build_features(df, account_created):
    """Event-order replay; state read before update (point-in-time correct)."""
    sender_pairs = defaultdict(set)          # sender -> recipients paid before
    sender_hist = defaultdict(list)          # sender -> (ts, amount)
    sender_new_recips = defaultdict(list)    # sender -> ts of first-payments
    recip_inbound = defaultdict(list)        # recipient -> (ts, sender, first_time)
    pair_hist = defaultdict(list)            # (sender, recipient) -> (ts, amount)
    recip_lifetime_n = defaultdict(int)      # recipient -> lifetime inbound count
    recip_first_seen = {}                    # recipient -> first inbound ts

    rows = []
    for t in df.itertuples(index=False):
        ts = t.timestamp
        hist = [(a, s) for a, s in sender_hist[t.sender] if a >= ts - pd.Timedelta(days=30)]
        sender_hist[t.sender] = hist
        avg = np.mean([s for _, s in hist]) if hist else t.amount
        first_time = t.recipient not in sender_pairs[t.sender]
        new7 = [x for x in sender_new_recips[t.sender] if x >= ts - pd.Timedelta(days=7)]
        inb = [(a, s, f) for a, s, f in recip_inbound[t.recipient]
               if a >= ts - pd.Timedelta(days=30)]
        recip_inbound[t.recipient] = inb
        rows.append({
            "amount": t.amount,
            "log_amount": float(np.log1p(t.amount)),
            "amount_over_sender_avg": t.amount / max(avg, 1e-6),
            "is_first_time_recipient": int(first_time),
            "sender_transfer_count_30d": len(hist),
            "sender_new_recipients_7d": len(new7),
            "hour_is_odd": int(ts.hour < 6),
            "recipient_account_age_days": (ts - account_created.get(t.recipient, ts)).days,
            "recipient_inbound_30d": len(inb),
            "recipient_unique_senders_30d": len({s for _, s, _ in inb}),
            "recipient_first_time_sender_ratio":
                (sum(f for _, _, f in inb) / len(inb)) if inb else 0.0,
            "device_mismatch": t.device_mismatch,
            "session_behavior_score": t.session_behavior_score,
            **_c8(t, ts, pair_hist, recip_lifetime_n, recip_first_seen, inb),
        })
        # update state
        sender_hist[t.sender].append((ts, t.amount))
        if first_time:
            sender_new_recips[t.sender].append(ts)
        sender_pairs[t.sender].add(t.recipient)
        recip_inbound[t.recipient].append((ts, t.sender, first_time))
        pair_hist[(t.sender, t.recipient)].append((ts, t.amount))
        recip_lifetime_n[t.recipient] += 1
        recip_first_seen.setdefault(t.recipient, ts)

    ff = pd.DataFrame(rows, columns=P2P_FEATURES)
    return pd.concat([df[["transfer_id", "timestamp", "label", "variant",
                          "sender", "recipient"]]
                      .reset_index(drop=True), ff], axis=1)


def _c8(t, ts, pair_hist, recip_lifetime_n, recip_first_seen, inb):
    """Counter-features for the red-team evasions (state read pre-update)."""
    ph = [(a, s) for a, s in pair_hist[(t.sender, t.recipient)]
          if a >= ts - pd.Timedelta(days=7)]
    # Recipient's inbound rate now (30d window, from `inb`) vs their lifetime rate.
    # A sleeper looks ordinary on account age but not on their own trend.
    first = recip_first_seen.get(t.recipient)
    life_days = max((ts - first).days, 1) if first is not None else 1
    lifetime_rate = recip_lifetime_n[t.recipient] / life_days
    recent_rate = len(inb) / 30.0
    accel = recent_rate / max(lifetime_rate, 1e-3)
    return {
        "pair_cum_amount_7d": float(sum(s for _, s in ph)),
        "pair_txn_count_7d": len(ph),
        "recipient_inbound_accel": float(min(accel, 50.0)),
    }


def analytic_thresholds(oof, n_days):
    # C12: shared mechanics from core; P2P cost constants (D-017), cap (D-023)
    from finguard.core import apply_alert_cap, graduated_thresholds
    t_hold, t_block = graduated_thresholds(COST_FN, COST_FRAUD_HOLD,
                                           COST_FP_BLOCK, COST_FP_HOLD)
    t_hold = apply_alert_cap(t_hold, oof, n_days, ALERT_CAP_PER_DAY)
    return t_hold, float(max(t_block, t_hold))


# D-043 friction policy: mandatory Confirmation-of-Payee + delayed settlement on
# first-time-recipient payments. Empirically-grounded effectiveness (UK PSR data shows
# CoP + scam warnings interrupt a meaningful share of APP scams; delayed settlement adds
# a recall window). Applied to fraud the MODEL MISSES — friction is the second line.
COP_ABANDON_APP = cfg.p2p_cop_abandon_app       # C18: default 0.40
SETTLEMENT_RECALL = cfg.p2p_settlement_recall   # C18: default 0.30


def apply_friction(te, yb, alerted, seed=42):
    """D-043: first-time-recipient payments get CoP + delayed settlement.
    Key realism: if a victim ABANDONS at the CoP prompt on the first payment to a
    scam recipient, the ENTIRE scheme collapses — every later installment to that
    recipient is prevented too, not just the first. Returns (prevented_mask, first_time)."""
    rng = np.random.default_rng(seed)
    te = te.reset_index(drop=True)
    first_time = te["is_first_time_recipient"].values.astype(bool)
    is_app = (te["label"].values == "p2p_app_scam")
    prevented = np.zeros(len(te), dtype=bool)

    # Scheme-level CoP interruption. CoP fires at the FIRST contact with a new recipient
    # (analyst-review fix): if the model missed that FIRST-chronological payment, CoP
    # gets its shot regardless of whether the model later catches installment 2/3 via
    # cumulative-amount features. Abandonment there collapses the whole scheme.
    ts = te["timestamp"].values
    fraud_idx = np.where(yb)[0]
    pairs = {}
    for i in fraud_idx:
        pairs.setdefault((te.at[i, "sender"], te.at[i, "recipient"]), []).append(i)
    for (s, r), idxs in pairs.items():
        first = min(idxs, key=lambda i: ts[i])           # first contact = CoP moment
        if is_app[first] and first_time[first] and not alerted[first] \
                and rng.random() < COP_ABANDON_APP:
            for i in idxs:
                prevented[i] = True   # victim walked away — whole scheme stopped

    # Delayed-settlement recall: independent per missed first-time payment not already
    # prevented (exposed to the settlement window regardless of scam type)
    for i in fraud_idx:
        if not prevented[i] and not alerted[i] and first_time[i]:
            if rng.random() < SETTLEMENT_RECALL:
                prevented[i] = True
    return prevented, first_time


def main():
    df, acct = generate()
    ff = build_features(df, acct)
    ff["y"] = (ff["label"] != "legit").astype(int)
    days = ff["timestamp"].dt.normalize()
    cutoff = days.unique()[int(len(days.unique()) * 0.7)]
    tr, te = ff[days < cutoff], ff[days >= cutoff]

    from finguard.core import score_calibrated, train_calibrated
    X, y = tr[P2P_FEATURES], tr["y"].values
    model, cal, oof_cal = train_calibrated(X, y, scale_pos_weight=COST_FN)

    n_tr_days = tr["timestamp"].dt.normalize().nunique()
    t_hold, t_block = analytic_thresholds(oof_cal, n_tr_days)

    score = score_calibrated(model, cal, te[P2P_FEATURES])
    yb = te["y"].values.astype(bool)
    n_days_te = te["timestamp"].dt.normalize().nunique()
    alerted, blocked = score >= t_hold, score >= t_block
    held = alerted & ~blocked
    cost = (COST_FN * (yb & ~alerted).sum() + COST_FRAUD_HOLD * (yb & held).sum()
            + COST_FP_BLOCK * (~yb & blocked).sum() + COST_FP_HOLD * (~yb & held).sum())

    # D-043 friction layer (second line of defense on model-missed fraud)
    prevented, first_time = apply_friction(te, yb, alerted)
    effective = alerted | prevented   # caught by model OR stopped by friction
    friction_volume = int((first_time).sum())        # legit + fraud first-time payments
    legit_friction = int((first_time & ~yb).sum())   # the friction cost: legit prompts

    report = {
        "test_rows": int(len(te)), "test_days": int(n_days_te),
        "fraud_rows": int(yb.sum()),
        "t_hold": round(t_hold, 4), "t_block": round(t_block, 4),
        "recall": round(float((yb & alerted).sum() / yb.sum()), 4),
        "recall_with_friction": round(float((yb & effective).sum() / yb.sum()), 4),
        "precision": round(float((yb & alerted).sum() / max(alerted.sum(), 1)), 4),
        "alerts_per_day": round(float(alerted.sum() / n_days_te), 1),
        "alert_cap": ALERT_CAP_PER_DAY,
        "holds_per_day": round(float(held.sum() / n_days_te), 1),
        "blocks_per_day": round(float(blocked.sum() / n_days_te), 1),
        "false_block_count": int((~yb & blocked).sum()),
        "cost_vs_naive": round(float(cost / (COST_FN * yb.sum())), 4),
        "friction_prompts_per_day": round(float(friction_volume / n_days_te), 1),
        "legit_friction_prompts_per_day": round(float(legit_friction / n_days_te), 1),
        "fraud_prevented_by_friction": int((yb & prevented).sum()),
        "recall_by_type": {
            k: round(float((te[te.label == k].index.isin(te.index[alerted])).mean()), 4)
            for k in ["p2p_app_scam", "p2p_ato_transfer"]
        },
        "recall_by_variant": {
            v: round(float((te[te.variant == v].index.isin(te.index[alerted])).mean()), 4)
            for v in ["app_blatant", "app_evasive", "ato_blatant", "ato_evasive"]
            if (te.variant == v).any()
        },
        "recall_by_variant_with_friction": {
            v: round(float((te[te.variant == v].index.isin(te.index[effective])).mean()), 4)
            for v in ["app_blatant", "app_evasive", "ato_blatant", "ato_evasive"]
            if (te.variant == v).any()
        },
        "hold_tier_used": bool(held.sum() > 0),
    }
    print(json.dumps(report, indent=2))
    with open("data/p2p_report.json", "w") as f:
        json.dump(report, f, indent=2)
    from finguard.experiments import log_run
    log_run("p2p_train", params={"features": P2P_FEATURES, "cost_fn": COST_FN},
            metrics=report, tag="cycle7")


if __name__ == "__main__":
    main()
