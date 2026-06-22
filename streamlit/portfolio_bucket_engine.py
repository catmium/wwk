from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import pandas as pd


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class BucketConfig:
    """
    นิยาม bucket แต่ละตัว
    start_offset_year / end_offset_year อ้างอิงจาก simulation start year

    ตัวอย่าง:
    - liquidity: 1-3
    - stability: 4-7
    - growth: 8+
    """
    bucket_name: str
    start_offset_year: int
    end_offset_year: Optional[int]   # None = no upper bound
    annual_return_rate: float


@dataclass
class BucketFundingRule:
    """
    กติกาการเติมเงิน / โอนเงินข้าม bucket
    """
    contribution_priority: List[str] = field(
        default_factory=lambda: ["liquidity", "stability", "growth"]
    )
    allow_cross_bucket_transfer: bool = True
    transfer_direction: str = "forward_only"
    # forward_only:
    #   - liquidity surplus -> stability
    #   - stability surplus -> growth
    #   - growth surplus -> stays in growth
    #
    # waterfall:
    #   - allow cover shortfall by pulling from longer-horizon buckets


# ============================================================
# DEFAULT CONFIG
# ============================================================

def default_bucket_configs() -> List[BucketConfig]:
    """
    default 3 buckets:
    - liquidity: ปี 1-3
    - stability: ปี 4-7
    - growth: ปี 8+
    """
    return [
        BucketConfig(
            bucket_name="liquidity",
            start_offset_year=1,
            end_offset_year=3,
            annual_return_rate=0.02,
        ),
        BucketConfig(
            bucket_name="stability",
            start_offset_year=4,
            end_offset_year=7,
            annual_return_rate=0.04,
        ),
        BucketConfig(
            bucket_name="growth",
            start_offset_year=8,
            end_offset_year=None,
            annual_return_rate=0.06,
        ),
    ]


# ============================================================
# VALIDATION
# ============================================================

def _sorted_bucket_configs(bucket_configs: List[BucketConfig]) -> List[BucketConfig]:
    return sorted(
        bucket_configs,
        key=lambda x: (x.start_offset_year, x.end_offset_year or 10**9, x.bucket_name)
    )


def validate_bucket_configs(bucket_configs: List[BucketConfig]) -> None:
    """
    validate bucket configs ว่า:
    - มี bucket_name ไม่ซ้ำ
    - offset range ถูกต้อง
    - annual_return_rate > -1
    - horizon ranges ไม่ overlap และควรต่อเนื่องกันจาก bucket แรกถึง bucket สุดท้าย
    """
    if not bucket_configs:
        raise ValueError("bucket_configs must not be empty")

    seen = set()
    for cfg in bucket_configs:
        if cfg.bucket_name in seen:
            raise ValueError(f"Duplicate bucket_name found: {cfg.bucket_name}")
        seen.add(cfg.bucket_name)

        if cfg.start_offset_year < 1:
            raise ValueError(
                f"{cfg.bucket_name}: start_offset_year must be >= 1"
            )

        if cfg.end_offset_year is not None and cfg.start_offset_year > cfg.end_offset_year:
            raise ValueError(
                f"{cfg.bucket_name}: start_offset_year > end_offset_year"
            )

        if cfg.annual_return_rate <= -1:
            raise ValueError(
                f"{cfg.bucket_name}: annual_return_rate must be > -1"
            )

    sorted_cfgs = _sorted_bucket_configs(bucket_configs)

    # bucket แรกควรเริ่มที่ 1
    if sorted_cfgs[0].start_offset_year != 1:
        raise ValueError(
            "bucket_configs must start from offset year 1"
        )

    # ห้าม overlap และควรต่อกันแบบไม่มี gap
    prev_end = None
    for idx, cfg in enumerate(sorted_cfgs):
        if idx == 0:
            prev_end = cfg.end_offset_year
            continue

        expected_start = (prev_end + 1) if prev_end is not None else None
        if expected_start is None:
            raise ValueError(
                "No bucket can appear after a bucket with end_offset_year=None"
            )

        if cfg.start_offset_year != expected_start:
            raise ValueError(
                "bucket_configs must be contiguous without gap/overlap: "
                f"expected start_offset_year={expected_start} for bucket={cfg.bucket_name}, "
                f"got {cfg.start_offset_year}"
            )
        prev_end = cfg.end_offset_year

    # bucket สุดท้ายควรเป็น open-ended เพื่อรองรับปี 8+
    if sorted_cfgs[-1].end_offset_year is not None:
        raise ValueError(
            "The last bucket must have end_offset_year=None to support long-term horizon"
        )


def validate_bucket_funding_rule(rule: BucketFundingRule, bucket_configs: List[BucketConfig]) -> None:
    """
    validate funding rule ว่า contribution_priority ครบและไม่สะกดผิด
    """
    valid_bucket_names = {x.bucket_name for x in bucket_configs}
    priority_names = list(rule.contribution_priority)

    if set(priority_names) != valid_bucket_names:
        raise ValueError(
            "BucketFundingRule.contribution_priority must contain exactly "
            f"these bucket names: {sorted(valid_bucket_names)}"
        )

    if len(priority_names) != len(valid_bucket_names):
        raise ValueError(
            "BucketFundingRule.contribution_priority must not contain duplicates"
        )

    if rule.transfer_direction not in {"forward_only", "waterfall"}:
        raise ValueError(
            "transfer_direction must be either 'forward_only' or 'waterfall'"
        )


# ============================================================
# PREPARE INPUTS
# ============================================================

def prepare_annual_expense(
    expense_df: pd.DataFrame,
    year_col: str = "year",
    amount_col: str = "inflated_amount",
) -> pd.DataFrame:
    """
    aggregate expense_df ให้เหลือ annual expense

    Expected output columns:
    - year
    - total_expense
    """
    if expense_df is None or expense_df.empty:
        return pd.DataFrame(columns=["year", "total_expense"])

    if year_col not in expense_df.columns:
        raise ValueError(f"expense_df must contain column: {year_col}")
    if amount_col not in expense_df.columns:
        raise ValueError(f"expense_df must contain column: {amount_col}")

    df = expense_df[[year_col, amount_col]].copy()
    df[year_col] = pd.to_numeric(df[year_col], errors="raise").astype(int)
    df[amount_col] = pd.to_numeric(df[amount_col], errors="raise").astype(float)

    agg = (
        df.groupby(year_col, as_index=False)[amount_col]
        .sum()
        .rename(columns={year_col: "year", amount_col: "total_expense"})
        .sort_values("year")
        .reset_index(drop=True)
    )
    agg["total_expense"] = agg["total_expense"].round(2)
    return agg


def build_funding_maps_from_saving_df(
    saving_df: pd.DataFrame,
    year_col: str = "year",
    contribution_col: str = "annual_contribution",
    topup_col: str = "annual_topup",
) -> Tuple[Dict[int, float], Dict[int, float]]:
    """
    ดึง annual contribution map และ annual topup map จาก saving_df

    Returns
    -------
    contribution_map : Dict[int, float]
        {year: annual_contribution}
    topup_map : Dict[int, float]
        {year: annual_topup}
    """
    if saving_df is None or saving_df.empty:
        return {}, {}

    required_cols = [year_col, contribution_col, topup_col]
    missing_cols = [c for c in required_cols if c not in saving_df.columns]
    if missing_cols:
        raise ValueError(
            f"saving_df is missing required columns: {missing_cols}"
        )

    df = saving_df[[year_col, contribution_col, topup_col]].copy()
    df[year_col] = pd.to_numeric(df[year_col], errors="raise").astype(int)
    df[contribution_col] = pd.to_numeric(df[contribution_col], errors="raise").astype(float)
    df[topup_col] = pd.to_numeric(df[topup_col], errors="raise").astype(float)

    # ถ้ามีปีซ้ำ จะ sum ให้เลยเพื่อความปลอดภัยของ helper นี้
    grouped = (
        df.groupby(year_col, as_index=False)[[contribution_col, topup_col]]
        .sum()
        .sort_values(year_col)
        .reset_index(drop=True)
    )

    contribution_map = dict(zip(grouped[year_col], grouped[contribution_col]))
    topup_map = dict(zip(grouped[year_col], grouped[topup_col]))
    return contribution_map, topup_map


# ============================================================
# BUCKET ASSIGNMENT
# ============================================================

def get_year_offset(simulation_start_year: int, year: int) -> int:
    """
    year offset โดยให้ start year มี offset = 1
    เช่น start_year=2026
    - 2026 => 1
    - 2027 => 2
    - 2033 => 8
    """
    return (year - simulation_start_year) + 1


def assign_bucket_by_year_offset(
    year_offset: int,
    bucket_configs: List[BucketConfig],
) -> str:
    """
    map year_offset -> bucket_name
    """
    validate_bucket_configs(bucket_configs)

    if year_offset < 1:
        raise ValueError("year_offset must be >= 1")

    for cfg in _sorted_bucket_configs(bucket_configs):
        start_ok = year_offset >= cfg.start_offset_year
        end_ok = (cfg.end_offset_year is None) or (year_offset <= cfg.end_offset_year)
        if start_ok and end_ok:
            return cfg.bucket_name

    raise ValueError(
        f"Cannot assign year_offset={year_offset} to any bucket. Check bucket_configs."
    )


def assign_expense_to_buckets(
    annual_expense_df: pd.DataFrame,
    simulation_start_year: int,
    bucket_configs: List[BucketConfig],
) -> pd.DataFrame:
    """
    assign annual expense เข้า bucket ตาม year offset

    Expected output columns:
    - year
    - year_offset
    - bucket_name
    - total_expense
    """
    validate_bucket_configs(bucket_configs)

    if annual_expense_df is None or annual_expense_df.empty:
        return pd.DataFrame(columns=["year", "year_offset", "bucket_name", "total_expense"])

    required_cols = ["year", "total_expense"]
    missing_cols = [c for c in required_cols if c not in annual_expense_df.columns]
    if missing_cols:
        raise ValueError(
            f"annual_expense_df is missing required columns: {missing_cols}"
        )

    df = annual_expense_df[required_cols].copy()
    df["year"] = pd.to_numeric(df["year"], errors="raise").astype(int)
    df["total_expense"] = pd.to_numeric(df["total_expense"], errors="raise").astype(float)
    df = df.sort_values("year").reset_index(drop=True)

    df["year_offset"] = df["year"].apply(lambda y: get_year_offset(simulation_start_year, int(y)))
    if (df["year_offset"] < 1).any():
        bad_years = df.loc[df["year_offset"] < 1, "year"].tolist()
        raise ValueError(
            f"Found expense year earlier than simulation_start_year={simulation_start_year}: {bad_years}"
        )

    df["bucket_name"] = df["year_offset"].apply(
        lambda off: assign_bucket_by_year_offset(int(off), bucket_configs)
    )
    df["total_expense"] = df["total_expense"].round(2)

    return df[["year", "year_offset", "bucket_name", "total_expense"]]


# ============================================================
# REQUIRED AMOUNT / INITIAL ALLOCATION
# ============================================================

def discount_amount(
    future_amount: float,
    annual_return_rate: float,
    years_from_start: int,
) -> float:
    """
    discount future amount กลับมาที่ปีเริ่ม simulation
    years_from_start:
    - ถ้า expense เกิดปี start_year => 0
    - ปีถัดไป => 1
    """
    return float(future_amount) / ((1 + annual_return_rate) ** years_from_start)


def _bucket_return_map(bucket_configs: List[BucketConfig]) -> Dict[str, float]:
    validate_bucket_configs(bucket_configs)
    return {cfg.bucket_name: float(cfg.annual_return_rate) for cfg in bucket_configs}


def calculate_bucket_requirements(
    bucket_assignment_df: pd.DataFrame,
    simulation_start_year: int,
    bucket_configs: List[BucketConfig],
    discount_rate_override_map: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """
    คำนวณ required_present_value ของแต่ละ bucket

    Parameters
    ----------
    discount_rate_override_map : Optional[Dict[str, float]]
        ถ้าระบุ จะ override discount rate สำหรับแต่ละ bucket
        แทนการใช้ annual_return_rate จาก BucketConfig
        เหมาะสำหรับ conservative discounting เช่น ส่ง min_return
        เพื่อให้ required_present_value สูงขึ้น (safety buffer)
        เหมาะกับ education planning ที่เป้าคือ cover expense

    Expected output columns:
    - bucket_name
    - required_present_value
    - total_future_expense
    - first_expense_year
    - last_expense_year
    """
    validate_bucket_configs(bucket_configs)

    base_cols = [
        "bucket_name",
        "required_present_value",
        "total_future_expense",
        "first_expense_year",
        "last_expense_year",
    ]

    if bucket_assignment_df is None or bucket_assignment_df.empty:
        rows = []
        for cfg in _sorted_bucket_configs(bucket_configs):
            rows.append({
                "bucket_name": cfg.bucket_name,
                "required_present_value": 0.0,
                "total_future_expense": 0.0,
                "first_expense_year": None,
                "last_expense_year": None,
            })
        return pd.DataFrame(rows, columns=base_cols)

    required_cols = ["year", "bucket_name", "total_expense"]
    missing_cols = [c for c in required_cols if c not in bucket_assignment_df.columns]
    if missing_cols:
        raise ValueError(
            f"bucket_assignment_df is missing required columns: {missing_cols}"
        )

    df = bucket_assignment_df[required_cols].copy()
    df["year"] = pd.to_numeric(df["year"], errors="raise").astype(int)
    df["total_expense"] = pd.to_numeric(df["total_expense"], errors="raise").astype(float)

    return_map = _bucket_return_map(bucket_configs)

    # Apply conservative discount rates if provided
    # (e.g. min_return แทน expected return เพื่อ over-estimate ว่าต้องมีเงินเท่าไร)
    if discount_rate_override_map:
        for b, rate in discount_rate_override_map.items():
            if b in return_map:
                # clamp เพื่อกัน -100% (ทำให้ discount factor = 0 / infinity)
                return_map[b] = max(float(rate), -0.9999)

    # start year => 0, next year => 1
    df["years_from_start"] = df["year"].apply(lambda y: int(y) - int(simulation_start_year))
    if (df["years_from_start"] < 0).any():
        bad_years = df.loc[df["years_from_start"] < 0, "year"].tolist()
        raise ValueError(
            f"Found year earlier than simulation_start_year={simulation_start_year}: {bad_years}"
        )

    df["discounted_amount"] = df.apply(
        lambda r: discount_amount(
            future_amount=float(r["total_expense"]),
            annual_return_rate=return_map[str(r["bucket_name"])],
            years_from_start=int(r["years_from_start"]),
        ),
        axis=1,
    )

    agg = (
        df.groupby("bucket_name", as_index=False)
        .agg(
            required_present_value=("discounted_amount", "sum"),
            total_future_expense=("total_expense", "sum"),
            first_expense_year=("year", "min"),
            last_expense_year=("year", "max"),
        )
    )

    # ensure every bucket exists in result even if no expense assigned
    rows = []
    by_bucket = {r["bucket_name"]: r for r in agg.to_dict(orient="records")}
    for cfg in _sorted_bucket_configs(bucket_configs):
        rec = by_bucket.get(cfg.bucket_name)
        if rec is None:
            rows.append({
                "bucket_name": cfg.bucket_name,
                "required_present_value": 0.0,
                "total_future_expense": 0.0,
                "first_expense_year": None,
                "last_expense_year": None,
            })
        else:
            rows.append({
                "bucket_name": cfg.bucket_name,
                "required_present_value": round(float(rec["required_present_value"]), 2),
                "total_future_expense": round(float(rec["total_future_expense"]), 2),
                "first_expense_year": int(rec["first_expense_year"]) if pd.notna(rec["first_expense_year"]) else None,
                "last_expense_year": int(rec["last_expense_year"]) if pd.notna(rec["last_expense_year"]) else None,
            })

    return pd.DataFrame(rows, columns=base_cols)


def allocate_initial_savings_to_buckets(
    initial_savings: float,
    bucket_requirement_df: pd.DataFrame,
    funding_rule: BucketFundingRule,
) -> pd.DataFrame:
    """
    allocate initial_savings ไปตาม priority
    โดยพยายาม fill bucket requirement จากใกล้ -> ไกล

    Expected output columns:
    - bucket_name
    - recommended_initial_amount
    - recommended_initial_weight
    - unmet_required_amount
    """
    if initial_savings < 0:
        raise ValueError("initial_savings must be >= 0")

    if bucket_requirement_df is None or bucket_requirement_df.empty:
        raise ValueError("bucket_requirement_df must not be empty")

    required_cols = ["bucket_name", "required_present_value"]
    missing_cols = [c for c in required_cols if c not in bucket_requirement_df.columns]
    if missing_cols:
        raise ValueError(
            f"bucket_requirement_df is missing required columns: {missing_cols}"
        )

    req_df = bucket_requirement_df.copy()
    req_df["required_present_value"] = pd.to_numeric(
        req_df["required_present_value"], errors="raise"
    ).astype(float)

    bucket_names = req_df["bucket_name"].astype(str).tolist()
    if set(bucket_names) != set(funding_rule.contribution_priority):
        raise ValueError(
            "bucket_requirement_df bucket_name values do not match funding_rule.contribution_priority"
        )

    remaining_cash = float(initial_savings)
    rows = []

    req_map = dict(zip(req_df["bucket_name"], req_df["required_present_value"]))

    for bucket_name in funding_rule.contribution_priority:
        required_amt = float(req_map.get(bucket_name, 0.0))
        allocated = min(remaining_cash, max(required_amt, 0.0))
        remaining_cash -= allocated
        unmet = max(0.0, required_amt - allocated)

        rows.append({
            "bucket_name": bucket_name,
            "recommended_initial_amount": round(float(allocated), 2),
            "recommended_initial_weight": 0.0,
            "unmet_required_amount": round(float(unmet), 2),
        })

    if remaining_cash > 0 and rows:
        rows[-1]["recommended_initial_amount"] = round(
            float(rows[-1]["recommended_initial_amount"] + remaining_cash), 2
        )
        remaining_cash = 0.0

    total_allocated = sum(float(r["recommended_initial_amount"]) for r in rows)
    if total_allocated > 0:
        for r in rows:
            r["recommended_initial_weight"] = round(
                float(r["recommended_initial_amount"]) / total_allocated, 6
            )
    else:
        for r in rows:
            r["recommended_initial_weight"] = 0.0

    return pd.DataFrame(
        rows,
        columns=[
            "bucket_name",
            "recommended_initial_amount",
            "recommended_initial_weight",
            "unmet_required_amount",
        ],
    )



# ============================================================
# PHASE 2 PLACEHOLDERS (ยังไม่ implement)
# ============================================================

# ============================================================

def _bucket_names_in_order(bucket_configs: List[BucketConfig]) -> List[str]:
    return [cfg.bucket_name for cfg in _sorted_bucket_configs(bucket_configs)]

