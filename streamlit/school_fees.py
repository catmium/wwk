"""
School-fees reference data, loaded from data/school_fees.csv.

CSV columns (internal keys; Page 4 translates for display):
    school_name, level, country, school_type,
    age_min, age_max, annual_cost,
    original_amount, original_currency,
    notes, source_year, ref_url
"""
import os
import pandas as pd
import streamlit as st

CUSTOM_SCHOOL_SENTINEL = "(พิมพ์เอง / custom)"

_CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "school_fees.csv")


@st.cache_data(show_spinner=False)
def load_school_fees() -> pd.DataFrame:
    if not os.path.exists(_CSV_PATH):
        return pd.DataFrame(columns=[
            "school_name", "level", "country", "school_type",
            "age_min", "age_max", "annual_cost",
            "original_amount", "original_currency",
            "notes", "source_year", "ref_url",
        ])
    df = pd.read_csv(_CSV_PATH)
    for col in ("age_min", "age_max", "source_year"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in ("annual_cost", "original_amount"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("school_name", "level", "country", "school_type"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    return df


def schools_for_level(level: str) -> list[str]:
    """Distinct school_name list for a given education level."""
    if not level:
        return []
    df = load_school_fees()
    if df.empty or "level" not in df.columns:
        return []
    names = (
        df.loc[df["level"] == level, "school_name"]
        .dropna()
        .astype(str)
        .str.strip()
    )
    names = [n for n in names.unique().tolist() if n]
    names.sort()
    return names


def lookup(level: str, school_name: str) -> dict | None:
    """Return the first matching row as a dict, or None."""
    if not level or not school_name or school_name == CUSTOM_SCHOOL_SENTINEL:
        return None
    df = load_school_fees()
    if df.empty:
        return None
    mask = (df["level"] == level) & (df["school_name"] == school_name)
    rows = df.loc[mask]
    if rows.empty:
        return None
    row = rows.iloc[0].to_dict()
    return row
