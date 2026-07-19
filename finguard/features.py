"""WS-2: Streaming feature computation + feature store.

Processes transactions in strict event order, maintaining rolling state per card,
device, and merchant — so every feature vector is point-in-time correct (no label
leakage: state is read BEFORE the current transaction is folded in).

FeatureStore is deliberately interface-shaped: the pilot uses InMemoryFeatureStore;
a RedisFeatureStore drop-in replaces it when the infra workstream activates
(docker daemon unavailable in the pilot environment — adaptation flagged to owner).
Institution scoping is explicit on every key per the federated-ready rule (D-012).
"""

from __future__ import annotations

from collections import defaultdict, deque

import numpy as np
import pandas as pd

HIGH_RISK_MCC = {"electronics", "gift_cards", "gaming", "crypto"}

FEATURE_COLUMNS = [
    "amount",
    "log_amount",
    "amount_over_card_avg",        # ticket size vs this card's rolling mean
    "txn_count_1h",                # card velocity, 1 hour
    "txn_count_24h",               # card velocity, 24 hours
    "amount_sum_24h",
    "seconds_since_last_txn",
    "is_new_device_for_card",
    "device_age_days",
    "is_foreign_country",          # differs from card's dominant country
    "is_new_merchant_for_card",
    "is_high_risk_mcc",
    "merchant_txns_10m",           # burst at one merchant (card-testing signal)
    "merchant_small_amt_10m",      # sub-$5 probes at one merchant in 10 min
    "device_card_count_1h",        # distinct cards seen on one device in 1h (bot signal)
    "session_behavior_score",      # behavioral-biometric match, provided upstream
    "is_ecom",
    # Cycle 3 (D-016): adversarial-robust additions — favor OBSERVED history over
    # attacker-suppliable fields (a spoofed device_age_days can't fake store history)
    "hour_dev_from_card_mean",     # circular deviation from card's usual transaction hour
    "amount_zscore_card",          # amount vs card's own mean/std, not just ratio
    "merchant_txn_count_log",      # merchant popularity (log1p of observed volume)
    "merchant_observed_age_days",  # how long WE have seen this merchant
    "device_observed_age_days",    # how long WE have seen this device (vs self-reported)
    "device_alltime_cards",        # distinct cards ever on this device (bot/mule signal)
]

# Human-readable names required by the explainability spec (D-011): the model
# feature name IS the displayed name — no separate translation layer.
FEATURE_DISPLAY = {
    "amount": "Transaction amount",
    "log_amount": "Transaction amount (log scale)",
    "amount_over_card_avg": "Amount vs card's usual spend",
    "txn_count_1h": "Card transactions in last hour",
    "txn_count_24h": "Card transactions in last 24h",
    "amount_sum_24h": "Card spend total in last 24h",
    "seconds_since_last_txn": "Time since card's previous transaction",
    "is_new_device_for_card": "New device for this card",
    "device_age_days": "Device age",
    "is_foreign_country": "Country differs from card's usual country",
    "is_new_merchant_for_card": "First time at this merchant",
    "is_high_risk_mcc": "High-risk merchant category",
    "merchant_txns_10m": "Merchant transaction burst (10 min)",
    "merchant_small_amt_10m": "Small-amount probes at merchant (10 min)",
    "device_card_count_1h": "Distinct cards on this device (1h)",
    "session_behavior_score": "Behavioral biometric match score",
    "is_ecom": "Online (card-not-present) transaction",
    "hour_dev_from_card_mean": "Unusual time of day for this card",
    "amount_zscore_card": "Amount deviation from card's spending pattern",
    "merchant_txn_count_log": "Merchant transaction volume",
    "merchant_observed_age_days": "How long this merchant has been observed",
    "device_observed_age_days": "How long this device has been observed",
    "device_alltime_cards": "Total distinct cards seen on this device",
}


class InMemoryFeatureStore:
    """Rolling state keyed by (institution_id, entity). Redis-swappable interface."""

    def __init__(self):
        self.card_times = defaultdict(deque)        # card -> recent txn timestamps
        self.card_amounts = defaultdict(deque)      # card -> (ts, amount)
        self.card_devices = defaultdict(set)
        self.card_merchants = defaultdict(set)
        self.card_countries = defaultdict(lambda: defaultdict(int))
        self.card_amt_stats = defaultdict(lambda: [0, 0.0])   # count, sum
        self.merchant_times = defaultdict(deque)    # merchant -> (ts, amount)
        self.device_cards = defaultdict(deque)      # device -> (ts, card)
        # Cycle 3 state
        self.card_hour_vec = defaultdict(lambda: [0.0, 0.0, 0])   # sum sin, sum cos, n
        self.card_amt_sq = defaultdict(float)                     # sum of amount^2
        self.merchant_stats = defaultdict(lambda: [None, 0])      # first_seen_ts, count
        self.device_first_seen = {}                               # device -> ts
        self.device_all_cards = defaultdict(set)                  # device -> {cards}

    @staticmethod
    def _k(inst, entity):
        return f"{inst}:{entity}"

    @staticmethod
    def _trim(dq, cutoff, key=lambda x: x):
        while dq and key(dq[0]) < cutoff:
            dq.popleft()

    def features_for(self, t) -> dict:
        """Read state for transaction t WITHOUT updating it."""
        ck = self._k(t.institution_id, t.card_id)
        mk = self._k(t.institution_id, t.merchant_id)
        dk = self._k(t.institution_id, t.device_id)
        ts = t.timestamp

        times = self.card_times[ck]
        self._trim(times, ts - pd.Timedelta(hours=24))
        txn_24h = len(times)
        txn_1h = sum(1 for x in times if x >= ts - pd.Timedelta(hours=1))
        last_gap = (ts - times[-1]).total_seconds() if times else 86400.0

        amts = self.card_amounts[ck]
        self._trim(amts, ts - pd.Timedelta(hours=24), key=lambda x: x[0])
        amt_24h = sum(a for _, a in amts)

        cnt, total = self.card_amt_stats[ck]
        card_avg = (total / cnt) if cnt else t.amount
        dom_country = max(self.card_countries[ck], key=self.card_countries[ck].get) \
            if self.card_countries[ck] else t.country

        mtimes = self.merchant_times[mk]
        self._trim(mtimes, ts - pd.Timedelta(minutes=10), key=lambda x: x[0])
        m_10m = len(mtimes)
        m_small_10m = sum(1 for _, a in mtimes if a < 5.0)

        dcards = self.device_cards[dk]
        self._trim(dcards, ts - pd.Timedelta(hours=1), key=lambda x: x[0])
        dev_cards_1h = len({c for _, c in dcards} | set()) + (0 if any(c == t.card_id for _, c in dcards) else 0)

        return {
            "amount": t.amount,
            "log_amount": float(np.log1p(t.amount)),
            "amount_over_card_avg": t.amount / max(card_avg, 1e-6),
            "txn_count_1h": txn_1h,
            "txn_count_24h": txn_24h,
            "amount_sum_24h": amt_24h,
            "seconds_since_last_txn": min(last_gap, 86400.0),
            "is_new_device_for_card": int(t.device_id not in self.card_devices[ck]),
            "device_age_days": t.device_age_days,
            "is_foreign_country": int(t.country != dom_country),
            "is_new_merchant_for_card": int(t.merchant_id not in self.card_merchants[ck]),
            "is_high_risk_mcc": int(t.merchant_category in HIGH_RISK_MCC),
            "merchant_txns_10m": m_10m,
            "merchant_small_amt_10m": m_small_10m,
            "device_card_count_1h": len({c for _, c in dcards}),
            "session_behavior_score": t.session_behavior_score,
            "is_ecom": int(t.channel == "ecom"),
            **self._cycle3_features(t, ck, mk, dk, cnt, total),
        }

    def _cycle3_features(self, t, ck, mk, dk, cnt, total) -> dict:
        ts = t.timestamp
        # Circular hour deviation from the card's own habit (0 = usual time, 12 = opposite)
        s, c, n = self.card_hour_vec[ck]
        if n:
            mean_hour = float(np.arctan2(s / n, c / n)) * 24 / (2 * np.pi) % 24
            hour_dev = min(abs(ts.hour - mean_hour), 24 - abs(ts.hour - mean_hour))
        else:
            hour_dev = 0.0
        # Amount z-score against the card's own history
        if cnt >= 3:
            mean = total / cnt
            var = max(self.card_amt_sq[ck] / cnt - mean ** 2, 1e-6)
            z = abs(t.amount - mean) / np.sqrt(var)
        else:
            z = 0.0
        first_m, m_count = self.merchant_stats[mk]
        m_age = (ts - first_m).total_seconds() / 86400 if first_m is not None else 0.0
        d_first = self.device_first_seen.get(dk)
        d_age = (ts - d_first).total_seconds() / 86400 if d_first is not None else 0.0
        return {
            "hour_dev_from_card_mean": float(hour_dev),
            "amount_zscore_card": float(min(z, 20.0)),
            "merchant_txn_count_log": float(np.log1p(m_count)),
            "merchant_observed_age_days": float(m_age),
            "device_observed_age_days": float(d_age),
            "device_alltime_cards": len(self.device_all_cards[dk]),
        }

    def update(self, t) -> None:
        """Fold transaction t into rolling state (called AFTER features_for)."""
        ck = self._k(t.institution_id, t.card_id)
        self.card_times[ck].append(t.timestamp)
        self.card_amounts[ck].append((t.timestamp, t.amount))
        self.card_devices[ck].add(t.device_id)
        self.card_merchants[ck].add(t.merchant_id)
        self.card_countries[ck][t.country] += 1
        st = self.card_amt_stats[ck]
        st[0] += 1
        st[1] += t.amount
        self.merchant_times[self._k(t.institution_id, t.merchant_id)].append((t.timestamp, t.amount))
        self.device_cards[self._k(t.institution_id, t.device_id)].append((t.timestamp, t.card_id))
        # Cycle 3 state
        mk, dk = self._k(t.institution_id, t.merchant_id), self._k(t.institution_id, t.device_id)
        ang = 2 * np.pi * t.timestamp.hour / 24
        hv = self.card_hour_vec[ck]
        hv[0] += float(np.sin(ang)); hv[1] += float(np.cos(ang)); hv[2] += 1
        self.card_amt_sq[ck] += t.amount ** 2
        ms = self.merchant_stats[mk]
        if ms[0] is None:
            ms[0] = t.timestamp
        ms[1] += 1
        self.device_first_seen.setdefault(dk, t.timestamp)
        self.device_all_cards[dk].add(t.card_id)


def build_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Replay the stream in event order and emit the point-in-time feature matrix."""
    store = InMemoryFeatureStore()
    rows = []
    for t in df.sort_values("timestamp").itertuples(index=False):
        rows.append(store.features_for(t))
        store.update(t)
    feats = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    out = df.sort_values("timestamp").reset_index(drop=True)
    meta_cols = ["transaction_id", "timestamp", "card_id", "label"] + \
        (["variant"] if "variant" in df.columns else [])
    return pd.concat([out[meta_cols], feats], axis=1)


if __name__ == "__main__":
    df = pd.read_parquet("data/transactions.parquet")
    ff = build_feature_frame(df)
    ff.to_parquet("data/features.parquet", index=False)
    fraud = (ff["label"] != "confirmed_legitimate")
    print(f"features rows={len(ff)}  cols={len(FEATURE_COLUMNS)}")
    print("\nmean feature values, fraud vs legit (sanity check):")
    print(ff.groupby(fraud.map({True: "fraud", False: "legit"}))[
        ["is_new_device_for_card", "is_foreign_country", "session_behavior_score",
         "merchant_small_amt_10m", "amount_over_card_avg"]].mean().round(3).to_string())
