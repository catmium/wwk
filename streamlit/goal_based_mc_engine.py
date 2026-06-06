"""
Goal-Based Monte Carlo Engine (liability-ledger architecture)
=============================================================
Single shared portfolio + per-goal liability ledger.
FIFO-by-goal-date liquidation with priority tie-breaker + skippable flag.
Vectorized over paths (n_paths, n_years) + payments tensor
(n_paths, n_years, n_goals).

Separate from portfolio_bucket_engine* — does NOT affect existing pages.

API surface used by 03b_Investment_Planning_2.py:
  - EducationGoal, GoalBasedMCConfig, GoalBasedMCResult dataclasses
  - build_goals_from_children(children, assumptions, expense_df=None)
  - run_goal_based_mc(...)
  - solve_required_monthly_contribution(...)
  - traffic_light_for_goal(fr_median, p_funded, fr_threshold, p_threshold)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# We re-use only the dataclass types — no behavioural import from existing engine.
from simulation_core import (
    Assumptions,
    Child,
    EducationPlan,
    SavingPlan,
    calculate_age_in_year,
)


# ============================================================
# DATA MODELS
# ============================================================
@dataclass
class EducationGoal:
    """หนึ่ง goal = หนึ่งระดับการศึกษาของลูกหนึ่งคน"""
    goal_id: str            # e.g. "child0__bachelor"
    child_name: str
    level: str              # e.g. "bachelor" (raw key)
    level_label: str        # ป้ายภาษาไทย เช่น "ปริญญาตรี"
    start_year: int
    end_year: int
    annual_costs: Dict[int, float]   # year → inflated amount (THB)
    priority: int = 50      # tiebreaker เมื่อปีเริ่มเท่ากัน (ค่าน้อย = สำคัญกว่า)
    skippable: bool = False # ถ้า True → จ่ายเท่าที่มี (ขาดก็ไม่จ่ายเพิ่ม)

    @property
    def total_nominal_cost(self) -> float:
        return float(sum(self.annual_costs.values()))


@dataclass
class AssetClass:
    """หนึ่ง asset class — return/std/clip ของสินทรัพย์หนึ่งชนิด"""
    key: str                    # "cash" | "bond" | "thai_stock" | "global_stock"
    name_th: str                # "เงินสด/เงินฝาก" | "ตราสารหนี้" | ...
    annual_mean_return: float   # decimal (e.g., 0.04)
    annual_std_return: float    # decimal (e.g., 0.04)
    min_return: float = -0.50   # decimal floor (post-clip)
    max_return: float = 0.80    # decimal ceiling (post-clip)


@dataclass
class GlidePath:
    """De-risking schedule — น้ำหนัก asset ที่แต่ละ years-to-earliest-goal"""
    name: str                                    # "aggressive" | "moderate" | "conservative"
    keypoints_years_to_goal: List[int]           # เช่น [15, 5, 0] (เรียงจากมากไปน้อย)
    # asset_key → list of weights (ความยาวเท่ากับ keypoints)
    weights: Dict[str, List[float]] = field(default_factory=dict)


# Default 4 asset classes
DEFAULT_ASSETS: List[AssetClass] = [
    AssetClass(key="cash",         name_th="เงินสด/เงินฝาก",  annual_mean_return=0.025, annual_std_return=0.010, min_return=-0.02, max_return=0.10),
    AssetClass(key="bond",         name_th="ตราสารหนี้",       annual_mean_return=0.040, annual_std_return=0.040, min_return=-0.15, max_return=0.20),
    AssetClass(key="thai_stock",   name_th="หุ้นไทย",          annual_mean_return=0.080, annual_std_return=0.180, min_return=-0.50, max_return=0.80),
    AssetClass(key="global_stock", name_th="หุ้นต่างประเทศ",   annual_mean_return=0.090, annual_std_return=0.150, min_return=-0.45, max_return=0.70),
]

# Correlation matrix — hard-coded (positive semi-definite, Cholesky-friendly)
# Order: cash, bond, thai_stock, global_stock
DEFAULT_CORRELATION: np.ndarray = np.array([
    [ 1.00, 0.10,  0.00,    0.00],   # cash
    [ 0.10, 1.00, -0.10,   -0.10],   # bond
    [ 0.00,-0.10,  1.00,    0.60],   # thai_stock
    [ 0.00,-0.10,  0.60,    1.00],   # global_stock
], dtype=float)


# Glide path templates — each row of weights sums to 1.0
GLIDE_PATH_TEMPLATES: Dict[str, GlidePath] = {
    "aggressive": GlidePath(
        name="aggressive",
        keypoints_years_to_goal=[15, 5, 0],
        weights={
            "cash":         [0.00, 0.10, 0.40],
            "bond":         [0.10, 0.30, 0.40],
            "thai_stock":   [0.40, 0.25, 0.10],
            "global_stock": [0.50, 0.35, 0.10],
        },
    ),
    "moderate": GlidePath(
        name="moderate",
        keypoints_years_to_goal=[15, 5, 0],
        weights={
            "cash":         [0.05, 0.20, 0.60],
            "bond":         [0.25, 0.40, 0.35],
            "thai_stock":   [0.30, 0.20, 0.025],
            "global_stock": [0.40, 0.20, 0.025],
        },
    ),
    "conservative": GlidePath(
        name="conservative",
        keypoints_years_to_goal=[15, 5, 0],
        weights={
            "cash":         [0.10, 0.30, 0.80],
            "bond":         [0.40, 0.50, 0.20],
            "thai_stock":   [0.20, 0.10, 0.00],
            "global_stock": [0.30, 0.10, 0.00],
        },
    ),
}


@dataclass
class GoalBasedMCConfig:
    """พารามิเตอร์ของ MC engine"""
    n_paths: int = 1000
    random_seed: Optional[int] = 42

    # Return model — single shared portfolio (legacy single-asset mode)
    annual_mean_return: float = 0.06   # decimal
    annual_std_return: float = 0.10    # decimal
    min_return: float = -0.30          # decimal floor (post-clip)
    max_return: float = 0.40           # decimal ceiling (post-clip)
    distribution: str = "student_t"    # "normal" | "student_t" | "fixed"
    student_t_df: int = 5

    # Behaviour
    no_return_when_negative: bool = True  # ไม่คิดดอกถ้ายอดติดลบ
    # Liquidation rule — เฉพาะ fifo_by_date ใน v1 (มี priority tiebreaker)
    liquidation_rule: str = "fifo_by_date"

    # FR / Traffic-light thresholds
    fr_green_threshold: float = 1.0     # FR median ≥ 1.0 → ผ่าน
    p_green_threshold: float = 0.85     # P(fund 100%) ≥ 85% → ผ่าน

    # ── Multi-asset / glide path (optional) ──
    use_multi_asset: bool = False                       # toggle
    assets: Optional[List[AssetClass]] = None           # default = DEFAULT_ASSETS
    glide_path: Optional[GlidePath] = None              # default = MODERATE (used only if override is None)
    correlation_matrix: Optional[np.ndarray] = None     # default = DEFAULT_CORRELATION (4 assets) / identity otherwise
    # ถ้าระบุค่านี้ → ใช้ matrix นี้เป็น weights_schedule โดยตรง (bypass glide path interpolation)
    # shape ต้องเป็น (n_years, n_assets) — n_years = simulation_end_year - simulation_start_year + 1
    weights_schedule_override: Optional[np.ndarray] = None


@dataclass
class GoalBasedMCResult:
    config: GoalBasedMCConfig
    goals: List[EducationGoal]
    years: List[int]

    # (n_paths, n_years)
    portfolio_value: np.ndarray   # ยอดสิ้นปีของ portfolio
    annual_returns: np.ndarray    # return rate ของแต่ละปี/แต่ละ path
    contributions: np.ndarray     # (n_years,) deterministic เงินใส่ปลายปี (รวม topup)

    # (n_paths, n_years, n_goals)
    payments: np.ndarray          # เงินที่จ่ายจริงต่อ goal/ปี/path
    requirements: np.ndarray      # เงินที่ goal เรียกร้องในปีนั้น (ก่อน partial)

    # (n_paths, n_goals)
    funded_ratios: np.ndarray     # Σpayment / Σrequirement ต่อ path/goal

    # (n_goals,)
    goal_funded_prob: np.ndarray  # สัดส่วน path ที่ FR≥1.0 ต่อ goal

    # ── Multi-asset / glide path metadata (optional) ──
    assets: Optional[List[AssetClass]] = None
    glide_path: Optional[GlidePath] = None
    # (n_years, n_assets) — น้ำหนัก asset แต่ละปี (เฉพาะ multi-asset)
    weights_schedule: Optional[np.ndarray] = None

    @property
    def n_paths(self) -> int:
        return int(self.portfolio_value.shape[0])

    @property
    def n_years(self) -> int:
        return int(self.portfolio_value.shape[1])

    @property
    def n_goals(self) -> int:
        return int(len(self.goals))


# ============================================================
# GOAL EXTRACTION
# ============================================================
def _level_label(level: str) -> str:
    """แปลง level key → ป้ายภาษาไทย (รองรับ level ที่ใช้ใน app)"""
    table = {
        "kindergarten":  "อนุบาล",
        "elementary":    "ประถมศึกษา",
        "middle_school": "มัธยมต้น",
        "high_school":   "มัธยมปลาย",
        "bachelor":      "ปริญญาตรี",
        "master":        "ปริญญาโท",
        "phd":           "ปริญญาเอก",
        "doctor":        "ปริญญาเอก",
    }
    key = str(level).strip().lower()
    return table.get(key, str(level))


# Priority order — ระดับเด็กกว่ามาก่อน เพราะหลีกเลี่ยงไม่ได้
_DEFAULT_PRIORITY = {
    "kindergarten":  10,
    "elementary":    20,
    "middle_school": 30,
    "high_school":   40,
    "bachelor":      50,
    "master":        60,
    "phd":           70,
    "doctor":        70,
}

# Default skippable — ระดับสูง user อาจตัดทิ้งได้ถ้าเงินไม่พอ
_DEFAULT_SKIPPABLE = {
    "master": True,
    "phd":    True,
    "doctor": True,
}


def build_goals_from_children(
    children: List[Child],
    assumptions: Assumptions,
    expense_df: Optional[pd.DataFrame] = None,
) -> List[EducationGoal]:
    """
    สกัด EducationGoal จาก children + assumptions

    ถ้ามี expense_df จาก simulate_education_plan แล้ว ให้ใช้ inflated_amount
    จาก expense_df เลย (สอดคล้องกับ Page 2 100%). ไม่งั้นคำนวณ inflation เอง
    จาก plan.cost_growth_rate / assumptions.education_inflation_rate.
    """
    goals: List[EducationGoal] = []

    # Build fast lookup จาก expense_df ถ้ามี
    df_lookup: Dict[Tuple[str, str], Dict[int, float]] = {}
    # extra_lookup: child_name → {year: รวม inflated_amount ของ child_extra ปีนั้น}
    extra_lookup: Dict[str, Dict[int, float]] = {}
    if isinstance(expense_df, pd.DataFrame) and not expense_df.empty:
        cat_str = expense_df["category"].astype(str)

        # 1) Education rows — ใช้เป็นค่า base ต่อระดับการศึกษา
        edu_mask = cat_str.str.endswith("education")
        edu_rows = expense_df.loc[edu_mask, ["year", "child_name", "sub_category", "inflated_amount"]]
        for (cname, lvl), grp in edu_rows.groupby(["child_name", "sub_category"]):
            yearly = grp.groupby("year")["inflated_amount"].sum().to_dict()
            df_lookup[(str(cname), str(lvl).strip().lower())] = {
                int(y): float(v) for y, v in yearly.items()
            }

        # 2) Child extra rows — ค่าใช้จ่ายพิเศษของลูก (ไม่ผูกกับระดับการศึกษา)
        #    จะถูก map เข้า goal ใดก็ตามของลูกคนนั้นที่ปีของ extra อยู่ในช่วงเรียน
        extra_mask = cat_str.str.contains("extra", case=False, na=False) & ~edu_mask
        if extra_mask.any():
            extra_rows = expense_df.loc[extra_mask, ["year", "child_name", "inflated_amount"]]
            # เก็บเฉพาะแถวที่มี child_name (extra ของลูก) — ไม่รวม parent expense
            extra_rows = extra_rows[extra_rows["child_name"].astype(str).str.len() > 0]
            for cname, grp in extra_rows.groupby("child_name"):
                yearly = grp.groupby("year")["inflated_amount"].sum().to_dict()
                extra_lookup[str(cname)] = {
                    int(y): float(v) for y, v in yearly.items()
                }

    for ci, child in enumerate(children):
        for pi, plan in enumerate(child.education_plan):
            level_key = str(plan.level).strip().lower()
            label = _level_label(level_key)

            byear = int(_birth_year(child))
            start_year = int(max(assumptions.start_year, byear + plan.start_age))
            end_year = int(byear + plan.end_age)
            if start_year > end_year:
                continue

            costs: Dict[int, float] = {}

            # 1) Base education cost — จาก expense_df ถ้ามี (ตรงกับ Page 2 เป๊ะ)
            cached = df_lookup.get((child.name, level_key))
            edu_found = False
            if cached:
                for y in range(start_year, end_year + 1):
                    if y in cached:
                        costs[y] = float(cached[y])
                        edu_found = True

            # 2) ถ้า expense_df ไม่ครอบคลุม education → คำนวณเองด้วย inflation แบบ deterministic
            if not edu_found:
                base_cost = float(plan.annual_cost or 0.0)
                growth = (
                    float(plan.cost_growth_rate)
                    if plan.cost_growth_rate is not None
                    else float(assumptions.education_inflation_rate)
                )
                base_year = (
                    int(plan.cost_basis_year)
                    if plan.cost_basis_year is not None
                    else int(assumptions.inflation_base_year or assumptions.start_year)
                )
                for y in range(start_year, end_year + 1):
                    yrs = max(0, y - base_year)
                    costs[y] = costs.get(y, 0.0) + base_cost * ((1.0 + growth) ** yrs)

            # 3) บวก child_extra ที่ตกอยู่ในช่วงปีการศึกษานี้ (overlap with start_year..end_year)
            child_extras = extra_lookup.get(child.name, {})
            if child_extras:
                for y in range(start_year, end_year + 1):
                    add = float(child_extras.get(y, 0.0))
                    if add > 0:
                        costs[y] = costs.get(y, 0.0) + add

            if not costs or sum(costs.values()) <= 0:
                continue

            goal_id = f"child{ci}__{level_key}"
            priority = _DEFAULT_PRIORITY.get(level_key, 50) + ci  # tiebreak ระหว่างลูก
            skippable = _DEFAULT_SKIPPABLE.get(level_key, False)

            goals.append(EducationGoal(
                goal_id=goal_id,
                child_name=child.name,
                level=level_key,
                level_label=label,
                start_year=start_year,
                end_year=end_year,
                annual_costs=costs,
                priority=priority,
                skippable=skippable,
            ))

    # เรียง FIFO-by-date (start_year), priority เป็น tiebreak (น้อยกว่า = ก่อน)
    goals.sort(key=lambda g: (g.start_year, g.priority, g.goal_id))
    return goals


def _birth_year(child: Child) -> int:
    from datetime import datetime
    return datetime.strptime(child.birth_date, "%Y-%m-%d").year


# ============================================================
# RETURN SAMPLING (vectorized)
# ============================================================
def _sample_returns(
    rng: np.random.Generator,
    n_paths: int,
    n_years: int,
    config: GoalBasedMCConfig,
) -> np.ndarray:
    """คืน returns shape (n_paths, n_years) — clipped"""
    mu = float(config.annual_mean_return)
    sd = float(config.annual_std_return)

    dist = (config.distribution or "student_t").lower()
    if dist == "fixed":
        out = np.full((n_paths, n_years), mu, dtype=float)
    elif dist == "normal":
        out = rng.normal(loc=mu, scale=sd, size=(n_paths, n_years))
    elif dist == "student_t":
        df = max(3, int(config.student_t_df))   # df<3 → variance ไม่จำกัด
        t_samples = rng.standard_t(df, size=(n_paths, n_years))
        out = mu + sd * t_samples
    else:
        raise ValueError(f"Unsupported distribution: {config.distribution}")

    return np.clip(out, config.min_return, config.max_return)


# ============================================================
# MULTI-ASSET HELPERS — Glide Path + Correlated Sampling
# ============================================================
def _interp_weights(
    glide: GlidePath,
    asset_keys: List[str],
    years_to_goal: float,
) -> np.ndarray:
    """Linear interpolation ของ weights ที่ years_to_goal ที่ระบุ
    Clamp นอกขอบ — สูงกว่า max keypoint → ใช้ค่า max; ต่ำกว่า min → ใช้ค่า min
    Normalize ให้รวม = 1 (กันความผิดพลาดเชิงเลข)
    """
    kpts = list(glide.keypoints_years_to_goal)
    # ทำให้ keypoints เรียงจากน้อยไปมาก (ง่ายต่อการ interp)
    order = np.argsort(kpts)
    kpts_sorted = [kpts[i] for i in order]
    n_assets = len(asset_keys)

    # weights matrix shape (len(kpts), n_assets)
    W = np.zeros((len(kpts_sorted), n_assets), dtype=float)
    for ai, ak in enumerate(asset_keys):
        ws = glide.weights.get(ak, [0.0] * len(kpts))
        for ki, oi in enumerate(order):
            W[ki, ai] = float(ws[oi])

    x = float(years_to_goal)
    if x <= kpts_sorted[0]:
        w = W[0].copy()
    elif x >= kpts_sorted[-1]:
        w = W[-1].copy()
    else:
        # find bracket
        for i in range(len(kpts_sorted) - 1):
            x0, x1 = kpts_sorted[i], kpts_sorted[i + 1]
            if x0 <= x <= x1:
                t = (x - x0) / max(1e-12, (x1 - x0))
                w = W[i] * (1.0 - t) + W[i + 1] * t
                break
        else:
            w = W[-1].copy()

    s = float(w.sum())
    if s > 0:
        w = w / s
    return w


def _build_weights_schedule(
    glide: GlidePath,
    asset_keys: List[str],
    years: List[int],
    earliest_goal_year: int,
) -> np.ndarray:
    """คืน weights schedule shape (n_years, n_assets)
    years_to_goal = max(0, earliest_goal_year - year[t])
    """
    n_years = len(years)
    n_assets = len(asset_keys)
    sched = np.zeros((n_years, n_assets), dtype=float)
    for t, y in enumerate(years):
        ytg = max(0.0, float(earliest_goal_year) - float(y))
        sched[t] = _interp_weights(glide, asset_keys, ytg)
    return sched


def _sample_multi_asset_returns(
    rng: np.random.Generator,
    n_paths: int,
    n_years: int,
    assets: List[AssetClass],
    correlation: np.ndarray,
    weights_schedule: np.ndarray,
    distribution: str,
    student_t_df: int,
) -> np.ndarray:
    """Sample portfolio returns (n_paths, n_years) จาก multivariate distribution
    + glide-path weighting

    ขั้นตอน:
      1) sample correlated standardized values (0,1) ผ่าน Cholesky
      2) scale ด้วย std + mean ของแต่ละ asset
      3) clip ตาม min/max ของแต่ละ asset
      4) portfolio_return[p,t] = Σ_i weights[t,i] * asset_return[p,t,i]
    """
    n_assets = len(assets)
    means = np.array([a.annual_mean_return for a in assets], dtype=float)
    stds  = np.array([a.annual_std_return for a in assets], dtype=float)
    mins  = np.array([a.min_return for a in assets], dtype=float)
    maxs  = np.array([a.max_return for a in assets], dtype=float)

    # Cholesky for correlation (ใช้ correlation ไม่ใช่ covariance — scale ด้วย std ทีหลัง)
    L = np.linalg.cholesky(correlation)

    dist = (distribution or "student_t").lower()
    shape = (n_paths, n_years, n_assets)

    if dist == "fixed":
        # ไม่มี randomness — ทุก asset คืน mean ของตัวเอง
        asset_returns = np.broadcast_to(means, shape).copy()
    elif dist == "normal":
        # iid standard normal → correlated normal ผ่าน Cholesky
        z = rng.standard_normal(size=shape)
        correlated = np.einsum("ij,ptj->pti", L, z)
        asset_returns = means + stds * correlated
    elif dist == "student_t":
        df = max(3, int(student_t_df))
        # Gaussian copula: t = z / sqrt(g/df), g ~ ChiSq(df)
        z = rng.standard_normal(size=shape)
        correlated = np.einsum("ij,ptj->pti", L, z)
        g = rng.chisquare(df, size=(n_paths, n_years, 1))
        t_samples = correlated / np.sqrt(g / df)
        asset_returns = means + stds * t_samples
    else:
        raise ValueError(f"Unsupported distribution: {distribution}")

    # Clip per asset
    asset_returns = np.clip(asset_returns, mins, maxs)

    # Portfolio return = Σ_i weights[t,i] * asset_return[p,t,i]
    # weights_schedule: (n_years, n_assets); asset_returns: (n_paths, n_years, n_assets)
    portfolio_returns = np.einsum("ti,pti->pt", weights_schedule, asset_returns)
    return portfolio_returns


# ============================================================
# MAIN MC LOOP — Liability Ledger
# ============================================================
def run_goal_based_mc(
    goals: List[EducationGoal],
    initial_savings: float,
    monthly_contribution: float,
    annual_topups: Dict[int, float],
    simulation_start_year: int,
    simulation_end_year: Optional[int],
    config: GoalBasedMCConfig,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> GoalBasedMCResult:
    """
    Monte Carlo แบบ goal-based / liability ledger

    Mechanics ต่อปี (ปลายปี):
      1) growth: portfolio *= (1+r)  — แต่ถ้า no_return_when_negative และยอด<0 จะข้าม
      2) deposit: portfolio += (annual_contribution_from_monthly + topup_ที่ปีนั้น)
      3) liquidation:
         - รวบรวม goal ที่ active ในปีนี้ (start_year ≤ y ≤ end_year)
         - เรียงตาม FIFO-by-date (start_year asc, priority asc)
         - non-skippable: จ่ายเต็มเสมอ (ปล่อยให้ portfolio ติดลบได้)
         - skippable: จ่ายเท่าที่มี (ไม่ทำให้ติดลบเพิ่ม)
      4) record payments & end-of-year portfolio
    """
    if simulation_end_year is None:
        if goals:
            simulation_end_year = max(g.end_year for g in goals)
        else:
            simulation_end_year = int(simulation_start_year)
    if simulation_end_year < simulation_start_year:
        simulation_end_year = simulation_start_year

    n_paths = int(max(1, config.n_paths))
    years = list(range(int(simulation_start_year), int(simulation_end_year) + 1))
    n_years = len(years)
    n_goals = len(goals)

    rng = np.random.default_rng(config.random_seed)

    # Returns: (n_paths, n_years) — branch by multi-asset toggle
    weights_schedule_out: Optional[np.ndarray] = None
    assets_out: Optional[List[AssetClass]] = None
    glide_out: Optional[GlidePath] = None

    if config.use_multi_asset:
        assets_out = list(config.assets) if config.assets is not None else list(DEFAULT_ASSETS)
        glide_out = config.glide_path if config.glide_path is not None else GLIDE_PATH_TEMPLATES["moderate"]

        asset_keys = [a.key for a in assets_out]
        default_keys = [a.key for a in DEFAULT_ASSETS]
        # Correlation: explicit override > DEFAULT_CORRELATION (only if assets match defaults) > identity
        if config.correlation_matrix is not None:
            corr = np.asarray(config.correlation_matrix, dtype=float)
            if corr.shape != (len(assets_out), len(assets_out)):
                raise ValueError(
                    f"correlation_matrix shape {corr.shape} != expected "
                    f"{(len(assets_out), len(assets_out))}"
                )
        elif asset_keys == default_keys:
            corr = DEFAULT_CORRELATION
        else:
            corr = np.eye(len(assets_out))

        # Weights schedule: explicit override > glide-path interpolation
        if config.weights_schedule_override is not None:
            ws = np.asarray(config.weights_schedule_override, dtype=float)
            expected_shape = (n_years, len(assets_out))
            if ws.shape != expected_shape:
                raise ValueError(
                    f"weights_schedule_override shape {ws.shape} != expected {expected_shape}"
                )
            weights_schedule_out = ws
        else:
            earliest_goal_year = min((g.start_year for g in goals), default=int(simulation_start_year))
            weights_schedule_out = _build_weights_schedule(
                glide_out, asset_keys, years, earliest_goal_year
            )
        returns = _sample_multi_asset_returns(
            rng=rng,
            n_paths=n_paths,
            n_years=n_years,
            assets=assets_out,
            correlation=corr,
            weights_schedule=weights_schedule_out,
            distribution=config.distribution,
            student_t_df=config.student_t_df,
        )
    else:
        returns = _sample_returns(rng, n_paths, n_years, config)

    # Contributions ปลายปี (deterministic) = monthly * 12 + topup
    annual_from_monthly = float(monthly_contribution) * 12.0
    contributions = np.array(
        [annual_from_monthly + float(annual_topups.get(int(y), 0.0)) for y in years],
        dtype=float,
    )

    # Per-year required ต่อ goal: (n_years, n_goals) — deterministic
    requirements_yg = np.zeros((n_years, n_goals), dtype=float)
    year_index = {y: i for i, y in enumerate(years)}
    for g_idx, g in enumerate(goals):
        for y, amt in g.annual_costs.items():
            if y in year_index:
                requirements_yg[year_index[y], g_idx] = float(amt)

    # Pre-sort goals by FIFO-by-date — index list for liquidation order
    goal_order = sorted(
        range(n_goals),
        key=lambda i: (goals[i].start_year, goals[i].priority, goals[i].goal_id),
    )
    skippable_mask = np.array([g.skippable for g in goals], dtype=bool)

    # Allocate output tensors
    portfolio_value = np.zeros((n_paths, n_years), dtype=float)
    payments = np.zeros((n_paths, n_years, n_goals), dtype=float)
    # broadcast requirements_yg into per-path tensor (used for FR calc downstream)
    requirements = np.broadcast_to(
        requirements_yg[None, :, :], (n_paths, n_years, n_goals)
    ).copy()

    # State per path
    balance = np.full(n_paths, float(initial_savings), dtype=float)

    progress_every = max(1, n_years // 20)

    for t in range(n_years):
        r_t = returns[:, t]

        # 1) Growth
        if config.no_return_when_negative:
            grow_mask = balance >= 0
            balance = np.where(grow_mask, balance * (1.0 + r_t), balance)
        else:
            balance = balance * (1.0 + r_t)

        # 2) Deposit
        balance = balance + contributions[t]

        # 3) Liquidation — serial over goals, vectorized over paths
        req_t = requirements_yg[t]  # (n_goals,)
        active_goal_indices = [g_idx for g_idx in goal_order if req_t[g_idx] > 0]

        for g_idx in active_goal_indices:
            need = float(req_t[g_idx])  # scalar — ทุก path ต้องการเท่ากัน (deterministic)
            if need <= 0:
                continue

            # จ่ายเท่าที่มี (cap at available balance) — ทั้ง skippable / non-skippable
            # ทำแบบนี้เพื่อให้ Funded Ratio สะท้อน fundability จริง:
            #   FR < 1.0 เมื่อเงินไม่พอ (แทนที่จะบังคับ FR=100% เสมอ)
            # skippable flag ยังใช้สำหรับ FIFO/priority semantics
            # แต่ payment math เหมือนกันทุก goal
            avail = np.maximum(balance, 0.0)
            paid = np.minimum(avail, need)
            payments[:, t, g_idx] = paid
            balance = balance - paid

        # 4) Record end-of-year balance
        portfolio_value[:, t] = balance

        if progress_callback is not None and (t % progress_every == 0 or t == n_years - 1):
            try:
                progress_callback(t + 1, n_years)
            except Exception:
                pass

    # Funded ratios per path/goal
    total_paid = payments.sum(axis=1)            # (n_paths, n_goals)
    total_req = requirements.sum(axis=1)          # (n_paths, n_goals)
    with np.errstate(divide="ignore", invalid="ignore"):
        funded_ratios = np.where(
            total_req > 0,
            total_paid / total_req,
            1.0,
        )

    # Probability of full funding (FR ≥ 1.0)
    if n_goals > 0:
        goal_funded_prob = (funded_ratios >= 1.0).mean(axis=0)
    else:
        goal_funded_prob = np.zeros(0, dtype=float)

    return GoalBasedMCResult(
        config=config,
        goals=goals,
        years=years,
        portfolio_value=portfolio_value,
        annual_returns=returns,
        contributions=contributions,
        payments=payments,
        requirements=requirements,
        funded_ratios=funded_ratios,
        goal_funded_prob=goal_funded_prob,
        assets=assets_out,
        glide_path=glide_out,
        weights_schedule=weights_schedule_out,
    )


# ============================================================
# REQUIRED-MONTHLY SOLVER (binary search)
# ============================================================
def solve_required_monthly_contribution(
    goals: List[EducationGoal],
    initial_savings: float,
    annual_topups: Dict[int, float],
    simulation_start_year: int,
    simulation_end_year: Optional[int],
    config: GoalBasedMCConfig,
    *,
    target_goal_id: Optional[str] = None,
    target_metric: str = "fr_median",   # "fr_median" | "p_funded"
    target_value: float = 1.0,
    lo: float = 0.0,
    hi: float = 1_000_000.0,
    max_iter: int = 24,
    tol: float = 1e-3,
) -> float:
    """
    หาเงินรายเดือนขั้นต่ำที่ทำให้ goal ที่กำหนด (หรือ aggregate) ถึง target

    - target_metric="fr_median": median FR ของ goal ≥ target_value (default 1.0)
    - target_metric="p_funded": P(FR≥1.0) ของ goal ≥ target_value (default 0.85)
    - target_goal_id=None: ใช้ goal ที่อ่อนแอที่สุด (FR median ต่ำสุด) เป็นเกณฑ์

    คืน 0 ถ้า initial setup ที่ monthly=0 ผ่าน target อยู่แล้ว
    คืน hi ถ้าทุก iteration ยังไม่ผ่าน (จะระบุว่า "เกิน hi")
    """
    def metric_at(monthly: float) -> float:
        res = run_goal_based_mc(
            goals=goals,
            initial_savings=initial_savings,
            monthly_contribution=monthly,
            annual_topups=annual_topups,
            simulation_start_year=simulation_start_year,
            simulation_end_year=simulation_end_year,
            config=config,
            progress_callback=None,
        )
        if not res.goals:
            return float("inf")

        if target_goal_id is not None:
            try:
                gi = [g.goal_id for g in res.goals].index(target_goal_id)
            except ValueError:
                return float("inf")
            fr_col = res.funded_ratios[:, gi]
            if target_metric == "p_funded":
                return float((fr_col >= 1.0).mean())
            return float(np.median(fr_col))
        else:
            # weakest goal across all
            if target_metric == "p_funded":
                return float(res.goal_funded_prob.min()) if res.n_goals else float("inf")
            fr_medians = np.median(res.funded_ratios, axis=0)
            return float(fr_medians.min())

    # ตรวจ lo ก่อน — ถ้าผ่านอยู่แล้ว
    m_lo = metric_at(lo)
    if m_lo >= target_value:
        return float(lo)

    # ตรวจ hi — ถ้ายังไม่ถึง
    m_hi = metric_at(hi)
    if m_hi < target_value:
        return float(hi)  # signal "ต้องมากกว่า hi"

    a, b = float(lo), float(hi)
    for _ in range(max_iter):
        mid = 0.5 * (a + b)
        m_mid = metric_at(mid)
        if m_mid >= target_value:
            b = mid
        else:
            a = mid
        if abs(b - a) < tol * max(1.0, b):
            break

    return float(b)


# ============================================================
# TRAFFIC LIGHT
# ============================================================
def traffic_light_for_goal(
    fr_median: float,
    p_funded: float,
    *,
    fr_threshold: float = 1.0,
    p_threshold: float = 0.85,
) -> str:
    """คืนสถานะ: 'green' | 'yellow' | 'red'

    - green: FR median ≥ threshold AND P ≥ threshold
    - yellow: ผ่านเพียงข้อเดียว
    - red: ไม่ผ่านทั้งสอง
    """
    fr_ok = float(fr_median) >= float(fr_threshold)
    p_ok = float(p_funded) >= float(p_threshold)
    if fr_ok and p_ok:
        return "green"
    if fr_ok or p_ok:
        return "yellow"
    return "red"


# ============================================================
# CONVENIENCE — SUMMARY DICT FOR UI
# ============================================================
def summarize_goal_metrics(result: GoalBasedMCResult) -> pd.DataFrame:
    """สร้าง DataFrame หนึ่งบรรทัดต่อ goal สำหรับ render ใน UI"""
    if not result.goals:
        return pd.DataFrame()

    rows = []
    fr = result.funded_ratios  # (n_paths, n_goals)
    for gi, g in enumerate(result.goals):
        fr_col = fr[:, gi]
        fr_median = float(np.median(fr_col))
        fr_p10 = float(np.percentile(fr_col, 10))
        fr_p90 = float(np.percentile(fr_col, 90))
        p_funded = float(result.goal_funded_prob[gi])

        # shortfall (THB) — ที่ p10 (worst-case)
        req_total = float(result.requirements[0, :, gi].sum())  # deterministic — เท่ากันทุก path
        paid_p10 = float(np.percentile(result.payments[:, :, gi].sum(axis=1), 10))
        shortfall_p10 = max(0.0, req_total - paid_p10)

        light = traffic_light_for_goal(
            fr_median, p_funded,
            fr_threshold=result.config.fr_green_threshold,
            p_threshold=result.config.p_green_threshold,
        )

        rows.append({
            "goal_id": g.goal_id,
            "child_name": g.child_name,
            "level": g.level,
            "level_label": g.level_label,
            "start_year": g.start_year,
            "end_year": g.end_year,
            "skippable": g.skippable,
            "priority": g.priority,
            "total_required": req_total,
            "fr_median": fr_median,
            "fr_p10": fr_p10,
            "fr_p90": fr_p90,
            "p_funded": p_funded,
            "shortfall_p10": shortfall_p10,
            "traffic_light": light,
        })
    return pd.DataFrame(rows)


def portfolio_percentile_bands(
    result: GoalBasedMCResult,
    percentiles: Tuple[int, int, int] = (10, 50, 90),
) -> pd.DataFrame:
    """คืน DataFrame: year, p10, p50, p90 ของ portfolio_value"""
    pv = result.portfolio_value  # (n_paths, n_years)
    rows = []
    for ti, y in enumerate(result.years):
        rows.append({
            "year": int(y),
            f"p{percentiles[0]}": float(np.percentile(pv[:, ti], percentiles[0])),
            f"p{percentiles[1]}": float(np.percentile(pv[:, ti], percentiles[1])),
            f"p{percentiles[2]}": float(np.percentile(pv[:, ti], percentiles[2])),
        })
    return pd.DataFrame(rows)


def liquidation_timeline(
    result: GoalBasedMCResult,
    percentile: int = 50,
) -> pd.DataFrame:
    """คืน DataFrame: year, goal_id, paid_pXX, required (deterministic)"""
    rows = []
    pay = result.payments
    req = result.requirements
    for ti, y in enumerate(result.years):
        for gi, g in enumerate(result.goals):
            paid_p = float(np.percentile(pay[:, ti, gi], percentile))
            need = float(req[0, ti, gi])
            if paid_p == 0 and need == 0:
                continue
            rows.append({
                "year": int(y),
                "goal_id": g.goal_id,
                "goal_label": f"{g.child_name} — {g.level_label}",
                "paid": paid_p,
                "required": need,
            })
    return pd.DataFrame(rows)
