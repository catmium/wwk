from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from scipy.stats import norm, t as student_t

from portfolio_bucket_engine import (
    BucketFundingRule,
    validate_bucket_configs,
    validate_bucket_funding_rule,
    default_bucket_configs,
    prepare_annual_expense,
    assign_expense_to_buckets,
    calculate_bucket_requirements,
    allocate_initial_savings_to_buckets,
    _bucket_names_in_order,
)

# ============================================================
# MONTE CARLO DATA MODELS
# ============================================================

@dataclass
class AssetReturnModel:
    """
    สมมติฐานผลตอบแทนของ asset แต่ละตัวภายใน bucket

    Parameters
    ----------
    asset_name : str
        ชื่อ asset เช่น "SET Index ETF", "Gov Bond Fund"
    weight : float
        สัดส่วนภายใน bucket (0–100 เป็น %) หรือ 0.0–1.0 fraction
        ระบบจะ normalize อัตโนมัติ
    mean_return : float
        expected annual return (0.06 = 6%)
    std_dev : float
        annual volatility
    min_return : Optional[float]
        lower bound สำหรับ clipping return
    max_return : Optional[float]
        upper bound สำหรับ clipping return
    distribution : str
        currently supported: "normal" | "fixed"
    """
    asset_name: str
    weight: float          # เก็บเป็น % (0-100) หรือ fraction (0-1) ก็ได้ — normalize ก่อนใช้
    mean_return: float
    std_dev: float
    min_return: Optional[float] = None
    max_return: Optional[float] = None
    distribution: str = "normal"


@dataclass
class BucketReturnModel:
    """
    สมมติฐานผลตอบแทนของ bucket สำหรับ Monte Carlo

    Parameters
    ----------
    bucket_name : str
        ชื่อ bucket เช่น liquidity / stability / growth
    mean_return : float
        expected annual return — ใช้เมื่อ assets ว่าง
    std_dev : float
        annual volatility — ใช้เมื่อ assets ว่าง
    min_return : Optional[float]
        lower bound สำหรับ clipping — ใช้เมื่อ assets ว่าง
    max_return : Optional[float]
        upper bound สำหรับ clipping — ใช้เมื่อ assets ว่าง
    distribution : str
        "normal" | "fixed" — ใช้เมื่อ assets ว่าง
    assets : List[AssetReturnModel]
        รายการ asset ย่อยใน bucket
        ถ้ามี (non-empty) จะ simulate แต่ละ asset แล้วรวม weighted average
        ถ้าว่าง จะ fallback ไป bucket-level mean/std
    intra_bucket_correlation : Optional[float]
        ค่า off-diagonal correlation ระหว่าง asset ภายใน bucket นี้
        ถ้า None จะ fallback ไป DEFAULT_INTRA_BUCKET_CORRELATION ตาม bucket_name
    """
    bucket_name: str
    mean_return: float
    std_dev: float
    min_return: Optional[float] = None
    max_return: Optional[float] = None
    distribution: str = "normal"
    assets: List[AssetReturnModel] = field(default_factory=list)
    intra_bucket_correlation: Optional[float] = None


# Hardcoded default intra-bucket correlation per design intent:
# liquidity is least correlated internally, growth most correlated.
# These apply only when BucketReturnModel.assets is non-empty and
# intra_bucket_correlation is not set on the model.
DEFAULT_INTRA_BUCKET_CORRELATION: Dict[str, float] = {
    "liquidity": 0.1,
    "stability": 0.3,
    "growth": 0.5,
    # Thai 2-bucket scheme (load-bearing keys used throughout MC engine):
    "สำหรับค่าใช้จ่ายระยะสั้น": 0.1,   # short / bill-paying bucket (years 1-3)
    "สำหรับค่าใช้จ่ายระยะยาว": 0.3,    # long / growth bucket (years 4-∞)
}


@dataclass
class MonteCarloConfig:
    """
    config สำหรับรัน Monte Carlo

    Attributes
    ----------
    keep_path_detail : bool
        เก็บ path × year × bucket detail (mc_path_detail_df)
        ใช้ memory ~N_paths × N_years × N_buckets rows
    keep_asset_detail : bool
        เก็บ path × year × bucket × asset detail (mc_path_asset_detail_df)
        ใช้สำหรับ debug/recheck logic — โดยเฉพาะการตรวจว่า weighted return ถูกต้อง
        เวลาที่เพิ่ม: negligible (sampling เกิดแล้ว แค่เก็บ intermediate results)
        memory: ~N_paths × N_years × N_buckets × N_assets rows
    """
    n_paths: int = 1000
    random_seed: Optional[int] = 42
    keep_path_detail: bool = False
    keep_asset_detail: bool = False
    success_threshold: float = 0.0


@dataclass
class TermAssetConfig:
    """
    สินทรัพย์แบบมี term (structured fund / structured note / term fund / term deposit)

    คุณสมบัติ
    --------
    - ซื้อปีเดียว (buy_year) ด้วยเงินก้อนขั้นต่ำ (min_initial_investment)
    - ล็อกจนครบกำหนด (term_years ปี) — ห้ามขาย/เติมระหว่างทาง
    - ครบกำหนดได้เงินก้อน (principal + gains) — rollover ได้สูงสุด max_rollovers ครั้ง
      (rollover = ล็อกเงินก้อนที่ครบกำหนดทั้งหมดต่ออีก 1 term)
    - เงินซื้อหักจาก LONG bucket; ถ้าเงินไม่พอ → ข้ามการซื้อทั้งก้อน

    Distribution (ผูกกับ payoff type)
    --------------------------------
    - "fixed"     : principal-protected / contractual (term deposit, capital-guaranteed note)
                    std_dev=0 → ผลตอบแทนคงที่ทุกปี = mean_return
    - "student_t" : market-linked / NAV-floating (term fund, participation structured note)
                    fat-tailed df=5 + clip ด้วย min_return/max_return

    Parameters
    ----------
    name : str
    buy_year : int
        ปีที่ซื้อ (absolute year)
    min_initial_investment : float
        เงินก้อนขั้นต่ำที่ต้องมีใน LONG bucket จึงจะซื้อได้
    term_years : int
        ความยาว term (>= 1)
    max_rollovers : int
        จำนวนครั้ง rollover สูงสุด (0 = ครบกำหนดแล้วจบ)
    mean_return : float
        expected annual return
    std_dev : float
        annual volatility (ต้อง 0 เมื่อ distribution="fixed")
    min_return / max_return : Optional[float]
        clip bounds ต่อปี
    distribution : str
        "fixed" | "student_t"
    """
    name: str
    buy_year: int
    min_initial_investment: float
    term_years: int
    max_rollovers: int = 0
    mean_return: float = 0.0
    std_dev: float = 0.0
    min_return: Optional[float] = None
    max_return: Optional[float] = None
    distribution: str = "fixed"


def validate_term_assets(term_assets: Optional[List[TermAssetConfig]]) -> None:
    """
    validate รายการ term asset:
    - name ไม่ว่าง/ไม่ซ้ำ
    - buy_year, term_years, min_initial_investment, max_rollovers ใช้ได้
    - distribution รองรับ ("fixed" | "student_t")
    - fixed ต้อง std_dev == 0
    - min_return <= max_return
    """
    if not term_assets:
        return

    allowed_dist = {"fixed", "student_t"}
    seen = set()

    for t in term_assets:
        if not t.name:
            raise ValueError("TermAssetConfig.name must not be empty")
        if t.name in seen:
            raise ValueError(f"Duplicate term asset name: {t.name}")
        seen.add(t.name)

        if int(t.term_years) < 1:
            raise ValueError(f"term_years must be >= 1 for term asset={t.name}")
        if float(t.min_initial_investment) <= 0:
            raise ValueError(
                f"min_initial_investment must be > 0 for term asset={t.name}"
            )
        if int(t.max_rollovers) < 0:
            raise ValueError(f"max_rollovers must be >= 0 for term asset={t.name}")

        if t.distribution not in allowed_dist:
            raise ValueError(
                f"Unsupported distribution '{t.distribution}' for term asset={t.name}. "
                f"Allowed values are {sorted(allowed_dist)}"
            )
        if float(t.std_dev) < 0:
            raise ValueError(f"std_dev must be >= 0 for term asset={t.name}")
        if t.distribution == "fixed" and float(t.std_dev) != 0:
            raise ValueError(
                f"For distribution='fixed', std_dev should be 0 for term asset={t.name}"
            )
        if (
            t.min_return is not None
            and t.max_return is not None
            and float(t.min_return) > float(t.max_return)
        ):
            raise ValueError(
                f"min_return must be <= max_return for term asset={t.name}"
            )


# NOTE: path summary มาจาก runtime DataFrame ที่สร้าง column ต่อ bucket
# แบบ dynamic ใน build_*_summary_df (ดู mc_path_summary_df ใน BucketMCResult).
# ไม่ใช้ dataclass เพื่อให้รองรับชื่อ bucket แบบกำหนดเอง (B6).


@dataclass
class BucketMCResult:
    bucket_requirement_df: pd.DataFrame
    initial_allocation_df: pd.DataFrame
    mc_year_summary_df: pd.DataFrame
    mc_bucket_summary_df: pd.DataFrame
    mc_engine_summary_df: pd.DataFrame
    mc_path_summary_df: pd.DataFrame
    mc_path_detail_df: pd.DataFrame
    # Asset-level detail — only populated when mc_config.keep_asset_detail=True
    # columns: path_id, year, bucket_name, asset_name, weight_pct, weight_normalized,
    #          sampled_return, weighted_contribution
    mc_path_asset_detail_df: pd.DataFrame = None
    # Term-asset purchase-skip summary — one row per term asset.
    # columns: term_name, buy_year, n_paths, n_skipped, skip_probability
    # Surfaces the % of simulated paths where a term asset could NOT be
    # purchased because the LONG bucket lacked the minimum investment.
    mc_term_skip_summary_df: pd.DataFrame = None

    def __post_init__(self):
        if self.mc_path_asset_detail_df is None:
            self.mc_path_asset_detail_df = pd.DataFrame()
        if self.mc_term_skip_summary_df is None:
            self.mc_term_skip_summary_df = pd.DataFrame()


# ============================================================
# DEFAULT MONTE CARLO CONFIG / HELPERS
# ============================================================

def default_bucket_return_models() -> List[BucketReturnModel]:
    """
    default assumption แบบง่ายก่อน
    intra_bucket_correlation ตั้งไว้ตาม DEFAULT_INTRA_BUCKET_CORRELATION
    """
    return [
        BucketReturnModel(
            bucket_name="liquidity",
            mean_return=0.02,
            std_dev=0.01,
            min_return=-0.05,
            max_return=0.08,
            distribution="normal",
            intra_bucket_correlation=DEFAULT_INTRA_BUCKET_CORRELATION["liquidity"],
        ),
        BucketReturnModel(
            bucket_name="stability",
            mean_return=0.04,
            std_dev=0.06,
            min_return=-0.20,
            max_return=0.20,
            distribution="normal",
            intra_bucket_correlation=DEFAULT_INTRA_BUCKET_CORRELATION["stability"],
        ),
        BucketReturnModel(
            bucket_name="growth",
            mean_return=0.06,
            std_dev=0.15,
            min_return=-0.40,
            max_return=0.40,
            distribution="normal",
            intra_bucket_correlation=DEFAULT_INTRA_BUCKET_CORRELATION["growth"],
        ),
    ]


def validate_bucket_return_models(
    bucket_return_models: List[BucketReturnModel],
    expected_bucket_names: Optional[List[str]] = None,
) -> None:
    """
    validate ว่า:
    - bucket_name ไม่ซ้ำ
    - mean/std ใช้ได้
    - distribution รองรับ
    - min/max ใช้ได้
    - ถ้ามี expected_bucket_names ต้อง match กันครบ
    """
    if not bucket_return_models:
        raise ValueError("bucket_return_models must not be empty")

    seen = set()
    allowed_dist = {"normal", "fixed", "student_t"}

    for m in bucket_return_models:
        if not m.bucket_name:
            raise ValueError("bucket_name must not be empty")

        if m.bucket_name in seen:
            raise ValueError(
                f"Duplicate bucket_name found in bucket_return_models: {m.bucket_name}"
            )
        seen.add(m.bucket_name)

        if m.distribution not in allowed_dist:
            raise ValueError(
                f"Unsupported distribution '{m.distribution}' for bucket={m.bucket_name}. "
                f"Allowed values are {sorted(allowed_dist)}"
            )

        if m.std_dev < 0:
            raise ValueError(
                f"std_dev must be >= 0 for bucket={m.bucket_name}"
            )

        if m.min_return is not None and m.max_return is not None and m.min_return > m.max_return:
            raise ValueError(
                f"min_return must be <= max_return for bucket={m.bucket_name}"
            )

        if m.distribution == "fixed" and m.std_dev != 0:
            raise ValueError(
                f"For distribution='fixed', std_dev should be 0 for bucket={m.bucket_name}"
            )

    # validate assets ภายใน bucket ด้วย
    for m in bucket_return_models:
        if m.assets:
            total_w = sum(float(a.weight) for a in m.assets)
            if total_w <= 0:
                raise ValueError(
                    f"bucket={m.bucket_name}: sum of asset weights must be > 0"
                )
            asset_names = [a.asset_name for a in m.assets]
            if len(asset_names) != len(set(asset_names)):
                raise ValueError(
                    f"bucket={m.bucket_name}: duplicate asset names found"
                )
            for a in m.assets:
                if a.std_dev < 0:
                    raise ValueError(
                        f"bucket={m.bucket_name}, asset={a.asset_name}: std_dev must be >= 0"
                    )
                if a.distribution not in {"normal", "fixed", "student_t"}:
                    raise ValueError(
                        f"bucket={m.bucket_name}, asset={a.asset_name}: "
                        f"unsupported distribution '{a.distribution}'"
                    )

            # validate intra_bucket_correlation (R1)
            if m.intra_bucket_correlation is not None:
                rho = float(m.intra_bucket_correlation)
                if rho < -1.0 or rho > 1.0:
                    raise ValueError(
                        f"bucket={m.bucket_name}: intra_bucket_correlation must be in [-1, 1]"
                    )

    if expected_bucket_names is not None:
        exp = list(expected_bucket_names)
        if set(exp) != seen:
            raise ValueError(
                "bucket_return_models bucket names do not match expected_bucket_names. "
                f"expected={sorted(set(exp))}, actual={sorted(seen)}"
            )


def validate_monte_carlo_config(mc_config: MonteCarloConfig) -> None:
    """
    validate MC config
    """
    if mc_config.n_paths < 1:
        raise ValueError("MonteCarloConfig.n_paths must be >= 1")

    if mc_config.success_threshold is None:
        raise ValueError("MonteCarloConfig.success_threshold must not be None")


# ============================================================
# RETURN SAMPLING
# ============================================================

def _resolve_intra_bucket_correlation(
    model: BucketReturnModel,
    n_assets: int,
) -> np.ndarray:
    """
    Build the (n_assets x n_assets) constant-off-diagonal correlation matrix
    for assets ภายใน bucket.

    Correlation is hard-coded per bucket via DEFAULT_INTRA_BUCKET_CORRELATION
    (default 0.3 ถ้า bucket_name ไม่อยู่ใน map). Per-model overrides
    (intra_bucket_correlation) are intentionally NOT honored —
    correlation is a fixed engine assumption, not a user-tunable knob.

    Off-diagonal values are clamped to (-0.999, 0.999) to keep the resulting
    covariance matrix strictly positive definite for numpy.multivariate_normal.
    """
    if n_assets <= 0:
        raise ValueError("n_assets must be > 0")
    if n_assets == 1:
        return np.ones((1, 1), dtype=float)

    rho = float(DEFAULT_INTRA_BUCKET_CORRELATION.get(model.bucket_name, 0.3))
    rho = max(-0.999, min(0.999, rho))
    mat = np.full((n_assets, n_assets), rho, dtype=float)
    np.fill_diagonal(mat, 1.0)
    return mat


def _build_path_rng(
    mc_config: MonteCarloConfig,
    path_id: int,
):
    """
    helper สำหรับสร้าง random generator ของแต่ละ path
    - ถ้ามี random_seed จะใช้ random_seed + path_id
    - ถ้าไม่มี random_seed จะใช้ RNG แบบ random state ใหม่
    """
    if mc_config.random_seed is None:
        return np.random.default_rng()
    return np.random.default_rng(int(mc_config.random_seed) + int(path_id))


# ============================================================
# PHASE MC-4 IMPLEMENTATION
# ============================================================

def build_mc_year_summary(
    mc_path_detail_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    aggregate path detail เป็น summary ระดับปี / bucket

    Expected input columns:
    - path_id
    - year
    - bucket_name
    - ending_balance
    - is_shortfall
    - investment_return

    Expected output columns:
    - year
    - bucket_name
    - p10_ending_balance
    - p50_ending_balance
    - p90_ending_balance
    - shortfall_probability
    - mean_investment_return
    """
    if mc_path_detail_df is None or mc_path_detail_df.empty:
        return pd.DataFrame(columns=[
            "year",
            "bucket_name",
            "p10_ending_balance",
            "p50_ending_balance",
            "p90_ending_balance",
            "shortfall_probability",
            "mean_investment_return",
        ])

    required_cols = [
        "path_id",
        "year",
        "bucket_name",
        "ending_balance",
        "is_shortfall",
        "investment_return",
    ]
    missing_cols = [c for c in required_cols if c not in mc_path_detail_df.columns]
    if missing_cols:
        raise ValueError(
            f"mc_path_detail_df is missing required columns: {missing_cols}"
        )

    df = mc_path_detail_df.copy()
    df["path_id"] = pd.to_numeric(df["path_id"], errors="raise").astype(int)
    df["year"] = pd.to_numeric(df["year"], errors="raise").astype(int)
    df["bucket_name"] = df["bucket_name"].astype(str)
    df["ending_balance"] = pd.to_numeric(df["ending_balance"], errors="raise").astype(float)
    df["investment_return"] = pd.to_numeric(df["investment_return"], errors="raise").astype(float)
    df["is_shortfall"] = df["is_shortfall"].astype(bool)

    rows = []

    grouped = df.groupby(["year", "bucket_name"], as_index=False)

    for (year, bucket_name), sub in grouped:
        ending_vals = sub["ending_balance"].astype(float)
        shortfall_prob = float(sub["is_shortfall"].mean())
        mean_inv_ret = float(sub["investment_return"].mean())

        rows.append({
            "year": int(year),
            "bucket_name": str(bucket_name),
            "p10_ending_balance": round(float(ending_vals.quantile(0.10)), 2),
            "p50_ending_balance": round(float(ending_vals.quantile(0.50)), 2),
            "p90_ending_balance": round(float(ending_vals.quantile(0.90)), 2),
            "shortfall_probability": round(shortfall_prob, 6),
            "mean_investment_return": round(mean_inv_ret, 2),
        })

    out = pd.DataFrame(rows)
    out = out.sort_values(["year", "bucket_name"]).reset_index(drop=True)
    return out


def build_mc_bucket_summary(
    mc_path_detail_df: pd.DataFrame,
    mc_path_summary_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    aggregate เป็น summary ระดับ bucket

    Expected input columns:
    mc_path_detail_df:
    - path_id
    - year
    - bucket_name
    - ending_balance
    - is_shortfall

    mc_path_summary_df:
    - path_id
    - path_success
    - final_total_balance
    - total_shortfall_amount
    - first_shortfall_year
    - <bucket_name>_terminal_balance — dynamic ต่อ bucket
      (รองรับชื่อ bucket แบบกำหนดเอง)

    Expected output columns:
    - bucket_name
    - success_probability
    - shortfall_probability
    - expected_terminal_balance
    - p10_terminal_balance
    - p50_terminal_balance
    - p90_terminal_balance
    - expected_shortfall
    """
    if mc_path_detail_df is None or mc_path_detail_df.empty:
        return pd.DataFrame(columns=[
            "bucket_name",
            "success_probability",
            "shortfall_probability",
            "expected_terminal_balance",
            "p10_terminal_balance",
            "p50_terminal_balance",
            "p90_terminal_balance",
            "expected_shortfall",
        ])

    required_detail_cols = [
        "path_id",
        "year",
        "bucket_name",
        "ending_balance",
        "is_shortfall",
    ]
    missing_detail_cols = [c for c in required_detail_cols if c not in mc_path_detail_df.columns]
    if missing_detail_cols:
        raise ValueError(
            f"mc_path_detail_df is missing required columns: {missing_detail_cols}"
        )

    df = mc_path_detail_df.copy()
    df["path_id"] = pd.to_numeric(df["path_id"], errors="raise").astype(int)
    df["year"] = pd.to_numeric(df["year"], errors="raise").astype(int)
    df["bucket_name"] = df["bucket_name"].astype(str)
    df["ending_balance"] = pd.to_numeric(df["ending_balance"], errors="raise").astype(float)
    df["is_shortfall"] = df["is_shortfall"].astype(bool)

    # terminal balance by path / bucket
    last_year_df = (
        df.sort_values(["path_id", "bucket_name", "year"])
        .groupby(["path_id", "bucket_name"], as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )

    rows = []

    grouped = last_year_df.groupby("bucket_name", as_index=False)

    for bucket_name, sub in grouped:
        terminal_vals = sub["ending_balance"].astype(float)

        # bucket success = bucket never shortfall ใน path นั้น
        bucket_path_shortfall = (
            df.loc[df["bucket_name"] == bucket_name]
            .groupby("path_id", as_index=False)["is_shortfall"]
            .any()
            .rename(columns={"is_shortfall": "has_shortfall"})
        )
        success_prob = float((~bucket_path_shortfall["has_shortfall"]).mean())
        shortfall_prob = float(bucket_path_shortfall["has_shortfall"].mean())

        # expected shortfall = เฉลี่ยเฉพาะส่วนที่ terminal balance ติดลบ
        negative_terminal = terminal_vals[terminal_vals < 0]
        expected_shortfall = float(abs(negative_terminal.mean())) if len(negative_terminal) > 0 else 0.0

        rows.append({
            "bucket_name": str(bucket_name),
            "success_probability": round(success_prob, 6),
            "shortfall_probability": round(shortfall_prob, 6),
            "expected_terminal_balance": round(float(terminal_vals.mean()), 2),
            "p10_terminal_balance": round(float(terminal_vals.quantile(0.10)), 2),
            "p50_terminal_balance": round(float(terminal_vals.quantile(0.50)), 2),
            "p90_terminal_balance": round(float(terminal_vals.quantile(0.90)), 2),
            "expected_shortfall": round(expected_shortfall, 2),
        })

    out = pd.DataFrame(rows)
    out = out.sort_values("bucket_name").reset_index(drop=True)
    return out


def build_mc_engine_summary(
    mc_path_summary_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    aggregate เป็น summary ทั้ง engine

    Expected input columns:
    - path_id
    - path_success
    - final_total_balance
    - total_shortfall_amount
    - first_shortfall_year
    - <bucket_name>_terminal_balance — dynamic ต่อ bucket
      (รองรับชื่อ bucket แบบกำหนดเอง)

    Expected output columns:
    - n_paths
    - success_probability
    - shortfall_probability
    - expected_final_total_balance
    - p10_final_total_balance
    - p50_final_total_balance
    - p90_final_total_balance
    - expected_shortfall
    - worst_shortfall
    - first_shortfall_year_mode
    """
    if mc_path_summary_df is None or mc_path_summary_df.empty:
        return pd.DataFrame(columns=[
            "n_paths",
            "success_probability",
            "shortfall_probability",
            "expected_final_total_balance",
            "p10_final_total_balance",
            "p50_final_total_balance",
            "p90_final_total_balance",
            "expected_shortfall",
            "worst_shortfall",
            "first_shortfall_year_mode",
        ])

    required_cols = [
        "path_id",
        "path_success",
        "final_total_balance",
        "total_shortfall_amount",
        "first_shortfall_year",
    ]
    missing_cols = [c for c in required_cols if c not in mc_path_summary_df.columns]
    if missing_cols:
        raise ValueError(
            f"mc_path_summary_df is missing required columns: {missing_cols}"
        )

    df = mc_path_summary_df.copy()
    df["path_id"] = pd.to_numeric(df["path_id"], errors="raise").astype(int)
    df["path_success"] = df["path_success"].astype(bool)
    df["final_total_balance"] = pd.to_numeric(df["final_total_balance"], errors="raise").astype(float)
    df["total_shortfall_amount"] = pd.to_numeric(df["total_shortfall_amount"], errors="raise").astype(float)

    n_paths = int(df["path_id"].nunique())
    success_probability = float(df["path_success"].mean())
    shortfall_probability = 1.0 - success_probability

    final_vals = df["final_total_balance"].astype(float)
    shortfall_vals = df["total_shortfall_amount"].astype(float)

    expected_shortfall = float(shortfall_vals.mean())
    worst_shortfall = float(shortfall_vals.max())

    # mode ของ first_shortfall_year (ถ้ามี)
    shortfall_year_series = df["first_shortfall_year"].dropna()
    if shortfall_year_series.empty:
        first_shortfall_year_mode: Optional[int] = None
    else:
        # mode() อาจได้หลายค่า เอาค่าแรก
        first_shortfall_year_mode = int(pd.Series(shortfall_year_series).mode().iloc[0])

    out = pd.DataFrame([{
        "n_paths": n_paths,
        "success_probability": round(success_probability, 6),
        "shortfall_probability": round(shortfall_probability, 6),
        "expected_final_total_balance": round(float(final_vals.mean()), 2),
        "p10_final_total_balance": round(float(final_vals.quantile(0.10)), 2),
        "p50_final_total_balance": round(float(final_vals.quantile(0.50)), 2),
        "p90_final_total_balance": round(float(final_vals.quantile(0.90)), 2),
        "expected_shortfall": round(expected_shortfall, 2),
        "worst_shortfall": round(worst_shortfall, 2),
        "first_shortfall_year_mode": first_shortfall_year_mode,
    }])

    return out


# optimized version 2
# LEVEL-2 OPTIMIZATION HELPERS

def _prepare_l2_static_context(
    annual_expense_df: pd.DataFrame,
    annual_contribution_map: Dict[int, float],
    annual_topup_map: Dict[int, float],
    bucket_assignment_df: pd.DataFrame,
    bucket_configs: List,
    simulation_start_year: int,
    simulation_end_year: int,
) -> Dict[str, object]:
    """
    Build static arrays and index mappings once.
    This is the main Level-2 optimization: convert dict/string lookups into array indexing.
    """
    ordered_bucket_names = _bucket_names_in_order(bucket_configs)
    n_buckets = len(ordered_bucket_names)
    n_years = int(simulation_end_year) - int(simulation_start_year) + 1

    bucket_to_idx = {b: i for i, b in enumerate(ordered_bucket_names)}
    years = list(range(int(simulation_start_year), int(simulation_end_year) + 1))
    year_to_idx = {y: i for i, y in enumerate(years)}

    # contribution / topup arrays by year
    contribution_arr = np.zeros(n_years, dtype=float)
    topup_arr = np.zeros(n_years, dtype=float)

    for y, v in annual_contribution_map.items():
        if int(y) in year_to_idx:
            contribution_arr[year_to_idx[int(y)]] = float(v)

    for y, v in annual_topup_map.items():
        if int(y) in year_to_idx:
            topup_arr[year_to_idx[int(y)]] = float(v)

    # expense array [year_idx, bucket_idx]
    expense_arr = np.zeros((n_years, n_buckets), dtype=float)
    if bucket_assignment_df is not None and not bucket_assignment_df.empty:
        required_cols = ["year", "bucket_name", "total_expense"]
        missing_cols = [c for c in required_cols if c not in bucket_assignment_df.columns]
        if missing_cols:
            raise ValueError(
                f"bucket_assignment_df is missing required columns: {missing_cols}"
            )

        grouped = (
            bucket_assignment_df.groupby(["year", "bucket_name"], as_index=False)["total_expense"]
            .sum()
        )

        for _, r in grouped.iterrows():
            y = int(r["year"])
            b = str(r["bucket_name"])
            if y in year_to_idx and b in bucket_to_idx:
                expense_arr[year_to_idx[y], bucket_to_idx[b]] = float(r["total_expense"])

    # Rolling-window context (Harold Evensky bucket methodology):
    # - bucket_window_sizes[bi] = configured window length in years for finite buckets.
    #   The final bucket has end_offset_year=None and uses sentinel -1; at runtime it
    #   absorbs whatever horizon years remain after the finite buckets.
    # - total_expense_by_year_arr is total annual expense per year (NOT pre-assigned to
    #   buckets). Rolling target weights re-partition this total each year based on
    #   each bucket's rolling window starting at the current year.
    bucket_window_sizes = np.full(n_buckets, -1, dtype=int)
    cfg_map = {cfg.bucket_name: cfg for cfg in bucket_configs}
    for i, b in enumerate(ordered_bucket_names):
        cfg = cfg_map[b]
        if cfg.end_offset_year is None:
            bucket_window_sizes[i] = -1
        else:
            bucket_window_sizes[i] = int(cfg.end_offset_year) - int(cfg.start_offset_year) + 1

    total_expense_by_year_arr = expense_arr.sum(axis=1)

    # OPT-1: Precompute rolling-window target weights for ALL years once.
    # _compute_rebalance_targets depends only on path-invariant inputs, so we
    # hoist it out of the per-path-per-year hot loop. Path simulation indexes
    # this matrix as target_weights_matrix[yi] instead of recomputing.
    target_weights_matrix = np.zeros((n_years, n_buckets), dtype=float)
    for _yi in range(n_years):
        target_weights_matrix[_yi] = _compute_rebalance_targets(
            yi=_yi,
            n_years=n_years,
            total_expense_by_year_arr=total_expense_by_year_arr,
            bucket_window_sizes=bucket_window_sizes,
            n_buckets=n_buckets,
        )

    # year array as int64 for fast columnar buffer fills (avoids int() calls in loop)
    years_arr = np.array(years, dtype=np.int64)

    return {
        "ordered_bucket_names": ordered_bucket_names,
        "bucket_to_idx": bucket_to_idx,
        "years": years,
        "years_arr": years_arr,
        "year_to_idx": year_to_idx,
        "n_buckets": n_buckets,
        "n_years": n_years,
        "contribution_arr": contribution_arr,
        "topup_arr": topup_arr,
        "expense_arr": expense_arr,
        "bucket_window_sizes": bucket_window_sizes,
        "total_expense_by_year_arr": total_expense_by_year_arr,
        "target_weights_matrix": target_weights_matrix,
    }


def _build_initial_balance_and_requirement_arrays(
    initial_allocation_df: pd.DataFrame,
    bucket_to_idx: Dict[str, int],
    n_buckets: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Convert initial_allocation_df into dense arrays.
    """
    balances0 = np.zeros(n_buckets, dtype=float)
    remaining_required0 = np.zeros(n_buckets, dtype=float)

    required_cols = ["bucket_name", "recommended_initial_amount", "unmet_required_amount"]
    missing_cols = [c for c in required_cols if c not in initial_allocation_df.columns]
    if missing_cols:
        raise ValueError(
            f"initial_allocation_df is missing required columns: {missing_cols}"
        )

    for _, r in initial_allocation_df.iterrows():
        b = str(r["bucket_name"])
        idx = bucket_to_idx[b]
        balances0[idx] = float(r["recommended_initial_amount"])
        remaining_required0[idx] = float(r["unmet_required_amount"])

    return balances0, remaining_required0


def _sample_returns_for_path(
    path_id: int,
    years: List[int],
    ordered_bucket_names: List[str],
    bucket_return_models: List[BucketReturnModel],
    mc_config: MonteCarloConfig,
    capture_detail: bool = False,
) -> Tuple[np.ndarray, List[dict]]:
    """
    Vectorized return sampler for Level-2 MC (A6).

    Per bucket, samples ALL years in a single multivariate_normal call instead of
    one call per (year, bucket). This reduces the number of RNG calls from
    n_years*n_buckets to n_buckets per path.

    Behaviour preserved vs the per-call version:
    - Per-bucket model is unchanged: same means, stds, correlation matrix and clipping.
    - Fixed-distribution assets still bypass the MVN draw (column overwritten with mean).
    - Same total RNG consumption per bucket: one MVN draw of size n_years uses the
      same underlying randomness as n_years independent MVN draws of size 1 in this
      bucket — only the dispatch shape changes.
    - capture_detail=True/False produce identical sampled_returns.

    Note: numerical path outputs vs the prior per-call sampler will differ for the
    same seed because the RNG stream is consumed in a different order. Existing
    tests assert per-call reproducibility on sample_one_bucket_return (unchanged)
    and statistical invariants, not path-level byte equality.
    """
    model_map = {m.bucket_name: m for m in bucket_return_models}
    n_years = len(years)
    n_buckets = len(ordered_bucket_names)
    out = np.zeros((n_years, n_buckets), dtype=float)
    asset_detail_rows: List[dict] = []

    rng = _build_path_rng(mc_config, path_id)

    # Gaussian copula refactor:
    #   1) Draw correlated standard-normal z via MVN with intra-bucket corr (size=n_years)
    #   2) Map to uniforms u = Phi(z) (norm.cdf)
    #   3) Map uniforms to t df=5 marginals: x = t.ppf(u, df=5)
    #   4) Scale per asset: r = mean + std * x
    #   5) Clip per asset's min/max
    #
    # Properties:
    #   - intra-bucket dependence preserved (rank correlation = Gaussian copula)
    #   - marginals are Student-t df=5 (hard-coded, fat tails)
    #   - years are iid (no autocorrelation): each row of MVN is independent
    #   - buckets are independent (no cross-bucket correlation): drawn in separate
    #     MVN calls from the same per-path RNG (seeded random_seed + path_id)
    #   - "fixed" distribution short-circuits: constant mean, no sampling
    DF_T = 5

    for bi, bucket_name in enumerate(ordered_bucket_names):
        m = model_map[bucket_name]

        if m.assets:
            assets = m.assets
            n_assets = len(assets)
            total_w = sum(float(a.weight) for a in assets)
            if total_w <= 0:
                raise ValueError(
                    f"bucket={bucket_name}: sum of asset weights must be > 0"
                )

            weights = np.array(
                [float(a.weight) / total_w for a in assets], dtype=float
            )
            means = np.array([float(a.mean_return) for a in assets], dtype=float)
            stds = np.array([float(a.std_dev) for a in assets], dtype=float)
            corr = _resolve_intra_bucket_correlation(m, n_assets)

            # Step 1: correlated standard normals z ~ N(0, corr), shape (n_years, n_assets)
            mean_zero = np.zeros(n_assets, dtype=float)
            try:
                z = rng.multivariate_normal(mean=mean_zero, cov=corr, size=n_years)
            except (ValueError, np.linalg.LinAlgError):
                # Degenerate corr → fall back to independent standard normals; downstream
                # mapping still produces valid (uncorrelated) Student-t marginals.
                z = rng.standard_normal(size=(n_years, n_assets))

            # Steps 2-3: Gaussian copula → uniforms → Student-t df=5 marginals
            # Clip u away from {0, 1} to avoid ±inf from t.ppf at the tails.
            u = norm.cdf(z)
            u = np.clip(u, 1e-12, 1.0 - 1e-12)
            t_samples = student_t.ppf(u, df=DF_T)

            # Step 4: scale per asset (mean + std * x)
            samples = means + stds * t_samples

            # "fixed" override per asset (no sampling)
            for ai, asset in enumerate(assets):
                if asset.distribution == "fixed":
                    samples[:, ai] = float(asset.mean_return)

            # Step 5: clip per asset min/max
            for ai, asset in enumerate(assets):
                lo = asset.min_return
                hi = asset.max_return
                if lo is not None or hi is not None:
                    samples[:, ai] = np.clip(
                        samples[:, ai],
                        -np.inf if lo is None else float(lo),
                        np.inf if hi is None else float(hi),
                    )

            weighted = samples @ weights
            out[:, bi] = np.round(weighted, 8)

            if capture_detail:
                for yi in range(n_years):
                    year = int(years[yi])
                    for ai, asset in enumerate(assets):
                        asset_r = float(samples[yi, ai])
                        asset_detail_rows.append({
                            "path_id": int(path_id),
                            "year": year,
                            "bucket_name": str(bucket_name),
                            "asset_name": str(asset.asset_name),
                            "weight_pct": round(float(asset.weight), 4),
                            "weight_normalized": round(float(weights[ai]), 6),
                            "sampled_return": round(asset_r, 8),
                            "weighted_contribution": round(
                                float(weights[ai]) * asset_r, 8
                            ),
                        })

        else:
            # Bucket-level path (no per-asset breakdown): single-marginal Student-t df=5.
            if m.distribution == "fixed":
                samples = np.full(n_years, float(m.mean_return), dtype=float)
            else:
                # student_t df=5 (hard-coded for all non-fixed). Use the copula stack
                # for stylistic parity with the asset path: z → u → t.ppf → scale.
                z = rng.standard_normal(size=n_years)
                u = np.clip(norm.cdf(z), 1e-12, 1.0 - 1e-12)
                samples = float(m.mean_return) + float(m.std_dev) * student_t.ppf(u, df=DF_T)

            lo = m.min_return
            hi = m.max_return
            if lo is not None or hi is not None:
                samples = np.clip(
                    samples,
                    -np.inf if lo is None else float(lo),
                    np.inf if hi is None else float(hi),
                )

            out[:, bi] = np.round(samples, 8)

            if capture_detail:
                for yi in range(n_years):
                    year = int(years[yi])
                    r = float(samples[yi])
                    asset_detail_rows.append({
                        "path_id": int(path_id),
                        "year": year,
                        "bucket_name": str(bucket_name),
                        "asset_name": f"[bucket-level] {bucket_name}",
                        "weight_pct": 100.0,
                        "weight_normalized": 1.0,
                        "sampled_return": round(r, 8),
                        "weighted_contribution": round(r, 8),
                    })

    return out, asset_detail_rows


# Offset added to the per-path seed when drawing TERM-asset returns so their
# RNG stream is independent of the bucket-return stream (which uses
# random_seed + path_id). Large prime keeps the two streams from colliding.
_TERM_RNG_OFFSET = 7_000_003


def _sample_term_returns_for_path(
    path_id: int,
    n_years: int,
    term_assets: List[TermAssetConfig],
    mc_config: MonteCarloConfig,
) -> np.ndarray:
    """
    Sample per-year returns for each term asset on one path.

    Returns
    -------
    np.ndarray, shape (n_years, n_term)
        term_returns[yi, j] = sampled annual return for term asset j in year yi.

    Behaviour
    ---------
    - "fixed": constant mean_return every year (std_dev=0), no clipping needed.
    - "student_t" (and any non-fixed): Student-t df=5 marginal via the same
      copula stack used for bucket-level returns —
        z ~ N(0,1); u = Phi(z); x = t.ppf(u, df=5); r = mean + std*x; clip.
    - Years are iid (each row independent). RNG is seeded from
      random_seed + path_id + _TERM_RNG_OFFSET so term draws do not perturb
      the bucket-return stream for the same seed.
    """
    n_term = len(term_assets)
    out = np.zeros((n_years, n_term), dtype=float)
    if n_term == 0 or n_years == 0:
        return out

    if mc_config.random_seed is None:
        rng = np.random.default_rng()
    else:
        rng = np.random.default_rng(
            int(mc_config.random_seed) + int(path_id) + _TERM_RNG_OFFSET
        )

    DF_T = 5

    for j, t in enumerate(term_assets):
        if t.distribution == "fixed":
            out[:, j] = float(t.mean_return)
            continue

        z = rng.standard_normal(size=n_years)
        u = np.clip(norm.cdf(z), 1e-12, 1.0 - 1e-12)
        samples = float(t.mean_return) + float(t.std_dev) * student_t.ppf(u, df=DF_T)

        lo = t.min_return
        hi = t.max_return
        if lo is not None or hi is not None:
            samples = np.clip(
                samples,
                -np.inf if lo is None else float(lo),
                np.inf if hi is None else float(hi),
            )
        out[:, j] = samples

    return out


def _term_quality_sort_key(t: TermAssetConfig, input_index: int) -> Tuple[float, float, int, int]:
    """
    Ordering used to break ties when funds are insufficient to buy every term
    asset competing at the SAME lock moment (same buy_year).

    Priority (best first):
        1. higher mean_return   → sort by -mean_return ascending
        2. lower std_dev        → ascending
        3. shorter term_years   → ascending
        4. original input order → ascending input_index
    """
    return (-float(t.mean_return), float(t.std_dev), int(t.term_years), int(input_index))


def _build_term_context(
    term_assets: Optional[List[TermAssetConfig]],
    simulation_start_year: int,
) -> Dict[str, object]:
    """
    Precompute path-invariant term scheduling once.

    Lock timing (locked design):
    - buy_year > start  : principal is drawn from the LONG bucket at END of the
      year BEFORE buy_year (lock_year = buy_year - 1), AFTER that year's
      rebalance — so it never starves the short bucket. BB(buy_year) = principal,
      first accrual in buy_year.
    - buy_year == start : there is no prior plan year, so the principal is locked
      at the very START of year 0 (before inflow/rebalance). BB(buy_year) =
      principal immediately, first accrual still in buy_year.

    Maturity (deferred-payout design):
    - lock → accrue every year for term_years*(max_rollovers+1) years
      (last accrual at buy_year + term_years*(max_rollovers+1) - 1) → then a
      dedicated PAYOUT year at payout_year = buy_year + term_years*(max_rollovers+1)
      with NO accrual: BB = matured value, return = 0, EB = 0 (money withdrawn).
      The matured cash becomes usable in payout_year. Rollovers simply extend the
      accrual span; there is no intermediate re-lock event.

    Selection when funds are insufficient: assets sharing a lock moment are
    attempted in `_term_quality_sort_key` order; all-or-nothing per asset;
    skip-and-continue to the next affordable asset; a skip is permanent.
    """
    term_list = list(term_assets) if term_assets else []
    n_term = len(term_list)
    start_year = int(simulation_start_year)

    buy_year = [int(t.buy_year) for t in term_list]
    min_inv = [float(t.min_initial_investment) for t in term_list]
    term_len = [int(t.term_years) for t in term_list]
    max_rollovers = [int(t.max_rollovers) for t in term_list]
    payout_year = [buy_year[j] + term_len[j] * (max_rollovers[j] + 1) for j in range(n_term)]

    # start-of-year-0 locks (buy_year == start), quality-ordered
    start0_order = sorted(
        [j for j in range(n_term) if buy_year[j] <= start_year],
        key=lambda j: _term_quality_sort_key(term_list[j], j),
    )

    # EOY locks keyed by absolute lock_year (= buy_year - 1), quality-ordered
    eoy_locks_by_year: Dict[int, List[int]] = {}
    for j in range(n_term):
        if buy_year[j] > start_year:
            lock_year = buy_year[j] - 1
            eoy_locks_by_year.setdefault(lock_year, []).append(j)
    for lock_year, idxs in eoy_locks_by_year.items():
        idxs.sort(key=lambda j: _term_quality_sort_key(term_list[j], j))

    # NEW timing: a term locks at the START of its buy_year (after that year's
    # top-up). start0 terms (buy_year <= start) key at start_year (year 0) so a
    # year-0 top-up can fund them if the initial allocation fell short.
    locks_by_buy_year: Dict[int, List[int]] = {}
    for j in range(n_term):
        _eff = max(buy_year[j], start_year)
        locks_by_buy_year.setdefault(_eff, []).append(j)
    for _y, _idxs in locks_by_buy_year.items():
        _idxs.sort(key=lambda j: _term_quality_sort_key(term_list[j], j))

    return {
        "term_list": term_list,
        "n_term": n_term,
        "buy_year": buy_year,
        "min_inv": min_inv,
        "term_len": term_len,
        "max_rollovers": max_rollovers,
        "payout_year": payout_year,
        "start0_order": start0_order,
        "eoy_locks_by_year": eoy_locks_by_year,
        "locks_by_buy_year": locks_by_buy_year,
    }


def _allocate_yearly_inflow_to_buckets_array_fast(
    inflow_amount: float,
    remaining_required_arr: np.ndarray,
    priority_idx_arr: np.ndarray,
    n_buckets: int,
) -> np.ndarray:
    """
    Allocates the yearly inflow across buckets using a precomputed integer
    priority-index array (priority_idx_arr) — eliminates per-call string→idx
    dict lookups in the hot loop. The numerical sequence (subtraction order,
    branching) is preserved bit-for-bit.
    """
    if inflow_amount < 0:
        raise ValueError("inflow_amount must be >= 0")

    alloc = np.zeros(n_buckets, dtype=float)
    remaining_amount = float(inflow_amount)
    n_priority = priority_idx_arr.shape[0]

    for i in range(n_priority):
        idx = int(priority_idx_arr[i])
        need = max(0.0, float(remaining_required_arr[idx]))

        if remaining_amount <= 0:
            break

        give = min(remaining_amount, need)
        alloc[idx] += give
        remaining_amount -= give

    if remaining_amount > 0:
        last_idx = int(priority_idx_arr[n_priority - 1])
        alloc[last_idx] += remaining_amount

    return alloc


def _compute_rebalance_targets(
    yi: int,
    n_years: int,
    total_expense_by_year_arr: np.ndarray,
    bucket_window_sizes: np.ndarray,
    n_buckets: int,
) -> np.ndarray:
    """
    Rolling-window target weights (Harold Evensky bucket methodology).

    At current year offset `yi` (0-indexed), each bucket gets a rolling expense
    window starting at the current year. The windows are contiguous:
        - bucket 0 covers years [yi, yi + w0)
        - bucket 1 covers years [yi + w0, yi + w0 + w1)
        - ...
        - the LAST bucket (sentinel size = -1) absorbs years up to n_years.

    Target weight per bucket = (total expense in that bucket's rolling window)
                               / (total expense across all bucket windows).

    Notes
    -----
    - Uses total annual expense per year (sum across pre-assigned buckets), so the
      rolling window does NOT inherit the original bucket-level expense assignment.
    - If the current year is past the horizon or all windows have zero expense,
      returns equal weights to keep the rebalance well-defined.
    - Buckets whose window starts past the horizon have weight 0.
    """
    if n_buckets == 0:
        return np.zeros(0, dtype=float)

    window_expense = np.zeros(n_buckets, dtype=float)
    cursor = int(yi)

    for bi in range(n_buckets):
        if cursor >= n_years:
            continue

        is_last = (bi == n_buckets - 1)
        w = int(bucket_window_sizes[bi])

        if is_last or w < 0:
            end = n_years
        else:
            end = min(cursor + w, n_years)

        start = cursor
        if start < end:
            window_expense[bi] = float(total_expense_by_year_arr[start:end].sum())

        cursor = end

    total = float(window_expense.sum())
    if total <= 0:
        return np.full(n_buckets, 1.0 / n_buckets, dtype=float)
    return window_expense / total


def _simulate_one_mc_path_l2(
    path_id: int,
    static_ctx: Dict[str, object],
    initial_allocation_df: pd.DataFrame,
    bucket_configs: List,
    funding_rule,
    bucket_return_models: List[BucketReturnModel],
    mc_config: MonteCarloConfig,
    success_threshold: float,
    keep_path_detail: bool,
    keep_asset_detail: bool = False,
    term_assets: Optional[List[TermAssetConfig]] = None,
    detail_buffers: Optional[Dict[str, np.ndarray]] = None,
    path_offset: int = 0,
):
    """
    Level-2 optimized path simulation.

    Key differences vs quick-wins version:
    - balances / requirements / transfers / returns use numpy arrays
    - no per-year dict lookups in the hot loop
    - no DataFrame work in hot loop
    - optional path detail only if explicitly requested
    """
    years = static_ctx["years"]
    ordered_bucket_names = static_ctx["ordered_bucket_names"]
    bucket_to_idx = static_ctx["bucket_to_idx"]
    n_buckets = int(static_ctx["n_buckets"])
    n_years = int(static_ctx["n_years"])
    contribution_arr = static_ctx["contribution_arr"]
    topup_arr = static_ctx["topup_arr"]
    expense_arr = static_ctx["expense_arr"]
    bucket_window_sizes = static_ctx["bucket_window_sizes"]
    total_expense_by_year_arr = static_ctx["total_expense_by_year_arr"]
    # OPT-1: precomputed rolling-window target weights (hoisted out of hot loop)
    target_weights_matrix = static_ctx.get("target_weights_matrix")
    # OPT-4: precomputed integer priority indices (avoid per-call dict lookup)
    priority_idx_arr = static_ctx.get("priority_idx_arr")
    # OPT-B: reuse precomputed initial balance/requirement arrays (built ONCE in outer runner)
    balances0 = static_ctx.get("balances0")
    remaining_required0 = static_ctx.get("remaining_required0")

    if balances0 is not None and remaining_required0 is not None:
        # Copy is required — both arrays are mutated during simulation.
        balances = balances0.copy()
        remaining_required = remaining_required0.copy()
    else:
        balances, remaining_required = _build_initial_balance_and_requirement_arrays(
            initial_allocation_df=initial_allocation_df,
            bucket_to_idx=bucket_to_idx,
            n_buckets=n_buckets,
        )

    sampled_returns, _asset_detail_rows_all = _sample_returns_for_path(
        path_id=path_id,
        years=years,
        ordered_bucket_names=ordered_bucket_names,
        bucket_return_models=bucket_return_models,
        mc_config=mc_config,
        capture_detail=keep_asset_detail,
    )

    any_shortfall = False
    first_shortfall_year = None
    # Track minimum BUCKET 0 balance (the bill-paying bucket) instead of
    # min total portfolio. By design only bucket 0 is hit by expense_out;
    # bucket 1 going to zero is normal (rebalance drains it to refill
    # bucket 0). A real shortfall = bucket 0 ended a year < 0 (couldn't pay).
    min_bucket0_balance = float("inf")
    detail_rows = [] if keep_path_detail else None

    # OPT-A2: pre-allocate transfer buffers ONCE outside the year loop.
    # Each year resets via .fill(0.0); inplace helpers accumulate via +=.
    # Saves 2 * n_years * n_buckets-sized np.zeros() allocs per path.
    transfer_in = np.zeros(n_buckets, dtype=float)
    transfer_out = np.zeros(n_buckets, dtype=float)
    # OPT-D: reusable zero buffer for no-inflow shortcut (never mutated).
    _zero_contribution_buf = np.zeros(n_buckets, dtype=float)

    # ----------------------------------------------------
    # TERM-ASSET SIDECAR LEDGER (kept OUT of the balances array, projected as a
    # separate "term" track in the detail df via bucket_kind="term")
    # ----------------------------------------------------
    # Term money is drawn from / paid back to the LONG bucket only. While locked
    # it compounds in its own sidecar ledger (term_value) — it cannot pay
    # expenses, so it never touches the bucket-0 shortfall logic — yet it is
    # counted toward terminal wealth as illiquid money. The LONG-bucket cash
    # flows (lock draw, maturity payout) fold into the existing
    # transfer_out/transfer_in buffers so the liquid EB identity is preserved.
    # The term track is additionally emitted as its own detail rows where the
    # SAME identity holds:
    #   EB_term = BB_term + transfer_in(lock) + investment_return(accrual)
    #             − transfer_out(payout)
    #
    # Timing (locked design):
    #   - Lock at EOY of (buy_year-1), AFTER that year's rebalance, so the draw
    #     never starves the short bucket. First plan-year buys lock at the very
    #     START of year 0 instead (no prior year exists).
    #   - Accrue exactly term_years times (buy_year .. buy_year+term_years-1).
    #   - Maturity payout at EOY of payout_year = buy_year+term_years-1, BEFORE
    #     that year's rebalance (Choice B) so matured cash can refill the short
    #     bucket the same year.
    #   - Insufficient funds among assets sharing a lock moment: attempt in
    #     quality order (return desc → std asc → term asc → input order);
    #     all-or-nothing; skip-and-continue; a skip is permanent.
    term_ctx = static_ctx.get("term_ctx")
    if term_ctx is None:
        _first_year = int(years[0]) if n_years > 0 else 0
        term_ctx = _build_term_context(term_assets, _first_year)
    _term_list = term_ctx["term_list"]
    n_term = int(term_ctx["n_term"])
    long_idx = n_buckets - 1  # payout target == funding source == long bucket

    if n_term > 0:
        # Seed FIRST-YEAR (start0) holdings already pre-funded from the initial
        # allocation: those start active with BB = principal and no year-0
        # transfer_in. Everything else starts empty.
        _seed_vals = static_ctx.get("term_initial_values") or [0.0] * n_term
        term_value = [float(_seed_vals[j]) for j in range(n_term)]   # compounded value
        term_active = [term_value[j] > 0.0 for j in range(n_term)]   # currently locked?
        term_bought = [term_value[j] > 0.0 for j in range(n_term)]   # ever purchased?
        term_skipped = [False] * n_term                              # purchase skipped?
        term_rollovers_left = list(term_ctx["max_rollovers"])
        term_min_inv = term_ctx["min_inv"]
        term_len = term_ctx["term_len"]
        # absolute payout year per asset; re-pinned at lock time (rollover bumps it)
        term_maturity_year = [int(term_ctx["payout_year"][j]) for j in range(n_term)]
        start0_order = term_ctx["start0_order"]
        locks_by_buy_year = term_ctx["locks_by_buy_year"]
        term_returns = _sample_term_returns_for_path(
            path_id=path_id,
            n_years=n_years,
            term_assets=_term_list,
            mc_config=mc_config,
        )
        # Per-year capture buffers (reused each year) → written to term detail rows.
        tb_bb = np.zeros(n_term, dtype=float)        # term BB (start-of-year value)
        tb_in = np.zeros(n_term, dtype=float)        # principal locked in this year
        tb_out = np.zeros(n_term, dtype=float)       # matured lump paid out this year
        tb_ret = np.zeros(n_term, dtype=float)       # accrual this year (currency)
        tb_eb = np.zeros(n_term, dtype=float)        # term EB (end-of-year value)
        tb_sampled = np.zeros(n_term, dtype=float)   # sampled term return this year

    for yi in range(n_years):
        year = int(years[yi])

        # OPT-3: alias instead of copy — `balances` is reassigned to a NEW array on the next line,
        # so the original buffer (now aliased as beginning_balances) is no longer mutated.
        beginning_balances = balances

        # OPT-A2: reset transfer buffers in-place (no new allocation)
        transfer_in.fill(0.0)
        transfer_out.fill(0.0)

        # Per-year term capture buffers reset (consumed by term detail rows).
        # tb_bb is captured BEFORE any term event so the term-track EB identity
        #   EB_term = BB_term + transfer_in(lock) + investment_return(accrual)
        #             − transfer_out(payout)
        # holds per row. tb_sampled records this year's sampled term return.
        if n_term > 0:
            tb_bb.fill(0.0)
            tb_in.fill(0.0)
            tb_out.fill(0.0)
            tb_ret.fill(0.0)
            tb_eb.fill(0.0)
            tb_sampled.fill(0.0)
            for j in range(n_term):
                tb_bb[j] = float(term_value[j])
                tb_sampled[j] = float(term_returns[yi, j])

        # ── Inflow + term lock (start-of-year ordering) ──
        # `balances` currently aliases beginning_balances; copy so BB keeps the
        # pre-inflow state and we can mutate freely.
        balances = balances.copy()

        # 1) TOP-UP — a start-of-year lump routed to the LONG (growth) bucket so a
        #    term scheduled this year can be funded from it (rebalance later moves
        #    whatever the short bucket needs). Recorded per-bucket as topup_in.
        topup_in = np.zeros(n_buckets, dtype=float)
        _topup_total = float(topup_arr[yi])
        if _topup_total > 0 and n_buckets > 0:
            topup_in[long_idx] = _topup_total
            balances[long_idx] += _topup_total

        # 2) TERM LOCKS for buy_year == year (after top-up, BEFORE monthly
        #    contribution). Affordability = current LONG balance (= beginning +
        #    top-up). Includes year-0 retries of start0 terms the initial
        #    allocation could not fund. All-or-nothing; skip is permanent.
        if n_term > 0:
            for j in locks_by_buy_year.get(year, []):
                if term_bought[j] or term_skipped[j]:
                    continue
                if float(balances[long_idx]) >= term_min_inv[j]:
                    balances[long_idx] -= term_min_inv[j]
                    transfer_out[long_idx] += term_min_inv[j]
                    tb_in[j] += term_min_inv[j]
                    term_value[j] = term_min_inv[j]
                    term_active[j] = True
                    term_bought[j] = True
                    term_maturity_year[j] = int(term_ctx["payout_year"][j])
                else:
                    term_skipped[j] = True

        # 3) MONTHLY CONTRIBUTION (gradual) — allocated per the funding rule.
        _contrib_total = float(contribution_arr[yi])
        if _contrib_total <= 0:
            contribution_in = np.zeros(n_buckets, dtype=float)
        else:
            contribution_in = _allocate_yearly_inflow_to_buckets_array_fast(
                inflow_amount=_contrib_total,
                remaining_required_arr=remaining_required,
                priority_idx_arr=priority_idx_arr,
                n_buckets=n_buckets,
            )
        balances = balances + contribution_in

        # 4) RETURN — the lump (beginning + top-up − term draw) earns the FULL
        #    year; the gradual monthly contribution earns HALF a year (×0.5)
        #    because it is paid in over the year.
        _lump_base = balances - contribution_in
        investment_return = (
            np.where(_lump_base > 0, _lump_base * sampled_returns[yi], 0.0)
            + np.where(contribution_in > 0, contribution_in * sampled_returns[yi] * 0.5, 0.0)
        )
        np.round(investment_return, 2, out=investment_return)

        year_total_expense = float(total_expense_by_year_arr[yi])
        expense_out_arr = np.zeros(n_buckets, dtype=float)
        if n_buckets > 0:
            expense_out_arr[0] = year_total_expense

        balances = balances + investment_return - expense_out_arr
        np.round(balances, 2, out=balances)

        # TERM ACCRUAL (EOY) — active (locked) holdings compound by their own
        # TERM return stream. start0 holdings locked THIS year are active and
        # accrue now (first accrual = buy_year). EOY locks happen AFTER rebalance
        # below, so they are not yet active here and do not accrue in their lock
        # year. The dedicated PAYOUT year (year == term_maturity_year) is skipped
        # by the `year < term_maturity_year` guard, so the money earns no return
        # in the year it is withdrawn.
        if n_term > 0:
            for j in range(n_term):
                if term_active[j] and year < term_maturity_year[j]:
                    _accrual = float(term_value[j]) * float(term_returns[yi, j])
                    tb_ret[j] += _accrual
                    term_value[j] += _accrual

        # TERM MATURITY / PAYOUT (Choice B) — the payout year is a dedicated
        # no-accrual year (= buy + term*(rollovers+1)). BB == matured value;
        # withdraw the whole lump into the LONG bucket BEFORE rebalance so the
        # cash can fund THIS year's expense, then deactivate. Rollovers are
        # already baked into term_maturity_year, so there is no re-lock here.
        if n_term > 0:
            for j in range(n_term):
                if term_active[j] and term_maturity_year[j] == year:
                    payout = float(term_value[j])
                    balances[long_idx] += payout
                    transfer_in[long_idx] += payout
                    tb_out[j] += payout
                    term_active[j] = False
                    term_value[j] = 0.0

        # C) (removed) — no shortfall waterfall. Negative balances in the short
        # bucket are addressed by step D's fill-to-PV (which transfers from the
        # long bucket); residual gaps are recorded as shortfall.

        # D) Rebalance — fill SHORT bucket up to the next-year rolling expense
        # requirement, drawing from the LONG bucket (index 1). Requirement is
        # recomputed each year from the rolling expense window (nominal sum,
        # i.e. PV at 0% discount). When the long bucket cannot fully cover the
        # gap, the unfilled remainder is recorded as shortfall.
        if n_buckets >= 2:
            # Rolling next-year expense window for the SHORT bucket:
            # years [yi+1, yi+1+w_short). For the final year (no future expense)
            # the requirement is 0.
            w_short = int(bucket_window_sizes[0])
            if w_short < 0:
                w_short = 1  # safety: treat unbounded short bucket as window=1 year
            req_start = yi + 1
            req_end = min(req_start + w_short, n_years)
            if req_start < req_end:
                short_requirement = float(total_expense_by_year_arr[req_start:req_end].sum())
            else:
                short_requirement = 0.0

            short_gap = short_requirement - float(balances[0])
            if short_gap > 0:
                long_available = max(0.0, float(balances[1]))
                xfer = min(short_gap, long_available)
                if xfer > 0:
                    balances[0] += xfer
                    balances[1] -= xfer
                    transfer_in[0] += xfer
                    transfer_out[1] += xfer
                # NOTE: previous "rebalance ไม่ครบเป้า" flag removed —
                # under-filling bucket 0 is just "less buffer for next year",
                # not a real shortfall. Real shortfall = bucket 0 actually
                # ended a year < 0 (couldn't pay this year's expense). See
                # the bucket-0 check below.

        np.round(balances, 2, out=balances)

        # Track bucket 0's minimum balance (the bill-paying bucket).
        min_bucket0_balance = min(min_bucket0_balance, float(balances[0]))

        # Finalize term end-of-year value (EB_term) for the projected term track.
        # Captured AFTER accrual, maturity/payout, and EOY lock so the per-row
        # identity EB = BB + transfer_in(lock) + investment_return(accrual)
        #               − transfer_out(payout) holds for every term row.
        if n_term > 0:
            for j in range(n_term):
                tb_eb[j] = float(term_value[j])

        # Detail row still records per-bucket negative state (informational —
        # lets the user see if bucket 1 ever ran out in path_detail), but
        # ONLY bucket 0 going negative drives any_shortfall / path_success.
        is_shortfall_arr = balances < 0
        if is_shortfall_arr[0]:
            any_shortfall = True
            if first_shortfall_year is None:
                first_shortfall_year = year

        if keep_path_detail:
            # Detail column order (Path × Year × Bucket) — matches the identity
            #   EB = BB + contribution_in + transfer_in + investment_return
            #          − expense_out − transfer_out
            # path_id / year / bucket_name come from the post-loop column build
            # (np.repeat/np.tile); supplemental columns sampled_return and
            # is_shortfall are written last and consumed by downstream summaries.
            # Per-year row block = n_buckets LIQUID rows + n_term TERM rows.
            # The term rows project the sidecar ledger as a parallel track
            # (bucket_kind="term"); the bucket_kind column itself is built once
            # in the runner (buffer path) or carried inline (fallback path).
            rows_per_year = n_buckets + n_term
            if detail_buffers is not None:
                _row_start = int(path_offset) + yi * rows_per_year
                _liq_end = _row_start + n_buckets
                detail_buffers["beginning_balance"][_row_start:_liq_end] = np.round(beginning_balances, 2)
                detail_buffers["contribution_in"][_row_start:_liq_end] = np.round(contribution_in, 2)
                detail_buffers["topup_in"][_row_start:_liq_end] = np.round(topup_in, 2)
                detail_buffers["investment_return"][_row_start:_liq_end] = np.round(investment_return, 2)
                detail_buffers["expense_out"][_row_start:_liq_end] = np.round(expense_out_arr, 2)
                detail_buffers["transfer_in"][_row_start:_liq_end] = np.round(transfer_in, 2)
                detail_buffers["transfer_out"][_row_start:_liq_end] = np.round(transfer_out, 2)
                detail_buffers["ending_balance"][_row_start:_liq_end] = np.round(balances, 2)
                detail_buffers["sampled_return"][_row_start:_liq_end] = np.round(sampled_returns[yi], 8)
                detail_buffers["is_shortfall"][_row_start:_liq_end] = is_shortfall_arr

                if n_term > 0:
                    _term_start = _liq_end
                    _term_end = _term_start + n_term
                    # Term-row column mapping (term semantics on shared columns):
                    #   beginning_balance = BB_term, transfer_in = principal locked,
                    #   investment_return = accrual (currency), transfer_out = payout,
                    #   ending_balance = EB_term. contribution_in / expense_out = 0.
                    detail_buffers["beginning_balance"][_term_start:_term_end] = np.round(tb_bb, 2)
                    detail_buffers["contribution_in"][_term_start:_term_end] = 0.0
                    detail_buffers["topup_in"][_term_start:_term_end] = 0.0
                    detail_buffers["investment_return"][_term_start:_term_end] = np.round(tb_ret, 2)
                    detail_buffers["expense_out"][_term_start:_term_end] = 0.0
                    detail_buffers["transfer_in"][_term_start:_term_end] = np.round(tb_in, 2)
                    detail_buffers["transfer_out"][_term_start:_term_end] = np.round(tb_out, 2)
                    detail_buffers["ending_balance"][_term_start:_term_end] = np.round(tb_eb, 2)
                    detail_buffers["sampled_return"][_term_start:_term_end] = np.round(tb_sampled, 8)
                    detail_buffers["is_shortfall"][_term_start:_term_end] = False
            else:
                for bi, bucket_name in enumerate(ordered_bucket_names):
                    detail_rows.append({
                        "path_id": int(path_id),
                        "year": int(year),
                        "bucket_name": str(bucket_name),
                        "bucket_kind": "liquid",
                        "beginning_balance": round(float(beginning_balances[bi]), 2),
                        "contribution_in": round(float(contribution_in[bi]), 2),
                        "topup_in": round(float(topup_in[bi]), 2),
                        "investment_return": round(float(investment_return[bi]), 2),
                        "expense_out": round(float(expense_out_arr[bi]), 2),
                        "transfer_in": round(float(transfer_in[bi]), 2),
                        "transfer_out": round(float(transfer_out[bi]), 2),
                        "ending_balance": round(float(balances[bi]), 2),
                        "sampled_return": round(float(sampled_returns[yi, bi]), 8),
                        "is_shortfall": bool(is_shortfall_arr[bi]),
                    })
                for j in range(n_term):
                    detail_rows.append({
                        "path_id": int(path_id),
                        "year": int(year),
                        "bucket_name": str(_term_list[j].name),
                        "bucket_kind": "term",
                        "beginning_balance": round(float(tb_bb[j]), 2),
                        "contribution_in": 0.0,
                        "topup_in": 0.0,
                        "investment_return": round(float(tb_ret[j]), 2),
                        "expense_out": 0.0,
                        "transfer_in": round(float(tb_in[j]), 2),
                        "transfer_out": round(float(tb_out[j]), 2),
                        "ending_balance": round(float(tb_eb[j]), 2),
                        "sampled_return": round(float(tb_sampled[j]), 8),
                        "is_shortfall": False,
                    })

    # Terminal wealth includes any still-locked term money. Term holdings are
    # illiquid (cannot pay expenses) but are real wealth, so they count toward
    # final_total_balance — which path_success measures against success_threshold.
    terminal_locked_term_value = round(float(sum(term_value)), 2) if n_term > 0 else 0.0
    final_total_balance = round(float(balances.sum()) + terminal_locked_term_value, 2)
    # Shortfall amount = worst negative bucket-0 balance across years.
    # Reflects "deepest underpayment" — how short the bill-paying bucket got.
    total_shortfall_amount = round(abs(min(min_bucket0_balance, 0.0)), 2)
    path_success = (not any_shortfall) and (final_total_balance >= float(success_threshold))

    path_summary = {
        "path_id": int(path_id),
        "path_success": bool(path_success),
        "final_total_balance": round(final_total_balance, 2),
        "total_shortfall_amount": round(total_shortfall_amount, 2),
        "first_shortfall_year": first_shortfall_year,
        # Illiquid locked term wealth at horizon end (0.0 when no term assets).
        "terminal_locked_term_value": terminal_locked_term_value,
    }
    # Per-bucket terminal balance — one column per configured bucket
    # (no longer hardcoded to liquidity/stability/growth).
    for _bname, _bidx in bucket_to_idx.items():
        path_summary[f"{_bname}_terminal_balance"] = round(float(balances[_bidx]), 2)

    # Per-path term-purchase outcome: True when the asset could NOT be bought
    # on this path because the LONG bucket lacked the minimum investment at the
    # lock moment. Aggregated downstream into mc_term_skip_summary_df.
    for j in range(n_term):
        path_summary[f"term_skipped__{_term_list[j].name}"] = bool(term_skipped[j])

    # A7: return raw row lists instead of per-path DataFrames.
    # The outer runner aggregates rows across all paths and builds ONE
    # DataFrame at the end, avoiding O(n_paths) DataFrame constructions
    # and an expensive pd.concat over many small frames.
    out_detail_rows = detail_rows if keep_path_detail else []
    out_asset_rows = _asset_detail_rows_all if keep_asset_detail else []
    return out_detail_rows, out_asset_rows, path_summary


def run_bucket_engine_monte_carlo_level2(
    expense_df: pd.DataFrame,
    initial_savings: float,
    annual_contribution_map: Dict[int, float],
    annual_topup_map: Dict[int, float],
    bucket_configs: Optional[List] = None,
    funding_rule=None,
    bucket_return_models: Optional[List[BucketReturnModel]] = None,
    mc_config: Optional[MonteCarloConfig] = None,
    simulation_start_year: Optional[int] = None,
    initial_allocation_override_df: Optional[pd.DataFrame] = None,
    term_assets: Optional[List[TermAssetConfig]] = None,
    progress_callback=None,
    progress_update_every: int = 10,
) -> BucketMCResult:
    """
    Level-2 optimized Monte Carlo runner.

    Compared with quick-wins version, this additionally:
    - replaces dict/string lookups in the hot loop with numpy arrays + index maps
    - avoids path-level DataFrame work inside the simulation loop
    - computes path summary inline without calling summarize_one_mc_path(...)

    Business logic remains the same:
    inflow allocation -> return -> expense -> shortfall cover -> rollover
    """
    bucket_configs = bucket_configs or default_bucket_configs()
    funding_rule = funding_rule or BucketFundingRule()
    bucket_return_models = bucket_return_models or default_bucket_return_models()
    mc_config = mc_config or MonteCarloConfig()

    validate_bucket_configs(bucket_configs)
    validate_bucket_funding_rule(funding_rule, bucket_configs)
    validate_bucket_return_models(
        bucket_return_models=bucket_return_models,
        expected_bucket_names=[cfg.bucket_name for cfg in bucket_configs],
    )
    validate_monte_carlo_config(mc_config)
    validate_term_assets(term_assets)

    if initial_savings < 0:
        raise ValueError("initial_savings must be >= 0")
    if progress_update_every < 1:
        raise ValueError("progress_update_every must be >= 1")

    # ----------------------------------------------------
    # Determine horizon once
    # ----------------------------------------------------
    annual_expense_df = prepare_annual_expense(expense_df)

    candidate_years = set()
    if annual_expense_df is not None and not annual_expense_df.empty:
        candidate_years.update(annual_expense_df["year"].astype(int).tolist())
    candidate_years.update(int(y) for y in annual_contribution_map.keys())
    candidate_years.update(int(y) for y in annual_topup_map.keys())

    if simulation_start_year is None:
        if not candidate_years:
            raise ValueError(
                "simulation_start_year is None and no years found in expense_df / inflow maps"
            )
        simulation_start_year = min(candidate_years)

    if not candidate_years:
        candidate_years = {int(simulation_start_year)}

    simulation_end_year = max(candidate_years)

    # ----------------------------------------------------
    # Deterministic planning layer once
    # ----------------------------------------------------
    bucket_assignment_df = assign_expense_to_buckets(
        annual_expense_df=annual_expense_df,
        simulation_start_year=int(simulation_start_year),
        bucket_configs=bucket_configs,
    )

    # Fix 1: ใช้ max(0, min_return) เป็น conservative discount rate
    # เหตุผล: ถ้า min_return ติดลบ (เช่น -40%) การ discount ด้วย rate ติดลบ
    # จะทำให้ required_present_value โป่งเกินจริง (เช่น 142M สำหรับ expense 3M)
    # floor ที่ 0% หมายความว่า "ต้องมีเงิน >= nominal future expense ทั้งหมด"
    # ซึ่งเป็น conservative กว่าการใช้ mean_return แต่สมเหตุสมผลสำหรับ planning
    conservative_discount_rate_map = {
        m.bucket_name: max(0.0, float(m.min_return)) if m.min_return is not None else 0.0
        for m in bucket_return_models
    }

    bucket_requirement_df = calculate_bucket_requirements(
        bucket_assignment_df=bucket_assignment_df,
        simulation_start_year=int(simulation_start_year),
        bucket_configs=bucket_configs,
        discount_rate_override_map=conservative_discount_rate_map,
    )

    # Fix 3: ใช้ manual allocation ถ้า user override ไว้
    if initial_allocation_override_df is not None:
        initial_allocation_df = initial_allocation_override_df
    else:
        initial_allocation_df = allocate_initial_savings_to_buckets(
            initial_savings=float(initial_savings),
            bucket_requirement_df=bucket_requirement_df,
            funding_rule=funding_rule,
        )

    # ----------------------------------------------------
    # Build static context once
    # ----------------------------------------------------
    static_ctx = _prepare_l2_static_context(
        annual_expense_df=annual_expense_df,
        annual_contribution_map=annual_contribution_map,
        annual_topup_map=annual_topup_map,
        bucket_assignment_df=bucket_assignment_df,
        bucket_configs=bucket_configs,
        simulation_start_year=int(simulation_start_year),
        simulation_end_year=int(simulation_end_year),
    )

    # OPT-4: precompute integer priority-index array ONCE for the fast inflow allocator.
    # Order preserved verbatim from funding_rule.contribution_priority so the
    # arithmetic sequence inside _allocate_yearly_inflow_to_buckets_array_fast
    # is bit-identical to the original string-keyed version.
    _bucket_to_idx = static_ctx["bucket_to_idx"]
    static_ctx["priority_idx_arr"] = np.array(
        [int(_bucket_to_idx[b]) for b in funding_rule.contribution_priority],
        dtype=np.int64,
    )

    # OPT-B: precompute initial balance + remaining requirement arrays ONCE.
    # _build_initial_balance_and_requirement_arrays iterates initial_allocation_df.iterrows()
    # which is expensive; hoisting it out of the per-path loop saves O(n_paths) DataFrame work.
    _balances0, _remaining_required0 = _build_initial_balance_and_requirement_arrays(
        initial_allocation_df=initial_allocation_df,
        bucket_to_idx=_bucket_to_idx,
        n_buckets=int(static_ctx["n_buckets"]),
    )
    static_ctx["balances0"] = _balances0
    static_ctx["remaining_required0"] = _remaining_required0

    # Precompute path-invariant term scheduling ONCE (start0 / EOY lock orders,
    # payout years). Reused by every path instead of rebuilding it per-path.
    static_ctx["term_ctx"] = _build_term_context(term_assets, int(simulation_start_year))
    _term_ctx = static_ctx["term_ctx"]
    _n_term = int(_term_ctx["n_term"])
    _term_names = [t.name for t in _term_ctx["term_list"]]

    # Pre-fund FIRST-YEAR (start0) term locks straight out of the initial
    # allocation, so they begin year 0 with BB = principal (drawn from initial
    # savings, NOT a year-0 transfer_in). Deterministic across paths: carve the
    # principal from the LONG bucket's initial balance in quality order;
    # insufficient funds → permanent skip. EOY locks (buy_year > start) are
    # unchanged — they still draw via transfer in their lock year.
    _term_initial_values = [0.0] * _n_term
    if _n_term > 0 and _term_ctx["start0_order"]:
        _long_idx0 = int(static_ctx["n_buckets"]) - 1
        _bal0_arr = static_ctx["balances0"]
        _prefund_drawn = 0.0
        for _j in _term_ctx["start0_order"]:
            _pp = float(_term_ctx["min_inv"][_j])
            if float(_bal0_arr[_long_idx0]) >= _pp:
                _bal0_arr[_long_idx0] -= _pp
                _term_initial_values[_j] = _pp
                _prefund_drawn += _pp
            # else: NOT funded from the initial allocation — left to retry at the
            # year-0 lock (it can use a year-0 top-up). Not a permanent skip here.
        # Reflect the carve-out in the displayed initial allocation (long bucket).
        if (
            _prefund_drawn > 0
            and initial_allocation_df is not None
            and not initial_allocation_df.empty
            and "bucket_name" in initial_allocation_df.columns
            and "recommended_initial_amount" in initial_allocation_df.columns
        ):
            _long_name0 = str(static_ctx["ordered_bucket_names"][_long_idx0])
            _lmask = initial_allocation_df["bucket_name"].astype(str) == _long_name0
            initial_allocation_df.loc[_lmask, "recommended_initial_amount"] = (
                initial_allocation_df.loc[_lmask, "recommended_initial_amount"].astype(float)
                - _prefund_drawn
            ).clip(lower=0.0)
    static_ctx["term_initial_values"] = _term_initial_values

    # ----------------------------------------------------
    # Main MC loop
    # A7: aggregate row dicts across ALL paths in a single flat list, then
    # build each DataFrame ONCE at the end. This avoids per-path DataFrame
    # construction and pd.concat() over n_paths small frames.
    # ----------------------------------------------------
    all_path_summaries: List[dict] = []
    all_path_detail_rows: List[dict] = []
    all_asset_detail_rows: List[dict] = []

    # Column order matches the EB identity:
    #   EB = BB + contribution_in + transfer_in + investment_return − expense_out − transfer_out
    # sampled_return and is_shortfall are supplemental columns consumed by
    # downstream summary builders.
    _detail_cols = [
        "path_id", "year", "bucket_name", "bucket_kind",
        "beginning_balance", "contribution_in", "topup_in", "investment_return", "expense_out",
        "transfer_in", "transfer_out", "ending_balance",
        "sampled_return", "is_shortfall",
    ]
    _asset_cols = [
        "path_id", "year", "bucket_name", "asset_name",
        "weight_pct", "weight_normalized", "sampled_return", "weighted_contribution",
    ]

    total_paths = int(mc_config.n_paths)

    # OPT-C: pre-allocate columnar buffers for path detail (avoid per-row dict appends).
    # Layout: row = path_id * (n_years * n_buckets) + yi * n_buckets + bi
    _n_rows_per_path = int(static_ctx["n_years"]) * (int(static_ctx["n_buckets"]) + _n_term)
    if mc_config.keep_path_detail:
        _n_total_rows = total_paths * _n_rows_per_path
        detail_buffers: Optional[Dict[str, np.ndarray]] = {
            "sampled_return":    np.empty(_n_total_rows, dtype=float),
            "beginning_balance": np.empty(_n_total_rows, dtype=float),
            "contribution_in":   np.empty(_n_total_rows, dtype=float),
            "topup_in":          np.empty(_n_total_rows, dtype=float),
            "transfer_in":       np.empty(_n_total_rows, dtype=float),
            "investment_return": np.empty(_n_total_rows, dtype=float),
            "expense_out":       np.empty(_n_total_rows, dtype=float),
            "transfer_out":      np.empty(_n_total_rows, dtype=float),
            "ending_balance":    np.empty(_n_total_rows, dtype=float),
            "is_shortfall":      np.empty(_n_total_rows, dtype=bool),
        }
    else:
        detail_buffers = None

    for path_id in range(total_paths):
        detail_rows_one, asset_rows_one, path_summary = _simulate_one_mc_path_l2(
            path_id=path_id,
            static_ctx=static_ctx,
            initial_allocation_df=initial_allocation_df,
            bucket_configs=bucket_configs,
            funding_rule=funding_rule,
            bucket_return_models=bucket_return_models,
            mc_config=mc_config,
            success_threshold=float(mc_config.success_threshold),
            keep_path_detail=bool(mc_config.keep_path_detail),
            keep_asset_detail=bool(mc_config.keep_asset_detail),
            term_assets=term_assets,
            detail_buffers=detail_buffers,
            path_offset=path_id * _n_rows_per_path,
        )

        all_path_summaries.append(path_summary)

        # When detail_buffers is used, _simulate_one_mc_path_l2 writes directly into
        # the buffers and returns an empty detail_rows_one list — skip the extend.
        if mc_config.keep_path_detail and detail_buffers is None and detail_rows_one:
            all_path_detail_rows.extend(detail_rows_one)

        if mc_config.keep_asset_detail and asset_rows_one:
            all_asset_detail_rows.extend(asset_rows_one)

        if progress_callback is not None:
            current_path = path_id + 1
            if (current_path % progress_update_every == 0) or (current_path == total_paths):
                progress_callback(current_path, total_paths)

    # ----------------------------------------------------
    # Build outputs (ONCE per frame, post-loop)
    # ----------------------------------------------------
    mc_path_summary_df = pd.DataFrame(all_path_summaries)
    if not mc_path_summary_df.empty:
        mc_path_summary_df = mc_path_summary_df.sort_values("path_id").reset_index(drop=True)

    if mc_config.keep_path_detail and detail_buffers is not None:
        # OPT-C: build path_id / year / bucket_name columns via np.repeat/np.tile.
        # Order must match the buffer write layout in _simulate_one_mc_path_l2:
        #   row = path_id * (n_years * n_buckets) + yi * n_buckets + bi
        _years_arr = static_ctx["years_arr"]
        _n_years = int(static_ctx["n_years"])
        _n_buckets = int(static_ctx["n_buckets"])
        _rows_per_year = _n_buckets + _n_term

        # Per-year name/kind blocks: n_buckets LIQUID rows then n_term TERM rows,
        # matching the buffer write order in _simulate_one_mc_path_l2:
        #   row = path_id*(n_years*rows_per_year) + yi*rows_per_year + within
        _per_year_names = np.array(
            list(static_ctx["ordered_bucket_names"]) + list(_term_names), dtype=object
        )
        _per_year_kinds = np.array(
            ["liquid"] * _n_buckets + ["term"] * _n_term, dtype=object
        )

        path_id_col = np.repeat(np.arange(total_paths, dtype=np.int64), _n_rows_per_path)
        year_col = np.tile(np.repeat(_years_arr, _rows_per_year), total_paths)
        bucket_col = np.tile(np.tile(_per_year_names, _n_years), total_paths)
        kind_col = np.tile(np.tile(_per_year_kinds, _n_years), total_paths)

        mc_path_detail_df = pd.DataFrame({
            "path_id":           path_id_col,
            "year":              year_col,
            "bucket_name":       bucket_col,
            "bucket_kind":       kind_col,
            "beginning_balance": detail_buffers["beginning_balance"],
            "contribution_in":   detail_buffers["contribution_in"],
            "topup_in":          detail_buffers["topup_in"],
            "investment_return": detail_buffers["investment_return"],
            "expense_out":       detail_buffers["expense_out"],
            "transfer_in":       detail_buffers["transfer_in"],
            "transfer_out":      detail_buffers["transfer_out"],
            "ending_balance":    detail_buffers["ending_balance"],
            "sampled_return":    detail_buffers["sampled_return"],
            "is_shortfall":      detail_buffers["is_shortfall"],
        })
        mc_path_detail_df = mc_path_detail_df.sort_values(
            ["path_id", "year", "bucket_kind", "bucket_name"]
        ).reset_index(drop=True)
    elif mc_config.keep_path_detail and all_path_detail_rows:
        mc_path_detail_df = pd.DataFrame(all_path_detail_rows, columns=_detail_cols)
        mc_path_detail_df = mc_path_detail_df.sort_values(
            ["path_id", "year", "bucket_kind", "bucket_name"]
        ).reset_index(drop=True)
    else:
        mc_path_detail_df = pd.DataFrame(columns=_detail_cols)

    if mc_config.keep_path_detail:
        # Year / bucket summaries operate on the LIQUID track only — term rows
        # are a projected sidecar and must not pollute liquid aggregates.
        if "bucket_kind" in mc_path_detail_df.columns:
            _liquid_detail_df = mc_path_detail_df[mc_path_detail_df["bucket_kind"] == "liquid"]
        else:
            _liquid_detail_df = mc_path_detail_df
        mc_year_summary_df = build_mc_year_summary(_liquid_detail_df)
        mc_bucket_summary_df = build_mc_bucket_summary(
            mc_path_detail_df=_liquid_detail_df,
            mc_path_summary_df=mc_path_summary_df,
        )
    else:
        mc_year_summary_df = pd.DataFrame(columns=[
            "year", "bucket_name", "p10_ending_balance", "p50_ending_balance",
            "p90_ending_balance", "shortfall_probability", "mean_investment_return",
        ])
        mc_bucket_summary_df = pd.DataFrame(columns=[
            "bucket_name", "success_probability", "shortfall_probability",
            "expected_terminal_balance", "p10_terminal_balance", "p50_terminal_balance",
            "p90_terminal_balance", "expected_shortfall",
        ])

    mc_engine_summary_df = build_mc_engine_summary(
        mc_path_summary_df=mc_path_summary_df,
    )

    # ---- Asset detail ----
    if mc_config.keep_asset_detail and all_asset_detail_rows:
        mc_path_asset_detail_df = pd.DataFrame(all_asset_detail_rows, columns=_asset_cols)
        mc_path_asset_detail_df = mc_path_asset_detail_df.sort_values(
            ["path_id", "year", "bucket_name"]
        ).reset_index(drop=True)
    else:
        mc_path_asset_detail_df = pd.DataFrame(columns=_asset_cols)

    # ---- Term-asset purchase-skip summary ----
    # One row per term asset. Aggregates the per-path term_skipped__<name> flags
    # into the share of simulated paths where the asset could NOT be purchased
    # because the LONG bucket lacked the minimum investment at its lock moment.
    _term_skip_cols = ["term_name", "buy_year", "n_paths", "n_skipped", "skip_probability"]
    if _n_term > 0 and not mc_path_summary_df.empty:
        _n_paths_total = int(mc_path_summary_df["path_id"].nunique())
        _skip_rows = []
        for _t in _term_ctx["term_list"]:
            _col = f"term_skipped__{_t.name}"
            if _col in mc_path_summary_df.columns:
                _n_skipped = int(mc_path_summary_df[_col].astype(bool).sum())
            else:
                _n_skipped = 0
            _skip_rows.append({
                "term_name": str(_t.name),
                "buy_year": int(_t.buy_year),
                "n_paths": _n_paths_total,
                "n_skipped": _n_skipped,
                "skip_probability": (
                    round(_n_skipped / _n_paths_total, 6) if _n_paths_total > 0 else 0.0
                ),
            })
        mc_term_skip_summary_df = pd.DataFrame(_skip_rows, columns=_term_skip_cols)
    else:
        mc_term_skip_summary_df = pd.DataFrame(columns=_term_skip_cols)

    return BucketMCResult(
        bucket_requirement_df=bucket_requirement_df,
        initial_allocation_df=initial_allocation_df,
        mc_year_summary_df=mc_year_summary_df,
        mc_bucket_summary_df=mc_bucket_summary_df,
        mc_engine_summary_df=mc_engine_summary_df,
        mc_path_summary_df=mc_path_summary_df,
        mc_path_detail_df=mc_path_detail_df,
        mc_path_asset_detail_df=mc_path_asset_detail_df,
        mc_term_skip_summary_df=mc_term_skip_summary_df,
    )