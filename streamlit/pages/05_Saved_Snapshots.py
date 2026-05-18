import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import pandas as pd
import altair as alt

from database import (
    list_all_cust_ids,
    list_snapshots,
    load_snapshot_by_id,
    load_latest_draft,
    count_records,
    prune_cust_id,
)
from asset_store import (
    load_bucket_definitions,
    get_saved_bucket_meta,
    has_saved_bucket_definitions,
)
from state import switch_page_with_persist, require_admin

require_admin()

from strings import (
    edu_level_label,
    school_type_label,
    country_label,
    gender_label,
    inflation_label,
    expense_type_label,
)


st.set_page_config(
    page_title="ข้อมูลที่บันทึกไว้",
    page_icon="💾",
    layout="wide",
)

st.title("💾 ข้อมูลที่บันทึกไว้ (Saved Snapshots)")
st.caption(
    "เรียกดูประวัติการบันทึกจากฐานข้อมูล `data.db` — "
    "เลือก Customer ID เพื่อดูสรุปแผน, preview ค่าทั้งหมด, "
    "ดาวน์โหลด หรือโหลดกลับเข้าสู่ session ได้"
)


# ============================================================
# HELPERS — parse draft → structured records
# ============================================================
TODAY = date.today()


def _to_date(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v)
        except Exception:
            return None
    return None


def _age_today(birth: Any) -> Optional[int]:
    d = _to_date(birth)
    if not d:
        return None
    years = TODAY.year - d.year - ((TODAY.month, TODAY.day) < (d.month, d.day))
    return max(years, 0)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


_CHILD_BASE_RE = re.compile(r"^child\.(\d+)\.([a-z_]+)$")
_CHILD_EDU_RE  = re.compile(r"^child\.(\d+)\.edu\.(\d+)\.([a-z_]+)$")
_CHILD_EXTRA_RE = re.compile(r"^child\.(\d+)\.extra\.(\d+)\.([a-z_]+)$")
_PARENT_RE     = re.compile(r"^parent\.(\d+)\.([a-z_]+)$")
_TOPUP_RE      = re.compile(r"^topup\.(\d+)\.([a-z_]+)$")


def _parse_draft(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a flat draft dict → structured groups for display + CSV."""
    overview = {
        "cust_id":              str(draft.get("cust_id", "") or ""),
        "n_children":           _safe_int(draft.get("n_children", 0)),
        "n_parent_expenses":    _safe_int(draft.get("n_parent_expenses", 0)),
        "n_topups":             _safe_int(draft.get("n_topups", 0)),
        "initial_savings":      _safe_float(draft.get("initial_savings", 0.0)),
        "monthly_contribution": _safe_float(draft.get("monthly_contribution", 0.0)),
        "saving_start_year":    _safe_int(draft.get("saving_start_year", TODAY.year)),
    }

    children: Dict[int, Dict[str, Any]] = {}
    edu_plans: List[Dict[str, Any]] = []
    extra_expenses: List[Dict[str, Any]] = []
    parent_expenses: Dict[int, Dict[str, Any]] = {}
    topups: Dict[int, Dict[str, Any]] = {}

    for k, v in draft.items():
        if not isinstance(k, str):
            continue

        m = _CHILD_EDU_RE.match(k)
        if m:
            ci, ei, field = int(m.group(1)), int(m.group(2)), m.group(3)
            rec = next((r for r in edu_plans if r["_ci"] == ci and r["_ei"] == ei), None)
            if rec is None:
                rec = {"_ci": ci, "_ei": ei}
                edu_plans.append(rec)
            rec[field] = v
            continue

        m = _CHILD_EXTRA_RE.match(k)
        if m:
            ci, xi, field = int(m.group(1)), int(m.group(2)), m.group(3)
            rec = next((r for r in extra_expenses if r["_ci"] == ci and r["_xi"] == xi), None)
            if rec is None:
                rec = {"_ci": ci, "_xi": xi}
                extra_expenses.append(rec)
            rec[field] = v
            continue

        m = _CHILD_BASE_RE.match(k)
        if m:
            ci, field = int(m.group(1)), m.group(2)
            children.setdefault(ci, {})[field] = v
            continue

        m = _PARENT_RE.match(k)
        if m:
            pi, field = int(m.group(1)), m.group(2)
            parent_expenses.setdefault(pi, {})[field] = v
            continue

        m = _TOPUP_RE.match(k)
        if m:
            ti, field = int(m.group(1)), m.group(2)
            topups.setdefault(ti, {})[field] = v
            continue

    # Materialize children records, sort by index, enrich with age.
    # IMPORTANT: respect the canonical n_children — stale child.N.* keys may
    # still exist in the draft after the user reduced the child count.
    n_children_cap = overview["n_children"]
    children_list = []
    for ci in sorted(children.keys()):
        if ci >= n_children_cap:
            continue
        rec = children[ci]
        b = _to_date(rec.get("birth_date"))
        children_list.append({
            "child_idx": ci,
            "name": str(rec.get("name", f"Child {ci+1}")),
            "gender": str(rec.get("gender", "")),
            "birth_date": b.isoformat() if b else "",
            "age_today": _age_today(rec.get("birth_date")),
            "n_edu": _safe_int(rec.get("n_edu", 0)),
            "n_extra": _safe_int(rec.get("n_extra", 0)),
        })

    # Per-child caps for edu / extra (trim stale rows from drafts that
    # previously had more rows for a given child).
    n_edu_cap   = {c["child_idx"]: c["n_edu"]   for c in children_list}
    n_extra_cap = {c["child_idx"]: c["n_extra"] for c in children_list}

    edu_plans = [
        r for r in edu_plans
        if r["_ci"] in n_edu_cap and r["_ei"] < n_edu_cap[r["_ci"]]
    ]
    extra_expenses = [
        r for r in extra_expenses
        if r["_ci"] in n_extra_cap and r["_xi"] < n_extra_cap[r["_ci"]]
    ]

    # Lookup child name by index
    name_of = {c["child_idx"]: c["name"] for c in children_list}

    # Enrich edu plans
    for rec in edu_plans:
        rec["child_name"] = name_of.get(rec["_ci"], f"Child {rec['_ci']+1}")
    edu_plans.sort(key=lambda r: (r["_ci"], r["_ei"]))

    for rec in extra_expenses:
        rec["child_name"] = name_of.get(rec["_ci"], f"Child {rec['_ci']+1}")
    extra_expenses.sort(key=lambda r: (r["_ci"], r["_xi"]))

    # Trim parent expenses + topups by their canonical counts as well.
    n_parent_cap = overview["n_parent_expenses"]
    n_topup_cap  = overview["n_topups"]
    parent_list = [
        parent_expenses[i] | {"parent_idx": i}
        for i in sorted(parent_expenses.keys())
        if i < n_parent_cap
    ]
    topup_list = [
        topups[i] | {"topup_idx": i}
        for i in sorted(topups.keys())
        if i < n_topup_cap
    ]

    # Aggregates
    total_annual_cost = sum(_safe_float(p.get("annual_cost", 0)) for p in edu_plans)
    total_topup       = sum(_safe_float(t.get("amount", 0)) for t in topup_list)
    total_parent_one_time = sum(
        _safe_float(p.get("amount", 0)) for p in parent_list
        if str(p.get("type", "one_time")) == "one_time"
    )
    total_parent_recurring_annual = sum(
        _safe_float(p.get("amount", 0)) for p in parent_list
        if str(p.get("type", "one_time")) == "recurring"
    )

    return {
        "overview": overview,
        "children": children_list,
        "edu_plans": edu_plans,
        "extra_expenses": extra_expenses,
        "parent_expenses": parent_list,
        "topups": topup_list,
        "totals": {
            "total_edu_annual_cost": total_annual_cost,
            "total_topup_amount": total_topup,
            "total_parent_one_time": total_parent_one_time,
            "total_parent_recurring_annual": total_parent_recurring_annual,
        },
    }


def _fmt_money(v: Any) -> str:
    try:
        return f"฿{float(v):,.0f}"
    except Exception:
        return "-"


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("## 💾 Saved Snapshots")
    if st.button("⬅️ กลับหน้าแรก", width="stretch"):
        switch_page_with_persist("01_User_Information.py")
    st.divider()
    st.caption(
        f"ฐานข้อมูล: `{os.path.basename(os.environ.get('WEALTH_KIDS_DB_PATH','data.db'))}` "
        f"(เก็บล่าสุดสูงสุด 10 รายการต่อ Customer ID)"
    )


# ============================================================
# SECTION 1: PICK A CUST_ID
# ============================================================
st.subheader("1) เลือก Customer ID")

try:
    _all_ids = list_all_cust_ids()
except Exception as e:
    st.error(f"ไม่สามารถเข้าถึงฐานข้อมูลได้: {e}")
    st.stop()

if not _all_ids:
    st.info("ยังไม่มีข้อมูลในฐานข้อมูล — ลองเข้าหน้า 'User Information' แล้วบันทึกการจำลองก่อน")
    st.stop()

_cid_df = pd.DataFrame(_all_ids).rename(columns={
    "cust_id": "Customer ID",
    "n_snapshots": "จำนวน Snapshot",
    "latest": "บันทึกล่าสุด",
    "latest_staff_id": "Staff ID (ล่าสุด)",
})
with st.container(border=True):
    st.dataframe(_cid_df, width="stretch", hide_index=True)

_options = [r["cust_id"] for r in _all_ids]
_default_idx = 0
_pre = st.session_state.get("draft", {}).get("cust_id")
if _pre and _pre in _options:
    _default_idx = _options.index(_pre)

_sel_cid = st.selectbox(
    "Customer ID",
    options=_options,
    index=_default_idx,
    key="snap_sel_cust_id",
)


# ============================================================
# SECTION 2: LIST SNAPSHOTS
# ============================================================
st.subheader(f"2) ประวัติของ `{_sel_cid}`")

try:
    _snaps = list_snapshots(_sel_cid)
except Exception as e:
    st.error(f"โหลดประวัติไม่สำเร็จ: {e}")
    st.stop()

if not _snaps:
    st.info("ไม่มี snapshot สำหรับ Customer ID นี้")
    st.stop()

_snap_df = pd.DataFrame(_snaps)
_snap_df["label"] = _snap_df.apply(
    lambda r: (
        f"#{r['id']} — {r['created_at']} "
        f"({r['n_fields']} fields"
        + (f", staff {r['staff_id']}" if r.get('staff_id') else "")
        + ")"
    ),
    axis=1,
)

with st.container(border=True):
    _show_cols = ["id", "created_at", "staff_id", "n_fields"]
    _show_cols = [c for c in _show_cols if c in _snap_df.columns]
    _show_df = _snap_df[_show_cols].rename(columns={
        "id": "Snapshot ID",
        "created_at": "เวลาที่บันทึก",
        "staff_id": "Staff ID",
        "n_fields": "จำนวน Field",
    })
    st.dataframe(_show_df, width="stretch", hide_index=True)

_label_to_id = dict(zip(_snap_df["label"].tolist(), _snap_df["id"].tolist()))
_sel_label = st.selectbox(
    "เลือก Snapshot ที่ต้องการดู",
    options=_snap_df["label"].tolist(),
    index=0,
    key="snap_sel_label",
)
_sel_id = int(_label_to_id[_sel_label])


# ============================================================
# SECTION 3: SNAPSHOT DETAILS — Tabs: สรุป | Field ทั้งหมด
# ============================================================
st.subheader(f"3) รายละเอียด Snapshot #{_sel_id}")

try:
    _draft = load_snapshot_by_id(_sel_id) or {}
except Exception as e:
    st.error(f"โหลด snapshot ไม่สำเร็จ: {e}")
    st.stop()

if not _draft:
    st.warning("Snapshot นี้ว่างเปล่า")
    st.stop()

_parsed = _parse_draft(_draft)

_tab_summary, _tab_raw = st.tabs(["📊 สรุปข้อมูลลูกค้า", "🗂️ Field ทั้งหมด"])

# ------------------------------------------------------------
# TAB: SUMMARY (visualize)
# ------------------------------------------------------------
with _tab_summary:
    _ov = _parsed["overview"]
    _t  = _parsed["totals"]

    # ---- 3.1 Plan overview metrics ----
    st.markdown("#### 📋 ภาพรวมแผน")
    with st.container(border=True):
        _c1, _c2, _c3, _c4 = st.columns(4)
        _c1.metric("จำนวนลูก", _ov["n_children"])
        _c2.metric("เงินต้น (Initial)", _fmt_money(_ov["initial_savings"]))
        _c3.metric("เงินฝากต่อเดือน", _fmt_money(_ov["monthly_contribution"]))
        _c4.metric("ปีเริ่มออม", _ov["saving_start_year"])

        _c5, _c6, _c7, _c8 = st.columns(4)
        _c5.metric("จำนวนแผนการศึกษา", len(_parsed["edu_plans"]))
        _c6.metric(
            "ค่าเทอม/ปี (รวมทุกแผน)",
            _fmt_money(_t["total_edu_annual_cost"]),
            help="ผลรวมของ annual_cost ของทุกแผนการศึกษาทุกคน (ก่อน inflation, ไม่หักช่วงอายุ)",
        )
        _c7.metric(
            "Top-up รวม",
            _fmt_money(_t["total_topup_amount"]),
            help=f"เงินก้อนใส่เพิ่ม {_ov['n_topups']} ครั้ง",
        )
        _c8.metric("ค่าใช้จ่ายพ่อแม่", _ov["n_parent_expenses"])

    # ---- 3.2 Children ----
    st.markdown("#### 👶 ลูกแต่ละคน")
    if not _parsed["children"]:
        st.info("ยังไม่มีข้อมูลลูกใน snapshot นี้")
    else:
        _ch_df = pd.DataFrame(_parsed["children"])
        _ch_df["เพศ"] = _ch_df["gender"].apply(gender_label)
        _ch_df_disp = _ch_df.rename(columns={
            "name": "ชื่อ",
            "birth_date": "วันเกิด",
            "age_today": "อายุปัจจุบัน (ปี)",
            "n_edu": "จำนวนแผนการศึกษา",
            "n_extra": "ค่าใช้จ่ายเพิ่มเติม",
        })[["ชื่อ", "เพศ", "วันเกิด", "อายุปัจจุบัน (ปี)", "จำนวนแผนการศึกษา", "ค่าใช้จ่ายเพิ่มเติม"]]
        st.dataframe(_ch_df_disp, width="stretch", hide_index=True)

    # ---- 3.3 Education plans ----
    st.markdown("#### 🎓 แผนการศึกษา (ต่อคน × ต่อช่วงอายุ)")
    if not _parsed["edu_plans"]:
        st.info("ยังไม่มีแผนการศึกษา")
    else:
        _ep = pd.DataFrame(_parsed["edu_plans"])
        # decorate with pretty labels
        _ep["ระดับ"]    = _ep.get("level", pd.Series([""]*len(_ep))).fillna("").apply(edu_level_label)
        _ep["ประเทศ"]   = _ep.get("country", pd.Series([""]*len(_ep))).fillna("").apply(country_label)
        _ep["ประเภท"]   = _ep.get("school_type", pd.Series([""]*len(_ep))).fillna("").apply(school_type_label)
        _ep["สถาบัน"]   = _ep.get("school_name", pd.Series([""]*len(_ep))).fillna("").astype(str)
        _ep["เริ่ม (อายุ)"] = pd.to_numeric(_ep.get("start_age"), errors="coerce").astype("Int64")
        _ep["จบ (อายุ)"]    = pd.to_numeric(_ep.get("end_age"),   errors="coerce").astype("Int64")
        _ep["ระยะเวลา (ปี)"] = (_ep["จบ (อายุ)"] - _ep["เริ่ม (อายุ)"] + 1)
        _ep["ค่าเทอม/ปี (฿)"] = pd.to_numeric(_ep.get("annual_cost"), errors="coerce")
        _ep["ค่าเทอมตลอดช่วง (฿)"] = _ep["ค่าเทอม/ปี (฿)"] * _ep["ระยะเวลา (ปี)"]
        _ep["Cost growth %/ปี"] = (pd.to_numeric(_ep.get("cost_growth_rate"), errors="coerce") * 100).round(2)

        _ep_disp = _ep.rename(columns={"child_name": "ลูก"})[[
            "ลูก", "ระดับ", "ประเทศ", "ประเภท", "สถาบัน",
            "เริ่ม (อายุ)", "จบ (อายุ)", "ระยะเวลา (ปี)",
            "ค่าเทอม/ปี (฿)", "ค่าเทอมตลอดช่วง (฿)", "Cost growth %/ปี",
        ]]
        st.dataframe(
            _ep_disp,
            width="stretch",
            hide_index=True,
            column_config={
                "ค่าเทอม/ปี (฿)": st.column_config.NumberColumn(format="%,.0f"),
                "ค่าเทอมตลอดช่วง (฿)": st.column_config.NumberColumn(format="%,.0f"),
                "Cost growth %/ปี": st.column_config.NumberColumn(format="%.2f"),
            },
        )

        # ---- Timeline (Gantt) chart by age ----
        _gantt_df = _ep.copy()
        _gantt_df["start_age_i"] = pd.to_numeric(_gantt_df["start_age"], errors="coerce")
        _gantt_df["end_age_i"]   = pd.to_numeric(_gantt_df["end_age"],   errors="coerce")
        _gantt_df["end_age_excl"] = _gantt_df["end_age_i"] + 1  # inclusive → exclusive for bar end
        _gantt_df = _gantt_df.dropna(subset=["start_age_i", "end_age_excl"])
        if not _gantt_df.empty:
            _gantt_df["ระดับ"] = _gantt_df["level"].fillna("").apply(edu_level_label)
            _gantt_df["annual_cost_num"] = pd.to_numeric(_gantt_df["annual_cost"], errors="coerce").fillna(0)
            _gantt_chart = (
                alt.Chart(_gantt_df)
                .mark_bar(cornerRadius=4, opacity=0.85)
                .encode(
                    x=alt.X(
                        "start_age_i:Q",
                        title="อายุ (ปี)",
                        scale=alt.Scale(zero=False),
                        axis=alt.Axis(format="d", tickMinStep=1),
                    ),
                    x2=alt.X2("end_age_excl:Q"),
                    y=alt.Y("child_name:N", title="ลูก", sort=None),
                    color=alt.Color("ระดับ:N", title="ระดับการศึกษา"),
                    tooltip=[
                        alt.Tooltip("child_name:N", title="ลูก"),
                        alt.Tooltip("ระดับ:N"),
                        alt.Tooltip("school_name:N", title="สถาบัน"),
                        alt.Tooltip("start_age_i:Q", title="เริ่มอายุ", format="d"),
                        alt.Tooltip("end_age_i:Q", title="จบอายุ", format="d"),
                        alt.Tooltip("annual_cost_num:Q", title="ค่าเทอม/ปี", format=",.0f"),
                    ],
                )
                .properties(height=max(70 * max(len(_parsed["children"]), 1), 160), title="📊 Timeline แผนการศึกษาตามช่วงอายุ")
            )
            st.altair_chart(_gantt_chart, width="stretch")

            # ---- Cost-by-level bar chart ----
            _by_level = (
                _gantt_df.assign(_dur=_gantt_df["end_age_i"] - _gantt_df["start_age_i"] + 1)
                .assign(_total=lambda d: d["annual_cost_num"] * d["_dur"])
                .groupby("ระดับ", as_index=False)["_total"].sum()
                .rename(columns={"_total": "ค่าเทอมรวม (฿)"})
                .sort_values("ค่าเทอมรวม (฿)", ascending=False)
            )
            _cost_chart = (
                alt.Chart(_by_level)
                .mark_bar()
                .encode(
                    x=alt.X("ค่าเทอมรวม (฿):Q", axis=alt.Axis(format=",.0f")),
                    y=alt.Y("ระดับ:N", sort="-x"),
                    color=alt.Color("ระดับ:N", legend=None),
                    tooltip=[
                        alt.Tooltip("ระดับ:N"),
                        alt.Tooltip("ค่าเทอมรวม (฿):Q", format=",.0f"),
                    ],
                )
                .properties(height=max(36 * len(_by_level), 160), title="💸 ค่าเทอมรวมตลอดช่วงตามระดับ (ทุกคนรวมกัน)")
            )
            st.altair_chart(_cost_chart, width="stretch")

    # ---- 3.4 Parent expenses ----
    st.markdown("#### 👨‍👩‍👧 ค่าใช้จ่ายพ่อแม่")
    if not _parsed["parent_expenses"]:
        st.info("ยังไม่มีค่าใช้จ่ายพ่อแม่ใน snapshot นี้")
    else:
        _pe = pd.DataFrame(_parsed["parent_expenses"])
        _pe["ประเภท"] = _pe.get("type", pd.Series([""]*len(_pe))).fillna("").apply(expense_type_label)
        _pe["Inflation"] = _pe.get("inflation_type", pd.Series([""]*len(_pe))).fillna("").apply(inflation_label)
        _pe["ปีเริ่ม"]  = pd.to_numeric(_pe.get("year"),     errors="coerce").astype("Int64")
        _pe["ปีจบ"]    = pd.to_numeric(_pe.get("end_year"), errors="coerce").astype("Int64")
        _pe["จำนวนเงิน (฿)"] = pd.to_numeric(_pe.get("amount"), errors="coerce")
        _pe_disp = _pe.rename(columns={"name": "ชื่อรายการ", "note": "หมายเหตุ"})
        _show_cols = ["ชื่อรายการ", "ประเภท", "จำนวนเงิน (฿)", "ปีเริ่ม", "ปีจบ", "Inflation", "หมายเหตุ"]
        _show_cols = [c for c in _show_cols if c in _pe_disp.columns]
        st.dataframe(
            _pe_disp[_show_cols],
            width="stretch",
            hide_index=True,
            column_config={
                "จำนวนเงิน (฿)": st.column_config.NumberColumn(format="%,.0f"),
            },
        )

    # ---- 3.5 Top-ups ----
    st.markdown("#### 💰 เงินก้อนเพิ่มเติม (Top-up)")
    if not _parsed["topups"]:
        st.info("ยังไม่มี Top-up ใน snapshot นี้")
    else:
        _tu = pd.DataFrame(_parsed["topups"])
        _tu["ปี"] = pd.to_numeric(_tu.get("year"), errors="coerce").astype("Int64")
        _tu["จำนวนเงิน (฿)"] = pd.to_numeric(_tu.get("amount"), errors="coerce")
        _tu_disp = _tu.rename(columns={"note": "หมายเหตุ"})
        _show_cols = ["ปี", "จำนวนเงิน (฿)", "หมายเหตุ"]
        _show_cols = [c for c in _show_cols if c in _tu_disp.columns]
        st.dataframe(
            _tu_disp[_show_cols],
            width="stretch",
            hide_index=True,
            column_config={
                "จำนวนเงิน (฿)": st.column_config.NumberColumn(format="%,.0f"),
            },
        )

    # ---- 3.6 Child extra expenses (if any) ----
    if _parsed["extra_expenses"]:
        st.markdown("#### 🎒 ค่าใช้จ่ายเพิ่มเติมของลูก")
        _xe = pd.DataFrame(_parsed["extra_expenses"])
        _xe["ประเภท"] = _xe.get("type", pd.Series([""]*len(_xe))).fillna("").apply(expense_type_label)
        _xe["Inflation"] = _xe.get("inflation_type", pd.Series([""]*len(_xe))).fillna("").apply(inflation_label)
        _xe["จำนวนเงิน (฿)"] = pd.to_numeric(_xe.get("amount"), errors="coerce")
        _xe_disp = _xe.rename(columns={"child_name": "ลูก", "name": "ชื่อรายการ", "note": "หมายเหตุ"})
        _show_cols = ["ลูก", "ชื่อรายการ", "ประเภท", "จำนวนเงิน (฿)", "Inflation", "หมายเหตุ"]
        _show_cols = [c for c in _show_cols if c in _xe_disp.columns]
        st.dataframe(
            _xe_disp[_show_cols],
            width="stretch",
            hide_index=True,
            column_config={"จำนวนเงิน (฿)": st.column_config.NumberColumn(format="%,.0f")},
        )


# ------------------------------------------------------------
# TAB: RAW FIELD TABLE
# ------------------------------------------------------------
with _tab_raw:
    def _stringify(v):
        if isinstance(v, (date, datetime)):
            return v.isoformat()
        if isinstance(v, (list, dict)):
            try:
                return json.dumps(v, ensure_ascii=False)
            except Exception:
                return str(v)
        return str(v)   # ← เปลี่ยนจาก `return v` เพื่อให้คอลัมน์ Value เป็น str ทั้งหมด

    _rows = [
        {"Field": k, "Type": type(v).__name__, "Value": _stringify(v)}
        for k, v in sorted(_draft.items())
    ]
    _preview_df = pd.DataFrame(_rows)
    for _col in _preview_df.columns:
        if _preview_df[_col].dtype == object:
            _preview_df[_col] = _preview_df[_col].astype(str)

    with st.container(border=True):
        _filter = st.text_input(
            "ค้นหา field (พิมพ์เพื่อกรอง)",
            value="",
            key="snap_field_filter",
            placeholder="เช่น cust_id, n_children, saving_initial",
        )
        if _filter.strip():
            _q = _filter.strip().lower()
            _view = _preview_df[_preview_df["Field"].str.lower().str.contains(_q, na=False)]
        else:
            _view = _preview_df

        st.dataframe(_view, width="stretch", hide_index=True, height=420)
        st.caption(f"แสดง {len(_view):,} จาก {len(_preview_df):,} field")


# ============================================================
# SECTION 4: HOUSEKEEPING (advanced)
# ============================================================
with st.expander("⚙️ ขั้นสูง: จัดการประวัติของ Customer ID นี้", expanded=False):
    st.caption(
        f"ระบบเก็บ snapshot ล่าสุดสูงสุด 10 รายการต่อ Customer ID — "
        f"ปัจจุบัน `{_sel_cid}` มี {count_records(_sel_cid)} รายการ"
    )
    _keep = st.number_input(
        "เก็บเฉพาะ N รายการล่าสุด",
        min_value=0, max_value=10, value=10, step=1,
        key="snap_prune_keep",
    )
    if st.button(
        f"🗑️ ลบรายการเก่า (เก็บไว้ {int(_keep)} รายการล่าสุด)",
        key="snap_btn_prune",
    ):
        try:
            deleted = prune_cust_id(_sel_cid, keep=int(_keep))
            st.success(f"ลบ {deleted} รายการเรียบร้อย")
            st.rerun()
        except Exception as e:
            st.error(f"ลบไม่สำเร็จ: {e}")


# ============================================================
# SECTION 5: ASSET CONFIG SNAPSHOT (per selected cust_id)
# ============================================================
st.subheader(f"4) 📊 Asset Config ล่าสุดของ `{_sel_cid}`")
st.caption(
    "สรุปข้อมูล asset config ล่าสุดที่ลูกค้าตั้งไว้ใน Page 3 — "
    "ระดับ Customer ID × Bucket × Asset"
)

with st.container(border=True):
    try:
        _sel_defs = load_bucket_definitions(_sel_cid)
    except Exception as e:
        st.error(f"โหลด asset config ไม่สำเร็จ: {e}")
        _sel_defs = None

    if not _sel_defs:
        st.info(f"ยังไม่มี asset config สำหรับ `{_sel_cid}`")
    else:
        _sel_rows: List[Dict[str, Any]] = []
        for _b_idx, _bdef in enumerate(_sel_defs):
            _bname = str(_bdef.get("name", f"Bucket {_b_idx+1}"))
            _y_start = _bdef.get("year_start", "")
            _y_end = _bdef.get("year_end", None)
            _y_end_str = "∞" if _y_end is None else str(_y_end)
            _bucket_label = f"{_bname} ({_y_start}–{_y_end_str})"
            _assets = _bdef.get("assets", []) or []
            if not _assets:
                _sel_rows.append({
                    "cust_id": _sel_cid,
                    "bucket": _bucket_label,
                    "asset": "(no asset)",
                    "weight_pct": None,
                    "mean_pct": None,
                    "std_pct": None,
                    "min_pct": None,
                    "max_pct": None,
                })
                continue
            for _a in _assets:
                _sel_rows.append({
                    "cust_id": _sel_cid,
                    "bucket": _bucket_label,
                    "asset": str(_a.get("asset_name", "")),
                    "weight_pct": _safe_float(_a.get("weight_pct", 0.0)),
                    "mean_pct":   _safe_float(_a.get("mean_pct", 0.0)),
                    "std_pct":    _safe_float(_a.get("std_pct", 0.0)),
                    "min_pct":    _safe_float(_a.get("min_pct", 0.0)),
                    "max_pct":    _safe_float(_a.get("max_pct", 0.0)),
                })

        _sel_df = pd.DataFrame(_sel_rows)
        st.dataframe(
            _sel_df,
            width="stretch",
            hide_index=True,
            column_config={
                "weight_pct": st.column_config.NumberColumn(format="%.2f"),
                "mean_pct":   st.column_config.NumberColumn(format="%.2f"),
                "std_pct":    st.column_config.NumberColumn(format="%.2f"),
                "min_pct":    st.column_config.NumberColumn(format="%.2f"),
                "max_pct":    st.column_config.NumberColumn(format="%.2f"),
            },
        )
        st.caption(f"พบ {len(_sel_defs)} bucket, {len(_sel_df)} แถว")


# ============================================================
# SECTION 6: AGGREGATE EXPORT — most-recent data per cust_id
# ============================================================
st.subheader("5) 📤 ดาวน์โหลด CSV รวม (ระดับ Customer ID)")
st.caption(
    "รวบรวมข้อมูล **ล่าสุด** ของทุก Customer ID ในฐานข้อมูลมาเป็น CSV — "
    "สำหรับนำไปวิเคราะห์ลูกค้าต่อ"
)


@st.cache_data(show_spinner=False)
def _build_aggregate_tables(cust_id_meta: List[Dict[str, Any]]):
    """For every cust_id, load its latest snapshot and build:
      - customer_df:     one row per cust_id (aggregates)
      - child_df:        one row per child
      - edu_df:          one row per child × edu plan
      - parent_df:       one row per parent expense
      - topup_df:        one row per top-up
      - asset_config_df: one row per cust_id × bucket × asset (Page 3 config)
    """
    customer_rows: List[Dict[str, Any]] = []
    child_rows:    List[Dict[str, Any]] = []
    edu_rows:      List[Dict[str, Any]] = []
    parent_rows:   List[Dict[str, Any]] = []
    topup_rows:    List[Dict[str, Any]] = []
    asset_rows:    List[Dict[str, Any]] = []

    for meta in cust_id_meta:
        cid = meta["cust_id"]
        latest_meta = meta  # has .latest = created_at
        staff_id = latest_meta.get("latest_staff_id", "")
        latest_created_at = latest_meta.get("latest", "")
        draft = load_latest_draft(cid) or {}
        parsed = _parse_draft(draft)
        ov = parsed["overview"]
        tot = parsed["totals"]

        customer_rows.append({
            "cust_id": cid,
            "staff_id": staff_id,
            "latest_created_at": latest_created_at,
            "n_snapshots": int(latest_meta.get("n_snapshots", 0)),
            "n_children": ov["n_children"],
            "n_parent_expenses": ov["n_parent_expenses"],
            "n_topups": ov["n_topups"],
            "initial_savings": ov["initial_savings"],
            "monthly_contribution": ov["monthly_contribution"],
            "saving_start_year": ov["saving_start_year"],
            "n_edu_plans_total": len(parsed["edu_plans"]),
            "total_edu_annual_cost": tot["total_edu_annual_cost"],
            "total_topup_amount": tot["total_topup_amount"],
            "total_parent_one_time": tot["total_parent_one_time"],
            "total_parent_recurring_annual": tot["total_parent_recurring_annual"],
            # Convenience: comma-joined child names
            "children_names": ", ".join(c["name"] for c in parsed["children"]),
        })

        for c in parsed["children"]:
            child_rows.append({
                "cust_id": cid,
                "staff_id": staff_id,
                "latest_created_at": latest_created_at,
                "child_idx": c["child_idx"],
                "child_name": c["name"],
                "gender": c["gender"],
                "birth_date": c["birth_date"],
                "age_today": c["age_today"],
                "n_edu_plans": c["n_edu"],
                "n_extra_expenses": c["n_extra"],
            })

        for p in parsed["edu_plans"]:
            start_age = _safe_int(p.get("start_age"), 0)
            end_age   = _safe_int(p.get("end_age"), 0)
            dur       = max(end_age - start_age + 1, 0)
            ac        = _safe_float(p.get("annual_cost"), 0.0)
            edu_rows.append({
                "cust_id": cid,
                "staff_id": staff_id,
                "latest_created_at": latest_created_at,
                "child_idx": p.get("_ci"),
                "child_name": p.get("child_name", ""),
                "edu_idx": p.get("_ei"),
                "level": str(p.get("level", "")),
                "level_label": edu_level_label(str(p.get("level", ""))) if p.get("level") else "",
                "country": str(p.get("country", "")),
                "country_label": country_label(str(p.get("country", ""))) if p.get("country") else "",
                "school_type": str(p.get("school_type", "")),
                "school_type_label": school_type_label(str(p.get("school_type", ""))) if p.get("school_type") else "",
                "school_name": str(p.get("school_name", "")),
                "start_age": start_age,
                "end_age": end_age,
                "duration_years": dur,
                "annual_cost": ac,
                "total_cost_in_range": ac * dur,
                "cost_growth_rate": _safe_float(p.get("cost_growth_rate"), 0.0),
                "cost_basis_year": _safe_int(p.get("cost_basis_year"), 0),
                "note": str(p.get("note", "")),
            })

        for pe in parsed["parent_expenses"]:
            parent_rows.append({
                "cust_id": cid,
                "staff_id": staff_id,
                "latest_created_at": latest_created_at,
                "parent_expense_idx": pe.get("parent_idx"),
                "name": str(pe.get("name", "")),
                "type": str(pe.get("type", "")),
                "amount": _safe_float(pe.get("amount"), 0.0),
                "year": _safe_int(pe.get("year"), 0),
                "end_year": _safe_int(pe.get("end_year"), 0) if pe.get("end_year") is not None else None,
                "inflation_type": str(pe.get("inflation_type", "")),
                "note": str(pe.get("note", "")),
            })

        for tu in parsed["topups"]:
            topup_rows.append({
                "cust_id": cid,
                "staff_id": staff_id,
                "latest_created_at": latest_created_at,
                "topup_idx": tu.get("topup_idx"),
                "year": _safe_int(tu.get("year"), 0),
                "amount": _safe_float(tu.get("amount"), 0.0),
                "note": str(tu.get("note", "")),
            })

        # ---- Page 3 asset config (flattened per bucket × asset) ----
        try:
            _defs = load_bucket_definitions(cid)
        except Exception:
            _defs = None
        if _defs:
            for b_idx, bdef in enumerate(_defs):
                bname = str(bdef.get("name", f"Bucket {b_idx+1}"))
                y_start = bdef.get("year_start", "")
                y_end = bdef.get("year_end", None)
                y_end_str = "" if y_end is None else str(y_end)
                discount_rate = _safe_float(bdef.get("discount_rate", 0.0))
                _assets = bdef.get("assets", []) or []
                for a_idx, a in enumerate(_assets):
                    asset_rows.append({
                        "cust_id": cid,
                        "staff_id": staff_id,
                        "latest_created_at": latest_created_at,
                        "bucket_idx": b_idx,
                        "bucket_name": bname,
                        "bucket_year_start": y_start,
                        "bucket_year_end": y_end_str,
                        "bucket_discount_rate": discount_rate,
                        "asset_idx": a_idx,
                        "asset_name": str(a.get("asset_name", f"Asset {a_idx+1}")),
                        "weight_pct": _safe_float(a.get("weight_pct", 0.0)),
                        "mean_pct":   _safe_float(a.get("mean_pct", 0.0)),
                        "std_pct":    _safe_float(a.get("std_pct", 0.0)),
                        "min_pct":    _safe_float(a.get("min_pct", 0.0)),
                        "max_pct":    _safe_float(a.get("max_pct", 0.0)),
                    })

    return (
        pd.DataFrame(customer_rows),
        pd.DataFrame(child_rows),
        pd.DataFrame(edu_rows),
        pd.DataFrame(parent_rows),
        pd.DataFrame(topup_rows),
        pd.DataFrame(asset_rows),
    )


with st.container(border=True):
    st.caption(
        "💡 เพื่อป้องกันการดึงข้อมูลจากฐานข้อมูลทุกครั้งที่หน้ารีโหลด — "
        "กดปุ่มด้านล่างเพื่อรวบรวมข้อมูลล่าสุดของทุก Customer ID มาเตรียม preview และ download"
    )

    _bc1, _bc2 = st.columns([1, 3])
    with _bc1:
        _build_clicked = st.button(
            "🔄 สร้างตารางสรุป",
            type="primary",
            width="stretch",
            key="btn_build_aggregate",
            help="ดึง snapshot ล่าสุดของทุก Customer ID มารวบรวมเป็นตาราง 5 ชุด",
        )
    with _bc2:
        if st.session_state.get("_aggregate_cache_ts"):
            st.caption(f"📌 สร้างล่าสุดเมื่อ: `{st.session_state['_aggregate_cache_ts']}` "
                       f"(กดปุ่มอีกครั้งเพื่อ refresh)")
        else:
            st.caption("⚠️ ยังไม่ได้สร้างตาราง — กดปุ่มซ้ายมือเพื่อเริ่ม")

    # Build (or rebuild) on click → cache in session_state
    if _build_clicked:
        with st.spinner("กำลังรวบรวมข้อมูลล่าสุดของทุก Customer ID..."):
            _c, _ch, _ed, _pa, _tu, _ac = _build_aggregate_tables(_all_ids)
            st.session_state["_aggregate_cache"] = {
                "cust_df":         _c,
                "child_df":        _ch,
                "edu_df":          _ed,
                "parent_df":       _pa,
                "topup_df":        _tu,
                "asset_config_df": _ac,
            }
            st.session_state["_aggregate_cache_ts"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.success(f"สร้างตารางเรียบร้อย — ครอบคลุม {len(_c):,} Customer ID")

    # Render preview + download buttons ONLY if cache exists
    _agg = st.session_state.get("_aggregate_cache")
    if _agg is None:
        st.info("กดปุ่ม **🔄 สร้างตารางสรุป** ก่อน จึงจะ preview / download ได้")
    else:
        _cust_df         = _agg["cust_df"]
        _child_df        = _agg["child_df"]
        _edu_df          = _agg["edu_df"]
        _parent_df       = _agg["parent_df"]
        _topup_df        = _agg["topup_df"]
        _asset_config_df = _agg.get("asset_config_df", pd.DataFrame())

        st.markdown(f"**ครอบคลุม {len(_cust_df):,} Customer ID** — ใช้ snapshot ล่าสุดของแต่ละคน")

        _e1, _e2, _e3, _e4, _e5 = st.columns(5)
        _e1.metric("จำนวน Customer", len(_cust_df))
        _e2.metric("จำนวนลูก (รวม)", len(_child_df))
        _e3.metric("แผนการศึกษา (รวม)", len(_edu_df))
        _e4.metric("Top-ups (รวม)", len(_topup_df))
        _e5.metric("Asset config (รวม)", len(_asset_config_df))

        # ---- Multi-tab preview of all 6 CSVs ----
        st.markdown("**🔍 ตัวอย่างข้อมูล (50 แถวแรก) — แต่ละ tab คือ 1 CSV**")
        _tab_c, _tab_ch, _tab_ed, _tab_pa, _tab_tu, _tab_ac = st.tabs([
            "1️⃣ Customer summary",
            "2️⃣ ลูก (per child)",
            "3️⃣ แผนการศึกษา",
            "4️⃣ ค่าใช้จ่ายพ่อแม่",
            "5️⃣ Top-ups",
            "6️⃣ Asset Config",
        ])

        with _tab_c:
            if _cust_df.empty:
                st.info("ไม่มีข้อมูล")
            else:
                _preview_cols = [
                    "cust_id", "staff_id", "latest_created_at", "n_children",
                    "initial_savings", "monthly_contribution",
                    "n_edu_plans_total", "total_edu_annual_cost", "total_topup_amount",
                    "children_names",
                ]
                _preview_cols = [c for c in _preview_cols if c in _cust_df.columns]
                st.dataframe(
                    _cust_df[_preview_cols].head(50),
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "initial_savings":       st.column_config.NumberColumn(format="%,.0f"),
                        "monthly_contribution":  st.column_config.NumberColumn(format="%,.0f"),
                        "total_edu_annual_cost": st.column_config.NumberColumn(format="%,.0f"),
                        "total_topup_amount":    st.column_config.NumberColumn(format="%,.0f"),
                    },
                )
                st.caption(f"แสดง {min(50, len(_cust_df)):,} จาก {len(_cust_df):,} แถว — กดดาวน์โหลดเพื่อรับข้อมูลเต็ม")

        with _tab_ch:
            if _child_df.empty:
                st.info("ไม่มีข้อมูลลูก")
            else:
                st.dataframe(_child_df.head(50), width="stretch", hide_index=True)
                st.caption(f"แสดง {min(50, len(_child_df)):,} จาก {len(_child_df):,} แถว")

        with _tab_ed:
            if _edu_df.empty:
                st.info("ไม่มีแผนการศึกษา")
            else:
                st.dataframe(
                    _edu_df.head(50),
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "annual_cost":         st.column_config.NumberColumn(format="%,.0f"),
                        "total_cost_in_range": st.column_config.NumberColumn(format="%,.0f"),
                        "cost_growth_rate":    st.column_config.NumberColumn(format="%.4f"),
                    },
                )
                st.caption(f"แสดง {min(50, len(_edu_df)):,} จาก {len(_edu_df):,} แถว")

        with _tab_pa:
            if _parent_df.empty:
                st.info("ไม่มีค่าใช้จ่ายพ่อแม่")
            else:
                st.dataframe(
                    _parent_df.head(50),
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "amount": st.column_config.NumberColumn(format="%,.0f"),
                    },
                )
                st.caption(f"แสดง {min(50, len(_parent_df)):,} จาก {len(_parent_df):,} แถว")

        with _tab_tu:
            if _topup_df.empty:
                st.info("ไม่มี Top-up")
            else:
                st.dataframe(
                    _topup_df.head(50),
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "amount": st.column_config.NumberColumn(format="%,.0f"),
                    },
                )
                st.caption(f"แสดง {min(50, len(_topup_df)):,} จาก {len(_topup_df):,} แถว")

        with _tab_ac:
            if _asset_config_df.empty:
                st.info("ยังไม่มี asset config สำหรับ Customer ID ใด ๆ")
            else:
                st.dataframe(
                    _asset_config_df.head(50),
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "weight_pct":           st.column_config.NumberColumn(format="%.2f"),
                        "mean_pct":             st.column_config.NumberColumn(format="%.2f"),
                        "std_pct":              st.column_config.NumberColumn(format="%.2f"),
                        "min_pct":              st.column_config.NumberColumn(format="%.2f"),
                        "max_pct":              st.column_config.NumberColumn(format="%.2f"),
                        "bucket_discount_rate": st.column_config.NumberColumn(format="%.4f"),
                    },
                )
                st.caption(f"แสดง {min(50, len(_asset_config_df)):,} จาก {len(_asset_config_df):,} แถว")

        # ---- Download buttons (6 separate CSVs) ----
        st.markdown("**📥 ดาวน์โหลด**")
        _d1, _d2, _d3 = st.columns(3)
        _d4, _d5, _d6 = st.columns(3)

        _today_tag = datetime.now().strftime("%Y%m%d_%H%M")

        with _d1:
            st.download_button(
                "1️⃣ Customer summary",
                data=_cust_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"customer_summary_{_today_tag}.csv",
                mime="text/csv",
                width="stretch",
                help="1 แถวต่อ Customer ID — aggregate metrics",
            )
        with _d2:
            st.download_button(
                "2️⃣ ลูก (per child)",
                data=_child_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"customer_children_{_today_tag}.csv",
                mime="text/csv",
                width="stretch",
                help="1 แถวต่อลูกแต่ละคน",
                disabled=_child_df.empty,
            )
        with _d3:
            st.download_button(
                "3️⃣ แผนการศึกษา (per child × plan)",
                data=_edu_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"customer_education_plans_{_today_tag}.csv",
                mime="text/csv",
                width="stretch",
                help="1 แถวต่อแผนการศึกษา — รวมทุกคนทุก cust_id",
                disabled=_edu_df.empty,
            )
        with _d4:
            st.download_button(
                "4️⃣ ค่าใช้จ่ายพ่อแม่",
                data=_parent_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"customer_parent_expenses_{_today_tag}.csv",
                mime="text/csv",
                width="stretch",
                disabled=_parent_df.empty,
            )
        with _d5:
            st.download_button(
                "5️⃣ Top-ups",
                data=_topup_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"customer_topups_{_today_tag}.csv",
                mime="text/csv",
                width="stretch",
                disabled=_topup_df.empty,
            )
        with _d6:
            st.download_button(
                "6️⃣ Asset Config",
                data=_asset_config_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"customer_asset_config_{_today_tag}.csv",
                mime="text/csv",
                width="stretch",
                help="1 แถวต่อ cust_id × bucket × asset (Page 3)",
                disabled=_asset_config_df.empty,
            )
