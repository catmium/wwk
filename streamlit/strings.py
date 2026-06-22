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

        # ── Section 0: Customer ID ──
        "cid_header":        "🆔 รหัสลูกค้า",
        "cid_caption":       "กรุณากรอก cust_id (ตัวเลขเท่านั้น 10 หลักพอดี) — ใช้สำหรับ run simulation และบันทึก/โหลดข้อมูลจากครั้งก่อน",
        "cid_placeholder":   "เช่น 0123456789 (สำหรับทดสอบ)",
        "cid_check_failed":  "ไม่สามารถตรวจสอบข้อมูลก่อนหน้าได้: {error}",
        "cid_prev_found":    "พบข้อมูลก่อนหน้าของ cust_id นี้",
        "cid_last_saved":    " บันทึกล่าสุด: {ts}",
        "cid_btn_import":    "📥 นำเข้าข้อมูลก่อนหน้า",
        "cid_imported":      "นำเข้าข้อมูล {n} ฟิลด์เรียบร้อย กำลังโหลดใหม่…",
        "cid_no_prev":       "ไม่พบข้อมูลก่อนหน้า",
        "cid_import_failed": "ไม่สามารถนำเข้าข้อมูลก่อนหน้าได้: {error}",

        # cust_id validation messages
        "cid_err_empty":     "กรุณากรอก cust_id",
        "cid_err_digits":    "cust_id ต้องเป็นตัวเลข (0–9) เท่านั้น",
        "cid_err_exact":     "cust_id ต้องมี {required} หลักพอดี (กรอกแล้ว {got} หลัก)",
        "cid_err_max":       "cust_id ต้องมีไม่เกิน {max} หลัก (กรอกแล้ว {got} หลัก)",
        "cid_err_min":       "cust_id ต้องมีอย่างน้อย {min} หลัก",

        # cust_id gate at run section
        "cid_gate_info":     "กรุณากรอก cust_id ที่ด้านบนของหน้าก่อนเริ่ม simulation ({error})",

        # Save warning after run
        "save_warn":         "Simulation สำเร็จ แต่ไม่สามารถบันทึกข้อมูลได้: {error}",

        # ── Section 1: Child ──แผนการ
        "sec1_header":       "1) ข้อมูลลูก",
        "sec1_caption":      "ระบุจำนวนลูก แผนการเรียน และค่าใช้จ่ายพิเศษของลูก",
        "metric_n_children": "จำนวนลูก",
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
        "edu_plan_header":   "แผนที่ {n} — {level}",

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

        # School name hybrid widget (selectbox + custom text)
        "label_school_name_custom":      "ระบุชื่อโรงเรียนเอง",
        "placeholder_school_name_custom":"ระบุชื่อโรงเรียน",

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
        "opt_country_FR":   "🇫🇷 ฝรั่งเศส",
        "opt_country_IT":   "🇮🇹 อิตาลี",
        "opt_country_NL":   "🇳🇱 เนเธอร์แลนด์",
        "opt_country_BE":   "🇧🇪 เบลเยียม",
        "opt_country_CH":   "🇨🇭 สวิตเซอร์แลนด์",
        "opt_country_SE":   "🇸🇪 สวีเดน",
        "opt_country_IE":   "🇮🇪 ไอร์แลนด์",
        "opt_country_Other":"🌐 อื่นๆ",

        # Slim expander (growth rate + basis year only)
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
        "parent_card_header":"ค่าใช้จ่ายครอบครัวที่ {n}",

        # ── Section 3: Saving Plan ──
        "sec3_header":           "2) แผนการออมเพื่อการศึกษา",
        "sec3_caption":          "ระบุเงินออมเริ่มต้นและการออมรายเดือน",
        "label_initial_savings": "เงินออมเริ่มต้น (฿)",
        "label_monthly_contrib": "ออมรายเดือน (฿)",
        "metric_n_topups":       "เงินก้อนพิเศษ (topup)",
        "topup_card_header":     "เงินก้อนพิเศษที่ {n}",

        # ── Section 4: Assumptions ──
        "sec4_header":             "3) สมมติฐาน",
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
        "sec5_header":      "4) สร้างแบบจำลอง",
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
        "status_fail":      "⚠️ **แผนการออมไม่เพียงพอ** — ต้องเพิ่มการออมอีก ฿{extra}/เดือน (ต้องออมเงินอย่างน้อย ฿{min_req}/เดือน เพื่อให้แผนนี้เพียงพอ)",
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

        # ── Simulate Assumption expander (interactive re-run) ──
        "assump_expander":      "🧪 ปรับสมมติฐานการจำลอง (ทดลองดูผลแบบ interactive)",
        "assump_caption":       "เปลี่ยนค่าด้านล่างแล้วกด ‘จำลองใหม่’ เพื่อดูผลทันที — ค่าที่ปรับจะถูกบันทึกลงฐานข้อมูลและซิงค์กลับไปยังหน้ากรอกข้อมูลโดยอัตโนมัติ",
        "assump_btn_rerun":     "🔄 จำลองใหม่",
        "assump_rerun_success": "✅ จำลองใหม่สำเร็จ และบันทึกลงฐานข้อมูลแล้ว",
        "assump_rerun_failed":  "❌ จำลองใหม่ล้มเหลว: {error}",

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
        "tables_section_header": "📊 ตารางข้อมูล",
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

        # ── Bucket horizon inputs (R13 — contiguous end-year semantics) ──
        "label_liquidity_end_year": "ปีสิ้นสุดของ Liquidity",
        "label_liquidity_help":     "Liquidity เริ่มที่ปี 1 — เลือกปีสุดท้ายที่ bucket นี้ครอบคลุม",
        "label_stability_end_year": "ปีสิ้นสุดของ Stability",
        "label_stability_help":     "Stability เริ่มอัตโนมัติที่ (ปีสิ้นสุดของ Liquidity + 1) — เลือกปีสุดท้ายที่ bucket นี้ครอบคลุม",
        "bucket_horizon_caption":   "Liquidity: ปี 1–{liq_end} | Stability: ปี {stab_start}–{stab_end} | Growth: ปี {grow_start}–∞ (rolling window — target weight ปรับใหม่ทุกปี)",

        # ── Allocation evolution chart (R6) ──
        "chart_alloc_title":        "**สัดส่วนเงินในแต่ละ Bucket รายปี (P50)**",
        "chart_alloc_caption":      "แสดงสัดส่วนเงินจริงใน Bucket แต่ละปี — จากค่า P50 (median) ของ simulation ทั้งหมด",

        # ── Section 2: Bucket & Asset Config ──
        "sec2_header":      "2) การตั้งค่า Bucket & Asset",
        "sec2_caption":     "โครงสร้าง 3 Bucket ตายตัว — กำหนดระยะเวลาด้านบน แล้วตั้งค่า asset ภายในแต่ละ Bucket",
        "bucket_tbl_header":"**ตั้งค่า Bucket**",
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
        "sec4_header":      "3) ตั้งค่า Monte Carlo",
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
        "sec6_header":      "4) ผลลัพธ์ Monte Carlo",
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
        "chart_sf_year_y":  "โอกาสเงินหมดในปีนี้ (% ของ paths)",
        "chart_cum_exp_caption": "เส้นประสีเทาเข้ม = ค่าใช้จ่ายสะสมรวมทุกปี (บาท)",
        "chart_cum_exp_tooltip": "ค่าใช้จ่ายสะสม (บาท)",
        "chart_seq_risk_title":  "**Sequence-of-returns risk — แบ่งกลุ่มตามผลตอบแทน 3 ปีแรก**",
        "chart_seq_risk_caption":(
            "แบ่ง paths เป็น 3 กลุ่มเท่ากัน (tercile) ตามค่าเฉลี่ย sampled return ใน 3 ปีแรก "
            "แล้วพล็อต median ของยอดเงินรวมทุก bucket — แสดงผลกระทบของ "
            "**ลำดับ** ผลตอบแทนต่อพอร์ตในระยะยาว"
        ),
        "chart_seq_bad":   "ขาลงช่วงต้น (กลุ่มล่าง 1/3)",
        "chart_seq_mid":   "ปานกลาง (กลุ่มกลาง 1/3)",
        "chart_seq_good":  "ขาขึ้นช่วงต้น (กลุ่มบน 1/3)",

        # CAGR / Annualized return distribution
        "chart_cagr_title":   "**ผลตอบแทนต่อปีที่เกิดขึ้นจริง (Annualized Return) — กระจายตัวทุกเส้นทาง**",
        "chart_cagr_caption": (
            "Dollar-weighted return เฉลี่ยต่อปี — ถ่วงน้ำหนักด้วย beginning_balance "
            "ของแต่ละ bucket × ปี (สะท้อนผลตอบแทนจริงบนเงินที่มีอยู่)"
        ),
        "kpi_cagr_p10":      "Pessimistic (P10)",
        "kpi_cagr_p50":      "Median (P50)",
        "kpi_cagr_p90":      "Optimistic (P90)",
        "kpi_cagr_expected": "คาดหวัง (Expected)",
        "kpi_cagr_p50_help": "ค่ากลางของผลตอบแทนต่อปีจาก simulation — Δ เทียบกับค่าคาดหวัง",
        "kpi_cagr_expected_help": (
            "ค่าเฉลี่ย expected return ของ bucket ถ่วงน้ำหนักด้วย initial allocation"
        ),

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

        # ── New visualizations (added) ──
        # Section header
        "viz_extra_header":          "### 🔭 มุมมองเพิ่มเติม",
        "viz_extra_caption":         "ภาพและตารางสรุปเพิ่มเติมเพื่อช่วยให้เห็นความเสี่ยงและกระแสเงินสดในแต่ละปีได้ชัดเจนขึ้น",

        # 1) Fan chart — portfolio total P10/P50/P90 vs year
        "fan_header":                "#### 📈 Fan Chart — เงินคงเหลือรวม (P10 / P50 / P90) ตามปี",
        "fan_caption":               "พื้นที่สีอ่อน = ช่วง P10–P90 (80% ของ simulation), เส้นสีเข้ม = P50 (ค่ากลาง)",
        "fan_y_title":               "ยอดเงินคงเหลือรวมทุกถัง (บาท)",
        "fan_x_title":               "ปี",
        "fan_tt_year":               "ปี",
        "fan_tt_p10":                "กรณีแย่ (P10)",
        "fan_tt_p50":                "กรณีกลาง (P50)",
        "fan_tt_p90":                "กรณีดี (P90)",
        "fan_band_label":            "ช่วง P10–P90",
        "fan_line_label":            "P50",

        # 2) Cashflow summary table (median per year)
        "cf_header":                 "#### 💵 ตารางกระแสเงินสดสรุปรายปี (Median)",
        "cf_caption":                "ค่าทุกตัวเป็น median รายปี — รวมข้ามคอลัมน์อาจไม่ตรงพอดี เพราะ median ของผลรวมไม่เท่ากับผลรวมของ median",
        "cf_col_year":               "ปี",
        "cf_col_contribution":       "เงินสะสม (P50)",
        "cf_col_inv_return":         "ผลตอบแทน (P50)",
        "cf_col_expense":            "ค่าใช้จ่าย (P50)",
        "cf_col_ending":             "ยอดคงเหลือสิ้นปี (P50)",
        "cf_col_sf_prob":            "โอกาสเงินไม่พอ",
        "dl_cashflow":               "⬇ ดาวน์โหลดตารางกระแสเงินสด CSV",

        # 3) Heatmap — shortfall probability bucket × year
        "heat_header":               "#### 🔥 Heatmap โอกาสเงินไม่พอ (ถัง × ปี)",
        "heat_caption":              "สีเข้ม = โอกาสเงินไม่พอสูงในปีนั้น ๆ ของถังนั้น ๆ — ช่วยระบุจุดอ่อนของแผน",
        "heat_x_title":              "ปี",
        "heat_y_title":              "กลุ่มลงทุน",
        "heat_tt_year":              "ปี",
        "heat_tt_bucket":            "กลุ่มลงทุน",
        "heat_tt_prob":              "โอกาสเงินไม่พอ",
        "heat_legend":               "โอกาสเงินไม่พอ",

        # 4) Drawdown distribution
        "dd_header":                 "#### 📉 การกระจายตัวของ Drawdown สูงสุด (per path)",
        "dd_caption":                "Drawdown = % ที่ยอดเงินรวมลดจากจุดสูงสุดที่เคยถึง ก่อนฟื้นกลับ — บอกระดับ downside risk ที่ผู้ลงทุนอาจเจอ",
        "dd_x_title":                "Max Drawdown (%)",
        "dd_y_title":                "จำนวน path",
        "dd_tt_bin":                 "ช่วง",
        "dd_tt_count":               "จำนวน path",
        "dd_kpi_p10":                "P10 (รุนแรงสุด 10%)",
        "dd_kpi_p50":                "Median",
        "dd_kpi_p90":                "P90 (อ่อนสุด 10%)",
        "dd_kpi_worst":              "Drawdown แย่ที่สุด",
        "dd_no_data":                "ไม่มีข้อมูล path detail (เปิด 'เก็บ path × year × bucket detail' ใน MC controls ก่อนรันใหม่)",
    },

    # ──────────────────────────────────────────────────────
    # PAGE 3B  หน้า Investment Planning 2 (Goal-Based MC)
    # ──────────────────────────────────────────────────────
    "p3b": {
        # ── Header ──
        "page_title":          "Investment Planning 2",
        "title":               "🎯 แผนการลงทุนแบบ Goal-Based (Monte Carlo)",
        "caption":             "วางแผนเงินลงทุนเป้าหมายค่าเล่าเรียนแต่ละระดับ — จ่ายเป้าหมายที่ใกล้กว่าก่อน (FIFO) พร้อมเลือกได้ว่า goal ใดเป็น 'จ่ายเท่าที่มี'",

        # ── Sidebar ──
        "sidebar_done":        "### ✅ คำนวณแล้ว",
        "sidebar_done_caption":"เลื่อนลงเพื่อดูผลลัพธ์",
        "btn_back":            "← กลับหน้าจำลองค่าใช้จ่าย",

        # ── Gate ──
        "gate_warn":           "ยังไม่พบผลลัพธ์จากหน้า Expense Simulation — กรุณาไปหน้าก่อนแล้วรัน simulation",

        # ── Section 1 — Plan Context ──
        "sec1_header":         "1) สรุปข้อมูลแผนการศึกษา",
        "ctx_n_goals":         "จำนวนเป้าหมาย",
        "ctx_total_required":  "ค่าใช้จ่ายรวม",
        "ctx_horizon":         "ช่วงเวลา",
        "ctx_horizon_val":     "{start}–{end} ({n} ปี)",
        "ctx_first_due":       "เป้าหมายแรกที่ต้องจ่าย",
        "ctx_first_due_val":   "{label} (ปี {year})",

        # ── Section 2 — Goal Configuration ──
        "sec2_header":         "2) ตั้งค่าเป้าหมายการศึกษา",
        "sec2_caption":        "เลือก 'จ่ายเท่าที่มี' สำหรับเป้าหมายที่ยอมข้ามได้ถ้าเงินไม่พอ (ปกติคือ ป.โท / ป.เอก)",
        "col_goal":            "เป้าหมาย",
        "col_due":             "ปีที่ต้องใช้",
        "col_required":        "เงินที่ต้องใช้รวม",
        "col_skippable":       "จ่ายเท่าที่มี",
        "col_priority":        "ลำดับความสำคัญ",
        "priority_help":       "เลขน้อย = สำคัญกว่า — ใช้เป็น tiebreaker เมื่อปีเริ่มเท่ากัน",

        # ── Section 3 — Portfolio & MC config ──
        "sec3_header":         "3) ตั้งค่าผลตอบแทนและ Monte Carlo",
        "lbl_mean":            "ผลตอบแทนคาดหวังต่อปี (%)",
        "lbl_std":              "ส่วนเบี่ยงเบนมาตรฐาน (%)",
        "lbl_min":             "ผลตอบแทนต่ำสุด (clip, %)",
        "lbl_max":             "ผลตอบแทนสูงสุด (clip, %)",
        "lbl_dist":            "การแจกแจง",
        "opt_dist_normal":     "Normal",
        "opt_dist_t":          "Student-t (df=5)",
        "lbl_n_paths":         "จำนวน path",
        "lbl_seed":            "Random seed",
        "lbl_no_neg_return":   "ไม่คิดดอกเมื่อยอดติดลบ",
        "lbl_fr_threshold":    "เกณฑ์ Funded Ratio (สีเขียว)",
        "lbl_p_threshold":     "เกณฑ์ P(จ่ายเต็ม) (สีเขียว)",

        # ── Section 3 — Asset Allocation + MC (consolidated) ──
        "sec3_caption_new":          "กำหนด asset / น้ำหนักเริ่มต้น / จุด rebalance และพารามิเตอร์ Monte Carlo",
        "dynamic_assets_header":     "**🧱 รายการ Asset (เพิ่ม/ลบได้)**",
        "dynamic_assets_caption":    "กรอกชื่อ asset + ผลตอบแทนคาดหวัง (%) + ความผันผวน (%) — รองรับจำนวน asset เท่าใดก็ได้",
        "col_asset_name":            "สินทรัพย์",
        "col_asset_mean":            "ผลตอบแทนคาดหวัง (%)",
        "col_asset_std":             "ส่วนเบี่ยงเบน (%)",

        # Initial allocation + Rebalance UI
        "initial_allocation_header": "**🎯 Initial Allocation — น้ำหนักเริ่มต้น (ปี {year})**",
        "initial_allocation_caption":"น้ำหนัก (%) ของแต่ละ asset ตั้งแต่ปีเริ่มต้น — จะใช้ค่านี้ไปเรื่อย ๆ จนถึงจุด rebalance ถัดไป (ถ้ามี)",
        "rebalances_header":         "**🔄 จุด Rebalance**",
        "rebalances_caption":        "เพิ่มจุดเปลี่ยนน้ำหนักได้ตามต้องการ — เลือกปี และระบุน้ำหนักใหม่ของแต่ละ asset",
        "btn_add_rebalance":         "➕ เพิ่มจุด Rebalance",
        "rebalance_event_header":    "🔄 Rebalance #{n} — ปี {year}",
        "rebalance_year_label":      "เลือกปี",
        "btn_delete_rebalance":      "🗑 ลบจุดนี้",
        "rebalance_sum_invalid":     "⚠️ Rebalance #{n} (ปี {year}): น้ำหนักต้องรวม 100% (ปัจจุบัน {pct:.1f}%)",
        "initial_sum_invalid":       "⚠️ Initial Allocation: น้ำหนักต้องรวม 100% (ปัจจุบัน {pct:.1f}%)",
        "no_more_years_warn":        "ไม่มีปีที่ว่างให้เพิ่ม rebalance",
        "weights_valid_ok":          "✅ น้ำหนักทุกจุดรวมเป็น 100% — พร้อมคำนวณ",
        "block_run_invalid_weights": "❌ ไม่สามารถคำนวณได้ — กรุณาแก้ไขน้ำหนัก asset ให้รวม 100% ทุกจุดก่อน",
        "no_assets_warn":            "⚠️ ต้องมีอย่างน้อย 1 asset ในรายการ",

        # Schedule visualization
        "glide_chart_header":        "**📉 น้ำหนักสินทรัพย์ตามเวลา (Step-function)**",
        "glide_chart_caption":       "เส้นแสดงน้ำหนักจริงในแต่ละปี — คงที่ระหว่างจุด rebalance",
        "glide_chart_x":             "ปี",
        "glide_chart_y":             "น้ำหนัก",
        "asset_cash_name":           "เงินสด/เงินฝาก",
        "asset_bond_name":           "ตราสารหนี้",
        "asset_thst_name":           "หุ้นไทย",
        "asset_glst_name":           "หุ้นต่างประเทศ",

        # MC sub-section
        "mc_subheader":              "**⚙️ พารามิเตอร์ Monte Carlo**",

        # ── Section 6 — Diagnostic Output Table ──
        "sec6_header":               "6) ตารางตรวจสอบ Logic (Diagnostic)",
        "sec6_caption":              "ตารางสรุปต่อปีสำหรับตรวจสอบความถูกต้องของ engine — แสดง median ของทุก path",
        "diag_col_year":             "ปี",
        "diag_col_contribution":     "เงินใส่ปลายปี",
        "diag_col_return_p50":       "Return (median, %)",
        "diag_col_portfolio_p10":    "Portfolio P10",
        "diag_col_portfolio_p50":    "Portfolio P50",
        "diag_col_portfolio_p90":    "Portfolio P90",
        "diag_col_required":         "ต้องจ่ายรวม",
        "diag_col_paid_p50":         "จ่ายจริง (median)",
        "diag_col_shortfall_p50":    "ขาด (median)",
        "diag_weights_header":       "**🧪 น้ำหนัก asset ที่ใช้แต่ละปี (เฉพาะโหมด Multi-Asset)**",

        # ── Section 7 — Cashflow Summary (median per year) ──
        "sec7_header":               "7) สรุป Cashflow รายปี (median)",
        "sec7_caption":              "สรุปการไหลของเงินในแต่ละปี โดยใช้ค่า median ของทุก path — หมายเหตุ: ค่า median ของแต่ละคอลัมน์มาจากคนละ path กัน จึงไม่บวกลบเท่ากันเป๊ะ (ยอดสิ้นปี ≠ ยอดต้นปี + ผลตอบแทน + เงินใส่ − จ่ายค่าเล่าเรียน เสมอ)",
        "cf_col_year":               "ปี",
        "cf_col_beginning":          "ยอดต้นปี (median)",
        "cf_col_growth":             "ผลตอบแทน (median)",
        "cf_col_contribution":       "เงินใส่",
        "cf_col_payment":            "จ่ายค่าเล่าเรียน (median)",
        "cf_col_ending":             "ยอดสิ้นปี (median)",

        # ── Section 4 — Run ──
        "sec4_header":         "4) คำนวณ",
        "btn_run":             "🚀 คำนวณ Monte Carlo",
        "btn_solve":           "🧮 หาเงินรายเดือนขั้นต่ำ (เป้าหมายอ่อนสุด FR≥1.0)",
        "running":             "กำลังคำนวณ...",
        "solving":             "กำลังหาเงินรายเดือนขั้นต่ำ...",
        "solve_result":        "เงินรายเดือนขั้นต่ำที่จำเป็น: **฿{amount:,.0f}/เดือน** (เพื่อให้ median FR ของเป้าหมายอ่อนสุด ≥ {target:.0%})",
        "solve_unreachable":   "ไม่สามารถบรรลุเป้าหมายได้แม้จะใส่เงินสูงสุด ({hi:,.0f}/เดือน) — ลองลดจำนวน goal, ลดต้นทุน, หรือเปลี่ยน skippable",

        # ── Section 5 — Results ──
        "sec5_header":         "5) ผลลัพธ์",
        "kpi_passed":          "เป้าหมายที่ผ่าน",
        "kpi_passed_val":      "{passed} จาก {total}",
        "kpi_avg_fr":          "Funded Ratio เฉลี่ย (median)",
        "kpi_worst_goal":      "เป้าหมายอ่อนสุด",
        "kpi_total_required":  "เงินที่ต้องใช้รวม",

        "goals_table_header":  "### 📊 สรุปสถานะแต่ละเป้าหมาย",
        "tbl_status":          "สถานะ",
        "tbl_goal":            "เป้าหมาย",
        "tbl_due":             "ปีที่ใช้",
        "tbl_fr_median":       "Funded Ratio (median)",
        "tbl_fr_range":        "FR (P10–P90)",
        "tbl_p_funded":        "P(จ่ายเต็ม)",
        "tbl_shortfall_p10":   "ขาด (worst, P10)",

        "light_green":         "🟢 ผ่าน",
        "light_yellow":        "🟡 เสี่ยง",
        "light_red":           "🔴 ไม่ผ่าน",

        "chart_fr_header":     "### 📈 Funded Ratio ของแต่ละเป้าหมาย",
        "chart_fr_caption":    "แท่งแสดง median FR; เส้นแสดงช่วง P10–P90 ของ FR",
        "chart_pv_header":     "### 💰 มูลค่า Portfolio ตลอดช่วงเวลา (P10/P50/P90)",
        "chart_pv_caption":    "พื้นที่สีอ่อน = ช่วง P10–P90; เส้นกลาง = median",
        "chart_liq_header":    "### 📅 เงินที่ต้องจ่ายในแต่ละปี (เรียงตาม FIFO)",
        "chart_liq_caption":   "แท่งแสดงเงินที่จ่ายจริง (median) ต่อปี ต่อเป้าหมาย",

        # ── Status / errors ──
        "stale_warn":          "ค่าที่กรอกเปลี่ยนแล้ว — กดคำนวณใหม่",
        "no_goals":            "ไม่พบเป้าหมายการศึกษา — กรุณาเพิ่มแผนการศึกษาในหน้ากรอกข้อมูล",
        "result_empty":        "ยังไม่ได้คำนวณ — กดปุ่ม '🚀 คำนวณ Monte Carlo'",
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
        "edu_age_overlap":        "ช่วงอายุของระดับ '{level_a}' ({start_a}-{end_a}) และ '{level_b}' ({start_b}-{end_b}) ของ {child} ซ้อนทับกัน — กรุณาปรับช่วงอายุให้ไม่ทับกันก่อน simulate",
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
