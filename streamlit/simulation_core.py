from dataclasses import dataclass, field, replace
from typing import List, Optional, Dict, Tuple
from datetime import datetime, date
import pandas as pd


# ============================================================
# DEFAULT EDUCATION CONFIG
# ============================================================
# อายุใช้แบบ inclusive range คือรวมทั้ง start_age และ end_age
# เช่น 4-6 ปี => ใช้อายุ 4, 5, 6
DEFAULT_EDUCATION_LEVELS = {
    "kindergarten": {"start_age": 4, "end_age": 6, "annual_cost": 500_000},
    "elementary": {"start_age": 7, "end_age": 12, "annual_cost": 1_000_000},
    "middle_school": {"start_age": 13, "end_age": 15, "annual_cost": 1_000_000},
    "high_school": {"start_age": 16, "end_age": 18, "annual_cost": 1_000_000},
    "bachelor": {"start_age": 19, "end_age": 22, "annual_cost": 3_000_000},
}


# ============================================================
# DATA MODELS
# ============================================================
@dataclass
class EducationPlan:
    level: str
    country: str
    school_type: str
    school_name: Optional[str] = None
    start_age: int = 0
    end_age: int = 0
    annual_cost: Optional[float] = None
    cost_growth_rate: Optional[float] = None
    cost_basis_year: Optional[int] = None
    note: Optional[str] = None


@dataclass
class ExtraExpense:
    name: str
    amount: float
    type: str = "one_time"  # one_time / recurring
    year: Optional[int] = None
    end_year: Optional[int] = None
    child_age: Optional[int] = None
    start_age: Optional[int] = None
    end_age: Optional[int] = None
    inflation_type: str = "general"  # general / education / none
    note: Optional[str] = None


@dataclass
class ParentExpense:
    name: str
    amount: float
    type: str = "one_time"  # one_time / recurring
    year: Optional[int] = None
    end_year: Optional[int] = None
    inflation_type: str = "general"  # general / education / none
    note: Optional[str] = None


@dataclass
class Child:
    name: str
    gender: str
    birth_date: str  # YYYY-MM-DD
    education_plan: List[EducationPlan] = field(default_factory=list)
    extra_expenses: List[ExtraExpense] = field(default_factory=list)


@dataclass
class AnnualTopup:
    year: int
    amount: float
    note: Optional[str] = None


@dataclass
class SavingPlan:
    initial_savings: float
    monthly_contribution: float
    saving_start_year: int = field(default_factory=lambda: date.today().year)
    annual_topups: List[AnnualTopup] = field(default_factory=list)


@dataclass
class Assumptions:
    start_year: int = field(default_factory=lambda: date.today().year)
    general_inflation_rate: float = 0.03
    education_inflation_rate: float = 0.05
    investment_return_rate: float = 0.06
    return_compound_mode: str = "yearly"  # yearly / monthly
    expense_timing: str = "end_of_year"  # start_of_year / midyear / end_of_year
    inflation_base_year: Optional[int] = None
    auto_add_th_international_highschool_before_university: bool = False
    default_highschool_start_age: int = 16
    default_highschool_end_age: int = 18
    validate_education_plan_overlap: bool = False
    open_recurring_default_years: int = 5  # legacy compatibility, unused under strict recurring rules


UNIVERSITY_LEVELS = {
    "bachelor", "master", "masters", "master_degree",
    "doctor", "doctoral", "phd", "university", "college",
}
HIGH_SCHOOL_LEVELS = {"high_school", "highschool"}


# ============================================================
# BASIC UTILITY FUNCTIONS
# ============================================================
def _parse_date(date_str: str) -> date:
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def _birth_year(child: Child) -> int:
    return _parse_date(child.birth_date).year


def calculate_age_in_year(birth_date: str, year: int) -> int:
    """อายุแบบง่าย = year - birth_year"""
    return year - _parse_date(birth_date).year


def _normalize_level(level: str) -> str:
    return str(level).strip().lower()


def _normalize_country(country: str) -> str:
    return str(country).strip().upper()


def _normalize_school_type(school_type: str) -> str:
    return str(school_type).strip().lower()


def _normalize_default_costs(
    default_costs: Optional[Dict[Tuple[str, str, str], float]]
) -> Dict[Tuple[str, str, str], float]:
    if not default_costs:
        return {}

    normalized: Dict[Tuple[str, str, str], float] = {}
    for (level, country, school_type), cost in default_costs.items():
        normalized[
            (_normalize_level(level), _normalize_country(country), _normalize_school_type(school_type))
        ] = float(cost)
    return normalized


def _lookup_default_cost(
    level: str,
    country: str,
    school_type: str,
    normalized_default_costs: Optional[Dict[Tuple[str, str, str], float]] = None,
) -> Optional[float]:
    if not normalized_default_costs:
        return None
    key = (_normalize_level(level), _normalize_country(country), _normalize_school_type(school_type))
    return normalized_default_costs.get(key)


def _apply_inflation(
    base_amount: float,
    growth_rate: float,
    target_year: int,
    base_year: int,
) -> float:
    """
    allow backward discount ได้
    - target_year > base_year => inflate
    - target_year < base_year => discount backward
    """
    years_elapsed = target_year - base_year
    return float(base_amount) * ((1 + growth_rate) ** years_elapsed)


def _get_effective_inflation_base_year(assumptions: Assumptions) -> int:
    if assumptions.inflation_base_year is not None:
        return assumptions.inflation_base_year
    return assumptions.start_year


def _prepare_assumptions(assumptions: Optional[Assumptions]) -> Assumptions:
    if assumptions is None:
        assumptions = Assumptions()
    prepared = replace(assumptions)
    if prepared.inflation_base_year is None:
        prepared.inflation_base_year = prepared.start_year
    return prepared


# ============================================================
# VALIDATION HELPERS
# ============================================================
def _validate_age_range(start_age: int, end_age: int, context: str) -> None:
    if start_age > end_age:
        raise ValueError(
            f"Invalid age range in {context}: start_age ({start_age}) > end_age ({end_age})"
        )


def _validate_year_range(start_year: int, end_year: int, context: str) -> None:
    if start_year > end_year:
        raise ValueError(
            f"Invalid year range in {context}: year ({start_year}) > end_year ({end_year})"
        )


def _validate_expense_type(expense_type: str, context: str) -> None:
    allowed = {"one_time", "recurring"}
    if expense_type not in allowed:
        raise ValueError(
            f"Invalid type in {context}: {expense_type}. Allowed values are {allowed}"
        )


def _validate_inflation_type(inflation_type: str, context: str) -> None:
    allowed = {"general", "education", "none"}
    if inflation_type not in allowed:
        raise ValueError(
            f"Invalid inflation_type in {context}: {inflation_type}. Allowed values are {allowed}"
        )


def _validate_education_plan(plan: EducationPlan, child_name: Optional[str] = None) -> None:
    context = f"EducationPlan(child={child_name}, level={plan.level})"
    _validate_age_range(plan.start_age, plan.end_age, context)
    if plan.annual_cost is not None and plan.annual_cost < 0:
        raise ValueError(f"annual_cost must be >= 0 in {context}")
    if plan.cost_growth_rate is not None and plan.cost_growth_rate < -1:
        raise ValueError(f"cost_growth_rate must be > -1 in {context}")


def _validate_extra_expense(ex: ExtraExpense, child_name: Optional[str] = None) -> None:
    context = f"ExtraExpense(child={child_name}, name={ex.name})"
    _validate_expense_type(ex.type, context)
    _validate_inflation_type(ex.inflation_type, context)

    if ex.amount < 0:
        raise ValueError(f"amount must be >= 0 in {context}")

    if ex.type == "one_time":
        has_year = ex.year is not None
        has_child_age = ex.child_age is not None
        if has_year == has_child_age:
            raise ValueError(
                f"{context}: one_time expense must specify exactly one trigger: year or child_age"
            )
        if ex.end_year is not None or ex.start_age is not None or ex.end_age is not None:
            raise ValueError(
                f"{context}: one_time expense must not use end_year/start_age/end_age"
            )
    else:
        has_year_range = ex.year is not None and ex.end_year is not None
        has_age_range = ex.start_age is not None and ex.end_age is not None
        if has_year_range and has_age_range:
            raise ValueError(
                f"{context}: recurring expense must use only one range type, either year/end_year or start_age/end_age"
            )
        if not has_year_range and not has_age_range:
            raise ValueError(
                f"{context}: recurring expense must specify a range using year/end_year or start_age/end_age"
            )
        if ex.child_age is not None:
            raise ValueError(
                f"{context}: recurring expense cannot use child_age; use start_age/end_age instead"
            )
        if has_year_range:
            _validate_year_range(ex.year, ex.end_year, context)
        if has_age_range:
            _validate_age_range(ex.start_age, ex.end_age, context)


def _validate_parent_expense(ex: ParentExpense) -> None:
    context = f"ParentExpense(name={ex.name})"
    _validate_expense_type(ex.type, context)
    _validate_inflation_type(ex.inflation_type, context)

    if ex.amount < 0:
        raise ValueError(f"amount must be >= 0 in {context}")

    if ex.type == "one_time":
        if ex.year is None:
            raise ValueError(f"{context}: one_time parent expense must specify year")
        if ex.end_year is not None:
            raise ValueError(f"{context}: one_time parent expense must not specify end_year")
    else:
        if ex.year is None or ex.end_year is None:
            raise ValueError(
                f"{context}: recurring parent expense must specify both year and end_year"
            )
        _validate_year_range(ex.year, ex.end_year, context)


def _validate_child(child: Child) -> None:
    _parse_date(child.birth_date)
    for plan in child.education_plan:
        _validate_education_plan(plan, child.name)
    for ex in child.extra_expenses:
        _validate_extra_expense(ex, child.name)


def _validate_annual_topup(topup: AnnualTopup) -> None:
    context = f"AnnualTopup(year={topup.year})"
    if topup.amount < 0:
        raise ValueError(f"amount must be >= 0 in {context}")


def _validate_saving_plan(saving_plan: SavingPlan) -> None:
    if saving_plan.initial_savings < 0:
        raise ValueError("SavingPlan.initial_savings must be >= 0")
    if saving_plan.monthly_contribution < 0:
        raise ValueError("SavingPlan.monthly_contribution must be >= 0")

    seen_years = set()
    for topup in saving_plan.annual_topups:
        _validate_annual_topup(topup)
        if topup.year in seen_years:
            raise ValueError(
                f"Duplicate annual topup year found: {topup.year}. Only one annual topup is allowed per year."
            )
        seen_years.add(topup.year)


def _validate_assumptions(assumptions: Assumptions) -> None:
    if assumptions.return_compound_mode not in {"yearly", "monthly"}:
        raise ValueError("Assumptions.return_compound_mode must be either 'yearly' or 'monthly'")

    if assumptions.expense_timing not in {"start_of_year", "midyear", "end_of_year"}:
        raise ValueError(
            "Assumptions.expense_timing must be one of {'start_of_year', 'midyear', 'end_of_year'}"
        )

    if assumptions.default_highschool_start_age > assumptions.default_highschool_end_age:
        raise ValueError(
            "Assumptions.default_highschool_start_age must be <= default_highschool_end_age"
        )

    for rate_name in [
        "general_inflation_rate",
        "education_inflation_rate",
        "investment_return_rate",
    ]:
        value = getattr(assumptions, rate_name)
        if value < -1:
            raise ValueError(f"Assumptions.{rate_name} must be > -1")


def _validate_education_plan_overlap(plans: List[EducationPlan], child_name: str) -> None:
    sorted_plans = sorted(plans, key=lambda p: (p.start_age, p.end_age, _normalize_level(p.level)))
    for i in range(1, len(sorted_plans)):
        prev = sorted_plans[i - 1]
        curr = sorted_plans[i]
        if curr.start_age <= prev.end_age:
            raise ValueError(
                "Education plan age ranges overlap for child="
                f"{child_name}: ({prev.level}, {prev.start_age}-{prev.end_age}) and "
                f"({curr.level}, {curr.start_age}-{curr.end_age})"
            )


def validate_simulation_inputs(
    children: List[Child],
    saving_plan: SavingPlan,
    assumptions: Assumptions,
    parent_expenses: Optional[List[ParentExpense]] = None,
) -> None:
    _validate_assumptions(assumptions)
    _validate_saving_plan(saving_plan)

    for child in children:
        _validate_child(child)

    if parent_expenses:
        for ex in parent_expenses:
            _validate_parent_expense(ex)


# ============================================================
# DEFAULT EDUCATION PLAN GENERATOR
# ============================================================
def generate_default_education_plan(
    country: str = "TH",
    school_type: str = "default",
) -> List[EducationPlan]:
    plans: List[EducationPlan] = []
    country = _normalize_country(country)
    school_type = _normalize_school_type(school_type)

    for level, cfg in DEFAULT_EDUCATION_LEVELS.items():
        plans.append(
            EducationPlan(
                level=level,
                country=country,
                school_type=school_type,
                school_name=None,
                start_age=cfg["start_age"],
                end_age=cfg["end_age"],
                annual_cost=cfg["annual_cost"],
                cost_growth_rate=None,
                cost_basis_year=None,
                note="system default",
            )
        )
    return plans


# ============================================================
# EDUCATION PLAN NORMALIZATION
# ============================================================
def _has_university_plan(plans: List[EducationPlan]) -> bool:
    return any(_normalize_level(p.level) in UNIVERSITY_LEVELS for p in plans)


def _has_highschool_plan(plans: List[EducationPlan]) -> bool:
    return any(_normalize_level(p.level) in HIGH_SCHOOL_LEVELS for p in plans)


def _normalize_plan_config(plan: EducationPlan) -> EducationPlan:
    return EducationPlan(
        level=_normalize_level(plan.level),
        country=_normalize_country(plan.country),
        school_type=_normalize_school_type(plan.school_type),
        school_name=plan.school_name,
        start_age=plan.start_age,
        end_age=plan.end_age,
        annual_cost=float(plan.annual_cost) if plan.annual_cost is not None else None,
        cost_growth_rate=float(plan.cost_growth_rate) if plan.cost_growth_rate is not None else None,
        cost_basis_year=plan.cost_basis_year,
        note=plan.note,
    )


def normalize_education_plan(
    child: Child,
    assumptions: Assumptions,
    normalized_default_costs: Optional[Dict[Tuple[str, str, str], float]] = None,
) -> Child:
    """
    แยก 2 ชั้นชัดเจน
    1) config normalization
    2) business normalization
    """
    _validate_child(child)
    normalized_default_costs = normalized_default_costs or {}

    # ---------- config normalization ----------
    plans = [_normalize_plan_config(p) for p in child.education_plan]

    # ---------- business normalization ----------
    if not plans:
        plans = generate_default_education_plan(country="TH", school_type="default")

    normalized_plans: List[EducationPlan] = []
    for p in plans:
        level_key = _normalize_level(p.level)
        annual_cost = p.annual_cost

        if annual_cost is None and level_key in DEFAULT_EDUCATION_LEVELS:
            annual_cost = float(DEFAULT_EDUCATION_LEVELS[level_key]["annual_cost"])

        if annual_cost is None:
            annual_cost = _lookup_default_cost(
                level=p.level,
                country=p.country,
                school_type=p.school_type,
                normalized_default_costs=normalized_default_costs,
            )

        if annual_cost is None:
            raise ValueError(
                f"Missing annual_cost for child={child.name}, "
                f"plan=({p.level}, {p.country}, {p.school_type}). "
                "Please provide annual_cost or configure default_costs."
            )

        normalized_plan = EducationPlan(
            level=level_key,
            country=_normalize_country(p.country),
            school_type=_normalize_school_type(p.school_type),
            school_name=p.school_name,
            start_age=p.start_age,
            end_age=p.end_age,
            annual_cost=float(annual_cost),
            cost_growth_rate=p.cost_growth_rate,
            cost_basis_year=p.cost_basis_year,
            note=p.note,
        )
        _validate_education_plan(normalized_plan, child.name)
        normalized_plans.append(normalized_plan)

    if assumptions.auto_add_th_international_highschool_before_university:
        has_university = _has_university_plan(normalized_plans)
        has_highschool = _has_highschool_plan(normalized_plans)
        if has_university and not has_highschool:
            hs_cost = _lookup_default_cost(
                level="high_school",
                country="TH",
                school_type="international",
                normalized_default_costs=normalized_default_costs,
            )
            if hs_cost is None:
                hs_cost = float(DEFAULT_EDUCATION_LEVELS["high_school"]["annual_cost"])

            auto_hs = EducationPlan(
                level="high_school",
                country="TH",
                school_type="international",
                school_name=None,
                start_age=assumptions.default_highschool_start_age,
                end_age=assumptions.default_highschool_end_age,
                annual_cost=float(hs_cost),
                cost_growth_rate=None,
                cost_basis_year=None,
                note="auto-added before university",
            )
            _validate_education_plan(auto_hs, child.name)
            normalized_plans.insert(0, auto_hs)

    if assumptions.validate_education_plan_overlap:
        _validate_education_plan_overlap(normalized_plans, child.name)

    return Child(
        name=child.name,
        gender=child.gender,
        birth_date=child.birth_date,
        education_plan=normalized_plans,
        extra_expenses=child.extra_expenses,
    )


# ============================================================
# DERIVE LAST EXPENSE YEAR
# ============================================================
def derive_last_expense_year(
    children: List[Child],
    assumptions: Assumptions,
    parent_expenses: Optional[List[ParentExpense]] = None,
) -> int:
    candidate_years: List[int] = [assumptions.start_year]

    for child in children:
        byear = _birth_year(child)

        for plan in child.education_plan:
            candidate_years.append(byear + plan.end_age)

        for ex in child.extra_expenses:
            _validate_extra_expense(ex, child.name)
            if ex.type == "one_time":
                if ex.year is not None:
                    candidate_years.append(ex.year)
                else:
                    candidate_years.append(byear + ex.child_age)
            else:
                if ex.year is not None and ex.end_year is not None:
                    candidate_years.append(ex.end_year)
                else:
                    candidate_years.append(byear + ex.end_age)

    if parent_expenses:
        for ex in parent_expenses:
            _validate_parent_expense(ex)
            if ex.type == "one_time":
                candidate_years.append(ex.year)
            else:
                candidate_years.append(ex.end_year)

    return max(candidate_years)


# ============================================================
# EXPENSE YEAR RESOLUTION
# ============================================================
def _resolve_extra_expense_years(
    child: Child,
    ex: ExtraExpense,
    assumptions: Assumptions,
) -> List[int]:
    _validate_extra_expense(ex, child.name)
    byear = _birth_year(child)

    if ex.type == "one_time":
        if ex.year is not None:
            return [ex.year] if ex.year >= assumptions.start_year else []
        target_year = byear + ex.child_age
        return [target_year] if target_year >= assumptions.start_year else []

    if ex.year is not None and ex.end_year is not None:
        s = max(assumptions.start_year, ex.year)
        e = ex.end_year
        return list(range(s, e + 1)) if s <= e else []

    s = max(assumptions.start_year, byear + ex.start_age)
    e = byear + ex.end_age
    return list(range(s, e + 1)) if s <= e else []


def _resolve_parent_expense_years(
    ex: ParentExpense,
    assumptions: Assumptions,
) -> List[int]:
    _validate_parent_expense(ex)

    if ex.type == "one_time":
        return [ex.year] if ex.year >= assumptions.start_year else []

    s = max(assumptions.start_year, ex.year)
    e = ex.end_year
    return list(range(s, e + 1)) if s <= e else []


# ============================================================
# BUILD EXPENSE TABLE
# ============================================================
def build_expense_table(
    children: List[Child],
    assumptions: Assumptions,
    parent_expenses: Optional[List[ParentExpense]] = None,
) -> pd.DataFrame:
    """
    Output schema:
    [
        "year",
        "child_name",
        "child_age",
        "category",
        "sub_category",
        "description",
        "base_amount",
        "inflated_amount",
    ]
    """
    rows: List[dict] = []

    for child in children:
        byear = _birth_year(child)

        # EDUCATION EXPENSES
        for plan in child.education_plan:
            start_year = max(assumptions.start_year, byear + plan.start_age)
            end_year = byear + plan.end_age
            if start_year > end_year:
                continue

            base_cost = float(plan.annual_cost)
            growth = (
                float(plan.cost_growth_rate)
                if plan.cost_growth_rate is not None
                else float(assumptions.education_inflation_rate)
            )
            base_year = (
                plan.cost_basis_year
                if plan.cost_basis_year is not None
                else _get_effective_inflation_base_year(assumptions)
            )

            for year in range(start_year, end_year + 1):
                child_age = calculate_age_in_year(child.birth_date, year)
                academic_year_no = child_age - plan.start_age + 1
                inflated_amount = _apply_inflation(
                    base_amount=base_cost,
                    growth_rate=growth,
                    target_year=year,
                    base_year=base_year,
                )
                school_name_part = f" - {plan.school_name}" if plan.school_name else ""
                description = (
                    f"{plan.level}{school_name_part} - {plan.school_type} - {plan.country} "
                    f"(year {academic_year_no})"
                )
                rows.append({
                    "year": year,
                    "child_name": child.name,
                    "child_age": child_age,
                    "category": child.name + " education",
                    "sub_category": plan.level,
                    "description": description,
                    "base_amount": round(base_cost, 2),
                    "inflated_amount": round(inflated_amount, 2),
                })

        # EXTRA EXPENSES
        for ex in child.extra_expenses:
            expense_years = _resolve_extra_expense_years(child=child, ex=ex, assumptions=assumptions)

            if ex.inflation_type == "education":
                growth = assumptions.education_inflation_rate
            elif ex.inflation_type == "general":
                growth = assumptions.general_inflation_rate
            else:
                growth = 0.0

            base_year = _get_effective_inflation_base_year(assumptions)

            for year in expense_years:
                child_age = calculate_age_in_year(child.birth_date, year)
                inflated_amount = _apply_inflation(
                    base_amount=ex.amount,
                    growth_rate=growth,
                    target_year=year,
                    base_year=base_year,
                )
                rows.append({
                    "year": year,
                    "child_name": child.name,
                    "child_age": child_age,
                    "category": child.name + " extra expense",
                    "sub_category": ex.name,
                    "description": ex.name,
                    "base_amount": round(ex.amount, 2),
                    "inflated_amount": round(inflated_amount, 2),
                })

    # PARENT EXPENSES
    if parent_expenses:
        for ex in parent_expenses:
            expense_years = _resolve_parent_expense_years(ex=ex, assumptions=assumptions)

            if ex.inflation_type == "education":
                growth = assumptions.education_inflation_rate
            elif ex.inflation_type == "general":
                growth = assumptions.general_inflation_rate
            else:
                growth = 0.0

            base_year = _get_effective_inflation_base_year(assumptions)
            for year in expense_years:
                inflated_amount = _apply_inflation(
                    base_amount=ex.amount,
                    growth_rate=growth,
                    target_year=year,
                    base_year=base_year,
                )
                rows.append({
                    "year": year,
                    "child_name": "Parent",
                    "child_age": None,
                    "category": "parent expense",
                    "sub_category": ex.name,
                    "description": ex.name,
                    "base_amount": round(ex.amount, 2),
                    "inflated_amount": round(inflated_amount, 2),
                })

    if not rows:
        return pd.DataFrame(columns=[
            "year", "child_name", "child_age", "category", "sub_category",
            "description", "base_amount", "inflated_amount"
        ])

    expense_df = pd.DataFrame(rows)
    expense_df = expense_df.sort_values(
        ["year", "child_name", "category", "sub_category", "description"],
        na_position="last",
    ).reset_index(drop=True)
    return expense_df


# ============================================================
# RETURN / CASHFLOW HELPERS
# ============================================================
def _timing_weight(expense_timing: str) -> float:
    if expense_timing == "start_of_year":
        return 1.0
    if expense_timing == "midyear":
        return 0.5
    return 0.0


def _calculate_yearly_return_simple(
    balance_before_return: float,
    annual_rate: float,
) -> float:
    if balance_before_return <= 0:
        return 0.0
    return float(balance_before_return) * float(annual_rate)


def _simulate_monthly_cashflow(
    beginning_balance: float,
    monthly_contribution: float,
    annual_rate: float,
    annual_topup: float = 0.0,
    expense_amount: float = 0.0,
    expense_timing: str = "end_of_year",
) -> Dict[str, float]:
    """
    Source of truth สำหรับ monthly mode
    Rule: No return while negative
    - balance <= 0 ในเดือนใด จะไม่เกิด return ในเดือนนั้น
    - ถ้าภายหลัง balance กลับมา > 0 จะกลับมาคิด return ได้อีก

    Event order:
    - start_of_year: apply topup + expense ก่อนเข้ารอบเดือน
    - midyear: apply topup + expense ตอนเริ่มเดือน 7
    - end_of_year: apply topup + expense หลังจบเดือน 12
    - monthly contribution ใส่สิ้นเดือน
    """
    monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
    balance = float(beginning_balance)
    total_return = 0.0
    min_balance = balance
    went_negative = balance < 0

    if expense_timing == "start_of_year":
        balance += float(annual_topup)
        balance -= float(expense_amount)
        min_balance = min(min_balance, balance)
        went_negative = went_negative or balance < 0

    for month in range(1, 13):
        if expense_timing == "midyear" and month == 7:
            balance += float(annual_topup)
            balance -= float(expense_amount)
            min_balance = min(min_balance, balance)
            went_negative = went_negative or balance < 0

        if balance > 0:
            monthly_return = balance * monthly_rate
            balance += monthly_return
            total_return += monthly_return

        balance += float(monthly_contribution)
        min_balance = min(min_balance, balance)
        went_negative = went_negative or balance < 0

    if expense_timing == "end_of_year":
        balance += float(annual_topup)
        balance -= float(expense_amount)
        min_balance = min(min_balance, balance)
        went_negative = went_negative or balance < 0

    return {
        "investment_return": round(total_return, 2),
        "ending_balance": round(balance, 2),
        "min_balance": round(min_balance, 2),
        "went_negative": bool(went_negative),
    }


# ============================================================
# BUILD SAVING TABLE
# ============================================================
def calculate_annual_savings(
    expense_df: pd.DataFrame,
    saving_plan: SavingPlan,
    assumptions: Assumptions,
) -> pd.DataFrame:
    """
    สร้าง saving_df ตาม schema หลัก:
    [
        "year",
        "beginning_bal",
        "annual_contribution",
        "annual_topup",
        "investment_return",
        "total_expense",
        "net_cashflow",
        "ending_bal",
        "is_shortfall",
    ]

    เพิ่มเติม:
    - min_bal_during_year
    - went_negative_intra_year
    - cumulative_income
    - cumulative_expense
    """
    _validate_saving_plan(saving_plan)
    _validate_assumptions(assumptions)

    topup_map = {t.year: float(t.amount) for t in saving_plan.annual_topups}

    if expense_df.empty:
        last_expense_year = saving_plan.saving_start_year
        yearly_expense_map: Dict[int, float] = {}
    else:
        last_expense_year = int(expense_df["year"].max())
        yearly_expense_map = (
            expense_df.groupby("year")["inflated_amount"]
            .sum()
            .astype(float)
            .to_dict()
        )

    start_year = int(saving_plan.saving_start_year)
    end_year = max(start_year, last_expense_year)

    rows: List[dict] = []
    balance = float(saving_plan.initial_savings)
    annual_contribution = float(saving_plan.monthly_contribution) * 12
    cumulative_income = 0.0
    cumulative_expense = 0.0

    for year in range(start_year, end_year + 1):
        beginning_bal = float(balance)
        total_expense = float(yearly_expense_map.get(year, 0.0))
        annual_topup = float(topup_map.get(year, 0.0))

        if assumptions.return_compound_mode == "monthly":
            monthly_result = _simulate_monthly_cashflow(
                beginning_balance=beginning_bal,
                monthly_contribution=float(saving_plan.monthly_contribution),
                annual_rate=float(assumptions.investment_return_rate),
                annual_topup=annual_topup,
                expense_amount=total_expense,
                expense_timing=assumptions.expense_timing,
            )
            investment_return = float(monthly_result["investment_return"])
            ending_bal = float(monthly_result["ending_balance"])
            min_bal_during_year = float(monthly_result["min_balance"])
            went_negative_intra_year = bool(monthly_result["went_negative"])
        else:
            timing_weight = _timing_weight(assumptions.expense_timing)
            contribution_return_base = annual_contribution * 0.5
            topup_return_base = annual_topup * timing_weight
            expense_return_reduction = total_expense * timing_weight
            balance_before_return = (
                beginning_bal
                + contribution_return_base
                + topup_return_base
                - expense_return_reduction
            )
            investment_return = _calculate_yearly_return_simple(
                balance_before_return=balance_before_return,
                annual_rate=float(assumptions.investment_return_rate),
            )
            ending_bal = (
                beginning_bal
                + annual_contribution
                + annual_topup
                + investment_return
                - total_expense
            )
            min_bal_during_year = min(beginning_bal, ending_bal)
            went_negative_intra_year = (beginning_bal < 0) or (ending_bal < 0)

        net_cashflow = annual_contribution + annual_topup + investment_return - total_expense
        is_shortfall = ending_bal < 0

        income_this_year = annual_contribution + annual_topup + investment_return
        cumulative_income += income_this_year
        cumulative_expense += total_expense

        rows.append({
            "year": year,
            "beginning_bal": round(beginning_bal, 2),
            "annual_contribution": round(annual_contribution, 2),
            "annual_topup": round(annual_topup, 2),
            "investment_return": round(investment_return, 2),
            "total_expense": round(total_expense, 2),
            "net_cashflow": round(net_cashflow, 2),
            "ending_bal": round(ending_bal, 2),
            "is_shortfall": bool(is_shortfall),
            "min_bal_during_year": round(min_bal_during_year, 2),
            "went_negative_intra_year": bool(went_negative_intra_year),
            "cumulative_income": round(cumulative_income, 2),
            "cumulative_expense": round(cumulative_expense, 2),
        })

        balance = ending_bal

    if not rows:
        return pd.DataFrame(columns=[
            "year", "beginning_bal", "annual_contribution", "annual_topup",
            "investment_return", "total_expense", "net_cashflow", "ending_bal",
            "is_shortfall", "min_bal_during_year", "went_negative_intra_year",
            "cumulative_income", "cumulative_expense"
        ])

    return pd.DataFrame(rows)


# ============================================================
# FUNDING CHECK HELPERS
# ============================================================
def is_plan_sufficient(saving_df: pd.DataFrame) -> bool:
    if saving_df.empty:
        return True
    return bool((saving_df["ending_bal"] >= 0).all())


def calculate_required_monthly_contribution(
    expense_df: pd.DataFrame,
    saving_plan: SavingPlan,
    assumptions: Assumptions,
    precision: float = 1.0,
    max_search_monthly: float = 10_000_000.0,
) -> float:
    """
    หาเงินออมขั้นต่ำต่อเดือนที่ทำให้แผนไม่ shortfall เลยแม้แต่ปีเดียว
    """
    _validate_saving_plan(saving_plan)
    _validate_assumptions(assumptions)

    test_plan = replace(saving_plan)
    test_plan.annual_topups = list(saving_plan.annual_topups)

    low = 0.0
    high = max(float(saving_plan.monthly_contribution), 1.0)

    def enough(monthly: float) -> bool:
        test_plan.monthly_contribution = float(monthly)
        test_saving_df = calculate_annual_savings(
            expense_df=expense_df,
            saving_plan=test_plan,
            assumptions=assumptions,
        )
        return is_plan_sufficient(test_saving_df)

    while not enough(high):
        high *= 2
        if high > max_search_monthly:
            raise ValueError(
                "Cannot find sufficient monthly contribution within max_search_monthly"
            )

    while (high - low) > precision:
        mid = (low + high) / 2
        if enough(mid):
            high = mid
        else:
            low = mid

    return round(high, 2)


# ============================================================
# BUILD SUMMARY TABLE
# ============================================================
def build_funding_summary(
    expense_df: pd.DataFrame,
    saving_df: pd.DataFrame,
    saving_plan: SavingPlan,
    assumptions: Assumptions,
) -> pd.DataFrame:
    total_expense = float(expense_df["inflated_amount"].sum()) if not expense_df.empty else 0.0
    final_ending_balance = (
        float(saving_df["ending_bal"].iloc[-1]) if not saving_df.empty else float(saving_plan.initial_savings)
    )
    sufficient = is_plan_sufficient(saving_df)

    first_shortfall_year = None
    if not saving_df.empty and saving_df["is_shortfall"].any():
        first_shortfall_year = int(saving_df.loc[saving_df["is_shortfall"], "year"].iloc[0])

    minimum_required_monthly = calculate_required_monthly_contribution(
        expense_df=expense_df,
        saving_plan=saving_plan,
        assumptions=assumptions,
    )
    additional_monthly_needed = round(
        max(0.0, minimum_required_monthly - float(saving_plan.monthly_contribution)),
        2,
    )

    last_expense_year = (
        int(expense_df["year"].max()) if not expense_df.empty else int(saving_plan.saving_start_year)
    )

    minimum_ending_balance = (
        float(saving_df["ending_bal"].min()) if not saving_df.empty else float(saving_plan.initial_savings)
    )
    worst_year = (
        int(saving_df.loc[saving_df["ending_bal"].idxmin(), "year"]) if not saving_df.empty else int(saving_plan.saving_start_year)
    )

    if not saving_df.empty:
        total_contribution = float(saving_df["annual_contribution"].sum())
        total_topup = float(saving_df["annual_topup"].sum())
        total_investment_return = float(saving_df["investment_return"].sum())
        ever_negative_intra_year = bool(saving_df["went_negative_intra_year"].any())
        first_negative_year = (
            int(saving_df.loc[saving_df["went_negative_intra_year"], "year"].iloc[0])
            if ever_negative_intra_year else None
        )
    else:
        total_contribution = 0.0
        total_topup = 0.0
        total_investment_return = 0.0
        ever_negative_intra_year = False
        first_negative_year = None

    total_funding = round(
        float(saving_plan.initial_savings) + total_contribution + total_topup + total_investment_return,
        2,
    )
    shortfall_amount_at_worst_point = round(abs(min(minimum_ending_balance, 0.0)), 2)

    if expense_df.empty:
        peak_annual_expense = 0.0
        peak_annual_expense_year = None
    else:
        annual_exp = expense_df.groupby("year")["inflated_amount"].sum()
        peak_annual_expense = float(annual_exp.max())
        peak_annual_expense_year = int(annual_exp.idxmax())

    summary_df = pd.DataFrame([
        {"metric": "is_current_plan_sufficient", "value": bool(sufficient)},
        {"metric": "current_monthly_contribution", "value": round(float(saving_plan.monthly_contribution), 2)},
        {"metric": "minimum_required_monthly_contribution", "value": round(minimum_required_monthly, 2)},
        {"metric": "additional_monthly_needed", "value": round(additional_monthly_needed, 2)},
        {"metric": "initial_savings", "value": round(float(saving_plan.initial_savings), 2)},
        {"metric": "total_projected_expense", "value": round(total_expense, 2)},
        {"metric": "peak_annual_expense", "value": round(peak_annual_expense, 2)},
        {"metric": "peak_annual_expense_year", "value": peak_annual_expense_year},
        {"metric": "total_contribution", "value": round(total_contribution, 2)},
        {"metric": "total_topup", "value": round(total_topup, 2)},
        {"metric": "total_investment_return", "value": round(total_investment_return, 2)},
        {"metric": "total_funding", "value": round(total_funding, 2)},
        {"metric": "final_ending_balance", "value": round(final_ending_balance, 2)},
        {"metric": "minimum_ending_balance", "value": round(minimum_ending_balance, 2)},
        {"metric": "worst_year", "value": worst_year},
        {"metric": "shortfall_amount_at_worst_point", "value": round(shortfall_amount_at_worst_point, 2)},
        {"metric": "first_shortfall_year", "value": first_shortfall_year},
        {"metric": "ever_negative_intra_year", "value": bool(ever_negative_intra_year)},
        {"metric": "first_negative_year", "value": first_negative_year},
        {"metric": "saving_start_year", "value": int(saving_plan.saving_start_year)},
        {"metric": "last_expense_year", "value": last_expense_year},
        {"metric": "return_compound_mode", "value": assumptions.return_compound_mode},
        {"metric": "expense_timing", "value": assumptions.expense_timing},
    ])
    return summary_df


# ============================================================
# MAIN FUNCTION
# ============================================================
def simulate_education_plan(
    children: List[Child],
    saving_plan: SavingPlan,
    assumptions: Optional[Assumptions] = None,
    default_costs: Optional[Dict[Tuple[str, str, str], float]] = None,
    parent_expenses: Optional[List[ParentExpense]] = None,
):
    """
    Main entry point

    Returns
    -------
    expense_df : pd.DataFrame
    saving_df : pd.DataFrame
    summary_df : pd.DataFrame
    """
    assumptions_local = _prepare_assumptions(assumptions)
    normalized_default_costs = _normalize_default_costs(default_costs)

    validate_simulation_inputs(
        children=children,
        saving_plan=saving_plan,
        assumptions=assumptions_local,
        parent_expenses=parent_expenses,
    )

    normalized_children = [
        normalize_education_plan(
            child=child,
            assumptions=assumptions_local,
            normalized_default_costs=normalized_default_costs,
        )
        for child in children
    ]

    expense_df = build_expense_table(
        children=normalized_children,
        assumptions=assumptions_local,
        parent_expenses=parent_expenses,
    )

    saving_df = calculate_annual_savings(
        expense_df=expense_df,
        saving_plan=saving_plan,
        assumptions=assumptions_local,
    )

    summary_df = build_funding_summary(
        expense_df=expense_df,
        saving_df=saving_df,
        saving_plan=saving_plan,
        assumptions=assumptions_local,
    )

    return expense_df, saving_df, summary_df
