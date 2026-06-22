"""Currency conversion — single source of truth for FX.

Rates live in data/fx_rate.csv (one THB-per-unit rate per currency). Everything
in the app is THB internally; convert at the edges with to_thb / to_ccy.
"""
import os
import pandas as pd
import streamlit as st

_CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "fx_rate.csv")


@st.cache_data(show_spinner=False)
def load_fx_table() -> pd.DataFrame:
    """Raw fx_rate.csv (currency, rate_to_thb, as_of_date) — for reference display."""
    if not os.path.exists(_CSV_PATH):
        return pd.DataFrame(columns=["currency", "rate_to_thb", "as_of_date"])
    return pd.read_csv(_CSV_PATH, encoding="utf-8-sig")


@st.cache_data(show_spinner=False)
def load_fx_rates() -> dict:
    """currency -> THB per 1 unit. Edit data/fx_rate.csv to update."""
    if not os.path.exists(_CSV_PATH):
        return {"THB": 1.0}
    df = pd.read_csv(_CSV_PATH, encoding="utf-8-sig")  # utf-8-sig strips the BOM
    rates = {
        str(r["currency"]).strip(): float(r["rate_to_thb"])
        for _, r in df.iterrows()
        if str(r.get("currency", "")).strip()
    }
    rates.setdefault("THB", 1.0)
    return rates


def _rate_for(currency, rate, rates):
    ccy = str(currency or "THB").strip() or "THB"
    if rate is not None:
        return float(rate)
    r = (rates or load_fx_rates()).get(ccy)
    if r is None:
        raise KeyError(f"No FX rate for {ccy!r} — add it to data/fx_rate.csv")
    return float(r)


def to_thb(amount, currency, rate=None, rates=None) -> float:
    """Convert `amount` in `currency` to THB.

    rate: optional explicit THB-per-unit override. When None, uses fx_rate.csv.
    (This override is the seam a future per-year / FX-risk rate slots into
    without changing callers.)
    """
    if amount is None or pd.isna(amount):
        return 0.0
    return float(amount) * _rate_for(currency, rate, rates)


def to_ccy(amount_thb, currency, rate=None, rates=None) -> float:
    """Convert THB back to `currency` (the reverse direction)."""
    if amount_thb is None or pd.isna(amount_thb):
        return 0.0
    return float(amount_thb) / _rate_for(currency, rate, rates)
