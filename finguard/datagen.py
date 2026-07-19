"""WS-1: Synthetic card-transaction generator.

Produces labeled transaction streams for the single-institution pilot (D-012).
Fraud scenarios follow the Phase 0 taxonomy (phase0/01_fraud_type_definitions.md):
  - confirmed_fraud_cnp        stolen-credential card-not-present fraud
  - confirmed_fraud_ato        account-takeover-driven card fraud
  - confirmed_fraud_synthetic_card  BIN-attack / card-testing patterns
Deterministic under a fixed seed; fraud prevalence is tunable (D-014).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

INSTITUTION_ID = "inst_001"  # single-institution pilot; scoping explicit per D-012

MCC_POOL = [
    "grocery", "fuel", "restaurant", "utilities", "streaming", "travel",
    "electronics", "fashion", "pharmacy", "gaming", "gift_cards", "crypto",
]
# Categories fraudsters favor (resellable / hard to trace)
HIGH_RISK_MCC = {"electronics", "gift_cards", "gaming", "crypto"}

COUNTRIES = ["US", "GB", "DE", "FR", "IN", "SG", "AU", "CA", "BR", "JP"]


@dataclass
class Cardholder:
    card_id: str
    home_country: str
    usual_merchants: list[str]
    usual_categories: list[str]
    spend_mu: float          # lognormal params for typical ticket size
    spend_sigma: float
    devices: list[str]
    active_hours: tuple[int, int]   # local hours the holder usually transacts
    txn_rate_per_day: float
    compromised: str | None = None  # None | "cnp" | "ato"
    history: list = field(default_factory=list)


def _make_population(rng: np.random.Generator, n_cards: int) -> list[Cardholder]:
    holders = []
    for i in range(n_cards):
        n_dev = rng.integers(1, 3)
        holders.append(Cardholder(
            card_id=f"card_{i:06d}",
            home_country=rng.choice(COUNTRIES, p=_country_weights()),
            usual_merchants=[f"m_{rng.integers(0, 4000):05d}" for _ in range(rng.integers(3, 9))],
            usual_categories=list(rng.choice(MCC_POOL, size=rng.integers(2, 5), replace=False)),
            spend_mu=float(rng.normal(3.4, 0.5)),      # median ticket ~ $30
            spend_sigma=float(rng.uniform(0.5, 1.0)),
            devices=[f"dev_{i:06d}_{d}" for d in range(n_dev)],
            active_hours=(int(rng.integers(6, 10)), int(rng.integers(19, 24))),
            txn_rate_per_day=float(rng.uniform(0.3, 4.0)),
        ))
    return holders


def _country_weights():
    w = np.array([0.35, 0.12, 0.08, 0.07, 0.12, 0.04, 0.05, 0.06, 0.06, 0.05])
    return w / w.sum()


def _legit_travel_burst(rng, h: Cardholder, ts) -> list[dict]:
    """v2 noise: real travel — legit txns from a foreign country on a sometimes-new
    device. Makes foreign-country and new-device signals no longer free wins."""
    away = str(rng.choice([c for c in COUNTRIES if c != h.home_country]))
    device = str(rng.choice(h.devices)) if rng.random() < 0.6 \
        else f"dev_{h.card_id[5:]}_travel{rng.integers(0, 100)}"
    out = []
    for d in range(int(rng.integers(2, 7))):          # a multi-day trip
        for _ in range(rng.poisson(max(h.txn_rate_per_day, 1.0))):
            out.append(dict(
                timestamp=ts + pd.Timedelta(days=d, hours=int(rng.integers(8, 23)),
                                            minutes=int(rng.integers(0, 60))),
                card_id=h.card_id,
                merchant_id=f"m_{rng.integers(0, 5000):05d}",   # unfamiliar merchants abroad
                merchant_category=str(rng.choice(["restaurant", "travel", "fashion", "fuel", "electronics"])),
                amount=round(float(rng.lognormal(h.spend_mu + 0.3, h.spend_sigma)), 2),
                country=away,
                device_id=device,
                device_age_days=float(rng.uniform(0.5, 400)),
                channel="pos" if rng.random() < 0.6 else "ecom",
                session_behavior_score=float(np.clip(rng.normal(0.80, 0.10), 0, 1)),
                label="confirmed_legitimate",
                variant="none",
            ))
    return out


def _legit_txn(rng, h: Cardholder, ts) -> dict:
    hour = int(rng.integers(h.active_hours[0], h.active_hours[1])) if rng.random() < 0.85 \
        else int(rng.integers(0, 24))
    novel_merchant = rng.random() < 0.15
    return dict(
        variant="none",
        timestamp=ts.replace(hour=hour, minute=int(rng.integers(0, 60)),
                             second=int(rng.integers(0, 60))),
        card_id=h.card_id,
        merchant_id=f"m_{rng.integers(0, 4000):05d}" if novel_merchant else str(rng.choice(h.usual_merchants)),
        merchant_category=str(rng.choice(MCC_POOL)) if novel_merchant else str(rng.choice(h.usual_categories)),
        amount=round(float(rng.lognormal(h.spend_mu, h.spend_sigma)), 2),
        country=h.home_country if rng.random() < 0.97 else str(rng.choice(COUNTRIES)),
        device_id=str(rng.choice(h.devices)),
        device_age_days=float(rng.uniform(30, 900)),
        channel="ecom" if rng.random() < 0.6 else "pos",
        session_behavior_score=float(np.clip(rng.normal(0.85, 0.08), 0, 1)),  # matches holder's biometric baseline
        label="confirmed_legitimate",
    )


def _cnp_burst(rng, h: Cardholder, ts) -> list[dict]:
    """Stolen credentials used remotely: new geo, new device, high-risk categories, escalating amounts."""
    fraud_country = str(rng.choice([c for c in COUNTRIES if c != h.home_country]))
    fraud_device = f"dev_fraud_{rng.integers(0, 10**6):06d}"
    n = int(rng.integers(2, 7))
    base_minute = int(rng.integers(0, 500))
    out = []
    for k in range(n):
        out.append(dict(
            timestamp=ts + pd.Timedelta(minutes=base_minute + k * int(rng.integers(2, 30))),
            card_id=h.card_id,
            merchant_id=f"m_{rng.integers(4000, 5000):05d}",   # merchants outside holder's pattern
            merchant_category=str(rng.choice(list(HIGH_RISK_MCC))),
            amount=round(float(rng.lognormal(h.spend_mu + 1.0 + 0.3 * k, 0.6)), 2),  # escalating
            country=fraud_country,
            device_id=fraud_device,
            device_age_days=float(rng.uniform(0, 0.2)),
            channel="ecom",
            session_behavior_score=float(np.clip(rng.normal(0.45, 0.15), 0, 1)),
            label="confirmed_fraud_cnp",
            variant="blatant",
        ))
    return out


def _cnp_evasive(rng, h: Cardholder, ts) -> list[dict]:
    """Evasive CNP: stays inside the victim's normal envelope — amounts in the usual
    band, aged-looking device fingerprint, home country, low velocity, mixed merchants."""
    device = f"dev_ev_{rng.integers(0, 10**6):06d}"
    n = int(rng.integers(1, 4))
    out = []
    for k in range(n):
        out.append(dict(
            timestamp=ts + pd.Timedelta(hours=int(rng.integers(2, 20)) * (k + 1),
                                        minutes=int(rng.integers(0, 60))),
            card_id=h.card_id,
            merchant_id=str(rng.choice(h.usual_merchants)) if rng.random() < 0.4
            else f"m_{rng.integers(0, 5000):05d}",
            merchant_category=str(rng.choice(h.usual_categories)) if rng.random() < 0.5
            else str(rng.choice(list(HIGH_RISK_MCC))),
            amount=round(float(rng.lognormal(h.spend_mu, h.spend_sigma)), 2),  # victim's band
            country=h.home_country,
            device_id=device,
            device_age_days=float(rng.uniform(20, 400)),      # spoofed/aged fingerprint
            channel="ecom",
            session_behavior_score=float(np.clip(rng.normal(0.65, 0.12), 0, 1)),  # overlaps legit
            label="confirmed_fraud_cnp",
            variant="evasive",
        ))
    return out


def _ato_burst(rng, h: Cardholder, ts) -> list[dict]:
    """Compromised account/session: card looks normal-ish but device/behavior mismatch."""
    fraud_device = f"dev_ato_{rng.integers(0, 10**6):06d}"
    n = int(rng.integers(1, 5))
    out = []
    for k in range(n):
        out.append(dict(
            timestamp=ts + pd.Timedelta(minutes=int(rng.integers(0, 720)) + k * int(rng.integers(5, 60))),
            card_id=h.card_id,
            # ATO actor sometimes mimics holder's merchants to evade
            merchant_id=str(rng.choice(h.usual_merchants)) if rng.random() < 0.3
            else f"m_{rng.integers(4000, 5000):05d}",
            merchant_category=str(rng.choice(list(HIGH_RISK_MCC | {"travel"}))),
            amount=round(float(rng.lognormal(h.spend_mu + 0.7, 0.7)), 2),
            country=h.home_country if rng.random() < 0.5 else str(rng.choice(COUNTRIES)),
            device_id=fraud_device,
            device_age_days=float(rng.uniform(0, 1.0)),
            channel="ecom",
            session_behavior_score=float(np.clip(rng.normal(0.30, 0.12), 0, 1)),  # biometric mismatch is the tell
            label="confirmed_fraud_ato",
            variant="blatant",
        ))
    return out


def _ato_slow_burn(rng, h: Cardholder, ts) -> list[dict]:
    """Evasive ATO: the compromised device warms up with small plausible purchases over
    days, behavior score drifting down gradually, before the cash-out attempt."""
    device = f"dev_sb_{rng.integers(0, 10**6):06d}"
    n_warm = int(rng.integers(2, 6))
    out = []
    for k in range(n_warm):
        out.append(dict(
            timestamp=ts + pd.Timedelta(days=k, hours=int(rng.integers(9, 22))),
            card_id=h.card_id,
            merchant_id=str(rng.choice(h.usual_merchants)),
            merchant_category=str(rng.choice(h.usual_categories)),
            amount=round(float(rng.lognormal(h.spend_mu - 0.5, 0.4)), 2),  # small, plausible
            country=h.home_country,
            device_id=device,
            device_age_days=float(k) + float(rng.uniform(0, 0.5)),
            channel="ecom",
            session_behavior_score=float(np.clip(rng.normal(0.72 - 0.05 * k, 0.08), 0, 1)),
            label="confirmed_fraud_ato",
            variant="evasive",
        ))
    out.append(dict(   # the cash-out
        timestamp=ts + pd.Timedelta(days=n_warm, hours=int(rng.integers(9, 22))),
        card_id=h.card_id,
        merchant_id=f"m_{rng.integers(0, 5000):05d}",
        merchant_category=str(rng.choice(list(HIGH_RISK_MCC))),
        amount=round(float(rng.lognormal(h.spend_mu + 1.2, 0.4)), 2),
        country=h.home_country,
        device_id=device,
        device_age_days=float(n_warm),
        channel="ecom",
        session_behavior_score=float(np.clip(rng.normal(0.55, 0.10), 0, 1)),
        label="confirmed_fraud_ato",
        variant="evasive",
    ))
    return out


def _card_testing_burst(rng, ts) -> list[dict]:
    """BIN attack: many small probes on one merchant across quasi-sequential cards."""
    merchant = f"m_{rng.integers(0, 5000):05d}"
    base = int(rng.integers(0, 10**5))
    device = f"dev_bot_{rng.integers(0, 10**6):06d}"
    country = str(rng.choice(COUNTRIES))
    n = int(rng.integers(8, 25))
    out = []
    for k in range(n):
        out.append(dict(
            timestamp=ts + pd.Timedelta(seconds=int(k * rng.integers(2, 20))),
            card_id=f"card_x{base + k:06d}",         # cards outside the known population
            merchant_id=merchant,
            merchant_category=str(rng.choice(MCC_POOL)),
            amount=round(float(rng.uniform(0.5, 3.0)), 2),   # tiny authorization probes
            country=country,
            device_id=device,
            device_age_days=0.0,
            channel="ecom",
            session_behavior_score=float(np.clip(rng.normal(0.15, 0.08), 0, 1)),
            label="confirmed_fraud_synthetic_card",
            variant="blatant",
        ))
    return out


def _card_testing_evasive(rng, ts) -> list[dict]:
    """Evasive testing: probes spread across merchants and devices, randomized $1–25
    amounts, minutes apart — no single-merchant burst to key on."""
    base = int(rng.integers(0, 10**5))
    n = int(rng.integers(5, 12))
    out = []
    for k in range(n):
        out.append(dict(
            timestamp=ts + pd.Timedelta(minutes=int(k * rng.integers(3, 25))),
            card_id=f"card_x{base + k:06d}",
            merchant_id=f"m_{rng.integers(0, 5000):05d}",     # different merchant each probe
            merchant_category=str(rng.choice(MCC_POOL)),
            amount=round(float(rng.uniform(1.0, 25.0)), 2),
            country=str(rng.choice(COUNTRIES)),
            device_id=f"dev_bot_{rng.integers(0, 10**6):06d}",  # rotating devices
            device_age_days=float(rng.uniform(0, 30)),
            channel="ecom",
            session_behavior_score=float(np.clip(rng.normal(0.45, 0.15), 0, 1)),
            label="confirmed_fraud_synthetic_card",
            variant="evasive",
        ))
    return out


def generate(n_cards: int = 2000, n_days: int = 30, fraud_prevalence: float = 0.002,
             seed: int = 42, evasive_share: float = 0.5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    holders = _make_population(rng, n_cards)
    start = pd.Timestamp("2026-06-01")
    rows: list[dict] = []

    for day in range(n_days):
        ts = start + pd.Timedelta(days=day)
        for h in holders:
            for _ in range(rng.poisson(h.txn_rate_per_day)):
                rows.append(_legit_txn(rng, h, ts))

    # v2 legit noise: ~8% of holders take one trip in the window
    for h in holders:
        if rng.random() < 0.08:
            ts = start + pd.Timedelta(days=int(rng.integers(0, max(n_days - 7, 1))))
            rows.extend(_legit_travel_burst(rng, h, ts))

    n_legit = len(rows)
    # Solve incident counts so labeled-fraud rows land near the target prevalence
    target_fraud_rows = int(n_legit * fraud_prevalence / (1 - fraud_prevalence))
    # Expected rows/incident: blatant cnp ~4, ato ~2.5, test ~16; evasive cnp ~2.5,
    # ato ~4.5 (warmup+cashout), test ~8. Mix 50/30/20 across types.
    mix = {"cnp": 0.5, "ato": 0.3, "test": 0.2}
    exp_rows = {
        "cnp": 4.0 * (1 - evasive_share) + 2.5 * evasive_share,
        "ato": 2.5 * (1 - evasive_share) + 4.5 * evasive_share,
        "test": 16.0 * (1 - evasive_share) + 8.0 * evasive_share,
    }
    denom = sum(mix[k] * exp_rows[k] for k in mix)
    n_incidents = max(1, int(target_fraud_rows / denom))

    for _ in range(n_incidents):
        kind = rng.choice(list(mix), p=list(mix.values()))
        evasive = rng.random() < evasive_share
        ts = start + pd.Timedelta(days=int(rng.integers(0, n_days)),
                                  hours=int(rng.integers(0, 24)))
        h = holders[rng.integers(0, len(holders))]
        if kind == "cnp":
            rows.extend(_cnp_evasive(rng, h, ts) if evasive else _cnp_burst(rng, h, ts))
        elif kind == "ato":
            rows.extend(_ato_slow_burn(rng, h, ts) if evasive else _ato_burst(rng, h, ts))
        else:
            rows.extend(_card_testing_evasive(rng, ts) if evasive else _card_testing_burst(rng, ts))

    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    df.insert(0, "transaction_id", [f"txn_{i:08d}" for i in range(len(df))])
    df.insert(1, "institution_id", INSTITUTION_ID)
    return df


def main():
    ap = argparse.ArgumentParser(description="FinGuard synthetic card-transaction generator (WS-1)")
    ap.add_argument("--cards", type=int, default=2000)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--prevalence", type=float, default=0.002)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--evasive-share", type=float, default=0.5)
    ap.add_argument("--out", default="data/transactions.parquet")
    args = ap.parse_args()

    df = generate(args.cards, args.days, args.prevalence, args.seed, args.evasive_share)
    import os
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    df.to_parquet(args.out, index=False)

    labels = df["label"].value_counts()
    fraud = labels.drop("confirmed_legitimate", errors="ignore").sum()
    print(f"rows={len(df)}  fraud_rows={fraud}  prevalence={fraud/len(df):.4%}")
    print(labels.to_string())
    fr = df[df["label"] != "confirmed_legitimate"]
    print("\nfraud variant mix:")
    print(fr.groupby(["label", "variant"]).size().to_string())
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
