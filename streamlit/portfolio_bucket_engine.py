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


@dataclass
class AnnualExpenseRow:
    """
    annual expense หลัง aggregate จาก expense_df
    """
    year: int
    total_expense: float


@dataclass
class BucketExpenseAssignmentRow:
    """
    expense ของแต่ละปีถูก assign เข้า bucket ไหน
    """
    year: int
    year_offset: int
    bucket_name: str
    total_expense: float


@dataclass
class BucketRequirementRow:
    """
    จำนวนเงินที่ควรมี ณ ปีเริ่มต้น เพื่อรองรับ future expense ของ bucket นั้น
    คิดแบบ discount ด้วย annual_return_rate ของ bucket
    """
    bucket_name: str
    required_present_value: float
    total_future_expense: float
    first_expense_year: Optional[int]
    last_expense_year: Optional[int]


@dataclass
class InitialAllocationRow:
    """
    recommended initial allocation จาก initial_savings ณ ปีเริ่ม simulation
    """
    bucket_name: str
    recommended_initial_amount: float
    recommended_initial_weight: float
    unmet_required_amount: float


@dataclass
class BucketYearState:
    """
    สถานะของ bucket รายปี
    """
    year: int
    bucket_name: str
    beginning_balance: float
    contribution_in: float
    transfer_in: float
    investment_return: float
    expense_out: float
    transfer_out: float
    ending_balance: float
    is_shortfall: bool


@dataclass
class TransferLog:
    """
    log การโอนเงินระหว่าง bucket
    """
    year: int
    from_bucket: str
    to_bucket: str
    amount: float
    reason: str


@dataclass
class BucketRecommendationSummary:
    """
    summary สุดท้ายระดับ bucket
    """
    bucket_name: str
    recommended_initial_amount: float
    recommended_initial_weight: float
    total_assigned_expense: float
    projected_terminal_value: float
    shortfall_amount: float
    is_sufficient: bool


@dataclass
class BucketEngineSummary:
    """
    summary ทั้ง engine
    """
    simulation_start_year: int
    simulation_end_year: int
    total_initial_savings: float
    total_contribution: float
    total_topup: float
    total_projected_expense: float
    final_total_balance: float
    total_shortfall_amount: float
    first_shortfall_year: Optional[int]
    is_plan_sufficient: bool


@dataclass
class BucketEngineResult:
    """
    output หลักของ engine
    """
    annual_expense_df: pd.DataFrame
    bucket_assignment_df: pd.DataFrame
    bucket_requirement_df: pd.DataFrame
    initial_allocation_df: pd.DataFrame
    bucket_year_state_df: pd.DataFrame
    transfer_log_df: pd.DataFrame
    bucket_summary_df: pd.DataFrame
    engine_summary_df: pd.DataFrame


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


def allocate_yearly_inflow_to_buckets(
    year: int,
    inflow_amount: float,
    current_balances: Dict[str, float],
    remaining_required_map: Dict[str, float],
    funding_rule: BucketFundingRule,
) -> Dict[str, float]:
    """
    allocate inflow ของปีนั้นไปตาม contribution priority
    - เติม bucket ที่ยังมี unmet requirement ก่อน
    - ถ้ามีเงินเหลือหลังจาก fill ทุก bucket แล้ว ให้ใส่ bucket สุดท้ายใน priority (growth)
    """
    if inflow_amount < 0:
        raise ValueError(f"inflow_amount must be >= 0 (year={year})")

    remaining_amount = float(inflow_amount)
    allocation_map = {k: 0.0 for k in funding_rule.contribution_priority}

    for bucket_name in funding_rule.contribution_priority:
        need = max(0.0, float(remaining_required_map.get(bucket_name, 0.0)))

        if remaining_amount <= 0:
            break

        alloc = min(remaining_amount, need)
        allocation_map[bucket_name] += alloc
        remaining_amount -= alloc

    # ถ้ายังมีเงินเหลือหลังจากเติม unmet requirement ครบทุก bucket
    # ให้ไปกองสุดท้ายใน priority (ปกติคือ growth)
    if remaining_amount > 0:
        last_bucket = funding_rule.contribution_priority[-1]
        allocation_map[last_bucket] += remaining_amount
        remaining_amount = 0.0

    return {k: round(float(v), 2) for k, v in allocation_map.items()}


def get_next_bucket_name(
    current_bucket_name: str,
    bucket_configs: List[BucketConfig],
) -> Optional[str]:
    ordered = _bucket_names_in_order(bucket_configs)
    if current_bucket_name not in ordered:
        raise ValueError(f"Unknown bucket_name: {current_bucket_name}")
    idx = ordered.index(current_bucket_name)
    if idx == len(ordered) - 1:
        return None
    return ordered[idx + 1]


def should_rollover_after_year(
    bucket_name: str,
    year_offset: int,
    bucket_configs: List[BucketConfig],
) -> bool:
    cfg_map = {cfg.bucket_name: cfg for cfg in bucket_configs}
    if bucket_name not in cfg_map:
        raise ValueError(f"Unknown bucket_name: {bucket_name}")
    cfg = cfg_map[bucket_name]
    if cfg.end_offset_year is None:
        return False
    return int(year_offset) >= int(cfg.end_offset_year)


def build_rollover_transfer(
    year: int,
    from_bucket: str,
    to_bucket: str,
    amount: float,
    reason: str = "rollover_after_horizon",
) -> TransferLog:
    return TransferLog(
        year=year,
        from_bucket=from_bucket,
        to_bucket=to_bucket,
        amount=round(float(amount), 2),
        reason=reason,
    )


def resolve_shortfall_with_cross_bucket_transfer(
    year: int,
    target_bucket: str,
    shortfall_amount: float,
    balances_after_expense: Dict[str, float],
    bucket_configs: List[BucketConfig],
    funding_rule: BucketFundingRule,
) -> Tuple[Dict[str, float], List[TransferLog], float]:
    """
    ถ้า transfer_direction == 'waterfall' จะพยายามดึงเงินจาก bucket ที่ยาวกว่า
    ลำดับ donor:
    - liquidity shortfall -> stability -> growth
    - stability shortfall -> growth
    - growth shortfall -> none
    """
    updated_balances = {k: float(v) for k, v in balances_after_expense.items()}
    logs: List[TransferLog] = []

    if shortfall_amount <= 0:
        return updated_balances, logs, 0.0

    if (not funding_rule.allow_cross_bucket_transfer) or (funding_rule.transfer_direction != "waterfall"):
        return updated_balances, logs, round(float(shortfall_amount), 2)

    ordered = _bucket_names_in_order(bucket_configs)
    if target_bucket not in ordered:
        raise ValueError(f"Unknown target_bucket: {target_bucket}")

    target_idx = ordered.index(target_bucket)
    donor_buckets = ordered[target_idx + 1:]
    remaining_shortfall = float(shortfall_amount)

    for donor in donor_buckets:
        if remaining_shortfall <= 0:
            break
        available = max(0.0, float(updated_balances.get(donor, 0.0)))
        if available <= 0:
            continue

        transfer_amt = min(available, remaining_shortfall)
        updated_balances[donor] = round(float(updated_balances[donor] - transfer_amt), 2)
        updated_balances[target_bucket] = round(float(updated_balances.get(target_bucket, 0.0) + transfer_amt), 2)
        remaining_shortfall -= transfer_amt

        logs.append(
            TransferLog(
                year=year,
                from_bucket=donor,
                to_bucket=target_bucket,
                amount=round(float(transfer_amt), 2),
                reason="cover_shortfall",
            )
        )

    return updated_balances, logs, round(float(max(remaining_shortfall, 0.0)), 2)


def initialize_bucket_balances(
    initial_allocation_df: pd.DataFrame,
) -> Dict[str, float]:
    required_cols = ["bucket_name", "recommended_initial_amount"]
    missing_cols = [c for c in required_cols if c not in initial_allocation_df.columns]
    if missing_cols:
        raise ValueError(f"initial_allocation_df is missing required columns: {missing_cols}")

    df = initial_allocation_df[required_cols].copy()
    df["recommended_initial_amount"] = pd.to_numeric(df["recommended_initial_amount"], errors="raise").astype(float)
    return {
        str(r["bucket_name"]): round(float(r["recommended_initial_amount"]), 2)
        for _, r in df.iterrows()
    }


def simulate_bucket_year(
    year: int,
    simulation_start_year: int,
    balances: Dict[str, float],
    annual_expense_map_by_bucket: Dict[Tuple[int, str], float],
    annual_contribution_map: Dict[int, float],
    annual_topup_map: Dict[int, float],
    remaining_required_map: Dict[str, float],
    bucket_configs: List[BucketConfig],
    funding_rule: BucketFundingRule,
) -> Tuple[
    Dict[str, float],
    List[BucketYearState],
    List[TransferLog],
    Dict[str, float],
]:
    """
    Assumption ของ MVP:
    - annual contribution + annual topup ถูกใส่ต้นปี
    - investment return คิดหลังเติม inflow ของปีนั้น
    - expense ถูกหักปลายปี
    - rollover เกิดปลายปีหลังจ่าย expense แล้ว
    - shortfall cover ข้าม bucket จะเกิดหลังจ่าย expense แล้ว (เฉพาะ waterfall)
    """
    validate_bucket_configs(bucket_configs)
    validate_bucket_funding_rule(funding_rule, bucket_configs)

    ordered_buckets = _bucket_names_in_order(bucket_configs)
    return_map = _bucket_return_map(bucket_configs)
    year_offset = get_year_offset(simulation_start_year, year)

    working_balances = {b: float(balances.get(b, 0.0)) for b in ordered_buckets}
    updated_remaining_required_map = {
        b: max(0.0, float(remaining_required_map.get(b, 0.0)))
        for b in ordered_buckets
    }

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
    expense_map = {
        b: float(annual_expense_map_by_bucket.get((year, b), 0.0))
        for b in ordered_buckets
    }
    beginning_balance_map = {
        b: float(working_balances.get(b, 0.0))
        for b in ordered_buckets
    }

    # Step A: contribution in + return + expense
    for b in ordered_buckets:
        working_balances[b] = round(float(working_balances[b] + allocation_map.get(b, 0.0)), 2)

        base_for_return = float(working_balances[b])
        inv_ret = round(base_for_return * return_map[b], 2) if base_for_return > 0 else 0.0
        investment_return_map[b] = inv_ret

        # Fix 2: ลด remaining requirement ด้วย investment return ที่เกิดขึ้นจริง
        # เหตุผล: return ที่เกิดในปีนี้ช่วย "เติม" เงินใน bucket แล้ว
        # ทำให้ contribution ปีถัดไปไม่ต้องแบกรับภาระทั้งหมด
        if inv_ret > 0:
            updated_remaining_required_map[b] = round(
                max(0.0, updated_remaining_required_map[b] - inv_ret), 2
            )

        working_balances[b] = round(base_for_return + inv_ret - expense_map[b], 2)

    transfer_logs: List[TransferLog] = []

    # Step B: cover shortfall (if waterfall)
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

            transfer_logs.extend(logs)
            working_balances = updated_balances

            if remaining_shortfall > 0:
                working_balances[b] = round(-remaining_shortfall, 2)
            else:
                working_balances[b] = max(0.0, round(float(working_balances[b]), 2))

    # Step C: rollover at end of bucket horizon
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

                transfer_logs.append(
                    build_rollover_transfer(
                        year=year,
                        from_bucket=b,
                        to_bucket=next_bucket,
                        amount=bal,
                        reason="rollover_after_horizon",
                    )
                )

    # Final states
    year_states: List[BucketYearState] = []
    for b in ordered_buckets:
        year_states.append(
            BucketYearState(
                year=int(year),
                bucket_name=b,
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

    return updated_balances, year_states, transfer_logs, updated_remaining_required_map


def run_bucket_engine(
    expense_df: pd.DataFrame,
    initial_savings: float,
    annual_contribution_map: Dict[int, float],
    annual_topup_map: Dict[int, float],
    simulation_start_year: Optional[int] = None,
    bucket_configs: Optional[List[BucketConfig]] = None,
    funding_rule: Optional[BucketFundingRule] = None,
) -> BucketEngineResult:
    bucket_configs = bucket_configs or default_bucket_configs()
    funding_rule = funding_rule or BucketFundingRule()

    validate_bucket_configs(bucket_configs)
    validate_bucket_funding_rule(funding_rule, bucket_configs)

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
        candidate_years = {simulation_start_year}

    simulation_end_year = max(candidate_years)

    bucket_assignment_df = assign_expense_to_buckets(
        annual_expense_df=annual_expense_df,
        simulation_start_year=simulation_start_year,
        bucket_configs=bucket_configs,
    )

    bucket_requirement_df = calculate_bucket_requirements(
        bucket_assignment_df=bucket_assignment_df,
        simulation_start_year=simulation_start_year,
        bucket_configs=bucket_configs,
    )

    initial_allocation_df = allocate_initial_savings_to_buckets(
        initial_savings=initial_savings,
        bucket_requirement_df=bucket_requirement_df,
        funding_rule=funding_rule,
    )

    balances = initialize_bucket_balances(initial_allocation_df)
    remaining_required_map = dict(
        zip(
            initial_allocation_df["bucket_name"],
            initial_allocation_df["unmet_required_amount"],
        )
    )

    annual_expense_map_by_bucket: Dict[Tuple[int, str], float] = {}
    if bucket_assignment_df is not None and not bucket_assignment_df.empty:
        grouped = (
            bucket_assignment_df.groupby(["year", "bucket_name"], as_index=False)["total_expense"]
            .sum()
        )
        for _, r in grouped.iterrows():
            annual_expense_map_by_bucket[(int(r["year"]), str(r["bucket_name"]))] = float(r["total_expense"])

    all_states: List[BucketYearState] = []
    all_logs: List[TransferLog] = []

    for year in range(int(simulation_start_year), int(simulation_end_year) + 1):
        balances, states, logs, remaining_required_map = simulate_bucket_year(
            year=year,
            simulation_start_year=simulation_start_year,
            balances=balances,
            annual_expense_map_by_bucket=annual_expense_map_by_bucket,
            annual_contribution_map=annual_contribution_map,
            annual_topup_map=annual_topup_map,
            remaining_required_map=remaining_required_map,
            bucket_configs=bucket_configs,
            funding_rule=funding_rule,
        )
        all_states.extend(states)
        all_logs.extend(logs)

    bucket_year_state_df = pd.DataFrame([vars(x) for x in all_states])
    transfer_log_df = pd.DataFrame([vars(x) for x in all_logs]) if all_logs else pd.DataFrame(
        columns=["year", "from_bucket", "to_bucket", "amount", "reason"]
    )

    bucket_summary_df = build_bucket_summary(
        bucket_year_state_df=bucket_year_state_df,
        initial_allocation_df=initial_allocation_df,
        bucket_assignment_df=bucket_assignment_df,
    )

    engine_summary_df = build_engine_summary(
        bucket_year_state_df=bucket_year_state_df,
        annual_expense_df=annual_expense_df,
        initial_savings=initial_savings,
        annual_contribution_map=annual_contribution_map,
        annual_topup_map=annual_topup_map,
        simulation_start_year=simulation_start_year,
    )

    return BucketEngineResult(
        annual_expense_df=annual_expense_df,
        bucket_assignment_df=bucket_assignment_df,
        bucket_requirement_df=bucket_requirement_df,
        initial_allocation_df=initial_allocation_df,
        bucket_year_state_df=bucket_year_state_df,
        transfer_log_df=transfer_log_df,
        bucket_summary_df=bucket_summary_df,
        engine_summary_df=engine_summary_df,
    )


def build_bucket_summary(
    bucket_year_state_df: pd.DataFrame,
    initial_allocation_df: pd.DataFrame,
    bucket_assignment_df: pd.DataFrame,
) -> pd.DataFrame:
    if bucket_year_state_df is None or bucket_year_state_df.empty:
        return pd.DataFrame(columns=[
            "bucket_name",
            "recommended_initial_amount",
            "recommended_initial_weight",
            "total_assigned_expense",
            "projected_terminal_value",
            "shortfall_amount",
            "is_sufficient",
        ])

    latest_state = (
        bucket_year_state_df.sort_values(["bucket_name", "year"])
        .groupby("bucket_name", as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )[["bucket_name", "ending_balance"]].rename(
        columns={"ending_balance": "projected_terminal_value"}
    )

    worst_shortfall = (
        bucket_year_state_df.groupby("bucket_name", as_index=False)["ending_balance"]
        .min()
        .rename(columns={"ending_balance": "min_ending_balance"})
    )
    worst_shortfall["shortfall_amount"] = worst_shortfall["min_ending_balance"].apply(
        lambda x: round(abs(min(float(x), 0.0)), 2)
    )
    worst_shortfall = worst_shortfall[["bucket_name", "shortfall_amount"]]

    suff = (
        bucket_year_state_df.groupby("bucket_name", as_index=False)["is_shortfall"]
        .any()
        .rename(columns={"is_shortfall": "has_shortfall"})
    )
    suff["is_sufficient"] = ~suff["has_shortfall"]
    suff = suff[["bucket_name", "is_sufficient"]]

    if bucket_assignment_df is None or bucket_assignment_df.empty:
        assigned = pd.DataFrame({
            "bucket_name": initial_allocation_df["bucket_name"],
            "total_assigned_expense": 0.0,
        })
    else:
        assigned = (
            bucket_assignment_df.groupby("bucket_name", as_index=False)["total_expense"]
            .sum()
            .rename(columns={"total_expense": "total_assigned_expense"})
        )

    out = initial_allocation_df.merge(assigned, on="bucket_name", how="left")
    out = out.merge(latest_state, on="bucket_name", how="left")
    out = out.merge(worst_shortfall, on="bucket_name", how="left")
    out = out.merge(suff, on="bucket_name", how="left")

    out["total_assigned_expense"] = out["total_assigned_expense"].fillna(0.0).round(2)
    out["projected_terminal_value"] = out["projected_terminal_value"].fillna(0.0).round(2)
    out["shortfall_amount"] = out["shortfall_amount"].fillna(0.0).round(2)
    out["is_sufficient"] = out["is_sufficient"].fillna(True)

    return out[[
        "bucket_name",
        "recommended_initial_amount",
        "recommended_initial_weight",
        "total_assigned_expense",
        "projected_terminal_value",
        "shortfall_amount",
        "is_sufficient",
    ]]


def build_engine_summary(
    bucket_year_state_df: pd.DataFrame,
    annual_expense_df: pd.DataFrame,
    initial_savings: float,
    annual_contribution_map: Dict[int, float],
    annual_topup_map: Dict[int, float],
    simulation_start_year: int,
) -> pd.DataFrame:
    if bucket_year_state_df is None or bucket_year_state_df.empty:
        simulation_end_year = simulation_start_year
        total_projected_expense = (
            float(annual_expense_df["total_expense"].sum())
            if annual_expense_df is not None and not annual_expense_df.empty
            else 0.0
        )
        return pd.DataFrame([{
            "simulation_start_year": int(simulation_start_year),
            "simulation_end_year": int(simulation_end_year),
            "total_initial_savings": round(float(initial_savings), 2),
            "total_contribution": round(sum(float(v) for v in annual_contribution_map.values()), 2),
            "total_topup": round(sum(float(v) for v in annual_topup_map.values()), 2),
            "total_projected_expense": round(float(total_projected_expense), 2),
            "final_total_balance": round(float(initial_savings), 2),
            "total_shortfall_amount": 0.0,
            "first_shortfall_year": None,
            "is_plan_sufficient": True,
        }])

    simulation_end_year = int(bucket_year_state_df["year"].max())
    total_projected_expense = (
        float(annual_expense_df["total_expense"].sum())
        if annual_expense_df is not None and not annual_expense_df.empty
        else 0.0
    )
    total_contribution = sum(float(v) for v in annual_contribution_map.values())
    total_topup = sum(float(v) for v in annual_topup_map.values())

    # final total balance = sum ending balances of all buckets in final year
    final_total_balance = float(
        bucket_year_state_df.loc[
            bucket_year_state_df["year"] == simulation_end_year,
            "ending_balance"
        ].sum()
    )

    # total shortfall amount = worst aggregate negative balance across all years
    total_balance_by_year = (
        bucket_year_state_df.groupby("year", as_index=False)["ending_balance"]
        .sum()
        .rename(columns={"ending_balance": "total_ending_balance"})
        .sort_values("year")
        .reset_index(drop=True)
    )
    min_total_balance = float(total_balance_by_year["total_ending_balance"].min())
    total_shortfall_amount = round(abs(min(min_total_balance, 0.0)), 2)

    shortfall_years = (
        bucket_year_state_df.loc[
            bucket_year_state_df["is_shortfall"],
            "year"
        ]
        .drop_duplicates()
        .sort_values()
        .tolist()
    )
    first_shortfall_year = int(shortfall_years[0]) if shortfall_years else None
    is_plan_sufficient = len(shortfall_years) == 0

    out = pd.DataFrame([{
        "simulation_start_year": int(simulation_start_year),
        "simulation_end_year": int(simulation_end_year),
        "total_initial_savings": round(float(initial_savings), 2),
        "total_contribution": round(float(total_contribution), 2),
        "total_topup": round(float(total_topup), 2),
        "total_projected_expense": round(float(total_projected_expense), 2),
        "final_total_balance": round(float(final_total_balance), 2),
        "total_shortfall_amount": round(float(total_shortfall_amount), 2),
        "first_shortfall_year": first_shortfall_year,
        "is_plan_sufficient": bool(is_plan_sufficient),
    }])
    return out


def run_bucket_engine_from_saving_df(
    expense_df: pd.DataFrame,
    saving_df: pd.DataFrame,
    initial_savings: float,
    simulation_start_year: Optional[int] = None,
    bucket_configs: Optional[List[BucketConfig]] = None,
    funding_rule: Optional[BucketFundingRule] = None,
) -> BucketEngineResult:
    contribution_map, topup_map = build_funding_maps_from_saving_df(saving_df)
    return run_bucket_engine(
        expense_df=expense_df,
        initial_savings=initial_savings,
        annual_contribution_map=contribution_map,
        annual_topup_map=topup_map,
        simulation_start_year=simulation_start_year,
        bucket_configs=bucket_configs,
        funding_rule=funding_rule,
    )


# ============================================================
# MANUAL ALLOCATION HELPERS (Fix 3)
# ============================================================

def validate_manual_allocation(
    manual_amounts: Dict[str, float],
    expected_bucket_names: List[str],
    initial_savings: float,
    tolerance: float = 1.0,
) -> List[str]:
    """
    Validate manually specified allocation amounts.

    Parameters
    ----------
    manual_amounts : Dict[str, float]
        {bucket_name: amount}
    expected_bucket_names : List[str]
        bucket names ที่ต้องมีครบ (จาก bucket_configs)
    initial_savings : float
        ต้องรวมกันได้ = initial_savings (±tolerance)
    tolerance : float
        ความคลาดเคลื่อนที่ยอมรับได้ (default 1 บาท)

    Returns
    -------
    List[str]
        รายการ error message (ถ้าว่าง = valid)
    """
    errors: List[str] = []

    if not manual_amounts:
        errors.append("manual_amounts ไม่มีข้อมูล")
        return errors

    expected = set(expected_bucket_names)
    actual = set(manual_amounts.keys())

    missing = expected - actual
    extra = actual - expected

    if missing:
        errors.append(f"ขาด bucket ใน manual_amounts: {sorted(missing)}")
    if extra:
        errors.append(f"มี bucket ที่ไม่ได้กำหนดใน bucket_configs: {sorted(extra)}")

    for b, amt in manual_amounts.items():
        if float(amt) < 0:
            errors.append(f"Bucket '{b}': amount ต้องไม่ติดลบ (ได้รับ {amt:,.2f})")

    total = sum(float(v) for v in manual_amounts.values())
    diff = total - float(initial_savings)
    if abs(diff) > float(tolerance):
        errors.append(
            f"ผลรวม manual allocation = {total:,.2f} "
            f"≠ initial_savings = {float(initial_savings):,.2f} "
            f"(ต่างกัน {diff:+,.2f})"
        )

    return errors


def create_manual_allocation_df(
    manual_amounts: Dict[str, float],
    bucket_requirement_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    สร้าง allocation DataFrame จากการกรอก manual
    Schema เหมือนกับ output ของ allocate_initial_savings_to_buckets()

    Parameters
    ----------
    manual_amounts : Dict[str, float]
        {bucket_name: amount}
    bucket_requirement_df : pd.DataFrame
        output จาก calculate_bucket_requirements()
        ใช้คำนวณ unmet_required_amount

    Returns
    -------
    pd.DataFrame with columns:
    - bucket_name
    - recommended_initial_amount
    - recommended_initial_weight
    - unmet_required_amount
    """
    if not manual_amounts:
        raise ValueError("manual_amounts ต้องไม่ว่าง")

    if bucket_requirement_df is None or bucket_requirement_df.empty:
        raise ValueError("bucket_requirement_df ต้องไม่ว่าง")

    req_map = dict(zip(
        bucket_requirement_df["bucket_name"].astype(str),
        pd.to_numeric(
            bucket_requirement_df["required_present_value"], errors="coerce"
        ).fillna(0.0),
    ))

    total_allocated = sum(max(0.0, float(v)) for v in manual_amounts.values())

    rows = []
    for bucket_name, amount in manual_amounts.items():
        amt = max(0.0, float(amount))
        required = float(req_map.get(str(bucket_name), 0.0))
        unmet = max(0.0, required - amt)
        weight = round(amt / total_allocated, 6) if total_allocated > 0 else 0.0

        rows.append({
            "bucket_name": str(bucket_name),
            "recommended_initial_amount": round(amt, 2),
            "recommended_initial_weight": weight,
            "unmet_required_amount": round(unmet, 2),
        })

    return pd.DataFrame(rows, columns=[
        "bucket_name",
        "recommended_initial_amount",
        "recommended_initial_weight",
        "unmet_required_amount",
    ])


def estimate_additional_monthly_contribution_for_bucket_engine(
    expense_df: pd.DataFrame,
    initial_savings: float,
    annual_contribution_map: Dict[int, float],
    annual_topup_map: Dict[int, float],
    simulation_start_year: Optional[int] = None,
    bucket_configs: Optional[List[BucketConfig]] = None,
    funding_rule: Optional[BucketFundingRule] = None,
    precision: float = 1.0,
    max_search_monthly: float = 10_000_000.0,
) -> float:
    """
    binary search หา monthly contribution เพิ่มเติมขั้นต่ำ
    โดยจะเพิ่ม annual contribution = extra_monthly * 12 ให้ทุกปีใน projection horizon
    """
    if precision <= 0:
        raise ValueError("precision must be > 0")

    bucket_configs = bucket_configs or default_bucket_configs()
    funding_rule = funding_rule or BucketFundingRule()

    annual_expense_df = prepare_annual_expense(expense_df)

    years = set()
    if annual_expense_df is not None and not annual_expense_df.empty:
        years.update(annual_expense_df["year"].astype(int).tolist())
    years.update(int(y) for y in annual_contribution_map.keys())
    years.update(int(y) for y in annual_topup_map.keys())

    if simulation_start_year is None:
        if not years:
            raise ValueError(
                "simulation_start_year is None and no years found in expense_df / inflow maps"
            )
        simulation_start_year = min(years)

    if not years:
        years = {simulation_start_year}

    end_year = max(years)
    projection_years = list(range(int(simulation_start_year), int(end_year) + 1))
    base_contribution_map = {int(k): float(v) for k, v in annual_contribution_map.items()}

    def enough(extra_monthly: float) -> bool:
        test_contribution_map = base_contribution_map.copy()
        extra_annual = float(extra_monthly) * 12.0

        for y in projection_years:
            test_contribution_map[y] = round(
                float(test_contribution_map.get(y, 0.0) + extra_annual),
                2,
            )

        result = run_bucket_engine(
            expense_df=expense_df,
            initial_savings=initial_savings,
            annual_contribution_map=test_contribution_map,
            annual_topup_map=annual_topup_map,
            simulation_start_year=simulation_start_year,
            bucket_configs=bucket_configs,
            funding_rule=funding_rule,
        )
        return bool(result.engine_summary_df["is_plan_sufficient"].iloc[0])

    low = 0.0
    high = 1.0

    while not enough(high):
        high *= 2.0
        if high > max_search_monthly:
            raise ValueError(
                "Cannot find sufficient monthly contribution within max_search_monthly"
            )

    while (high - low) > precision:
        mid = (low + high) / 2.0
        if enough(mid):
            high = mid
        else:
            low = mid

    return round(float(high), 2)