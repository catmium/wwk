# strings.py
# ============================================================
# ทุก UI string ของ app อยู่ที่นี่
# แก้คำ ปรับภาษา เปลี่ยน label → แก้ไฟล์นี้ที่เดียว
#
# วิธีใช้:
#   from strings import S, SC
#   S("p1", "title")                             # → "📘 จำลองค่าใช้จ่าย..."
#   S("p1", "child_expander", n=1, name="บี")    # → "ลูกคนที่ 1: บี"
#   SC("btn_add")                                # → "➕ เพิ่ม"
# ============================================================

from typing import Dict, Any

_S: Dict[str, Any] = {

    # ──────────────────────────────────────────────────────
    # COMMON  ใช้ร่วมกันทุกหน้า
    # ──────────────────────────────────────────────────────
    "common": {
        "btn_add":           "➕ เพิ่มรายการ",
        "btn_remove_last":   "🗑 ลบรายการล่าสุด",
        "note_optional":     "หมายเหตุ (ไม่บังคับ)",
        "name":              "ชื่อ",
        "amount":            "จำนวนเงิน",
        "year":              "ปี",
        "start_year":        "ปีเริ่มต้น",
        "end_year":          "ปีสิ้นสุด",
        "start_age":         "อายุเริ่มต้น",
        "end_age":           "อายุสิ้นสุด",
        "child_age":         "อายุลูก",
        "type":              "ประเภท",
        "download_csv":      "⬇ ดาวน์โหลด CSV",
        "inclusive_help":    "นับรวมปีนี้ด้วย",
        # option labels ที่ใช้บ่อยข้าม page
        "opt_one_time":      "ครั้งเดียว",
        "opt_recurring":     "ทุกปี",
        "opt_by_year":       "กำหนดตามปี",
        "opt_by_child_age":  "กำหนดตามอายุลูก",
        "opt_infl_general":  "เงินเฟ้อทั่วไป",
        "opt_infl_edu":      "เงินเฟ้อการศึกษา",
        "opt_infl_none":     "ไม่คิดเงินเฟ้อ",
        "opt_gender_m":      "ชาย",
        "opt_gender_f":      "หญิง",
        "opt_gender_other":  "อื่นๆ",
    },

    # ──────────────────────────────────────────────────────
    # SIDEBAR  workflow indicator (ใช้ร่วมกันทุกหน้า)
    # ──────────────────────────────────────────────────────
    "sidebar": {
        "workflow_header":   "## Workflow",
        "step1_active":      "**① กรอกข้อมูล** ← *คุณอยู่ที่นี่*",
        "step1_done":        "**① กรอกข้อมูล** ✅",
        "step2":             "**② จำลองค่าใช้จ่าย**",
        "step2_done":        "**② จำลองค่าใช้จ่าย** ✅",
        "step3":             "**③ แผนการลงทุน**",
        "snapshot_header":   "### 📊 สรุปข้อมูลที่กรอก",
        "metric_children":   "จำนวนลูก",
        "metric_edu_plans":  "แผนการศึกษา",
        "metric_parent_exp": "ค่าใช้จ่ายครอบครัว",
        "metric_monthly":    "ออมรายเดือน (฿)",
        "metric_initial":    "เงินออมเริ่มต้น (฿)",
    },

    # ──────────────────────────────────────────────────────
    # PAGE 1  หน้า User Information
    # ──────────────────────────────────────────────────────
    "p1": {
        # ── Page header ──
        "page_title":        "Education & Family Expense Simulation",
        "title":             "📘 แบบจำลองค่าใช้จ่ายทางการศึกษา",
        "caption":           "กรอกข้อมูลลูก ค่าใช้จ่าย แผนออม และสมมติฐาน แล้วกด Simulation เพื่อดูผลการจำลอง",

        # ── Section 1: Child ──แผนการ
        "sec1_header":       "1) ข้อมูลลูก",
        "sec1_caption":      "ระบุจำนวนลูก แผนการเรียน และค่าใช้จ่ายพิเศษของลูก",
        "metric_n_children": "จำนวนลูก",
        "btn_add_child":     "➕ เพิ่มลูก",
        "btn_rem_child":     "🗑 ลบรายการล่าสุด",
        "child_expander":    "ลูกคนที่ {n}: {name}",

        # ── Tabs ──
        "tab_basic":         "ข้อมูลพื้นฐาน",
        "tab_edu":           "แผนการศึกษา",
        "tab_extra":         "ค่าใช้จ่ายพิเศษ",

        # ── Tab: Basic Info ──
        "basic_caption":     "กรอกข้อมูลพื้นฐานของลูกก่อน แล้วค่อยไปที่แท็บ แผนการศึกษา และ ค่าใช้จ่ายพิเศษ",
        "label_child_name":  "ชื่อลูก",
        "label_gender":      "เพศ",
        "label_birth_date":  "วันเกิด",

        # ── Tab: Education Plans ──
        "edu_caption":       "กรอกรายละเอียดแผนการเรียนแต่ละช่วงอายุ",
        "metric_n_edu":      "แผนการศึกษา",
        "btn_load_template": "📋 โหลด template มาตรฐาน",
        "edu_plan_header":   "แผนที่ {n} — {level}",
        "btn_reset_preset":  "↺ รีเซ็ตค่าเริ่มต้น",

        # Education plan primary fields
        "label_edu_level":   "ระดับการศึกษา",
        "label_start_age":   "อายุเริ่มต้น",
        "label_end_age":     "อายุสิ้นสุด",
        "label_annual_cost": "ค่าใช้จ่ายต่อปี (฿)",

        # Row 2 fields (always visible)
        "label_country":          "ประเทศ",
        "label_school_type":      "ประเภทโรงเรียน",
        "label_school_name":      "ชื่อโรงเรียน",
        "label_note":             "หมายเหตุ",

        # Country option labels
        "opt_country_":     "(ไม่ระบุ)",
        "opt_country_TH":   "🇹🇭 ไทย",
        "opt_country_US":   "🇺🇸 สหรัฐฯ",
        "opt_country_UK":   "🇬🇧 อังกฤษ",
        "opt_country_AU":   "🇦🇺 ออสเตรเลีย",
        "opt_country_JP":   "🇯🇵 ญี่ปุ่น",
        "opt_country_SG":   "🇸🇬 สิงคโปร์",
        "opt_country_CN":   "🇨🇳 จีน",
        "opt_country_DE":   "🇩🇪 เยอรมนี",
        "opt_country_Other":"🌐 อื่นๆ",

        # Slim expander (growth rate + basis year only)
        "edu_advanced_expander":  "⚙️ ปรับอัตราเงินเฟ้อและปีฐาน (ไม่บังคับ)",
        "label_override_growth":  "กำหนด cost growth rate และ basis year เอง",
        "label_cost_growth_rate": "อัตราเงินเฟ้อค่าเล่าเรียน (%)",
        "label_cost_basis_year":  "ปีฐานของค่าใช้จ่าย",

        # Fee reference button
        "btn_fee_reference":      "📚 ดูค่าเล่าเรียนโรงเรียนในไทยและต่างประเทศ",

        # Education level option labels
        "edu_level_kindergarten":  "อนุบาล",
        "edu_level_elementary":    "ประถมศึกษา",
        "edu_level_middle_school": "มัธยมต้น",
        "edu_level_high_school":   "มัธยมปลาย",
        "edu_level_bachelor":      "ปริญญาตรี",
        "edu_level_master":        "ปริญญาโท",
        "edu_level_doctor":        "ปริญญาเอก",
        "edu_level_other":         "อื่นๆ",

        # School type option labels
        "school_type_international":       "นานาชาติ",
        "school_type_government":          "รัฐบาล",
        "school_type_private":             "เอกชน",
        "school_type_foreign_university":  "มหาวิทยาลัยต่างประเทศ",
        "school_type_other":               "อื่นๆ",

        # ── Tab: Child Extra Expenses ──
        "extra_caption":     "ค่าใช้จ่ายพิเศษของลูก เช่น กิจกรรมนอกหลักสูตร ท่องเที่ยว — เลือกได้ทั้งแบบครั้งเดียวหรือทุกปี กำหนดได้ตามปีหรืออายุลูก",
        "metric_n_extra":    "ค่าใช้จ่ายพิเศษ",
        "extra_card_header": "ค่าใช้จ่ายพิเศษที่ {n}",
        "label_trigger":     "กำหนดเวลาโดย",
        "label_infl_type":   "ประเภทเงินเฟ้อ",

        # ── Section 2: Parent Expenses ──
        "sec2_header":       "2) ค่าใช้จ่ายครอบครัว",
        "sec2_caption":      "ค่าใช้จ่ายพิเศษที่ไม่ได้ผูกกับลูกโดยตรง ที่อาจกระทบกับเงินออมเพื่อการศึกษา",
        "metric_n_parent":   "รายการค่าใช้จ่าย",
        "btn_add_parent":    "➕ เพิ่มรายการ",
        "parent_card_header":"ค่าใช้จ่ายครอบครัวที่ {n}",

        # ── Section 3: Saving Plan ──
        "sec3_header":           "3) แผนการออมเพื่อการศึกษา",
        "sec3_caption":          "ระบุเงินออมเริ่มต้นและการออมรายเดือน",
        "label_initial_savings": "เงินออมเริ่มต้น (฿)",
        "label_monthly_contrib": "ออมรายเดือน (฿)",
        "metric_n_topups":       "เงินก้อนพิเศษ (topup)",
        "btn_add_topup":         "➕ เพิ่มเงินก้อนพิเศษ",
        "topup_card_header":     "เงินก้อนพิเศษที่ {n}",

        # ── Section 4: Assumptions ──
        "sec4_header":             "4) สมมติฐาน",
        "label_general_infl":      "อัตราเงินเฟ้อทั่วไป (%)",
        "label_general_infl_help": "เช่น 3.0 = เงินเฟ้อ 3% ต่อปี",
        "label_edu_infl":          "อัตราเงินเฟ้อค่าเล่าเรียน (%)",
        "label_edu_infl_help":     "เช่น 5.0 = เงินเฟ้อ 5% ต่อปี",
        "label_invest_return":     "อัตราผลตอบแทนการลงทุน (%)",
        "label_invest_return_help":"เช่น 6.0 = ผลตอบแทน 6% ต่อปี",
        "advanced_assump":         "สมมติฐานขั้นสูง",
        "label_compound_mode":     "วิธีคิดดอกเบี้ยทบต้น",
        "label_expense_timing":    "จังหวะค่าใช้จ่าย",
        "opt_compound_yearly":     "รายปี",
        "opt_compound_monthly":    "รายเดือน",
        "opt_timing_start":        "ต้นปี",
        "opt_timing_mid":          "กลางปี",
        "opt_timing_end":          "ปลายปี",

        # ── Section 5: Review & Run ──
        "sec5_header":      "5) สร้างแบบจำลอง",
        "review_expander":  "📋 ทบทวนข้อมูล",
        "btn_run":          "🚀 Simulation",
        "sim_success":      "✅ Simulation สำเร็จ — กำลังไปหน้าผลลัพธ์...",
        "sim_failed":       "❌ Simulation ล้มเหลว: {error}",
        "footer_expander":  "ดูผล Simulation ล่าสุด",

        # Review table row labels
        "review_children":        "จำนวนลูก",
        "review_edu_plans":       "แผนการศึกษา",
        "review_child_extra":     "ค่าใช้จ่ายพิเศษของลูก",
        "review_parent_exp":      "ค่าใช้จ่ายครอบครัว",
        "review_topups":          "เงินก้อนพิเศษ",
        "review_initial_savings": "เงินออมเริ่มต้น (฿)",
        "review_monthly":         "ออมรายเดือน (฿)",
        "review_general_infl":    "เงินเฟ้อทั่วไป",
        "review_edu_infl":        "เงินเฟ้อการศึกษา",
        "review_invest_return":   "ผลตอบแทนการลงทุน",
        "review_col_item":        "รายการ",
        "review_col_value":       "ค่า",
    },

    # ──────────────────────────────────────────────────────
    # PAGE 2  หน้า Expense Simulation
    # ──────────────────────────────────────────────────────
    "p2": {
        # ── Page header ──
        "page_title":       "Expense Simulation",
        "title":            "📊 ผลการจำลองค่าใช้จ่าย",
        "caption":          "สรุปผลการจำลองค่าใช้จ่ายและแผนออมทรัพย์ตลอดช่วงเวลาที่คาดการณ์",

        # ── Sidebar ──
        "step2_active":     "**② จำลองค่าใช้จ่าย** ← *คุณอยู่ที่นี่*",
        "btn_back":         "← กลับหน้ากรอกข้อมูล",
        "btn_next":         "→ แผนการลงทุน",

        # ── Gate (no simulation yet) ──
        "gate_warn":        "กรุณากรอกข้อมูลและกด รัน ที่หน้ากรอกข้อมูลก่อน",
        "gate_btn":         "← ไปหน้ากรอกข้อมูล",
        "err_no_saving":    "ไม่พบข้อมูล saving_df — กรุณา run simulation ใหม่",

        # ── Status banner ──
        "status_ok":        "✅ **แผนการออมเพียงพอ** — เงินออมของคุณครอบคลุมค่าใช้จ่ายทั้งหมดที่คาดการณ์ไว้",
        "status_fail":      "⚠️ **แผนการออมไม่เพียงพอ** — ต้องเพิ่มการออมอีก ฿{extra}/เดือน (ต้องออมเงินอย่างน้อย ฿{yr}/เดือน เพื่อให้แผนนี้เพียงพอ)",
        "shortfall_start":  "เริ่มปี {year}",

        # ── KPI cards ──
        "kpi_total_expense":    "ค่าใช้จ่ายรวมที่คาดการณ์",
        "kpi_final_balance":    "ยอดเงินรวมที่คาดการณ์",
        "kpi_shortfall_year":   "ปีแรกที่เงินไม่พอ",
        "kpi_no_shortfall":     "ไม่มี",
        "kpi_peak_expense":     "ค่าใช้จ่ายสูงสุดต่อปี",
        "kpi_peak_year_delta":  "ปี {year}",
        "kpi_invest_return":    "ผลตอบแทนการลงทุน (รวม)",
        "kpi_surplus":          "เกิน",
        "kpi_deficit":          "ขาด",

        # ── Chart section headers ──
        "chart1_header":    "พอร์ตโฟลิโอ (ตั้งแต่ปีที่เริ่มออมเงินจนถึงปีสุดท้ายที่มีค่าใช้จ่าย)",
        "chart1_caption":   "เงินออมสะสม (รวมผลตอบแทน) เทียบกับค่าใช้จ่ายสะสม และยอดเงินคงเหลือรายปี",
        "chart2_header":    "ค่าใช้จ่ายปรับตามอัตราเงินเฟ้อ",
        "chart2_caption":   "แบ่งตามปี",
        "chart3_header":    "แหล่งที่มาของเงิน",
        "chart3_lifetime":  "แบ่งตามหมวด",
        "chart3_by_year":   "แบ่งตามปี",
        "chart4_header":    "ค่าใช้จ่ายรวมแยกตามหมวด",
        "chart4_caption":   "แบ่งตามหมวด",

        # ── Chart labels / series names ──
        "series_cum_fund":  "เงินออมสะสม",
        "series_cum_exp":   "ค่าใช้จ่ายสะสม",
        "series_balance":   "ยอดเงินคงเหลือ",
        "shortfall_marker": "⚠ เงินไม่พอ",

        # Funding source component labels
        "comp_initial":     "เงินออมเริ่มต้น",
        "comp_contrib":     "ออมรายปี",
        "comp_topup":       "เงินก้อนพิเศษ",
        "comp_return":      "ผลตอบแทนการลงทุน",

        # ── Chart axis labels ──
        "axis_year":        "ปี",
        "axis_amount":      "จำนวนเงิน (฿)",
        "axis_total_amount":"จำนวนเงินรวม (฿)",
        "legend_series":    "ชุดข้อมูล",
        "legend_category":  "หมวด",
        "legend_component": "ส่วนประกอบ",

        # ── Data tables ──
        "tbl_summary":      "📋 สรุปผล Simulation",
        "tbl_expense":      "📋 ตารางค่าใช้จ่าย",
        "tbl_saving":       "📋 ตารางแผนออมเงิน",
        "info_no_summary":  "ไม่มีข้อมูล summary",
        "info_no_expense":  "ไม่มีข้อมูล expense",
        "err_missing_cols": "expense_df ขาดคอลัมน์: {cols}",
        "dl_expense":       "⬇ ดาวน์โหลด expense CSV",
        "dl_saving":        "⬇ ดาวน์โหลด saving CSV",

        # ── Bottom CTA ──
        "cta_header":       "### พร้อมวางแผนการลงทุนหรือยัง?",
        "cta_caption":      "นำผลลัพธ์นี้ไปวางแผนการลงทุนได้ที่หน้าถัดไป",
        "cta_btn":          "🏦 ไปหน้าแผนการลงทุน →",
    },

    # ──────────────────────────────────────────────────────
    # PAGE 3  หน้า Investment Planning
    # ──────────────────────────────────────────────────────
    "p3": {
        # ── Page header ──
        "page_title":       "Investment Planning",
        "title":            "📈 สร้างแบบจำลองแผนการลงทุนด้วยวิธี Monte Carlo",
        "caption":          "สร้างสถานการณ์จำลองผลตอบแทนการลงทุนที่หลากหลายเพื่อช่วยในการประเมินแผนการลงทุนของคุณ",

        # ── Sidebar ──
        "workflow_header":  "### 🗺️ ขั้นตอน",
        "step3_active":     "**③ แผนการลงทุน** ← คุณอยู่ที่นี่",
        "btn_back":         "← กลับหน้าจำลองค่าใช้จ่าย",
        "plan_summary":     "### 📋 สรุปแผน",
        "sidebar_horizon":  "ช่วงเวลา: {start}–{end} ({n} ปี)",
        "sim_done_header":  "### ✅ Simulation สำเร็จ",
        "sim_done_caption": "เลื่อนลงเพื่อดูผลลัพธ์ หรือรันใหม่ด้วยค่าอื่น",

        # ── Gate ──
        "gate_warn":        "ยังไม่พบผลลัพธ์จาก Expense Simulation — กรุณาไปหน้า Expense แล้วรัน simulation ก่อน",

        # ── Section 1: Plan Context ──
        "sec1_header":      "1) สรุปข้อมูลแผน",
        "ctx_total_exp":    "ค่าใช้จ่ายรวม",
        "ctx_horizon":      "ช่วงเวลา",
        "ctx_horizon_val":  "{start}–{end} ({n} ปี)",
        "ctx_peak":         "ค่าใช้จ่ายสูงสุด",
        "ctx_peak_val":     "฿{amount:,.0f} (ปี {year})",
        "ctx_ttl_cont":     "เงินออมทั้งหมด (ไม่รวมผลตอบแทนจากการลงทุน)",
        "ctx_initial":      "เงินออมเริ่มต้น + เงินก้อนพิเศษ",
        "ctx_monthly":      "ออมรายเดือน",

        # ── Section 2: Bucket & Asset Config ──
        "sec2_header":      "2) การตั้งค่า Bucket & Asset",
        "sec2_caption":     "กำหนดจำนวน bucket กรอบเวลาแต่ละ bucket และ asset ภายใน — ระบบจะ simulate return ของแต่ละ asset แล้วรวม weighted average เป็น bucket return",
        "bucket_tbl_header":"**ตั้งค่า Bucket** (เพิ่ม/ลบ/แก้ไขได้)",
        "bucket_tbl_hint":  "year_end = 0 หมายถึง open-ended (bucket สุดท้าย) | discount_rate_pct ใช้คิด PV requirement",
        "asset_tbl_header": "**ตั้งค่า Asset แต่ละ Bucket**",
        "asset_tbl_hint":   "ค่า return เป็น % (6.0 = 6% ต่อปี) | weight_pct รวมเท่าไรก็ได้ — ระบบ normalize อัตโนมัติ",

        # Bucket table columns
        "col_bucket_name":      "ชื่อ Bucket",
        "col_year_start":       "ปีเริ่ม",
        "col_year_end":         "ปีสิ้นสุด (0 = ∞)",
        "col_discount_rate":    "Discount Rate %",

        # Asset table columns
        "col_asset_name":       "ชื่อ Asset",
        "col_weight":           "สัดส่วน %",
        "col_mean_return":      "ผลตอบแทนเฉลี่ย %",
        "col_std":              "ความเสี่ยง (Std) %",
        "col_min_return":       "ผลตอบแทนต่ำสุด %",
        "col_max_return":       "ผลตอบแทนสูงสุด %",

        # Asset metrics inside expander
        "metric_n_assets":      "จำนวน Asset",
        "metric_total_weight":  "น้ำหนักรวม",
        "metric_eff_mean":      "ผลตอบแทนเฉลี่ย (weighted)",
        "asset_eff_caption":    "ผลตอบแทนรวม → เฉลี่ย: **{mean:.2f}%**, std: **{std:.2f}%** (weighted avg จาก {n} asset)",
        "err_no_asset":         "ต้องมีอย่างน้อย 1 asset ที่มี weight > 0",
        "warn_zero_std":        "⚠️ มี asset ที่ std_pct = 0 → return คงที่ทุก path (ไม่มี randomness)",

        # Bucket expander label
        "bucket_expander":      "📦 {name}  (ปี {start} – {end})",

        # Validation
        "bucket_valid":         "✅ ตั้งค่า Bucket ถูกต้อง ({n} buckets)",
        "err_bucket_min":       "ต้องมีอย่างน้อย 1 bucket",
        "err_bucket_dup":       "ชื่อ bucket ต้องไม่ซ้ำกัน",
        "err_bucket_start":     "Bucket แรกต้องเริ่มที่ year_start = 1",
        "err_bucket_gap":       "Bucket '{name}' ควรเริ่มที่ปี {expected} (ต้องต่อเนื่องไม่มี gap)",
        "err_bucket_last":      "Bucket สุดท้าย ('{name}') ต้องมี year_end = 0 (∞)",

        # Asset Performance Preview
        "preview_expander":     "📊 ดูตัวอย่างผลตอบแทน Asset",
        "preview_rr_map":       "**Risk–Return Map** (วงกลมใหญ่ = สัดส่วนมาก)",
        "preview_composition":  "**สัดส่วน Asset แต่ละ Bucket** (% normalized)",
        "preview_dist":         "**การกระจายตัวของผลตอบแทน** (2,000 scenarios ต่อ asset)",
        "preview_summary":      "**สรุปผลตอบแทน Asset**",
        "preview_sharpe_note":  "*Sharpe = mean / std (ไม่หัก risk-free rate) — ใช้เปรียบเทียบเชิง relative เท่านั้น",
        "preview_empty":        "กรอก asset ใน Section 2 ก่อนเพื่อดู preview",

        # ── Section 3: Initial Portfolio Allocation ──
        "sec3_header":      "3) การจัดสรรเงินเริ่มต้น",
        "sec3_caption":     "ระบบคำนวณ recommended allocation โดยใช้ weighted expected return ของแต่ละ bucket เพื่อประมาณเงินที่ต้องมีใน bucket นั้น",
        "alloc_rec_header": "**แนะนำ: Auto Allocation**",
        "alloc_rate_desc":  "Discount rate ที่ใช้: {rates}",
        "alloc_req_expander":"รายละเอียด Bucket Requirement (PV ของค่าใช้จ่าย)",
        "alloc_warn":       "ไม่สามารถคำนวณ recommended allocation ได้: {err}",
        "alloc_mode_label": "โหมดการจัดสรร",
        "alloc_mode_auto":  "🤖 Auto (ใช้ค่า recommended)",
        "alloc_mode_manual":"✏️ Manual (กรอกเอง)",
        "manual_header":    "**กรอก Manual Allocation**",
        "manual_amount_hint":"กรอกจำนวนเงินแต่ละ bucket รวมกันต้องได้ = {total:,.0f} บาท",
        "manual_pct_hint":  "กรอก % แต่ละ bucket รวมกันต้องได้ = 100% (เงินออมเริ่มต้น = {total:,.0f} บาท)",
        "manual_input_mode":"กรอกเป็น",
        "manual_opt_amount":"💰 จำนวนเงิน (บาท)",
        "manual_opt_pct":   "📊 สัดส่วน (%)",
        "manual_valid":     "✅ รวม = {total:,.0f} บาท — ถูกต้อง",
        "err_manual_pct":   "% รวมกันต้องได้ 100% แต่ได้ {total:.2f}%",

        # ── Section 4: MC Config ──
        "sec4_header":      "4) ตั้งค่า Monte Carlo",
        "advanced_settings_header": "⚙️ Advanced Settings",
        "label_n_paths":    "จำนวน paths",
        "label_n_paths_help":"จำนวน Monte Carlo simulation paths",
        "label_seed":       "Random seed",
        "label_seed_help":  "กำหนด seed เพื่อให้ผลลัพธ์ reproducible",
        "debug_header":     "**ตัวเลือก Debug / Audit**",
        "debug_header_caption": "ตัวเลือก Debug / Audit",
        "label_keep_path":  "เก็บ path × year × bucket detail",
        "label_keep_path_help":"mc_path_detail_df — ดู ending_balance รายปีรายถัง",
        "label_keep_asset": "เก็บ path × year × bucket × asset detail",
        "label_keep_asset_help":"mc_path_asset_detail_df — recheck weighted return ราย asset",

        # ── Run button & validation ──
        "btn_run":          "🚀 Portfolio Monte Carlo",
        "warn_fix_bucket":  "กรุณาแก้ไขการตั้งค่า Bucket ให้ถูกต้องก่อนรัน simulation",
        "warn_fix_alloc":   "กรุณาแก้ไข manual allocation ให้ถูกต้องก่อนรัน simulation",
        "sim_success":      "✅ Monte Carlo simulation สำเร็จ",
        "sim_failed":       "❌ Simulation ล้มเหลว: {error}",

        # ── Section 6: Results ──
        "sec6_header":      "5) ผลลัพธ์ Monte Carlo",
        "status_good":      "✅ **แผนการลงทุนผ่าน** — Success probability: {prob:.1%}  (shortfall: {sfail:.1%})",
        "status_warn":      "⚠️ **ความเสี่ยงปานกลาง** — Success probability: {prob:.1%}  (shortfall: {sfail:.1%})",
        "status_bad":       "❌ **ความเสี่ยงสูง** — Success probability: {prob:.1%}  (shortfall: {sfail:.1%})",
        "no_result":        "กรอกค่าและกด **รัน Portfolio Monte Carlo** เพื่อดูผลลัพธ์",

        # KPI labels
        "kpi_success_prob":  "โอกาสสำเร็จตามแผน",
        "kpi_shortfall_prob": "โอกาสเงินไม่พอ",
        "kpi_exp_balance":   "เงินคงเหลือปลายแผน (คาดการณ์)",
        "kpi_p10_balance":   "เงินคงเหลือ กรณี Pessimistic (P10)",
        "kpi_p50_balance":   "เงินคงเหลือ กรณีกลาง (P50)",
        "kpi_p90_balance":   "เงินคงเหลือ กรณี Optimistic (P90)",
        "kpi_exp_shortfall": "ยอดขาดเงินเฉลี่ย",
        "kpi_exp_shortfall_help": "ค่าเฉลี่ยของยอดเงินที่ขาด",
        "kpi_worst":         "ยอดขาดเงินสูงสุดที่พบ",
        "kpi_worst_help":    "กรณีเลวร้ายสุดที่เกิดขึ้นใน Simulation ทั้งหมด",
        "kpi_first_sf_year": "ปีที่มีโอกาสเงินไม่พอสูงสุด",

        # Charts section
        "charts_header":    "### 📈 Charts",
        "chart_p50_balance":"**Ending Balance รายปี / Bucket — แถบ P10–P90, เส้น P50**",
        "chart_shortfall":  "**Shortfall Probability รายปี / Bucket**",
        "chart_final_dist": "**การกระจายตัวของเงินคงเหลือ ณ สิ้นแผน — ทุกเส้นทางจำลอง**",
        "chart_sf_year":    "**ปีที่มักเกิดเหตุการณ์เงินไม่พอ — กระจายตัวตามปี**",

        # Tables section
        "tables_header":    "### 📊 ตารางข้อมูล",
        "tbl_engine":       "📑 สรุปผล Engine",
        "tbl_bucket":       "🪣 สรุปผลรายถัง",
        "tbl_risk_years":   "⚠️ ปีที่มีความเสี่ยงสูง",
        "tbl_worst_paths":  "📉 Paths ที่แย่ที่สุด",
        "tbl_allocation":   "💰 Bucket Requirement / การจัดสรรเริ่มต้น",
        "tbl_alloc_req":    "**Bucket Requirement**",
        "tbl_alloc_init":   "**การจัดสรรเริ่มต้น**",
        "tbl_p50_pivot":    "📊 P50 Ending Balance Pivot",
        "tbl_sf_pivot":     "📊 Shortfall Probability Pivot",

        # Raw data section
        "raw_header":       "### 🔍 ข้อมูลดิบ (Audit / Recheck)",
        "tbl_path_detail":  "📋 Path × Year × Bucket detail",
        "tbl_path_hint":    "filter (เว้นว่าง = ทุก path, แสดงสูงสุด 500 rows)",
        "tbl_path_filter":  "กรอง path_id",
        "tbl_path_rows":    "แสดง {shown:,} จาก {total:,} rows",
        "dl_path":          "⬇ ดาวน์โหลด path detail CSV",
        "tbl_asset_detail": "📋 Path × Year × Bucket × Asset detail (recheck logic)",
        "tbl_asset_verify": "**เช็ค logic:** `sum(weighted_contribution)` per (path_id, year, bucket_name) ควรเท่ากับ `sampled_return` ของ bucket นั้นใน Path × Bucket detail",
        "filter_path_id":   "path_id",
        "filter_bucket":    "bucket_name",
        "filter_year":      "year",
        "tbl_asset_rows":   "แสดง {shown:,} จาก {total:,} rows (กรองด้วย filter ด้านบน)",
        "tbl_verify_expander":"🔬 Verification: sum(weighted_contribution) per group",
        "tbl_verify_caption":"เปรียบเทียบ sum_weighted_contribution กับ sampled_return ใน Path × Bucket detail",
        "dl_asset":         "⬇ ดาวน์โหลด asset detail CSV",

        # Diagnostic expander
        "diag_expander":    "🔬 Simulation Diagnostic",
        "diag_run_params":  "**Run parameters**",
        "diag_n_paths":     "จำนวน paths ที่รัน",
        "diag_initial":     "เงินออมเริ่มต้น",
        "diag_total_exp":   "ค่าใช้จ่ายรวม",
        "diag_models":      "**Bucket return models ที่ใช้จริงใน simulation นี้**",
        "diag_zero_std_warn":"⚠️ ไม่มี randomness",
        "diag_zero_std_err":"พบ std_dev = 0 ใน asset บางตัว! ทุก path จะได้ return เดิม — กรุณาแก้ใน Section 2",
        "diag_final_dist":  "**การกระจายตัวของ final_total_balance ทุก path**",
    },

    # ──────────────────────────────────────────────────────
    # PAGE 4  หน้า School Fees Reference
    # ──────────────────────────────────────────────────────
    "p4": {
        "page_title":        "School Fees Reference",
        "title":             "📚 ข้อมูลค่าศึกษาโรงเรียน & มหาวิทยาลัย",
        "caption":           "ข้อมูลอ้างอิงค่าศึกษาปี 2024–2025 (ราคาโดยประมาณ ควรยืนยันกับสถาบันโดยตรง)",

        # Filters
        "filter_header":     "🔍 ค้นหาและกรอง",
        "filter_search":     "ค้นหาชื่อโรงเรียน / มหาวิทยาลัย",
        "filter_country":    "ประเทศ",
        "filter_type":       "ประเภทสถาบัน",
        "filter_level":      "ระดับการศึกษา",
        "filter_all":        "ทั้งหมด",

        # Table columns
        "col_name":          "ชื่อสถาบัน",
        "col_country":       "ประเทศ",
        "col_type":          "ประเภท",
        "col_level":         "ระดับ",
        "col_age_range":     "ช่วงอายุ",
        "col_annual_thb":    "ค่าเล่าเรียน/ปี (฿)",
        "col_original":      "ต้นฉบับ",
        "col_notes":         "หมายเหตุ",
        "col_source_year":   "ปีอ้างอิง",

        # Summary
        "result_count":      "พบ {n} สถาบัน",
        "disclaimer":        "⚠️ ข้อมูลนี้เป็นราคาโดยประมาณเพื่อใช้ในการวางแผนเท่านั้น ราคาจริงอาจแตกต่างกันตามหลักสูตร ค่าธรรมเนียมเพิ่มเติม และปีการศึกษา กรุณาติดต่อสถาบันโดยตรงเพื่อยืนยันราคาที่แน่นอน",
        "back_btn":          "← กลับหน้ากรอกข้อมูล",
        "dl_btn":            "⬇ ดาวน์โหลด CSV",

        # Empty state
        "no_results":        "ไม่พบสถาบันที่ตรงกับเงื่อนไขการค้นหา",
    },

    # ──────────────────────────────────────────────────────
    # VALIDATION WARNINGS / ERRORS
    # ──────────────────────────────────────────────────────
    "warn": {
        "child_name_empty":       "พบชื่อลูกว่างอย่างน้อย 1 รายการ",
        "edu_age_range":          "แผนการศึกษาของ {child} ({level}) มีอายุเริ่มต้นมากกว่าอายุสิ้นสุด",
        "child_extra_year_range": "ค่าใช้จ่ายพิเศษ '{name}' ของ {child} มีปีเริ่มต้นมากกว่าปีสิ้นสุด",
        "child_extra_age_range":  "ค่าใช้จ่ายพิเศษ '{name}' ของ {child} มีอายุเริ่มต้นมากกว่าอายุสิ้นสุด",
        "parent_year_range":      "ค่าใช้จ่ายครอบครัว '{name}' มีปีเริ่มต้นมากกว่าปีสิ้นสุด",
        "hs_age_range":           "อายุเริ่มม.ปลายมากกว่าอายุสิ้นสุดม.ปลาย",
        "negative_contribution":  "ยอดออมรายเดือนติดลบ",
    },
}


# ──────────────────────────────────────────────────────────
# PUBLIC API
# ──────────────────────────────────────────────────────────

def S(page: str, key: str, **fmt) -> str:
    """
    ดึง string จาก _S dict พร้อม format ถ้ามี kwargs

    ตัวอย่าง:
        S("p1", "title")
        S("p1", "child_expander", n=1, name="น้องบี")
        S("warn", "edu_age_range", child="น้องบี", level="อนุบาล")
    """
    val = _S.get(page, {}).get(key, f"[{page}.{key}]")
    if fmt:
        try:
            val = val.format(**fmt)
        except KeyError:
            pass
    return val


def SC(key: str, **fmt) -> str:
    """Shortcut สำหรับ common strings"""
    return S("common", key, **fmt)


# ──────────────────────────────────────────────────────────
# OPTION-LABEL HELPERS  (ใช้เป็น format_func ใน selectbox)
# ──────────────────────────────────────────────────────────

def edu_level_label(level_key: str) -> str:
    """'kindergarten' → 'อนุบาล'"""
    return S("p1", f"edu_level_{level_key}") or level_key


def school_type_label(type_key: str) -> str:
    """'international' → 'นานาชาติ'"""
    return S("p1", f"school_type_{type_key}") or type_key


def expense_type_label(type_key: str) -> str:
    """'one_time' → 'ครั้งเดียว'"""
    return {
        "one_time":  SC("opt_one_time"),
        "recurring": SC("opt_recurring"),
    }.get(type_key, type_key)


def trigger_label(trigger_key: str) -> str:
    """'by_year' → 'กำหนดตามปี'"""
    return {
        "by_year":      SC("opt_by_year"),
        "by_child_age": SC("opt_by_child_age"),
    }.get(trigger_key, trigger_key)


def inflation_label(infl_key: str) -> str:
    """'general' → 'เงินเฟ้อทั่วไป'"""
    return {
        "general":   SC("opt_infl_general"),
        "education": SC("opt_infl_edu"),
        "none":      SC("opt_infl_none"),
    }.get(infl_key, infl_key)


def gender_label(gender_key: str) -> str:
    """'M' → 'ชาย'"""
    return {
        "M":     SC("opt_gender_m"),
        "F":     SC("opt_gender_f"),
        "Other": SC("opt_gender_other"),
    }.get(gender_key, gender_key)


def country_label(country_key: str) -> str:
    """'' → '(ไม่ระบุ)', 'TH' → '🇹🇭 ไทย', 'US' → '🇺🇸 สหรัฐฯ'"""
    return S("p1", f"opt_country_{country_key}") or country_key


def compound_mode_label(mode_key: str) -> str:
    """'yearly' → 'รายปี'"""
    return {
        "yearly":  S("p1", "opt_compound_yearly"),
        "monthly": S("p1", "opt_compound_monthly"),
    }.get(mode_key, mode_key)


def expense_timing_label(timing_key: str) -> str:
    """'end_of_year' → 'ปลายปี'"""
    return {
        "start_of_year": S("p1", "opt_timing_start"),
        "midyear":       S("p1", "opt_timing_mid"),
        "end_of_year":   S("p1", "opt_timing_end"),
    }.get(timing_key, timing_key)
