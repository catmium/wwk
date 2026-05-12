import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import pandas as pd

from strings import S

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title=S("p4", "page_title"),
    page_icon="📚",
    layout="wide",
)

# ============================================================
# SCHOOL FEES DATASET
# ============================================================
# Columns: name, country, type, level, age_min, age_max,
#          annual_thb, original_amount, original_currency,
#          notes, source_year, ref_url

_DATA = [
    # ──────────────────────────────────────────────────────────────────────────
    # INTERNATIONAL SCHOOLS — THAILAND
    # ──────────────────────────────────────────────────────────────────────────

    # ISB
    ("ISB – International School Bangkok",         "TH", "นานาชาติ", "อนุบาล",     3,  5,    640_000, 640_000,   "THB", "Nursery–KG; ปีการศึกษา 2025/26",              2025, "https://www.isb.ac.th"),
    ("ISB – International School Bangkok",         "TH", "นานาชาติ", "ประถมศึกษา", 6,  11,   985_000, 985_000,   "THB", "Grade 1–5; ปีการศึกษา 2025/26",               2025, "https://www.isb.ac.th"),
    ("ISB – International School Bangkok",         "TH", "นานาชาติ", "มัธยมต้น",   12, 14, 1_085_000, 1_085_000, "THB", "Grade 6–8; ปีการศึกษา 2025/26",               2025, "https://www.isb.ac.th"),
    ("ISB – International School Bangkok",         "TH", "นานาชาติ", "มัธยมปลาย",  15, 18, 1_175_000, 1_175_000, "THB", "Grade 9–12; ปีการศึกษา 2025/26",              2025, "https://www.isb.ac.th"),

    # NIST
    ("NIST International School",                  "TH", "นานาชาติ", "อนุบาล",     3,  5,    550_000, 550_000,   "THB", "Early Years; ประมาณการ 2024/25",               2024, "https://www.nist.ac.th"),
    ("NIST International School",                  "TH", "นานาชาติ", "ประถมศึกษา", 6,  11,   720_000, 720_000,   "THB", "Primary; ประมาณการ 2024/25",                   2024, "https://www.nist.ac.th"),
    ("NIST International School",                  "TH", "นานาชาติ", "มัธยมต้น",   12, 14,   820_000, 820_000,   "THB", "MYP; ประมาณการ 2024/25",                       2024, "https://www.nist.ac.th"),
    ("NIST International School",                  "TH", "นานาชาติ", "มัธยมปลาย",  15, 18,   870_000, 870_000,   "THB", "IB Diploma; ประมาณการ 2024/25",                2024, "https://www.nist.ac.th"),

    # Bangkok Patana
    ("Bangkok Patana School",                      "TH", "นานาชาติ", "อนุบาล",     3,  5,    540_000, 540_000,   "THB", "Early Years; 2024/25",                         2024, "https://www.patana.ac.th"),
    ("Bangkok Patana School",                      "TH", "นานาชาติ", "ประถมศึกษา", 6,  11,   710_000, 710_000,   "THB", "Primary; 2024/25",                             2024, "https://www.patana.ac.th"),
    ("Bangkok Patana School",                      "TH", "นานาชาติ", "มัธยมต้น",   12, 14,   800_000, 800_000,   "THB", "Secondary Y7–9; 2024/25",                      2024, "https://www.patana.ac.th"),
    ("Bangkok Patana School",                      "TH", "นานาชาติ", "มัธยมปลาย",  15, 18,   945_000, 945_000,   "THB", "Sixth Form IB; 2024/25",                       2024, "https://www.patana.ac.th"),

    # Harrow Bangkok
    ("Harrow International School Bangkok",        "TH", "นานาชาติ", "อนุบาล",     3,  5,    650_000, 650_000,   "THB", "Early Years; ประมาณการ 2024/25",               2024, "https://www.harrowschool.ac.th"),
    ("Harrow International School Bangkok",        "TH", "นานาชาติ", "ประถมศึกษา", 6,  11,   850_000, 850_000,   "THB", "Junior School; ประมาณการ 2024/25",             2024, "https://www.harrowschool.ac.th"),
    ("Harrow International School Bangkok",        "TH", "นานาชาติ", "มัธยมต้น",   12, 14,   980_000, 980_000,   "THB", "Senior School; ประมาณการ 2024/25",             2024, "https://www.harrowschool.ac.th"),
    ("Harrow International School Bangkok",        "TH", "นานาชาติ", "มัธยมปลาย",  15, 18, 1_100_000, 1_100_000, "THB", "Sixth Form; ประมาณการ 2024/25",               2024, "https://www.harrowschool.ac.th"),

    # Rugby School Thailand
    ("Rugby School Thailand",                      "TH", "นานาชาติ", "อนุบาล",     3,  5,    480_000, 480_000,   "THB", "Prep School; ประมาณการ 2024/25",               2024, "https://www.rugbyschoolthailand.com"),
    ("Rugby School Thailand",                      "TH", "นานาชาติ", "ประถมศึกษา", 6,  11,   670_000, 670_000,   "THB", "Junior; ประมาณการ 2024/25",                    2024, "https://www.rugbyschoolthailand.com"),
    ("Rugby School Thailand",                      "TH", "นานาชาติ", "มัธยมปลาย",  15, 18,   900_000, 900_000,   "THB", "Senior + A-Level; ประมาณการ 2024/25",          2024, "https://www.rugbyschoolthailand.com"),

    # Shrewsbury
    ("Shrewsbury International School",            "TH", "นานาชาติ", "อนุบาล",     3,  5,    500_000, 500_000,   "THB", "Early Years; ประมาณการ 2024/25",               2024, "https://www.shrewsbury.ac.th"),
    ("Shrewsbury International School",            "TH", "นานาชาติ", "ประถมศึกษา", 6,  11,   710_000, 710_000,   "THB", "Junior; ประมาณการ 2024/25",                    2024, "https://www.shrewsbury.ac.th"),
    ("Shrewsbury International School",            "TH", "นานาชาติ", "มัธยมต้น",   12, 14,   820_000, 820_000,   "THB", "Senior; ประมาณการ 2024/25",                    2024, "https://www.shrewsbury.ac.th"),
    ("Shrewsbury International School",            "TH", "นานาชาติ", "มัธยมปลาย",  15, 18,   950_000, 950_000,   "THB", "Sixth Form IB/A-Level; ประมาณการ",             2024, "https://www.shrewsbury.ac.th"),

    # Wells
    ("Wells International School",                 "TH", "นานาชาติ", "ประถมศึกษา", 6,  11,   400_000, 400_000,   "THB", "ประมาณการ 2024/25",                            2024, "https://www.wells.ac.th"),
    ("Wells International School",                 "TH", "นานาชาติ", "มัธยมต้น",   12, 14,   450_000, 450_000,   "THB", "ประมาณการ 2024/25",                            2024, "https://www.wells.ac.th"),
    ("Wells International School",                 "TH", "นานาชาติ", "มัธยมปลาย",  15, 18,   500_000, 500_000,   "THB", "ประมาณการ 2024/25",                            2024, "https://www.wells.ac.th"),

    # St. Andrews
    ("St. Andrews International School BKK",       "TH", "นานาชาติ", "อนุบาล",     3,  5,    380_000, 380_000,   "THB", "Early Years; ประมาณการ 2024/25",               2024, "https://www.standrews.ac.th"),
    ("St. Andrews International School BKK",       "TH", "นานาชาติ", "ประถมศึกษา", 6,  11,   500_000, 500_000,   "THB", "Primary; ประมาณการ 2024/25",                   2024, "https://www.standrews.ac.th"),
    ("St. Andrews International School BKK",       "TH", "นานาชาติ", "มัธยมปลาย",  15, 18,   620_000, 620_000,   "THB", "Secondary; ประมาณการ 2024/25",                 2024, "https://www.standrews.ac.th"),

    # KIS
    ("KIS International School",                   "TH", "นานาชาติ", "อนุบาล",     3,  5,    330_000, 330_000,   "THB", "ประมาณการ 2024/25",                            2024, "https://www.kis.ac.th"),
    ("KIS International School",                   "TH", "นานาชาติ", "ประถมศึกษา", 6,  11,   440_000, 440_000,   "THB", "ประมาณการ 2024/25",                            2024, "https://www.kis.ac.th"),
    ("KIS International School",                   "TH", "นานาชาติ", "มัธยมปลาย",  15, 18,   560_000, 560_000,   "THB", "ประมาณการ 2024/25",                            2024, "https://www.kis.ac.th"),

    # SIS Bangkok — ตั้งอยู่ในไทย (ประเทศ = TH)
    ("Singapore International School (BKK)",       "TH", "นานาชาติ", "ประถมศึกษา", 6,  11,   260_000, 260_000,   "THB", "SIS Bangkok; หลักสูตรสิงคโปร์ ประมาณการ 2024/25", 2024, "https://www.sisb.ac.th"),
    ("Singapore International School (BKK)",       "TH", "นานาชาติ", "มัธยมปลาย",  15, 18,   364_000, 364_000,   "THB", "SIS Bangkok; หลักสูตรสิงคโปร์ ประมาณการ 2024/25", 2024, "https://www.sisb.ac.th"),

    # ──────────────────────────────────────────────────────────────────────────
    # THAI PRIVATE SCHOOLS
    # ──────────────────────────────────────────────────────────────────────────

    ("Assumption College (อัสสัมชัญ)",             "TH", "เอกชน",    "ประถมศึกษา", 6,  11,    60_000, 60_000,    "THB", "โรงเรียนคาทอลิกชาย; ประมาณการ 2024",          2024, "https://www.assumption.ac.th"),
    ("Assumption College (อัสสัมชัญ)",             "TH", "เอกชน",    "มัธยมต้น",   12, 14,    70_000, 70_000,    "THB", "ประมาณการ 2024",                               2024, "https://www.assumption.ac.th"),
    ("Assumption College (อัสสัมชัญ)",             "TH", "เอกชน",    "มัธยมปลาย",  15, 18,    80_000, 80_000,    "THB", "ประมาณการ 2024",                               2024, "https://www.assumption.ac.th"),

    ("Sacred Heart Convent (เซนต์โยเซฟ)",          "TH", "เอกชน",    "ประถมศึกษา", 6,  11,    50_000, 50_000,    "THB", "โรงเรียนคาทอลิกหญิง; ประมาณการ 2024",         2024, "https://www.shconvent.ac.th"),
    ("Sacred Heart Convent (เซนต์โยเซฟ)",          "TH", "เอกชน",    "มัธยมต้น",   12, 14,    60_000, 60_000,    "THB", "ประมาณการ 2024",                               2024, "https://www.shconvent.ac.th"),
    ("Sacred Heart Convent (เซนต์โยเซฟ)",          "TH", "เอกชน",    "มัธยมปลาย",  15, 18,    65_000, 65_000,    "THB", "ประมาณการ 2024",                               2024, "https://www.shconvent.ac.th"),

    ("KVIS – Kamnoetvidya Science Academy",         "TH", "เอกชน",    "มัธยมปลาย",  15, 18,   180_000, 180_000,   "THB", "โรงเรียนวิทย์ PTT; ประมาณการ 2024",           2024, "https://www.kvis.ac.th"),

    ("Denla British School",                        "TH", "เอกชน",    "อนุบาล",     3,  5,    200_000, 200_000,   "THB", "ประมาณการ 2024/25",                            2024, "https://www.denlabritish.com"),
    ("Denla British School",                        "TH", "เอกชน",    "ประถมศึกษา", 6,  11,   300_000, 300_000,   "THB", "ประมาณการ 2024/25",                            2024, "https://www.denlabritish.com"),
    ("Denla British School",                        "TH", "เอกชน",    "มัธยมต้น",   12, 14,   350_000, 350_000,   "THB", "ประมาณการ 2024/25",                            2024, "https://www.denlabritish.com"),
    ("Denla British School",                        "TH", "เอกชน",    "มัธยมปลาย",  15, 18,   400_000, 400_000,   "THB", "ประมาณการ 2024/25",                            2024, "https://www.denlabritish.com"),

    # ──────────────────────────────────────────────────────────────────────────
    # THAI GOVERNMENT SCHOOLS
    # ──────────────────────────────────────────────────────────────────────────

    ("Triam Udom Suksa (เตรียมอุดมศึกษา)",         "TH", "รัฐบาล",   "มัธยมปลาย",  15, 18,     5_000, 5_000,     "THB", "โรงเรียนรัฐบาลชั้นนำ; ค่าเล่าเรียนต่ำมาก",   2024, "https://www.triamudom.ac.th"),
    ("Mahidol Wittayanusorn (มหิดลวิทยานุสรณ์)",   "TH", "รัฐบาล",   "มัธยมปลาย",  15, 18,    12_000, 12_000,    "THB", "โรงเรียนวิทยาศาสตร์ชั้นนำ; ค่าเล่าเรียนต่ำ", 2024, "https://www.mwit.ac.th"),

    # ──────────────────────────────────────────────────────────────────────────
    # THAI UNIVERSITIES — หลักสูตรภาษาไทย
    # ──────────────────────────────────────────────────────────────────────────

    ("จุฬาลงกรณ์มหาวิทยาลัย (หลักสูตรไทย)",       "TH", "รัฐบาล",   "ปริญญาตรี",  18, 22,    30_000, 30_000,    "THB", "ค่าเล่าเรียนเฉลี่ยต่อปี; ประมาณการ 2024",    2024, "https://www.chula.ac.th"),
    ("มหาวิทยาลัยมหิดล (หลักสูตรไทย)",            "TH", "รัฐบาล",   "ปริญญาตรี",  18, 22,    35_000, 35_000,    "THB", "ค่าเล่าเรียนเฉลี่ยต่อปี; ประมาณการ 2024",    2024, "https://www.mahidol.ac.th"),
    ("มหาวิทยาลัยธรรมศาสตร์ (หลักสูตรไทย)",       "TH", "รัฐบาล",   "ปริญญาตรี",  18, 22,    25_000, 25_000,    "THB", "ค่าเล่าเรียนเฉลี่ยต่อปี; ประมาณการ 2024",    2024, "https://www.tu.ac.th"),
    ("มหาวิทยาลัยเกษตรศาสตร์ (หลักสูตรไทย)",      "TH", "รัฐบาล",   "ปริญญาตรี",  18, 22,    22_000, 22_000,    "THB", "ค่าเล่าเรียนเฉลี่ยต่อปี; ประมาณการ 2024",    2024, "https://www.ku.ac.th"),
    ("มหาวิทยาลัยขอนแก่น (หลักสูตรไทย)",          "TH", "รัฐบาล",   "ปริญญาตรี",  18, 22,    20_000, 20_000,    "THB", "ค่าเล่าเรียนเฉลี่ยต่อปี; ประมาณการ 2024",    2024, "https://www.kku.ac.th"),
    ("มหาวิทยาลัยเชียงใหม่ (หลักสูตรไทย)",        "TH", "รัฐบาล",   "ปริญญาตรี",  18, 22,    22_000, 22_000,    "THB", "ค่าเล่าเรียนเฉลี่ยต่อปี; ประมาณการ 2024",    2024, "https://www.cmu.ac.th"),

    # Thai universities — international programs
    ("MUIC – Mahidol Univ. International College", "TH", "รัฐบาล",   "ปริญญาตรี",  18, 22,   600_000, 600_000,   "THB", "หลักสูตรนานาชาติ; ประมาณการ 2024/25",         2024, "https://muic.mahidol.ac.th"),
    ("MUIC – Mahidol Univ. International College", "TH", "รัฐบาล",   "ปริญญาโท",   23, 24,   660_000, 660_000,   "THB", "หลักสูตรนานาชาติ; ประมาณการ 2024/25",         2024, "https://muic.mahidol.ac.th"),
    ("CU – Chulalongkorn Intl Programs",           "TH", "รัฐบาล",   "ปริญญาตรี",  18, 22,   540_000, 540_000,   "THB", "หลักสูตรนานาชาติ; ประมาณการ 2024/25",         2024, "https://www.inter.chula.ac.th"),
    ("ABAC – Assumption Univ. (Intl)",             "TH", "เอกชน",    "ปริญญาตรี",  18, 22,   220_000, 220_000,   "THB", "หลักสูตรนานาชาติ; ประมาณการ 2024/25",         2024, "https://www.au.edu"),
    ("Bangkok Univ. (Intl Program)",               "TH", "เอกชน",    "ปริญญาตรี",  18, 22,   180_000, 180_000,   "THB", "หลักสูตรนานาชาติ; ประมาณการ 2024/25",         2024, "https://www.bu.ac.th"),

    # ──────────────────────────────────────────────────────────────────────────
    # OVERSEAS — UNITED STATES
    # ──────────────────────────────────────────────────────────────────────────

    ("MIT / Harvard / Stanford (Top 5 US)",        "US", "มหาวิทยาลัยต่างประเทศ", "ปริญญาตรี",  18, 22, 2_450_000, 70_000,  "USD", "ค่าเล่าเรียน+ค่าครองชีพ; USD 70k/yr × 35 THB", 2024, "https://college.harvard.edu/financial-aid/tuition-fees"),
    ("UC Berkeley / UCLA (UC System)",             "US", "มหาวิทยาลัยต่างประเทศ", "ปริญญาตรี",  18, 22, 1_680_000, 48_000,  "USD", "ต่างรัฐ; ค่าเล่าเรียน+ค่าครองชีพ",            2024, "https://admission.universityofcalifornia.edu/tuition-financial-aid/"),
    ("State University (In-State US)",             "US", "มหาวิทยาลัยต่างประเทศ", "ปริญญาตรี",  18, 22,   875_000, 25_000,  "USD", "ในรัฐ; ค่าเล่าเรียน+ค่าครองชีพ",              2024, "https://bigfuture.collegeboard.org/pay-for-college/college-costs/college-costs-calculator"),
    ("Top US MBA (Harvard/Wharton/Booth)",         "US", "มหาวิทยาลัยต่างประเทศ", "ปริญญาโท",   23, 25, 2_800_000, 80_000,  "USD", "MBA 2 ปี; รวมค่าครองชีพ",                      2024, "https://www.hbs.edu/mba/financial-aid/Pages/tuition.aspx"),
    ("US Top-10 Master's Program",                 "US", "มหาวิทยาลัยต่างประเทศ", "ปริญญาโท",   23, 24, 2_100_000, 60_000,  "USD", "1–2 ปี; รวมค่าครองชีพ",                        2024, "https://www.usnews.com/best-graduate-schools"),
    ("US Community College → Transfer",           "US", "มหาวิทยาลัยต่างประเทศ", "ปริญญาตรี",  18, 22,   490_000, 14_000,  "USD", "2+2 pathway; ค่าเล่าเรียนเฉลี่ย",              2024, "https://bigfuture.collegeboard.org"),

    # ──────────────────────────────────────────────────────────────────────────
    # OVERSEAS — UNITED KINGDOM
    # ──────────────────────────────────────────────────────────────────────────

    ("Oxford / Cambridge / LSE",                   "UK", "มหาวิทยาลัยต่างประเทศ", "ปริญญาตรี",  18, 21, 1_380_000, 30_000,  "GBP", "ต่างชาติ; ค่าเล่าเรียน GBP 30k + ค่าครองชีพ", 2024, "https://www.ox.ac.uk/admissions/undergraduate/fees-and-funding/tuition-fees"),
    ("UK Russell Group (Top 24)",                  "UK", "มหาวิทยาลัยต่างประเทศ", "ปริญญาตรี",  18, 21,   920_000, 20_000,  "GBP", "ค่าเล่าเรียน GBP 20k + ค่าครองชีพ",           2024, "https://www.russellgroup.ac.uk"),
    ("UK Top MBA (LBS / Oxford Saïd)",             "UK", "มหาวิทยาลัยต่างประเทศ", "ปริญญาโท",   23, 24, 1_840_000, 40_000,  "GBP", "1 ปี MBA; ค่าเล่าเรียน GBP 40k",               2024, "https://www.london.edu/programmes/mba"),
    ("UK A-Level / Sixth Form College",            "UK", "นานาชาติ",               "มัธยมปลาย",  16, 18,   920_000, 20_000,  "GBP", "2 ปี A-Level; ค่าเล่าเรียน GBP 20k/yr",        2024, "https://www.ucas.com"),

    # ──────────────────────────────────────────────────────────────────────────
    # OVERSEAS — AUSTRALIA
    # ──────────────────────────────────────────────────────────────────────────

    ("ANU / Melbourne / Sydney (Go8)",             "AU", "มหาวิทยาลัยต่างประเทศ", "ปริญญาตรี",  18, 22,   990_000, 45_000,  "AUD", "AUD 45k/yr × 22 THB + ค่าครองชีพ",             2024, "https://www.anu.edu.au/study/fees"),
    ("Non-Go8 Australian University",              "AU", "มหาวิทยาลัยต่างประเทศ", "ปริญญาตรี",  18, 22,   700_000, 32_000,  "AUD", "AUD 32k/yr + ค่าครองชีพ; ประมาณการ",          2024, "https://www.studyaustralia.gov.au/en/plan-your-studies/fees-and-costs"),
    ("Australian Master's (1–2 yr)",               "AU", "มหาวิทยาลัยต่างประเทศ", "ปริญญาโท",   23, 24,   880_000, 40_000,  "AUD", "AUD 40k/yr × 22 THB",                           2024, "https://www.studyaustralia.gov.au/en/plan-your-studies/fees-and-costs"),
    ("Australian High School (Yr 11–12)",          "AU", "นานาชาติ",               "มัธยมปลาย",  16, 18,   616_000, 28_000,  "AUD", "AUD 28k/yr รวมค่าที่พัก",                       2024, "https://www.studyaustralia.gov.au"),
    ("Australian Secondary (Yr 8–10)",             "AU", "นานาชาติ",               "มัธยมต้น",   13, 15,   528_000, 24_000,  "AUD", "AUD 24k/yr รวมค่าที่พัก",                       2024, "https://www.studyaustralia.gov.au"),

    # ──────────────────────────────────────────────────────────────────────────
    # OVERSEAS — SINGAPORE
    # ──────────────────────────────────────────────────────────────────────────

    ("NUS / NTU (National Universities SG)",       "SG", "มหาวิทยาลัยต่างประเทศ", "ปริญญาตรี",  18, 22,   625_000, 24_000,  "SGD", "SGD 24k/yr × 26 THB; ต่างชาติ",                2024, "https://www.nus.edu.sg/registrar/administrative-policies-procedures/undergraduate/financial-matters/tuition-fees"),
    ("SMU – Singapore Management Univ.",           "SG", "มหาวิทยาลัยต่างประเทศ", "ปริญญาตรี",  18, 22,   676_000, 26_000,  "SGD", "SGD 26k/yr × 26 THB; ต่างชาติ",                2024, "https://www.smu.edu.sg/admissions/fees-scholarships/fees"),
    ("NUS / NTU MBA",                              "SG", "มหาวิทยาลัยต่างประเทศ", "ปริญญาโท",   23, 24,   780_000, 30_000,  "SGD", "SGD 30k/yr × 26 THB",                           2024, "https://bschool.nus.edu.sg/mba/"),
    ("United World College South East Asia (SG)",  "SG", "นานาชาติ",               "มัธยมต้น",   12, 14,   780_000, 30_000,  "SGD", "UWCSEA; SGD 30k/yr × 26 THB",                   2024, "https://www.uwcsea.edu.sg"),
    ("United World College South East Asia (SG)",  "SG", "นานาชาติ",               "มัธยมปลาย",  15, 18,   910_000, 35_000,  "SGD", "UWCSEA IB Diploma; SGD 35k/yr × 26 THB",        2024, "https://www.uwcsea.edu.sg"),

    # ──────────────────────────────────────────────────────────────────────────
    # OVERSEAS — JAPAN
    # ──────────────────────────────────────────────────────────────────────────

    ("University of Tokyo / Kyoto (National JP)",  "JP", "มหาวิทยาลัยต่างประเทศ", "ปริญญาตรี",  18, 22,   200_000, 535_800,  "JPY", "¥535,800/yr × 0.23 THB; ค่าเล่าเรียนเท่ากับนักศึกษาญี่ปุ่น", 2024, "https://www.u-tokyo.ac.jp/en/admissions/index.html"),
    ("Waseda / Keio (Private JP)",                 "JP", "มหาวิทยาลัยต่างประเทศ", "ปริญญาตรี",  18, 22,   300_000, 1_300_000,"JPY", "¥1.3M/yr × 0.23 THB; เอกชน",                   2024, "https://www.waseda.jp/top/en"),
    ("Japan Master's (National University)",       "JP", "มหาวิทยาลัยต่างประเทศ", "ปริญญาโท",   23, 25,   220_000, 950_000,  "JPY", "¥950k/yr × 0.23 THB",                           2024, "https://www.jasso.or.jp/en/"),
    ("Japan High School (Public)",                 "JP", "รัฐบาล",                 "มัธยมปลาย",  16, 18,   100_000, 430_000,  "JPY", "¥430k/yr รวมค่าครองชีพเบื้องต้น",               2024, "https://www.mext.go.jp/en/"),
    ("Japan High School (Private International)",  "JP", "เอกชน",                  "มัธยมปลาย",  16, 18,   350_000, 1_500_000,"JPY", "¥1.5M/yr × 0.23 THB",                           2024, "https://www.jasso.or.jp/en/"),

    # ──────────────────────────────────────────────────────────────────────────
    # OVERSEAS — GERMANY
    # ──────────────────────────────────────────────────────────────────────────

    ("LMU / TU Munich / Heidelberg",               "DE", "มหาวิทยาลัยต่างประเทศ", "ปริญญาตรี",  18, 22,   490_000, 14_000,  "EUR", "ค่าเล่าเรียนต่ำมาก + ค่าครองชีพ EUR 14k/yr × 35 THB", 2024, "https://www.studying-in-germany.org/tuition-fees-germany/"),
    ("Germany Master's (Eng. / MBA)",              "DE", "มหาวิทยาลัยต่างประเทศ", "ปริญญาโท",   23, 25,   525_000, 15_000,  "EUR", "รวมค่าครองชีพ; ค่าเล่าเรียนต่ำมาก",              2024, "https://www.studying-in-germany.org/tuition-fees-germany/"),

    # ──────────────────────────────────────────────────────────────────────────
    # OVERSEAS — CHINA
    # Exchange rate: 1 CNY ≈ 4.8 THB
    # ──────────────────────────────────────────────────────────────────────────

    ("Peking University / Tsinghua (Top CN)",      "CN", "มหาวิทยาลัยต่างประเทศ", "ปริญญาตรี",  18, 22,   340_000, 70_833,  "CNY", "¥70,833/yr (~¥30k ค่าเรียน + ¥40k ครองชีพ) × 4.8", 2024, "https://www.campuschina.org"),
    ("Fudan / Zhejiang / SJTU (National CN)",      "CN", "มหาวิทยาลัยต่างประเทศ", "ปริญญาตรี",  18, 22,   280_000, 58_333,  "CNY", "¥58,333/yr รวมค่าครองชีพ × 4.8 THB",            2024, "https://www.campuschina.org"),
    ("Top CN University MBA (CEIBS/PKU/THU)",      "CN", "มหาวิทยาลัยต่างประเทศ", "ปริญญาโท",   23, 25,   380_000, 79_167,  "CNY", "¥79,167/yr รวมค่าครองชีพ × 4.8 THB",            2024, "https://www.ceibs.edu"),
    ("China Master's (National University)",       "CN", "มหาวิทยาลัยต่างประเทศ", "ปริญญาโท",   23, 25,   250_000, 52_083,  "CNY", "¥52,083/yr รวมค่าครองชีพ × 4.8 THB",            2024, "https://www.campuschina.org"),

    # International schools in China (fees in USD; 1 USD ≈ 35 THB)
    ("Western Academy of Beijing (WAB)",           "CN", "นานาชาติ",               "ประถมศึกษา", 6,  11,   700_000, 20_000,  "USD", "USD 20k/yr × 35 THB; โรงเรียนนานาชาติในปักกิ่ง", 2024, "https://www.wab.edu"),
    ("Western Academy of Beijing (WAB)",           "CN", "นานาชาติ",               "มัธยมต้น",   12, 14,   840_000, 24_000,  "USD", "USD 24k/yr × 35 THB",                            2024, "https://www.wab.edu"),
    ("Western Academy of Beijing (WAB)",           "CN", "นานาชาติ",               "มัธยมปลาย",  15, 18,   980_000, 28_000,  "USD", "USD 28k/yr × 35 THB; IB Diploma",                2024, "https://www.wab.edu"),
    ("Shanghai American School (SAS)",             "CN", "นานาชาติ",               "ประถมศึกษา", 6,  11,   770_000, 22_000,  "USD", "USD 22k/yr × 35 THB; โรงเรียนนานาชาติในเซี่ยงไฮ้", 2024, "https://www.saschina.org"),
    ("Shanghai American School (SAS)",             "CN", "นานาชาติ",               "มัธยมปลาย",  15, 18, 1_050_000, 30_000,  "USD", "USD 30k/yr × 35 THB",                            2024, "https://www.saschina.org"),
]

_COLS = [
    "ชื่อสถาบัน", "ประเทศ", "ประเภท", "ระดับ",
    "อายุต่ำสุด", "อายุสูงสุด",
    "ค่าเล่าเรียน/ปี (฿)", "ราคาต้นฉบับ", "สกุลเงินต้นฉบับ",
    "หมายเหตุ", "ปีอ้างอิง", "เว็บไซต์",
]


def load_data() -> pd.DataFrame:
    df = pd.DataFrame(_DATA, columns=_COLS)
    df["ช่วงอายุ"] = df.apply(
        lambda r: f"{int(r['อายุต่ำสุด'])}–{int(r['อายุสูงสุด'])} ปี", axis=1
    )
    df["ต้นฉบับ"] = df.apply(
        lambda r: f"{r['ราคาต้นฉบับ']:,.0f} {r['สกุลเงินต้นฉบับ']}", axis=1
    )
    return df


# ============================================================
# INIT
# ============================================================
df_all = load_data()

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("## 📚 School Fees Reference")
    if st.button(S("p4", "back_btn"), use_container_width=True):
        st.switch_page("01_User_Information.py")

# ============================================================
# PAGE HEADER
# ============================================================
st.title(S("p4", "title"))
st.caption(S("p4", "caption"))
st.warning(S("p4", "disclaimer"))
st.markdown("---")

# ============================================================
# FILTERS
# ============================================================
st.subheader(S("p4", "filter_header"))

f_col1, f_col2, f_col3, f_col4 = st.columns([2, 1, 1, 1])

with f_col1:
    search_text = st.text_input(
        S("p4", "filter_search"),
        placeholder="เช่น ISB, Harrow, จุฬา, MIT...",
        key="ref_search",
    )

with f_col2:
    country_opts = [S("p4", "filter_all")] + sorted(df_all["ประเทศ"].unique().tolist())
    selected_country = st.selectbox(S("p4", "filter_country"), country_opts, key="ref_country")

with f_col3:
    type_opts = [S("p4", "filter_all")] + sorted(df_all["ประเภท"].unique().tolist())
    selected_type = st.selectbox(S("p4", "filter_type"), type_opts, key="ref_type")

with f_col4:
    level_order = ["อนุบาล", "ประถมศึกษา", "มัธยมต้น", "มัธยมปลาย", "ปริญญาตรี", "ปริญญาโท", "ปริญญาเอก"]
    available_levels = [l for l in level_order if l in df_all["ระดับ"].unique()]
    level_opts = [S("p4", "filter_all")] + available_levels
    selected_level = st.selectbox(S("p4", "filter_level"), level_opts, key="ref_level")

# st.markdown("---")

# ============================================================
# FILTERING
# ============================================================
df_filtered = df_all.copy()

if search_text.strip():
    mask = df_filtered["ชื่อสถาบัน"].str.contains(search_text.strip(), case=False, na=False)
    df_filtered = df_filtered[mask]

if selected_country != S("p4", "filter_all"):
    df_filtered = df_filtered[df_filtered["ประเทศ"] == selected_country]

if selected_type != S("p4", "filter_all"):
    df_filtered = df_filtered[df_filtered["ประเภท"] == selected_type]

if selected_level != S("p4", "filter_all"):
    df_filtered = df_filtered[df_filtered["ระดับ"] == selected_level]

# Sort: level order → country → name
level_order_map = {l: i for i, l in enumerate(level_order)}
df_filtered = df_filtered.copy()
df_filtered["_level_sort"] = df_filtered["ระดับ"].map(level_order_map).fillna(99)
df_filtered = df_filtered.sort_values(["_level_sort", "ประเทศ", "ชื่อสถาบัน"]).drop(columns=["_level_sort"])

# ============================================================
# RESULTS
# ============================================================
st.markdown(f"**{S('p4', 'result_count', n=len(df_filtered))}**")

if df_filtered.empty:
    st.info(S("p4", "no_results"))
else:
    display_cols = [
        "ชื่อสถาบัน", "ประเทศ", "ประเภท", "ระดับ",
        "ช่วงอายุ", "ค่าเล่าเรียน/ปี (฿)", "ต้นฉบับ",
        "หมายเหตุ", "ปีอ้างอิง", "เว็บไซต์",
    ]

    st.dataframe(
        df_filtered[display_cols].reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
        column_config={
            "ค่าเล่าเรียน/ปี (฿)": st.column_config.NumberColumn(
                "ค่าเล่าเรียน/ปี (฿)",
                format="฿%,.0f",
            ),
            "ปีอ้างอิง": st.column_config.NumberColumn(
                "ปีอ้างอิง",
                format="%d",
            ),
            "เว็บไซต์": st.column_config.LinkColumn(
                "เว็บไซต์",
                display_text="🔗 เปิด",
            ),
        },
    )

    # Download (exclude URL column from CSV — raw URL is cleaner in export)
    csv_cols = [c for c in display_cols if c != "เว็บไซต์"] + ["เว็บไซต์"]
    csv_bytes = df_filtered[csv_cols].to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        label=S("p4", "dl_btn"),
        data=csv_bytes,
        file_name="school_fees_reference.csv",
        mime="text/csv",
    )
