from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from portfolio_bucket_engine import (
    BucketConfig,
    BucketFundingRule,
    validate_bucket_configs,
    validate_bucket_funding_rule,
    default_bucket_configs,
    prepare_annual_expense,
    assign_expense_to_buckets,
    calculate_bucket_requirements,
    allocate_initial_savings_to_buckets,
    initialize_bucket_balances,
    allocate_yearly_inflow_to_buckets,
    resolve_shortfall_with_cross_bucket_transfer,
    should_rollover_after_year,
    get_next_bucket_name,
    get_year_offset,
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
    """
    bucket_name: str
    mean_return: float
    std_dev: float
    min_return: Optional[float] = None
    max_return: Optional[float] = None
    distribution: str = "normal"
    assets: List[AssetReturnModel] = field(default_factory=list)


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
class BucketMCPathYearState:
    path_id: int
    year: int
    bucket_name: str
    sampled_return: float
    beginning_balance: float
    contribution_in: float
    transfer_in: float
    investment_return: float
    expense_out: float
    transfer_out: float
    ending_balance: float
    is_shortfall: bool


@dataclass
class BucketMCPathSummary:
    path_id: int
    path_success: bool
    final_total_balance: float
    total_shortfall_amount: float
    first_shortfall_year: Optional[int]
    liquidity_terminal_balance: float
    stability_terminal_balance: float
    growth_terminal_balance: float


@dataclass
class BucketMCYearSummary:
    year: int
    bucket_name: str
    p10_ending_balance: float
    p50_ending_balance: float
    p90_ending_balance: float
    shortfall_probability: float
    mean_investment_return: float


@dataclass
class BucketMCBucketSummary:
    bucket_name: str
    success_probability: float
    shortfall_probability: float
    expected_terminal_balance: float
    p10_terminal_balance: float
    p50_terminal_balance: float
    p90_terminal_balance: float
    expected_shortfall: float


@dataclass
class BucketMCEngineSummary:
    n_paths: int
    success_probability: float
    shortfall_probability: float
    expected_final_total_balance: float
    p10_final_total_balance: float
    p50_final_total_balance: float
    p90_final_total_balance: float
    expected_shortfall: float
    worst_shortfall: float
    first_shortfall_year_mode: Optional[int]


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

    def __post_init__(self):
        if self.mc_path_asset_detail_df is None:
            self.mc_path_asset_detail_df = pd.DataFrame()


# ============================================================
# DEFAULT MONTE CARLO CONFIG / HELPERS
# ============================================================

def default_bucket_return_models() -> List[BucketReturnModel]:
    """
    default assumption แบบง่ายก่อน
    """
    return [
        BucketReturnModel(
            bucket_name="liquidity",
            mean_return=0.02,
            std_dev=0.01,
            min_return=-0.05,
            max_return=0.08,
            distribution="normal",
        ),
        BucketReturnModel(
            bucket_name="stability",
            mean_return=0.04,
            std_dev=0.06,
            min_return=-0.20,
            max_return=0.20,
            distribution="normal",
        ),
        BucketReturnModel(
            bucket_name="growth",
            mean_return=0.06,
            std_dev=0.15,
            min_return=-0.40,
            max_return=0.40,
            distribution="normal",
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
    allowed_dist = {"normal", "fixed"}

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
                if a.distribution not in {"normal", "fixed"}:
                    raise ValueError(
                        f"bucket={m.bucket_name}, asset={a.asset_name}: "
                        f"unsupported distribution '{a.distribution}'"
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

def _clip_return(
    value: float,
    min_return: Optional[float],
    max_return: Optional[float],
) -> float:
    if min_return is not None:
        value = max(value, float(min_return))
    if max_return is not None:
        value = min(value, float(max_return))
    return float(value)


def _sample_single_return(
    mean_return: float,
    std_dev: float,
    min_return: Optional[float],
    max_return: Optional[float],
    distribution: str,
    rng,
    label: str = "",
) -> float:
    """
    internal helper: sample 1 ครั้งจาก distribution ที่กำหนด แล้ว clip
    """
    if distribution == "fixed":
        sampled = float(mean_return)

    elif distribution == "normal":
        sampled = float(rng.normal(loc=mean_return, scale=std_dev))

    else:
        raise ValueError(
            f"Unsupported distribution '{distribution}' for '{label}'"
        )

    return float(_clip_return(sampled, min_return, max_return))


def sample_one_bucket_return(
    bucket_return_model: BucketReturnModel,
    rng,
    capture_asset_detail: bool = False,
) -> "float | tuple[float, list]":
    """
    sample annual return สำหรับ bucket เดียว 1 ครั้ง

    ถ้า bucket_return_model.assets มีข้อมูล → simulate แต่ละ asset
    แล้วรวม weighted average (normalize weight อัตโนมัติ)

    ถ้า assets ว่าง → fallback ไป bucket-level mean/std (พฤติกรรมเดิม)

    Parameters
    ----------
    bucket_return_model : BucketReturnModel
    rng : numpy random generator
    capture_asset_detail : bool
        ถ้า True จะ return (weighted_return, asset_detail_rows_list)
        ถ้า False (default) จะ return float เหมือนเดิม

    Returns
    -------
    float  (when capture_asset_detail=False)
        sampled_return
    tuple[float, list]  (when capture_asset_detail=True)
        (sampled_return, asset_detail_rows)
        asset_detail_rows = list of dicts with keys:
          asset_name, weight_pct, weight_normalized, sampled_return, weighted_contribution
    """
    if bucket_return_model.assets:
        # --- Asset-level weighted simulation ---
        total_weight = sum(float(a.weight) for a in bucket_return_model.assets)
        if total_weight <= 0:
            raise ValueError(
                f"bucket={bucket_return_model.bucket_name}: "
                "sum of asset weights must be > 0"
            )

        weighted_return = 0.0
        asset_detail_rows = [] if capture_asset_detail else None

        for asset in bucket_return_model.assets:
            w = float(asset.weight) / total_weight  # normalize
            asset_r = _sample_single_return(
                mean_return=asset.mean_return,
                std_dev=asset.std_dev,
                min_return=asset.min_return,
                max_return=asset.max_return,
                distribution=asset.distribution,
                rng=rng,
                label=f"{bucket_return_model.bucket_name}/{asset.asset_name}",
            )
            weighted_return += w * asset_r

            if capture_asset_detail:
                asset_detail_rows.append({
                    "asset_name":          str(asset.asset_name),
                    "weight_pct":          round(float(asset.weight), 4),
                    "weight_normalized":   round(w, 6),
                    "sampled_return":      round(float(asset_r), 8),
                    "weighted_contribution": round(float(w * asset_r), 8),
                })

        result = round(float(weighted_return), 8)
        return (result, asset_detail_rows) if capture_asset_detail else result

    else:
        # --- Bucket-level simulation (original behaviour) ---
        sampled = _sample_single_return(
            mean_return=bucket_return_model.mean_return,
            std_dev=bucket_return_model.std_dev,
            min_return=bucket_return_model.min_return,
            max_return=bucket_return_model.max_return,
            distribution=bucket_return_model.distribution,
            rng=rng,
            label=bucket_return_model.bucket_name,
        )
        result = round(float(sampled), 8)
        if capture_asset_detail:
            # bucket-level (no per-asset breakdown) — return single pseudo-row
            asset_detail_rows = [{
                "asset_name":          f"[bucket-level] {bucket_return_model.bucket_name}",
                "weight_pct":          100.0,
                "weight_normalized":   1.0,
                "sampled_return":      result,
                "weighted_contribution": result,
            }]
            return (result, asset_detail_rows)
        return result


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


def sample_bucket_returns_for_path(
    path_id: int,
    years: List[int],
    bucket_return_models: List[BucketReturnModel],
    mc_config: MonteCarloConfig,
) -> "tuple[pd.DataFrame, pd.DataFrame]":
    """
    sample annual return ของทุก bucket สำหรับ 1 path

    Returns
    -------
    bucket_return_df : pd.DataFrame
        columns: path_id, year, bucket_name, sampled_return

    asset_detail_df : pd.DataFrame
        columns: path_id, year, bucket_name, asset_name,
                 weight_pct, weight_normalized, sampled_return, weighted_contribution
        Empty DataFrame when mc_config.keep_asset_detail=False
    """
    validate_monte_carlo_config(mc_config)
    validate_bucket_return_models(bucket_return_models)

    if path_id < 0:
        raise ValueError("path_id must be >= 0")

    if not years:
        raise ValueError("years must not be empty")

    years_sorted = sorted(int(y) for y in years)
    rng = _build_path_rng(mc_config, path_id)
    capture = bool(mc_config.keep_asset_detail)

    bucket_rows = []
    asset_rows = [] if capture else None

    for year in years_sorted:
        for model in bucket_return_models:
            if capture:
                ret, detail = sample_one_bucket_return(model, rng, capture_asset_detail=True)
                for d in detail:
                    d["path_id"]     = int(path_id)
                    d["year"]        = int(year)
                    d["bucket_name"] = str(model.bucket_name)
                    asset_rows.append(d)
            else:
                ret = sample_one_bucket_return(model, rng, capture_asset_detail=False)

            bucket_rows.append({
                "path_id":      int(path_id),
                "year":         int(year),
                "bucket_name":  str(model.bucket_name),
                "sampled_return": ret,
            })

    bucket_df = pd.DataFrame(
        bucket_rows,
        columns=["path_id", "year", "bucket_name", "sampled_return"],
    )

    if capture and asset_rows:
        asset_df = pd.DataFrame(asset_rows, columns=[
            "path_id", "year", "bucket_name", "asset_name",
            "weight_pct", "weight_normalized", "sampled_return", "weighted_contribution",
        ])
    else:
        asset_df = pd.DataFrame()

    return bucket_df, asset_df


def sample_bucket_returns_all_paths(
    years: List[int],
    bucket_return_models: List[BucketReturnModel],
    mc_config: MonteCarloConfig,
) -> "tuple[pd.DataFrame, pd.DataFrame]":
    """
    sample annual return ของทุก bucket สำหรับทุก paths

    Returns
    -------
    bucket_return_df : pd.DataFrame
        columns: path_id, year, bucket_name, sampled_return
    asset_detail_df : pd.DataFrame
        Empty when mc_config.keep_asset_detail=False
    """
    validate_monte_carlo_config(mc_config)
    validate_bucket_return_models(bucket_return_models)

    if not years:
        raise ValueError("years must not be empty")

    all_bucket_parts: List[pd.DataFrame] = []
    all_asset_parts: List[pd.DataFrame] = []

    for path_id in range(int(mc_config.n_paths)):
        bkt_df, ast_df = sample_bucket_returns_for_path(
            path_id=path_id,
            years=years,
            bucket_return_models=bucket_return_models,
            mc_config=mc_config,
        )
        all_bucket_parts.append(bkt_df)
        if mc_config.keep_asset_detail and not ast_df.empty:
            all_asset_parts.append(ast_df)

    if not all_bucket_parts:
        return (
            pd.DataFrame(columns=["path_id", "year", "bucket_name", "sampled_return"]),
            pd.DataFrame(),
        )

    bucket_out = pd.concat(all_bucket_parts, axis=0, ignore_index=True)
    bucket_out = bucket_out.sort_values(["path_id", "year", "bucket_name"]).reset_index(drop=True)

    if all_asset_parts:
        asset_out = pd.concat(all_asset_parts, axis=0, ignore_index=True)
        asset_out = asset_out.sort_values(["path_id", "year", "bucket_name", "asset_name"]).reset_index(drop=True)
    else:
        asset_out = pd.DataFrame()

    return bucket_out, asset_out

## MC-2 start here

def build_sampled_return_map_for_path(
    sampled_return_df: pd.DataFrame,
    path_id: int,
) -> Dict[Tuple[int, str], float]:
    """
    convert sampled return df -> {(year, bucket_name): sampled_return}
    สำหรับ path เดียว

    Expected input columns:
    - path_id
    - year
    - bucket_name
    - sampled_return

    Returns
    -------
    Dict[Tuple[int, str], float]
        key = (year, bucket_name)
        value = sampled_return
    """
    if sampled_return_df is None or sampled_return_df.empty:
        raise ValueError("sampled_return_df must not be empty")

    required_cols = ["path_id", "year", "bucket_name", "sampled_return"]
    missing_cols = [c for c in required_cols if c not in sampled_return_df.columns]
    if missing_cols:
        raise ValueError(
            f"sampled_return_df is missing required columns: {missing_cols}"
        )

    df = sampled_return_df[required_cols].copy()
    df["path_id"] = pd.to_numeric(df["path_id"], errors="raise").astype(int)
    df["year"] = pd.to_numeric(df["year"], errors="raise").astype(int)
    df["bucket_name"] = df["bucket_name"].astype(str)
    df["sampled_return"] = pd.to_numeric(df["sampled_return"], errors="raise").astype(float)

    df = df.loc[df["path_id"] == int(path_id)].copy()
    if df.empty:
        raise ValueError(f"No sampled return rows found for path_id={path_id}")

    # กันกรณี duplicate key
    dup_mask = df.duplicated(subset=["year", "bucket_name"], keep=False)
    if dup_mask.any():
        dup_rows = df.loc[dup_mask, ["year", "bucket_name"]].drop_duplicates()
        raise ValueError(
            "Found duplicate (year, bucket_name) rows for path_id="
            f"{path_id}: {dup_rows.to_dict(orient='records')}"
        )

    return {
        (int(r["year"]), str(r["bucket_name"])): float(r["sampled_return"])
        for _, r in df.iterrows()
    }


def summarize_one_mc_path(
    path_year_state_df: pd.DataFrame,
    success_threshold: float = 0.0,
) -> Dict[str, Optional[float]]:
    """
    summarize ผลของ 1 path

    Expected input columns:
    - path_id
    - year
    - bucket_name
    - ending_balance
    - is_shortfall

    Optional columns:
    - beginning_balance
    - contribution_in
    - transfer_in
    - investment_return
    - expense_out
    - transfer_out

    Returns
    -------
    Dict[str, Optional[float]]
        keys:
        - path_id
        - path_success
        - final_total_balance
        - total_shortfall_amount
        - first_shortfall_year
        - liquidity_terminal_balance
        - stability_terminal_balance
        - growth_terminal_balance
    """
    if path_year_state_df is None or path_year_state_df.empty:
        raise ValueError("path_year_state_df must not be empty")

    required_cols = ["path_id", "year", "bucket_name", "ending_balance", "is_shortfall"]
    missing_cols = [c for c in required_cols if c not in path_year_state_df.columns]
    if missing_cols:
        raise ValueError(
            f"path_year_state_df is missing required columns: {missing_cols}"
        )

    df = path_year_state_df.copy()
    df["path_id"] = pd.to_numeric(df["path_id"], errors="raise").astype(int)
    df["year"] = pd.to_numeric(df["year"], errors="raise").astype(int)
    df["bucket_name"] = df["bucket_name"].astype(str)
    df["ending_balance"] = pd.to_numeric(df["ending_balance"], errors="raise").astype(float)
    df["is_shortfall"] = df["is_shortfall"].astype(bool)

    unique_path_ids = df["path_id"].drop_duplicates().tolist()
    if len(unique_path_ids) != 1:
        raise ValueError(
            "summarize_one_mc_path expects data from exactly one path_id, "
            f"but found: {unique_path_ids}"
        )

    path_id = int(unique_path_ids[0])

    # -------------------------
    # final total balance
    # -------------------------
    final_year = int(df["year"].max())
    final_total_balance = float(
        df.loc[df["year"] == final_year, "ending_balance"].sum()
    )

    # -------------------------
    # path success
    # success = no shortfall in any bucket/year
    # and final_total_balance >= success_threshold
    # -------------------------
    has_any_shortfall = bool(df["is_shortfall"].any())
    path_success = (not has_any_shortfall) and (final_total_balance >= float(success_threshold))

    # -------------------------
    # first shortfall year
    # -------------------------
    shortfall_years = (
        df.loc[df["is_shortfall"], "year"]
        .drop_duplicates()
        .sort_values()
        .tolist()
    )
    first_shortfall_year = int(shortfall_years[0]) if shortfall_years else None

    # -------------------------
    # total shortfall amount
    # ใช้ aggregate total ending balance by year
    # แล้วดู worst negative aggregate balance
    # -------------------------
    total_balance_by_year = (
        df.groupby("year", as_index=False)["ending_balance"]
        .sum()
        .rename(columns={"ending_balance": "total_ending_balance"})
        .sort_values("year")
        .reset_index(drop=True)
    )
    min_total_balance = float(total_balance_by_year["total_ending_balance"].min())
    total_shortfall_amount = round(abs(min(min_total_balance, 0.0)), 2)

    # -------------------------
    # terminal balance by bucket
    # -------------------------
    terminal_by_bucket = (
        df.loc[df["year"] == final_year, ["bucket_name", "ending_balance"]]
        .copy()
    )

    terminal_map = {
        str(r["bucket_name"]): float(r["ending_balance"])
        for _, r in terminal_by_bucket.iterrows()
    }

    summary = {
        "path_id": path_id,
        "path_success": bool(path_success),
        "final_total_balance": round(final_total_balance, 2),
        "total_shortfall_amount": round(total_shortfall_amount, 2),
        "first_shortfall_year": first_shortfall_year,
    }
    # Dynamic terminal balance columns per bucket (ไม่ hardcode bucket names)
    for bkt_name, bal in terminal_map.items():
        summary[f"{bkt_name}_terminal_balance"] = round(float(bal), 2)

    return summary

# ============================================================
# PHASE MC-3 IMPLEMENTATION
# ============================================================

def simulate_bucket_year_one_path(
    path_id: int,
    year: int,
    simulation_start_year: int,
    balances: Dict[str, float],
    annual_expense_map_by_bucket: Dict[Tuple[int, str], float],
    annual_contribution_map: Dict[int, float],
    annual_topup_map: Dict[int, float],
    remaining_required_map: Dict[str, float],
    sampled_return_map: Dict[Tuple[int, str], float],
    bucket_configs: List,
    funding_rule,
) -> Tuple[
    Dict[str, float],
    List[BucketMCPathYearState],
    Dict[str, float],
]:
    """
    simulate 1 ปี สำหรับ 1 path

    Assumption ของ MVP (เหมือน deterministic engine เดิมมากที่สุด):
    - annual contribution + annual topup ถูกใส่ต้นปี
    - investment return คิดหลังเติม inflow ของปีนั้น
    - expense ถูกหักปลายปี
    - rollover เกิดปลายปีหลังจ่าย expense แล้ว
    - shortfall cover ข้าม bucket จะเกิดหลังจ่าย expense แล้ว (เฉพาะ waterfall)
    - sampled_return_map มี key = (year, bucket_name)

    Returns
    -------
    updated_balances : Dict[str, float]
    year_states : List[BucketMCPathYearState]
    updated_remaining_required_map : Dict[str, float]
    """
    validate_bucket_configs(bucket_configs)
    validate_bucket_funding_rule(funding_rule, bucket_configs)

    if path_id < 0:
        raise ValueError("path_id must be >= 0")

    ordered_buckets = _bucket_names_in_order(bucket_configs)
    year_offset = get_year_offset(simulation_start_year, year)

    # copy state
    working_balances = {b: float(balances.get(b, 0.0)) for b in ordered_buckets}
    updated_remaining_required_map = {
        b: max(0.0, float(remaining_required_map.get(b, 0.0)))
        for b in ordered_buckets
    }

    # ----------------------------------------------------
    # Step A: allocate inflow of this year
    # ----------------------------------------------------
    total_inflow = float(annual_contribution_map.get(year, 0.0)) + float(annual_topup_map.get(year, 0.0))
    allocation_map = allocate_yearly_inflow_to_buckets(
        year=year,
        inflow_amount=total_inflow,
        current_balances=working_balances,
        remaining_required_map=updated_remaining_required_map,
        funding_rule=funding_rule,
    )

    # reduce unmet requirement using inflow allocated this year
    for b in ordered_buckets:
        updated_remaining_required_map[b] = round(
            max(0.0, updated_remaining_required_map.get(b, 0.0) - allocation_map.get(b, 0.0)),
            2,
        )

    transfer_in_map = {b: 0.0 for b in ordered_buckets}
    transfer_out_map = {b: 0.0 for b in ordered_buckets}
    investment_return_map = {b: 0.0 for b in ordered_buckets}
    sampled_return_used_map = {b: 0.0 for b in ordered_buckets}
    expense_map = {
        b: float(annual_expense_map_by_bucket.get((year, b), 0.0))
        for b in ordered_buckets
    }
    beginning_balance_map = {
        b: float(working_balances.get(b, 0.0))
        for b in ordered_buckets
    }

    # ----------------------------------------------------
    # Step B: contribution in + sampled return + expense
    # ----------------------------------------------------
    for b in ordered_buckets:
        # add inflow to bucket first
        working_balances[b] = round(float(working_balances[b] + allocation_map.get(b, 0.0)), 2)
        base_for_return = float(working_balances[b])

        # sampled return for this path/year/bucket
        sampled_return = float(sampled_return_map.get((year, b), 0.0))
        sampled_return_used_map[b] = sampled_return

        # apply investment return
        inv_ret = round(base_for_return * sampled_return, 2) if base_for_return > 0 else 0.0
        investment_return_map[b] = inv_ret

        # Fix 2: ลด remaining requirement ด้วย investment return จริงที่เกิดขึ้น
        # return ที่ได้ในปีนี้ช่วย "เติม" เงินใน bucket แล้ว ลด burden ของ contribution ปีถัดไป
        if inv_ret > 0:
            updated_remaining_required_map[b] = round(
                max(0.0, updated_remaining_required_map[b] - inv_ret), 2
            )

        # expense at end of year
        working_balances[b] = round(base_for_return + inv_ret - expense_map[b], 2)

    # ----------------------------------------------------
    # Step C: cover shortfall (if waterfall)
    # ----------------------------------------------------
    for b in ordered_buckets:
        if working_balances[b] < 0:
            needed = abs(float(working_balances[b]))

            updated_balances, logs, remaining_shortfall = resolve_shortfall_with_cross_bucket_transfer(
                year=year,
                target_bucket=b,
                shortfall_amount=needed,
                balances_after_expense=working_balances,
                bucket_configs=bucket_configs,
                funding_rule=funding_rule,
            )

            for lg in logs:
                transfer_out_map[lg.from_bucket] += float(lg.amount)
                transfer_in_map[lg.to_bucket] += float(lg.amount)

            working_balances = updated_balances

            if remaining_shortfall > 0:
                working_balances[b] = round(-remaining_shortfall, 2)
            else:
                working_balances[b] = max(0.0, round(float(working_balances[b]), 2))

    # ----------------------------------------------------
    # Step D: rollover at end of bucket horizon
    # ----------------------------------------------------
    for b in ordered_buckets:
        if should_rollover_after_year(b, year_offset, bucket_configs):
            next_bucket = get_next_bucket_name(b, bucket_configs)
            bal = float(working_balances.get(b, 0.0))

            if next_bucket is not None and bal > 0:
                working_balances[b] = 0.0
                working_balances[next_bucket] = round(
                    float(working_balances.get(next_bucket, 0.0) + bal),
                    2,
                )
                transfer_out_map[b] += bal
                transfer_in_map[next_bucket] += bal

    # ----------------------------------------------------
    # Step E: build path-year states
    # ----------------------------------------------------
    year_states: List[BucketMCPathYearState] = []
    for b in ordered_buckets:
        year_states.append(
            BucketMCPathYearState(
                path_id=int(path_id),
                year=int(year),
                bucket_name=b,
                sampled_return=round(float(sampled_return_used_map.get(b, 0.0)), 8),
                beginning_balance=round(float(beginning_balance_map[b]), 2),
                contribution_in=round(float(allocation_map.get(b, 0.0)), 2),
                transfer_in=round(float(transfer_in_map.get(b, 0.0)), 2),
                investment_return=round(float(investment_return_map.get(b, 0.0)), 2),
                expense_out=round(float(expense_map.get(b, 0.0)), 2),
                transfer_out=round(float(transfer_out_map.get(b, 0.0)), 2),
                ending_balance=round(float(working_balances.get(b, 0.0)), 2),
                is_shortfall=bool(float(working_balances.get(b, 0.0)) < 0),
            )
        )

    updated_balances = {
        b: round(float(working_balances.get(b, 0.0)), 2)
        for b in ordered_buckets
    }

    return updated_balances, year_states, updated_remaining_required_map


def simulate_bucket_engine_one_path(
    path_id: int,
    annual_expense_df: pd.DataFrame,
    bucket_assignment_df: pd.DataFrame,
    bucket_requirement_df: pd.DataFrame,
    initial_allocation_df: pd.DataFrame,
    annual_contribution_map: Dict[int, float],
    annual_topup_map: Dict[int, float],
    sampled_return_df: pd.DataFrame,
    simulation_start_year: int,
    bucket_configs: List,
    funding_rule,
    keep_path_detail: bool = False,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """
    simulate 1 path จนจบ projection horizon

    Returns
    -------
    path_year_state_df : pd.DataFrame
        columns:
        - path_id
        - year
        - bucket_name
        - sampled_return
        - beginning_balance
        - contribution_in
        - transfer_in
        - investment_return
        - expense_out
        - transfer_out
        - ending_balance
        - is_shortfall

    path_summary_dict : Dict[str, float]
        keys:
        - path_id
        - path_success
        - final_total_balance
        - total_shortfall_amount
        - first_shortfall_year
        - liquidity_terminal_balance
        - stability_terminal_balance
        - growth_terminal_balance
    """
    validate_bucket_configs(bucket_configs)
    validate_bucket_funding_rule(funding_rule, bucket_configs)

    if path_id < 0:
        raise ValueError("path_id must be >= 0")

    if initial_allocation_df is None or initial_allocation_df.empty:
        raise ValueError("initial_allocation_df must not be empty")

    if bucket_requirement_df is None or bucket_requirement_df.empty:
        raise ValueError("bucket_requirement_df must not be empty")

    # ----------------------------------------------------
    # build return map for this path
    # ----------------------------------------------------
    sampled_return_map = build_sampled_return_map_for_path(
        sampled_return_df=sampled_return_df,
        path_id=path_id,
    )

    # ----------------------------------------------------
    # initial balances
    # ----------------------------------------------------
    balances = initialize_bucket_balances(initial_allocation_df)

    # use unmet_required_amount as remaining requirement to be filled by future inflows
    if "bucket_name" not in initial_allocation_df.columns or "unmet_required_amount" not in initial_allocation_df.columns:
        raise ValueError(
            "initial_allocation_df must contain ['bucket_name', 'unmet_required_amount']"
        )

    remaining_required_map = {
        str(r["bucket_name"]): float(r["unmet_required_amount"])
        for _, r in initial_allocation_df[["bucket_name", "unmet_required_amount"]].iterrows()
    }

    # ----------------------------------------------------
    # determine projection years
    # ----------------------------------------------------
    years = set()

    if annual_expense_df is not None and not annual_expense_df.empty and "year" in annual_expense_df.columns:
        years.update(
            pd.to_numeric(annual_expense_df["year"], errors="raise").astype(int).tolist()
        )

    years.update(int(y) for y in annual_contribution_map.keys())
    years.update(int(y) for y in annual_topup_map.keys())

    # include sampled return years for this path
    sampled_years = {y for (y, _b) in sampled_return_map.keys()}
    years.update(int(y) for y in sampled_years)

    if not years:
        years = {int(simulation_start_year)}

    start_year = int(simulation_start_year)
    end_year = max(int(y) for y in years)

    # ----------------------------------------------------
    # build expense map by bucket
    # ----------------------------------------------------
    annual_expense_map_by_bucket: Dict[Tuple[int, str], float] = {}

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
            annual_expense_map_by_bucket[(int(r["year"]), str(r["bucket_name"]))] = float(r["total_expense"])

    # ----------------------------------------------------
    # simulate year by year
    # ----------------------------------------------------
    all_states: List[BucketMCPathYearState] = []

    for year in range(start_year, end_year + 1):
        balances, states, remaining_required_map = simulate_bucket_year_one_path(
            path_id=path_id,
            year=year,
            simulation_start_year=simulation_start_year,
            balances=balances,
            annual_expense_map_by_bucket=annual_expense_map_by_bucket,
            annual_contribution_map=annual_contribution_map,
            annual_topup_map=annual_topup_map,
            remaining_required_map=remaining_required_map,
            sampled_return_map=sampled_return_map,
            bucket_configs=bucket_configs,
            funding_rule=funding_rule,
        )
        all_states.extend(states)

    path_year_state_df = pd.DataFrame([vars(x) for x in all_states])

    # keep_path_detail=False:
    # caller may choose not to persist this df,
    # butเรายังคืน df นี้ไปเพื่อให้ summarize_one_mc_path ใช้ได้ทันที
    path_summary_dict = summarize_one_mc_path(
        path_year_state_df=path_year_state_df,
        success_threshold=0.0,
    )

    return path_year_state_df, path_summary_dict

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
    - liquidity_terminal_balance
    - stability_terminal_balance
    - growth_terminal_balance

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
    - liquidity_terminal_balance
    - stability_terminal_balance
    - growth_terminal_balance

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

### run_bucket_engine_monte_carlo() start here

# def run_bucket_engine_monte_carlo(
#     expense_df: pd.DataFrame,
#     initial_savings: float,
#     annual_contribution_map: Dict[int, float],
#     annual_topup_map: Dict[int, float],
#     bucket_configs: Optional[List] = None,
#     funding_rule=None,
#     bucket_return_models: Optional[List[BucketReturnModel]] = None,
#     mc_config: Optional[MonteCarloConfig] = None,
#     simulation_start_year: Optional[int] = None,
#     progress_callback=None,
# ) -> BucketMCResult:
#     """
#     main Monte Carlo entry point

#     Flow:
#     1) build deterministic planning layer
#        - annual_expense_df
#        - bucket_assignment_df
#        - bucket_requirement_df
#        - initial_allocation_df
#     2) sample annual returns for all paths
#     3) run path-level simulation for each path
#     4) aggregate summaries

#     Parameters
#     ----------
#     expense_df : pd.DataFrame
#         อย่างน้อยต้องมี:
#         - year
#         - inflated_amount
#     initial_savings : float
#     annual_contribution_map : Dict[int, float]
#         {year: annual_contribution}
#     annual_topup_map : Dict[int, float]
#         {year: annual_topup}
#     bucket_configs : Optional[List]
#         ถ้าไม่ส่งมา จะใช้ default_bucket_configs()
#     funding_rule : Optional
#         ถ้าไม่ส่งมา จะใช้ BucketFundingRule()
#     bucket_return_models : Optional[List[BucketReturnModel]]
#         ถ้าไม่ส่งมา จะใช้ default_bucket_return_models()
#     mc_config : Optional[MonteCarloConfig]
#         ถ้าไม่ส่งมา จะใช้ MonteCarloConfig()
#     simulation_start_year : Optional[int]
#         ถ้าไม่ส่งมา จะ infer จากปีใน expense / contribution / topup

#     Returns
#     -------
#     BucketMCResult
#     """
#     # ----------------------------------------------------
#     # defaults
#     # ----------------------------------------------------
#     bucket_configs = bucket_configs or default_bucket_configs()
#     funding_rule = funding_rule or BucketFundingRule()
#     bucket_return_models = bucket_return_models or default_bucket_return_models()
#     mc_config = mc_config or MonteCarloConfig()

#     # ----------------------------------------------------
#     # validations
#     # ----------------------------------------------------
#     validate_bucket_configs(bucket_configs)
#     validate_bucket_funding_rule(funding_rule, bucket_configs)
#     validate_bucket_return_models(
#         bucket_return_models=bucket_return_models,
#         expected_bucket_names=[cfg.bucket_name for cfg in bucket_configs],
#     )
#     validate_monte_carlo_config(mc_config)

#     if initial_savings < 0:
#         raise ValueError("initial_savings must be >= 0")

#     # ----------------------------------------------------
#     # determine simulation_start_year
#     # ----------------------------------------------------
#     annual_expense_df = prepare_annual_expense(expense_df)

#     candidate_years = set()

#     if annual_expense_df is not None and not annual_expense_df.empty:
#         candidate_years.update(
#             annual_expense_df["year"].astype(int).tolist()
#         )

#     candidate_years.update(int(y) for y in annual_contribution_map.keys())
#     candidate_years.update(int(y) for y in annual_topup_map.keys())

#     if simulation_start_year is None:
#         if not candidate_years:
#             raise ValueError(
#                 "simulation_start_year is None and no years found in expense_df / inflow maps"
#             )
#         simulation_start_year = min(candidate_years)

#     # ถ้าไม่มีอะไรเลย ให้ใช้ start year เป็นปีเดียว
#     if not candidate_years:
#         candidate_years = {int(simulation_start_year)}

#     simulation_end_year = max(candidate_years)
#     projection_years = list(range(int(simulation_start_year), int(simulation_end_year) + 1))

#     # ----------------------------------------------------
#     # deterministic planning layer
#     # ----------------------------------------------------
#     bucket_assignment_df = assign_expense_to_buckets(
#         annual_expense_df=annual_expense_df,
#         simulation_start_year=int(simulation_start_year),
#         bucket_configs=bucket_configs,
#     )

#     bucket_requirement_df = calculate_bucket_requirements(
#         bucket_assignment_df=bucket_assignment_df,
#         simulation_start_year=int(simulation_start_year),
#         bucket_configs=bucket_configs,
#     )

#     initial_allocation_df = allocate_initial_savings_to_buckets(
#         initial_savings=float(initial_savings),
#         bucket_requirement_df=bucket_requirement_df,
#         funding_rule=funding_rule,
#     )

#     # ----------------------------------------------------
#     # sample returns for all paths
#     # ----------------------------------------------------
#     sampled_return_df = sample_bucket_returns_all_paths(
#         years=projection_years,
#         bucket_return_models=bucket_return_models,
#         mc_config=mc_config,
#     )

#     # ----------------------------------------------------
#     # run simulation for each path
#     # ----------------------------------------------------
#     all_path_summaries: List[Dict[str, float]] = []
#     all_path_detail_parts: List[pd.DataFrame] = []

#     for path_id in range(int(mc_config.n_paths)):
#         path_year_state_df, path_summary = simulate_bucket_engine_one_path(
#             path_id=path_id,
#             annual_expense_df=annual_expense_df,
#             bucket_assignment_df=bucket_assignment_df,
#             bucket_requirement_df=bucket_requirement_df,
#             initial_allocation_df=initial_allocation_df,
#             annual_contribution_map=annual_contribution_map,
#             annual_topup_map=annual_topup_map,
#             sampled_return_df=sampled_return_df,
#             simulation_start_year=int(simulation_start_year),
#             bucket_configs=bucket_configs,
#             funding_rule=funding_rule,
#             keep_path_detail=mc_config.keep_path_detail,
#         )

#         all_path_summaries.append(path_summary)

#         if mc_config.keep_path_detail:
#             all_path_detail_parts.append(path_year_state_df)
        
            
#         # ----------------------------------------------------
#         # progress callback
#         # ----------------------------------------------------
#         if progress_callback is not None:
#             progress_callback(path_id + 1, int(mc_config.n_paths))

#     # ----------------------------------------------------
#     # build mc_path_summary_df
#     # ----------------------------------------------------
#     if all_path_summaries:
#         mc_path_summary_df = pd.DataFrame(all_path_summaries)
#         mc_path_summary_df = mc_path_summary_df.sort_values("path_id").reset_index(drop=True)
#     else:
#         mc_path_summary_df = pd.DataFrame(columns=[
#             "path_id",
#             "path_success",
#             "final_total_balance",
#             "total_shortfall_amount",
#             "first_shortfall_year",
#             "liquidity_terminal_balance",
#             "stability_terminal_balance",
#             "growth_terminal_balance",
#         ])

#     # ----------------------------------------------------
#     # build mc_path_detail_df
#     # ----------------------------------------------------
#     if mc_config.keep_path_detail and all_path_detail_parts:
#         mc_path_detail_df = pd.concat(all_path_detail_parts, axis=0, ignore_index=True)
#         mc_path_detail_df = mc_path_detail_df.sort_values(
#             ["path_id", "year", "bucket_name"]
#         ).reset_index(drop=True)
#     else:
#         mc_path_detail_df = pd.DataFrame(columns=[
#             "path_id",
#             "year",
#             "bucket_name",
#             "sampled_return",
#             "beginning_balance",
#             "contribution_in",
#             "transfer_in",
#             "investment_return",
#             "expense_out",
#             "transfer_out",
#             "ending_balance",
#             "is_shortfall",
#         ])

#     # ----------------------------------------------------
#     # build aggregated summaries
#     # ----------------------------------------------------
#     if mc_config.keep_path_detail:
#         mc_year_summary_df = build_mc_year_summary(mc_path_detail_df)
#         mc_bucket_summary_df = build_mc_bucket_summary(
#             mc_path_detail_df=mc_path_detail_df,
#             mc_path_summary_df=mc_path_summary_df,
#         )
#     else:
#         # ถ้าไม่เก็บ path detail จะยังทำ engine summary ได้
#         mc_year_summary_df = pd.DataFrame(columns=[
#             "year",
#             "bucket_name",
#             "p10_ending_balance",
#             "p50_ending_balance",
#             "p90_ending_balance",
#             "shortfall_probability",
#             "mean_investment_return",
#         ])
#         mc_bucket_summary_df = pd.DataFrame(columns=[
#             "bucket_name",
#             "success_probability",
#             "shortfall_probability",
#             "expected_terminal_balance",
#             "p10_terminal_balance",
#             "p50_terminal_balance",
#             "p90_terminal_balance",
#             "expected_shortfall",
#         ])

#     mc_engine_summary_df = build_mc_engine_summary(
#         mc_path_summary_df=mc_path_summary_df,
#     )

#     # ----------------------------------------------------
#     # return result
#     # ----------------------------------------------------
#     return BucketMCResult(
#         bucket_requirement_df=bucket_requirement_df,
#         initial_allocation_df=initial_allocation_df,
#         mc_year_summary_df=mc_year_summary_df,
#         mc_bucket_summary_df=mc_bucket_summary_df,
#         mc_engine_summary_df=mc_engine_summary_df,
#         mc_path_summary_df=mc_path_summary_df,
#         mc_path_detail_df=mc_path_detail_df,
#     )

# optimized version 1

from typing import Dict, List, Optional, Tuple
import pandas as pd


# ============================================================
# Helper: precompute expense map once
# ============================================================
def _build_annual_expense_map_by_bucket_once(
    bucket_assignment_df: pd.DataFrame,
) -> Dict[Tuple[int, str], float]:
    expense_map = {}

    if bucket_assignment_df is None or bucket_assignment_df.empty:
        return expense_map

    grouped = (
        bucket_assignment_df
        .groupby(["year", "bucket_name"], as_index=False)["total_expense"]
        .sum()
    )

    for _, r in grouped.iterrows():
        expense_map[(int(r["year"]), str(r["bucket_name"]))] = float(r["total_expense"])

    return expense_map


# ============================================================
# Helper: simulate one path (fast version)
# ============================================================
def _simulate_one_mc_path_fast(
    path_id: int,
    simulation_start_year: int,
    simulation_end_year: int,
    initial_allocation_df: pd.DataFrame,
    annual_expense_map_by_bucket: Dict[Tuple[int, str], float],
    annual_contribution_map: Dict[int, float],
    annual_topup_map: Dict[int, float],
    sampled_return_df_one_path: pd.DataFrame,
    bucket_configs: List,
    funding_rule,
    keep_path_detail: bool,
    success_threshold: float,
):
    # initial balances
    balances = initialize_bucket_balances(initial_allocation_df)

    remaining_required_map = {
        r["bucket_name"]: float(r["unmet_required_amount"])
        for _, r in initial_allocation_df.iterrows()
    }

    sampled_return_map = build_sampled_return_map_for_path(
        sampled_return_df=sampled_return_df_one_path,
        path_id=path_id,
    )

    any_shortfall = False
    first_shortfall_year = None
    min_total_balance = float("inf")
    detail_rows = [] if keep_path_detail else None

    for year in range(simulation_start_year, simulation_end_year + 1):
        balances, states, remaining_required_map = simulate_bucket_year_one_path(
            path_id=path_id,
            year=year,
            simulation_start_year=simulation_start_year,
            balances=balances,
            annual_expense_map_by_bucket=annual_expense_map_by_bucket,
            annual_contribution_map=annual_contribution_map,
            annual_topup_map=annual_topup_map,
            remaining_required_map=remaining_required_map,
            sampled_return_map=sampled_return_map,
            bucket_configs=bucket_configs,
            funding_rule=funding_rule,
        )

        total_balance = 0.0
        for s in states:
            total_balance += float(s.ending_balance)
            if s.is_shortfall:
                any_shortfall = True
                if first_shortfall_year is None:
                    first_shortfall_year = int(s.year)

            if keep_path_detail:
                detail_rows.append(vars(s))

        min_total_balance = min(min_total_balance, total_balance)

    final_total_balance = round(sum(balances.values()), 2)
    total_shortfall_amount = round(abs(min(min_total_balance, 0.0)), 2)

    path_summary = {
        "path_id": path_id,
        "path_success": (not any_shortfall) and final_total_balance >= success_threshold,
        "final_total_balance": final_total_balance,
        "total_shortfall_amount": total_shortfall_amount,
        "first_shortfall_year": first_shortfall_year,
        "liquidity_terminal_balance": round(balances.get("liquidity", 0.0), 2),
        "stability_terminal_balance": round(balances.get("stability", 0.0), 2),
        "growth_terminal_balance": round(balances.get("growth", 0.0), 2),
    }

    if keep_path_detail:
        path_detail_df = pd.DataFrame(detail_rows)
    else:
        path_detail_df = pd.DataFrame()

    return path_detail_df, path_summary


# ============================================================
# ✅ OPTIMIZED MONTE CARLO (QUICK WINS)
# ============================================================
def run_bucket_engine_monte_carlo(
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
    progress_callback=None,
    progress_update_every: int = 1,
) -> BucketMCResult:
    """
    Optimized Monte Carlo engine (quick wins)
    - Logic identical to original version
    - Much lower DataFrame + memory overhead

    Parameters
    ----------
    initial_allocation_override_df : Optional[pd.DataFrame]
        ถ้าระบุ จะใช้ allocation นี้แทน auto-computed allocation
        ต้องมี columns: bucket_name, recommended_initial_amount,
        recommended_initial_weight, unmet_required_amount
        (ใช้สำหรับ manual allocation mode)
    """

    bucket_configs = bucket_configs or default_bucket_configs()
    funding_rule = funding_rule or BucketFundingRule()
    bucket_return_models = bucket_return_models or default_bucket_return_models()
    mc_config = mc_config or MonteCarloConfig()

    validate_bucket_configs(bucket_configs)
    validate_bucket_funding_rule(funding_rule, bucket_configs)
    validate_bucket_return_models(
        bucket_return_models,
        expected_bucket_names=[b.bucket_name for b in bucket_configs],
    )
    validate_monte_carlo_config(mc_config)

    # ----------------------------------------------------
    # planning layer (ONCE)
    # ----------------------------------------------------
    annual_expense_df = prepare_annual_expense(expense_df)

    candidate_years = set()
    if not annual_expense_df.empty:
        candidate_years |= set(annual_expense_df["year"].astype(int))
    candidate_years |= set(annual_contribution_map.keys())
    candidate_years |= set(annual_topup_map.keys())

    simulation_start_year = simulation_start_year or min(candidate_years)
    simulation_end_year = max(candidate_years)
    projection_years = list(range(simulation_start_year, simulation_end_year + 1))

    bucket_assignment_df = assign_expense_to_buckets(
        annual_expense_df=annual_expense_df,
        simulation_start_year=simulation_start_year,
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
        simulation_start_year=simulation_start_year,
        bucket_configs=bucket_configs,
        discount_rate_override_map=conservative_discount_rate_map,
    )

    # Fix 3: ใช้ manual allocation ถ้า user override ไว้
    if initial_allocation_override_df is not None:
        initial_allocation_df = initial_allocation_override_df
    else:
        initial_allocation_df = allocate_initial_savings_to_buckets(
            initial_savings=initial_savings,
            bucket_requirement_df=bucket_requirement_df,
            funding_rule=funding_rule,
        )

    annual_expense_map_by_bucket = _build_annual_expense_map_by_bucket_once(
        bucket_assignment_df
    )

    # ----------------------------------------------------
    # Monte Carlo loop
    # ----------------------------------------------------
    all_path_summaries = []
    all_path_details  = [] if mc_config.keep_path_detail  else None
    all_asset_details = [] if mc_config.keep_asset_detail else None

    total_paths = int(mc_config.n_paths)

    for path_id in range(total_paths):
        sampled_return_df_one_path, asset_detail_df_one_path = sample_bucket_returns_for_path(
            path_id=path_id,
            years=projection_years,
            bucket_return_models=bucket_return_models,
            mc_config=mc_config,
        )

        path_detail_df, path_summary = _simulate_one_mc_path_fast(
            path_id=path_id,
            simulation_start_year=simulation_start_year,
            simulation_end_year=simulation_end_year,
            initial_allocation_df=initial_allocation_df,
            annual_expense_map_by_bucket=annual_expense_map_by_bucket,
            annual_contribution_map=annual_contribution_map,
            annual_topup_map=annual_topup_map,
            sampled_return_df_one_path=sampled_return_df_one_path,
            bucket_configs=bucket_configs,
            funding_rule=funding_rule,
            keep_path_detail=mc_config.keep_path_detail,
            success_threshold=mc_config.success_threshold,
        )

        all_path_summaries.append(path_summary)

        if mc_config.keep_path_detail:
            all_path_details.append(path_detail_df)

        if mc_config.keep_asset_detail and not asset_detail_df_one_path.empty:
            all_asset_details.append(asset_detail_df_one_path)

        if progress_callback and (
            (path_id + 1) % progress_update_every == 0
            or path_id + 1 == total_paths
        ):
            progress_callback(path_id + 1, total_paths)

    # ----------------------------------------------------
    # build outputs
    # ----------------------------------------------------
    mc_path_summary_df = pd.DataFrame(all_path_summaries)

    if mc_config.keep_path_detail and all_path_details:
        mc_path_detail_df = pd.concat(all_path_details, ignore_index=True)
    else:
        mc_path_detail_df = pd.DataFrame()

    if mc_config.keep_asset_detail and all_asset_details:
        mc_path_asset_detail_df = pd.concat(all_asset_details, ignore_index=True)
        mc_path_asset_detail_df = mc_path_asset_detail_df.sort_values(
            ["path_id", "year", "bucket_name", "asset_name"]
        ).reset_index(drop=True)
    else:
        mc_path_asset_detail_df = pd.DataFrame()

    mc_engine_summary_df = build_mc_engine_summary(mc_path_summary_df)

    if mc_config.keep_path_detail:
        mc_year_summary_df = build_mc_year_summary(mc_path_detail_df)
        mc_bucket_summary_df = build_mc_bucket_summary(
            mc_path_detail_df, mc_path_summary_df
        )
    else:
        mc_year_summary_df = pd.DataFrame()
        mc_bucket_summary_df = pd.DataFrame()

    return BucketMCResult(
        bucket_requirement_df=bucket_requirement_df,
        initial_allocation_df=initial_allocation_df,
        mc_year_summary_df=mc_year_summary_df,
        mc_bucket_summary_df=mc_bucket_summary_df,
        mc_engine_summary_df=mc_engine_summary_df,
        mc_path_summary_df=mc_path_summary_df,
        mc_path_detail_df=mc_path_detail_df,
        mc_path_asset_detail_df=mc_path_asset_detail_df,
    )

# optimized version 2
# LEVEL-2 OPTIMIZATION HELPERS

def _validate_supported_l2_setup(bucket_configs: List) -> None:
    """
    Level-2 version assumes contiguous ordered buckets from bucket_configs.
    It supports any number of buckets, but is optimized for small fixed bucket count.
    """
    validate_bucket_configs(bucket_configs)


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

    # bucket horizon end offsets and next bucket idx
    horizon_end_offsets = np.full(n_buckets, -1, dtype=int)
    next_bucket_idx = np.full(n_buckets, -1, dtype=int)

    cfg_map = {cfg.bucket_name: cfg for cfg in bucket_configs}
    for i, b in enumerate(ordered_bucket_names):
        cfg = cfg_map[b]
        horizon_end_offsets[i] = -1 if cfg.end_offset_year is None else int(cfg.end_offset_year)
        next_bucket_idx[i] = i + 1 if i + 1 < n_buckets else -1

    return {
        "ordered_bucket_names": ordered_bucket_names,
        "bucket_to_idx": bucket_to_idx,
        "years": years,
        "year_to_idx": year_to_idx,
        "n_buckets": n_buckets,
        "n_years": n_years,
        "contribution_arr": contribution_arr,
        "topup_arr": topup_arr,
        "expense_arr": expense_arr,
        "horizon_end_offsets": horizon_end_offsets,
        "next_bucket_idx": next_bucket_idx,
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
    Unified return sampler for Level-2 MC.

    Always samples per-asset when assets are defined in the BucketReturnModel
    (correct portfolio behaviour), falling back to bucket-level when assets list
    is empty. Both capture_detail=True and capture_detail=False make identical
    RNG calls in the same order, so sampled_returns is deterministically the same
    regardless of whether detail is captured.

    Parameters
    ----------
    capture_detail : bool
        If True, collect per-asset detail rows and return them.
        If False, skip detail collection — same sampling, less memory overhead.

    Returns
    -------
    sampled_returns : np.ndarray shape [n_years, n_buckets]
        Weighted-average bucket return for each (year, bucket).
    asset_detail_rows : list of dicts
        Empty list when capture_detail=False.
        Keys: path_id, year, bucket_name, asset_name,
              weight_pct, weight_normalized, sampled_return, weighted_contribution
    """
    model_map = {m.bucket_name: m for m in bucket_return_models}
    n_years = len(years)
    n_buckets = len(ordered_bucket_names)
    out = np.zeros((n_years, n_buckets), dtype=float)
    asset_detail_rows: List[dict] = []

    rng = _build_path_rng(mc_config, path_id)

    for yi in range(n_years):
        year = int(years[yi])
        for bi, bucket_name in enumerate(ordered_bucket_names):
            m = model_map[bucket_name]
            if capture_detail:
                ret, detail = sample_one_bucket_return(m, rng, capture_asset_detail=True)
                for row in detail:
                    row["path_id"] = int(path_id)
                    row["year"] = year
                    row["bucket_name"] = str(bucket_name)
                    asset_detail_rows.append(row)
            else:
                ret = sample_one_bucket_return(m, rng, capture_asset_detail=False)
            out[yi, bi] = ret

    return out, asset_detail_rows


def _allocate_yearly_inflow_to_buckets_array(
    inflow_amount: float,
    remaining_required_arr: np.ndarray,
    contribution_priority_names: List[str],
    bucket_to_idx: Dict[str, int],
    n_buckets: int,
) -> np.ndarray:
    """
    Same logic as allocate_yearly_inflow_to_buckets(...), but array-based.
    """
    if inflow_amount < 0:
        raise ValueError("inflow_amount must be >= 0")

    alloc = np.zeros(n_buckets, dtype=float)
    remaining_amount = float(inflow_amount)

    for bucket_name in contribution_priority_names:
        idx = bucket_to_idx[bucket_name]
        need = max(0.0, float(remaining_required_arr[idx]))

        if remaining_amount <= 0:
            break

        give = min(remaining_amount, need)
        alloc[idx] += give
        remaining_amount -= give

    if remaining_amount > 0:
        last_idx = bucket_to_idx[contribution_priority_names[-1]]
        alloc[last_idx] += remaining_amount
        remaining_amount = 0.0

    return alloc


def _resolve_shortfall_array(
    year: int,
    target_idx: int,
    balances_arr: np.ndarray,
    ordered_bucket_names: List[str],
    funding_rule,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Same logic as resolve_shortfall_with_cross_bucket_transfer(...), but array-based.

    Returns
    -------
    balances_arr : updated balances
    transfer_in_arr : per bucket transfer in for this step
    transfer_out_arr : per bucket transfer out for this step
    """
    n_buckets = len(ordered_bucket_names)
    transfer_in_arr = np.zeros(n_buckets, dtype=float)
    transfer_out_arr = np.zeros(n_buckets, dtype=float)

    if balances_arr[target_idx] >= 0:
        return balances_arr, transfer_in_arr, transfer_out_arr

    if (not funding_rule.allow_cross_bucket_transfer) or (funding_rule.transfer_direction != "waterfall"):
        return balances_arr, transfer_in_arr, transfer_out_arr

    shortfall = abs(float(balances_arr[target_idx]))

    # donor buckets are longer horizon buckets to the right
    for donor_idx in range(target_idx + 1, n_buckets):
        if shortfall <= 0:
            break

        available = max(0.0, float(balances_arr[donor_idx]))
        if available <= 0:
            continue

        xfer = min(available, shortfall)
        balances_arr[donor_idx] -= xfer
        balances_arr[target_idx] += xfer
        transfer_out_arr[donor_idx] += xfer
        transfer_in_arr[target_idx] += xfer
        shortfall -= xfer

    return balances_arr, transfer_in_arr, transfer_out_arr


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
    horizon_end_offsets = static_ctx["horizon_end_offsets"]
    next_bucket_idx = static_ctx["next_bucket_idx"]

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
    min_total_balance = float("inf")
    detail_rows = [] if keep_path_detail else None

    priority_idx_names = list(funding_rule.contribution_priority)
    start_year = int(years[0])

    for yi in range(n_years):
        year = int(years[yi])
        year_offset = (year - start_year) + 1

        beginning_balances = balances.copy()

        # A) inflow allocation
        total_inflow = float(contribution_arr[yi] + topup_arr[yi])
        contribution_in = _allocate_yearly_inflow_to_buckets_array(
            inflow_amount=total_inflow,
            remaining_required_arr=remaining_required,
            contribution_priority_names=priority_idx_names,
            bucket_to_idx=bucket_to_idx,
            n_buckets=n_buckets,
        )
        remaining_required = np.maximum(0.0, remaining_required - contribution_in)

        # B) add inflow, apply return, apply expense
        transfer_in = np.zeros(n_buckets, dtype=float)
        transfer_out = np.zeros(n_buckets, dtype=float)

        balances = balances + contribution_in
        base_for_return = balances.copy()
        investment_return = np.where(base_for_return > 0, base_for_return * sampled_returns[yi], 0.0)
        investment_return = np.round(investment_return, 2)

        # Fix 2: ลด remaining requirement ด้วย investment return จริงที่เกิดขึ้น (numpy version)
        remaining_required = np.maximum(0.0, remaining_required - np.maximum(0.0, investment_return))

        balances = base_for_return + investment_return - expense_arr[yi]
        balances = np.round(balances, 2)

        # C) shortfall cover in bucket order
        for bi in range(n_buckets):
            if balances[bi] < 0:
                balances, xfer_in_step, xfer_out_step = _resolve_shortfall_array(
                    year=year,
                    target_idx=bi,
                    balances_arr=balances,
                    ordered_bucket_names=ordered_bucket_names,
                    funding_rule=funding_rule,
                )
                transfer_in += xfer_in_step
                transfer_out += xfer_out_step

                if balances[bi] < 0:
                    any_shortfall = True
                    if first_shortfall_year is None:
                        first_shortfall_year = year

        # D) rollover at end of bucket horizon
        for bi in range(n_buckets):
            end_offset = int(horizon_end_offsets[bi])
            next_idx = int(next_bucket_idx[bi])

            if end_offset != -1 and year_offset >= end_offset and next_idx != -1:
                bal = float(balances[bi])
                if bal > 0:
                    balances[bi] = 0.0
                    balances[next_idx] += bal
                    transfer_out[bi] += bal
                    transfer_in[next_idx] += bal

        balances = np.round(balances, 2)

        total_balance_this_year = float(np.round(balances.sum(), 2))
        min_total_balance = min(min_total_balance, total_balance_this_year)

        is_shortfall_arr = balances < 0
        if is_shortfall_arr.any():
            any_shortfall = True
            if first_shortfall_year is None:
                first_shortfall_year = year

        if keep_path_detail:
            for bi, bucket_name in enumerate(ordered_bucket_names):
                detail_rows.append({
                    "path_id": int(path_id),
                    "year": int(year),
                    "bucket_name": str(bucket_name),
                    "sampled_return": round(float(sampled_returns[yi, bi]), 8),
                    "beginning_balance": round(float(beginning_balances[bi]), 2),
                    "contribution_in": round(float(contribution_in[bi]), 2),
                    "transfer_in": round(float(transfer_in[bi]), 2),
                    "investment_return": round(float(investment_return[bi]), 2),
                    "expense_out": round(float(expense_arr[yi, bi]), 2),
                    "transfer_out": round(float(transfer_out[bi]), 2),
                    "ending_balance": round(float(balances[bi]), 2),
                    "is_shortfall": bool(is_shortfall_arr[bi]),
                })

    final_total_balance = round(float(balances.sum()), 2)
    total_shortfall_amount = round(abs(min(min_total_balance, 0.0)), 2)
    path_success = (not any_shortfall) and (final_total_balance >= float(success_threshold))

    path_summary = {
        "path_id": int(path_id),
        "path_success": bool(path_success),
        "final_total_balance": round(final_total_balance, 2),
        "total_shortfall_amount": round(total_shortfall_amount, 2),
        "first_shortfall_year": first_shortfall_year,
        "liquidity_terminal_balance": round(float(balances[bucket_to_idx.get("liquidity", 0)]), 2)
            if "liquidity" in bucket_to_idx else 0.0,
        "stability_terminal_balance": round(float(balances[bucket_to_idx.get("stability", 0)]), 2)
            if "stability" in bucket_to_idx else 0.0,
        "growth_terminal_balance": round(float(balances[bucket_to_idx.get("growth", 0)]), 2)
            if "growth" in bucket_to_idx else 0.0,
    }

    if keep_path_detail:
        path_detail_df = pd.DataFrame(detail_rows)
    else:
        path_detail_df = pd.DataFrame(columns=[
            "path_id", "year", "bucket_name", "sampled_return", "beginning_balance",
            "contribution_in", "transfer_in", "investment_return", "expense_out",
            "transfer_out", "ending_balance", "is_shortfall",
        ])

    if keep_asset_detail and _asset_detail_rows_all:
        asset_detail_df = pd.DataFrame(_asset_detail_rows_all)
        # reorder columns for readability
        _adtl_cols = ["path_id", "year", "bucket_name", "asset_name",
                      "weight_pct", "weight_normalized", "sampled_return", "weighted_contribution"]
        asset_detail_df = asset_detail_df[[c for c in _adtl_cols if c in asset_detail_df.columns]]
    else:
        asset_detail_df = pd.DataFrame(columns=[
            "path_id", "year", "bucket_name", "asset_name",
            "weight_pct", "weight_normalized", "sampled_return", "weighted_contribution",
        ])

    return path_detail_df, asset_detail_df, path_summary


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

    _validate_supported_l2_setup(bucket_configs)
    validate_bucket_funding_rule(funding_rule, bucket_configs)
    validate_bucket_return_models(
        bucket_return_models=bucket_return_models,
        expected_bucket_names=[cfg.bucket_name for cfg in bucket_configs],
    )
    validate_monte_carlo_config(mc_config)

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
    # floor ที่ 0% = ต้องมีเงิน >= nominal future expense ทั้งหมด
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

    # ----------------------------------------------------
    # Main MC loop
    # ----------------------------------------------------
    all_path_summaries = []
    all_path_detail_parts = [] if mc_config.keep_path_detail else None
    all_asset_detail_parts = [] if mc_config.keep_asset_detail else None

    total_paths = int(mc_config.n_paths)

    for path_id in range(total_paths):
        path_detail_df, asset_detail_df_one, path_summary = _simulate_one_mc_path_l2(
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
        )

        all_path_summaries.append(path_summary)

        if mc_config.keep_path_detail:
            all_path_detail_parts.append(path_detail_df)

        if mc_config.keep_asset_detail and not asset_detail_df_one.empty:
            all_asset_detail_parts.append(asset_detail_df_one)

        if progress_callback is not None:
            current_path = path_id + 1
            if (current_path % progress_update_every == 0) or (current_path == total_paths):
                progress_callback(current_path, total_paths)

    # ----------------------------------------------------
    # Build outputs
    # ----------------------------------------------------
    mc_path_summary_df = pd.DataFrame(all_path_summaries)
    if not mc_path_summary_df.empty:
        mc_path_summary_df = mc_path_summary_df.sort_values("path_id").reset_index(drop=True)

    if mc_config.keep_path_detail:
        if all_path_detail_parts:
            mc_path_detail_df = pd.concat(all_path_detail_parts, axis=0, ignore_index=True)
            mc_path_detail_df = mc_path_detail_df.sort_values(
                ["path_id", "year", "bucket_name"]
            ).reset_index(drop=True)
        else:
            mc_path_detail_df = pd.DataFrame(columns=[
                "path_id", "year", "bucket_name", "sampled_return", "beginning_balance",
                "contribution_in", "transfer_in", "investment_return", "expense_out",
                "transfer_out", "ending_balance", "is_shortfall",
            ])
    else:
        mc_path_detail_df = pd.DataFrame(columns=[
            "path_id", "year", "bucket_name", "sampled_return", "beginning_balance",
            "contribution_in", "transfer_in", "investment_return", "expense_out",
            "transfer_out", "ending_balance", "is_shortfall",
        ])

    if mc_config.keep_path_detail:
        mc_year_summary_df = build_mc_year_summary(mc_path_detail_df)
        mc_bucket_summary_df = build_mc_bucket_summary(
            mc_path_detail_df=mc_path_detail_df,
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
    if mc_config.keep_asset_detail and all_asset_detail_parts:
        mc_path_asset_detail_df = pd.concat(all_asset_detail_parts, axis=0, ignore_index=True)
        mc_path_asset_detail_df = mc_path_asset_detail_df.sort_values(
            ["path_id", "year", "bucket_name"]
        ).reset_index(drop=True)
    else:
        mc_path_asset_detail_df = pd.DataFrame(columns=[
            "path_id", "year", "bucket_name", "asset_name",
            "weight_pct", "weight_normalized", "sampled_return", "weighted_contribution",
        ])

    return BucketMCResult(
        bucket_requirement_df=bucket_requirement_df,
        initial_allocation_df=initial_allocation_df,
        mc_year_summary_df=mc_year_summary_df,
        mc_bucket_summary_df=mc_bucket_summary_df,
        mc_engine_summary_df=mc_engine_summary_df,
        mc_path_summary_df=mc_path_summary_df,
        mc_path_detail_df=mc_path_detail_df,
        mc_path_asset_detail_df=mc_path_asset_detail_df,
    )


