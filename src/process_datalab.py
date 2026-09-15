# -*- coding: utf-8 -*-
"""
datalab_raw 의 3개 탭(숙박_체류시간 / 방문자 / 관광소비) zip 을 지역-월 패널로 병합한다.
process_sukbak.py 의 숙박 처리 로직(정합성 검증 완료)을 그대로 포함하고,
방문자·관광소비 탭의 "월별 시계열"을 추가로 붙인다.

이번 단계(2a) 범위: **월별 시계열만**. 스냅샷(거리별/성연령/외국인/업종구조/거주지분포)
→ region_static_features 확장은 다음 단계(2b)에서.

출력 (processed/):
  - tourism_panel.csv          지역 x 월 패널 (숙박 + 방문자 + 관광소비 월별 지표)
  - quadrant_snapshots.csv     [숙박 E] 방문자 체류특성 (지역코드 x 3기간)
  - region_static_features.csv [숙박 C] 숙박 목적지 유입 지역 분포 → 동일광역 집중도
  - national_benchmark.csv     기준연월별 전국평균(숙박방문자비율 / 체류시간 / 관광소비액)
  - _processing_report.txt     처리 로그 / 경고 / 불일치

표준 라이브러리만 사용.
"""

import csv
import datetime as dt
import glob
import io
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE, "datalab_raw")
OUT_DIR = os.path.join(BASE, "processed")

N_REGIONS = 89
YM_MIN, YM_MAX = "202201", "202606"   # 조회 설계 구간. 이 밖의 월(일부 zip에 섞인 202607 등)은 버림

# --------------------------------------------------------------------------- #
# zip 내부 멤버 이름(공백/타임스탬프/.csv 제거)을 논리 키로 매핑
# --------------------------------------------------------------------------- #
SUKBAK_KEYS = {
    "순방문자수및숙박비율": "S_visitors",
    "평균숙박일": "S_nights",
    "숙박목적지검색건수": "S_search",
    "숙박유형별방문자비율": "S_type",
    "숙박방문자비율추이": "S_ratio",
    "평균체류시간추이": "S_dwell",
    "숙박목적지유입지역분포": "S_inflow",
    "방문자체류특성": "S_quad",
}
VISITOR_KEYS = {
    "방문자수(연인원)추이": "V_trend",
    "내비게이션목적지유형별검색량": "V_navsearch",
}
CONSUME_KEYS = {
    "관광소비추이_내국인": "C_dom",
    "관광소비추이_외지인": "C_ext",
    "관광소비추이_현지인": "C_loc",
    "전국대비관광소비추이_내국인": "C_nat_dom",
    "전국대비관광소비추이_외지인": "C_nat_ext",
    "전국대비관광소비추이_현지인": "C_nat_loc",
    "지역화폐관광소비추이": "C_localcur",
}

NATIONAL_LABEL = "전국 기초지자체별 평균"

STAY_TYPE_COLS = ["1박", "2박", "3박", "4박", "5박", "6박", "7박이상"]
STAY_TYPE_OUT = ["숙박유형_" + c for c in STAY_TYPE_COLS]

PROV_ALIASES = {
    "강원특별자치도": {"강원특별자치도", "강원도"},
    "전북특별자치도": {"전북특별자치도", "전라북도"},
    "전남광주통합특별시": {"전남광주통합특별시", "전라남도", "광주광역시"},
}

KNOWN_MISSING = {
    ("대구광역시_군위군__숙박_체류시간__202201_202306.zip", "S_inflow"):
        "군위군 202201~202306: 대구광역시 편입 전이라 구조상 데이터 없음",
}

SUKBAK_PANEL = (
    ["순 방문자수", "숙박자 비율", "평균 숙박일수", "체류시간(분)",
     "검색건수", "전년동기 검색건수", "전년동기 대비 증감률"]
    + STAY_TYPE_OUT
    + ["숙박방문자비율_추이"]
)
VISITOR_PANEL = ["방문자수_연인원", "전년동월_방문자수", "방문자수_증감률", "내비_목적지검색량"]
CONSUME_PANEL = [
    "관광소비_내국인_천원", "관광소비_외지인_천원", "관광소비_현지인_천원",
    "관광소비_내국인_전국대비율", "관광소비_외지인_전국대비율", "관광소비_현지인_전국대비율",
    "지역화폐_소비액_천원",
]
PANEL_COLS = ["광역지자체명", "지역명", "기준연월"] + SUKBAK_PANEL + VISITOR_PANEL + CONSUME_PANEL

RATIO_DIFF_TOL = 0.05


# --------------------------------------------------------------------------- #
# 유틸
# --------------------------------------------------------------------------- #
def decode_member_name(raw):
    for enc in ("cp949", "euc-kr"):
        try:
            return raw.encode("cp437").decode(enc)
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return raw


def normalize_member(name):
    base = os.path.basename(name)
    base = re.sub(r"^\d{14}_", "", base)
    base = re.sub(r"\.csv$", "", base, flags=re.I)
    return base.replace(" ", "")


def parse_zip_name(path):
    stem = re.sub(r"\.zip$", "", os.path.basename(path), flags=re.I)
    parts = stem.split("__")
    period = parts[-1]
    prov, _, region = parts[0].partition("_")
    return prov, region, period


def read_members(zf, key_map):
    """zip 안에서 key_map 에 해당하는 멤버만 {논리키: (헤더, rows)} 로."""
    out = {}
    present = set()
    for info in zf.infolist():
        if info.is_dir():
            continue
        k = key_map.get(normalize_member(decode_member_name(info.filename)))
        if not k:
            continue
        text = zf.read(info).decode("utf-8-sig")
        rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
        if rows:
            out[k] = (rows[0], rows[1:])
            present.add(k)
    return out


def col_idx(hdr):
    return {h.strip(): i for i, h in enumerate(hdr)}


def ym_of(idx, row):
    for name in ("기준연월", "기준년월"):
        if name in idx:
            return row[idx[name]].strip()
    return row[0].strip()


def to_float(s):
    try:
        return float(str(s).strip())
    except (ValueError, AttributeError):
        return None


def fmt(x, nd=1):
    return "" if x is None else ("%." + str(nd) + "f") % x


# --------------------------------------------------------------------------- #
# 탭별 월 시계열 추출
# --------------------------------------------------------------------------- #
def extract_sukbak_monthly(mem, region, national, national_conflicts, zname, match_failures):
    """숙박_체류시간 zip → {ym: {panel col: val}}. national/conflicts 는 부수효과로 채움."""
    monthly = {}

    def ensure(ym):
        return monthly.setdefault(ym, {})

    if "S_visitors" in mem:
        hdr, rows = mem["S_visitors"]
        idx = col_idx(hdr)
        for r in rows:
            d = ensure(ym_of(idx, r))
            d["순 방문자수"] = r[idx.get("순 방문자수", 1)].strip()
            d["숙박자 비율"] = r[idx.get("숙박자 비율", 2)].strip()
    if "S_nights" in mem:
        hdr, rows = mem["S_nights"]
        idx = col_idx(hdr)
        for r in rows:
            ensure(ym_of(idx, r))["평균 숙박일수"] = r[idx.get("평균 숙박일수", 1)].strip()
    if "S_search" in mem:
        hdr, rows = mem["S_search"]
        idx = col_idx(hdr)
        for r in rows:
            d = ensure(ym_of(idx, r))
            d["검색건수"] = r[idx.get("검색건수", 1)].strip()
            d["전년동기 검색건수"] = r[idx.get("전년동기 검색건수", 2)].strip()
            d["전년동기 대비 증감률"] = r[idx.get("전년동기 대비 증감률", 3)].strip()
    if "S_type" in mem:
        hdr, rows = mem["S_type"]
        idx = col_idx(hdr)
        for r in rows:
            d = ensure(ym_of(idx, r))
            for src, out in zip(STAY_TYPE_COLS, STAY_TYPE_OUT):
                if src in idx:
                    d[out] = r[idx[src]].strip()
    for mk, vcol_name, out_col, nat_key in [
        ("S_ratio", "숙박방문자 비율", "숙박방문자비율_추이", "ratio"),
        ("S_dwell", "체류시간(분)", "체류시간(분)", "dwell"),
    ]:
        if mk not in mem:
            continue
        hdr, rows = mem[mk]
        idx = col_idx(hdr)
        vcol = idx.get(vcol_name, 2)
        found = False
        for r in rows:
            ym = ym_of(idx, r)
            nm = r[idx["지역명"]].strip()
            val = r[vcol].strip()
            if nm == region:
                found = True
                ensure(ym)[out_col] = val
            elif nm == NATIONAL_LABEL:
                fv = to_float(val)
                if fv is None:
                    continue
                slot = national.setdefault(ym, {})
                if nat_key not in slot:
                    slot[nat_key] = fv
                elif abs(slot[nat_key] - fv) > 1e-9:
                    national_conflicts.append((ym, nat_key, slot[nat_key], fv, zname))
        if not found:
            match_failures.append((zname, "%s 에서 지역명 '%s' 행 없음" % (mk, region)))
    return monthly


def extract_visitor_monthly(mem):
    monthly = defaultdict(dict)
    if "V_trend" in mem:
        hdr, rows = mem["V_trend"]
        idx = col_idx(hdr)
        for r in rows:
            ym = ym_of(idx, r)
            monthly[ym]["방문자수_연인원"] = r[idx.get("방문자수", 1)].strip()
            monthly[ym]["전년동월_방문자수"] = r[idx.get("전년동월방문자수", 2)].strip()
            monthly[ym]["방문자수_증감률"] = r[idx.get("방문자수증감률", 3)].strip()
    if "V_navsearch" in mem:
        hdr, rows = mem["V_navsearch"]
        idx = col_idx(hdr)
        tcol = idx.get("목적지 유형", 1)
        vcol = idx.get("목적지 검색량", 2)
        for r in rows:
            if r[tcol].strip() == "전체":
                monthly[ym_of(idx, r)]["내비_목적지검색량"] = r[vcol].strip()
    return monthly


def extract_consume_monthly(mem, national):
    monthly = defaultdict(dict)
    for mk, out_col in [("C_dom", "관광소비_내국인_천원"),
                        ("C_ext", "관광소비_외지인_천원"),
                        ("C_loc", "관광소비_현지인_천원")]:
        if mk not in mem:
            continue
        hdr, rows = mem[mk]
        idx = col_idx(hdr)
        gcol = idx.get("업종대분류명", 1)
        vcol = idx.get("소비액(천원)", 2)
        for r in rows:
            if r[gcol].strip() == "전체":
                monthly[ym_of(idx, r)][out_col] = r[vcol].strip()
    for mk, out_col in [("C_nat_dom", "관광소비_내국인_전국대비율"),
                        ("C_nat_ext", "관광소비_외지인_전국대비율"),
                        ("C_nat_loc", "관광소비_현지인_전국대비율")]:
        if mk not in mem:
            continue
        hdr, rows = mem[mk]
        idx = col_idx(hdr)
        rcol = idx.get("전국 대비 관광소비율", 4)
        ncol = idx.get("전국 관광소비액(백만원)", 3)
        for r in rows:
            ym = ym_of(idx, r)
            monthly[ym][out_col] = r[rcol].strip()
            if mk == "C_nat_dom":
                fv = to_float(r[ncol])
                if fv is not None:
                    national.setdefault(ym, {}).setdefault("consume_dom_nat_mil", fv)
    if "C_localcur" in mem:
        hdr, rows = mem["C_localcur"]
        idx = col_idx(hdr)
        vcol = idx.get("소비금액(천원)", 2)
        for r in rows:
            monthly[ym_of(idx, r)]["지역화폐_소비액_천원"] = r[vcol].strip()
    return monthly


# --------------------------------------------------------------------------- #
# 메인
# --------------------------------------------------------------------------- #
def main():
    report = []

    def log(m=""):
        report.append(m)

    log("데이터랩 3개 탭 병합 리포트 (단계 2a: 월별 시계열)")
    log("실행: " + dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log("RAW_DIR: " + RAW_DIR)
    log("")

    all_zips = glob.glob(os.path.join(RAW_DIR, "*.zip"))
    by_tab = {"숙박_체류시간": [], "방문자": [], "관광소비": []}
    for p in all_zips:
        b = os.path.basename(p)
        for t in by_tab:
            if ("__%s__" % t) in b:
                by_tab[t].append(p)
    for t, lst in by_tab.items():
        log("%s zip: %d개 (기대 %d = 89x3)" % (t, len(lst), N_REGIONS * 3))
    log("")

    panel = {}                     # (prov, region, ym) -> {col: val}
    national = {}                   # ym -> {ratio, dwell, consume_dom_nat_mil}
    national_conflicts = []
    quadrant_rows = []
    inflow_by_region = {}           # (prov, region) -> {period: (hdr, rows)}
    missing_members = []
    match_failures = []
    ratio_total = ratio_mismatch = 0
    ratio_maxdiff = 0.0

    def put(prov, region, ym, d):
        slot = panel.setdefault((prov, region, ym), {})
        for k, v in d.items():
            if v != "" and v is not None:
                slot[k] = v

    # ---- 숙박_체류시간 ---------------------------------------------------- #
    for zp in sorted(by_tab["숙박_체류시간"]):
        prov, region, period = parse_zip_name(zp)
        zname = os.path.basename(zp)
        try:
            zf = zipfile.ZipFile(zp)
        except zipfile.BadZipFile:
            match_failures.append((zname, "손상된 zip"))
            continue
        mem = read_members(zf, SUKBAK_KEYS)
        for k in SUKBAK_KEYS.values():
            if k not in mem:
                missing_members.append((zname, k))
        monthly = extract_sukbak_monthly(mem, region, national, national_conflicts,
                                         zname, match_failures)
        for ym, d in monthly.items():
            a, b = to_float(d.get("숙박자 비율")), to_float(d.get("숙박방문자비율_추이"))
            if a is not None and b is not None:
                ratio_total += 1
                diff = abs(a - b)
                if diff > RATIO_DIFF_TOL:
                    ratio_mismatch += 1
                if diff > ratio_maxdiff:
                    ratio_maxdiff = diff
            put(prov, region, ym, d)
        if "S_inflow" in mem:
            inflow_by_region.setdefault((prov, region), {})[period] = mem["S_inflow"]
        if "S_quad" in mem:
            hdr, rows = mem["S_quad"]
            idx = col_idx(hdr)
            hit = next((r for r in rows if r[idx["지역명"]].strip() == region), None)
            if hit is None:
                match_failures.append((zname, "S_quad 에서 지역명 '%s' 행 없음" % region))
            else:
                quadrant_rows.append({
                    "지역코드": hit[idx["지역코드"]].strip(),
                    "지역명": region,
                    "기간": period,
                    "평균체류시간": hit[idx.get("평균 체류시간", 2)].strip(),
                    "평균숙박일수": hit[idx.get("평균 숙박일수", 3)].strip(),
                })
        zf.close()

    # ---- 방문자 -------------------------------------------------------------- #
    for zp in sorted(by_tab["방문자"]):
        prov, region, period = parse_zip_name(zp)
        zname = os.path.basename(zp)
        try:
            zf = zipfile.ZipFile(zp)
        except zipfile.BadZipFile:
            match_failures.append((zname, "손상된 zip"))
            continue
        mem = read_members(zf, VISITOR_KEYS)
        for k in VISITOR_KEYS.values():
            if k not in mem:
                missing_members.append((zname, k))
        for ym, d in extract_visitor_monthly(mem).items():
            put(prov, region, ym, d)
        zf.close()

    # ---- 관광소비 --------------------------------------------------------- #
    for zp in sorted(by_tab["관광소비"]):
        prov, region, period = parse_zip_name(zp)
        zname = os.path.basename(zp)
        try:
            zf = zipfile.ZipFile(zp)
        except zipfile.BadZipFile:
            match_failures.append((zname, "손상된 zip"))
            continue
        mem = read_members(zf, CONSUME_KEYS)
        for k in ("C_dom", "C_ext", "C_loc", "C_nat_dom"):
            if k not in mem:
                missing_members.append((zname, k))
        for ym, d in extract_consume_monthly(mem, national).items():
            put(prov, region, ym, d)
        zf.close()

    # ---- 패널 행 완성 -------------------------------------------------------- #
    panel_rows = []
    out_of_window = []
    for (prov, region, ym), d in panel.items():
        if not (YM_MIN <= ym <= YM_MAX):
            out_of_window.append((prov, region, ym))
            continue
        row = {"광역지자체명": prov, "지역명": region, "기준연월": ym}
        for c in PANEL_COLS[3:]:
            row[c] = d.get(c, "")
        panel_rows.append(row)
    panel_rows.sort(key=lambda r: (r["광역지자체명"], r["지역명"], r["기준연월"]))
    for ym in list(national):
        if not (YM_MIN <= ym <= YM_MAX):
            national.pop(ym, None)

    # ---- [C] 동일광역 유입 집중도 (숙박 목적지 유입 분포, 최신 기간) ------- #
    static_rows = []
    c_block_missing = []
    for (prov, region), by_period in sorted(inflow_by_region.items()):
        period = max(by_period)
        hdr, rows = by_period[period]
        idx = col_idx(hdr)
        pc = idx.get("광역지자체명", 0)
        cc = idx.get("기초지자체명", 1)
        sc = idx.get("기초지자체별 거주 방문자 비율", 2)
        prov_blocks = set()
        recs = []
        for r in rows:
            s = to_float(r[sc])
            if s is None:
                continue
            prov_blocks.add(r[pc].strip())
            recs.append((r[pc].strip(), r[cc].strip(), s))
        if not recs:
            match_failures.append(("(%s %s)" % (prov, region), "S_inflow 유효행 없음"))
            continue
        aliases = PROV_ALIASES.get(prov, {prov})
        block = [(nm, s) for (sp, nm, s) in recs if sp in aliases]
        if not block:
            c_block_missing.append((prov, region, period))
            continue
        block.sort(key=lambda t: t[1], reverse=True)
        hhi = sum((s / 100.0) ** 2 for _, s in block)
        static_rows.append({
            "광역지자체명": prov, "지역명": region, "기준기간": period,
            "유입광역수": str(len(prov_blocks)), "유입기초수": str(len(recs)),
            "동일광역_기초수": str(len(block)),
            "동일광역_최대유입기초": block[0][0],
            "동일광역_최대유입기초_비율": fmt(block[0][1], 1),
            "동일광역_상위3비율합": fmt(sum(s for _, s in block[:3]), 1),
            "동일광역_HHI": fmt(hhi, 4),
        })
    static_rows.sort(key=lambda r: (r["광역지자체명"], r["지역명"]))

    # ---- national_benchmark --------------------------------------------- #
    nat_rows = []
    for ym in sorted(national):
        s = national[ym]
        nat_rows.append({
            "기준연월": ym,
            "숙박방문자비율_전국평균": fmt(s.get("ratio")),
            "체류시간분_전국평균": fmt(s.get("dwell")),
            "관광소비_내국인_전국액_백만원": fmt(s.get("consume_dom_nat_mil"), 0),
        })

    quadrant_rows.sort(key=lambda r: (r["지역명"], r["기간"]))

    # ---- 쓰기 --------------------------------------------------------------- #
    os.makedirs(OUT_DIR, exist_ok=True)

    def write_csv(name, cols, rows):
        with open(os.path.join(OUT_DIR, name), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)

    write_csv("tourism_panel.csv", PANEL_COLS, panel_rows)
    write_csv("national_benchmark.csv",
              ["기준연월", "숙박방문자비율_전국평균", "체류시간분_전국평균",
               "관광소비_내국인_전국액_백만원"], nat_rows)
    write_csv("region_static_features.csv",
              ["광역지자체명", "지역명", "기준기간", "유입광역수", "유입기초수",
               "동일광역_기초수", "동일광역_최대유입기초", "동일광역_최대유입기초_비율",
               "동일광역_상위3비율합", "동일광역_HHI"], static_rows)
    write_csv("quadrant_snapshots.csv",
              ["지역코드", "지역명", "기간", "평균체류시간", "평균숙박일수"], quadrant_rows)
    if national_conflicts:
        write_csv("_national_benchmark_conflicts.csv",
                  ["기준연월", "필드", "채택값", "다른값", "출처zip"],
                  [{"기준연월": a, "필드": b, "채택값": c, "다른값": d, "출처zip": e}
                   for (a, b, c, d, e) in national_conflicts])

    # ---- 리포트 ----------------------------------------------------------- #
    regions_seen = sorted({(r["광역지자체명"], r["지역명"]) for r in panel_rows})
    months_seen = sorted({r["기준연월"] for r in panel_rows})
    log("[패널]")
    log("  행수: %d" % len(panel_rows))
    log("  지역수: %d / 기대 %d" % (len(regions_seen), N_REGIONS))
    log("  월 범위: %s ~ %s (%d개월)" % (months_seen[0], months_seen[-1], len(months_seen)))
    log("")

    # 컬럼별 결측(빈 문자열) 비율
    log("[패널 컬럼별 채움률]")
    n = len(panel_rows)
    for c in PANEL_COLS[3:]:
        filled = sum(1 for r in panel_rows if r[c] != "")
        log("  %-26s %5d/%d  (%.0f%%)" % (c, filled, n, 100.0 * filled / n if n else 0))
    log("")

    # 지역별 월 수 이상치
    if out_of_window:
        log("[조회구간 밖 월 제거] %d행 (예: %s)" %
            (len(out_of_window), ", ".join("%s %s %s" % t for t in sorted(out_of_window)[:5])))
        log("")

    cnt_by_region = Counter((p, r) for (p, r, ym) in panel if YM_MIN <= ym <= YM_MAX)
    odd = {k: v for k, v in cnt_by_region.items() if v != len(months_seen)}
    log("[지역별 월 수 != %d] %d건" % (len(months_seen), len(odd)))
    for (p, r), v in sorted(odd.items()):
        log("  %s %s : %d개월" % (p, r, v))
    log("")

    explained = [(z, k) for (z, k) in missing_members if (z, k) in KNOWN_MISSING]
    unexplained = [(z, k) for (z, k) in missing_members if (z, k) not in KNOWN_MISSING]
    log("[누락 멤버 - 사유 확인됨] %d건" % len(explained))
    for z, k in explained:
        log("  %s (%s) : %s" % (z, k, KNOWN_MISSING[(z, k)]))
    log("")
    log("[누락 멤버 - 미확인] %d건" % len(unexplained))
    for z, k in unexplained[:60]:
        log("  %s : %s" % (z, k))
    if len(unexplained) > 60:
        log("  ... 외 %d건" % (len(unexplained) - 60))
    log("")

    log("[C 동일광역 블록 없음] %d건" % len(c_block_missing))
    for cp, cr, cper in c_block_missing:
        log("  %s %s (%s)" % (cp, cr, cper))
    log("")
    log("[지역명 매칭 실패 / 손상] %d건" % len(match_failures))
    for z, d in match_failures[:60]:
        log("  %s : %s" % (z, d))
    if len(match_failures) > 60:
        log("  ... 외 %d건" % (len(match_failures) - 60))
    log("")

    log("[정합성: 숙박자 비율 <-> 숙박방문자비율_추이]")
    if ratio_total and ratio_mismatch == 0:
        log("  완전 일치 (%d행, 최대차 %.4f)" % (ratio_total, ratio_maxdiff))
    else:
        log("  비교 %d행 / 불일치 %d행 / 최대차 %.4f" % (ratio_total, ratio_mismatch, ratio_maxdiff))
    log("")
    log("[전국평균 값 불일치] %d건" % len(national_conflicts))
    log("")

    log("[산출물 행수]")
    log("  tourism_panel.csv          : %d" % len(panel_rows))
    log("  national_benchmark.csv     : %d" % len(nat_rows))
    log("  region_static_features.csv : %d" % len(static_rows))
    log("  quadrant_snapshots.csv     : %d" % len(quadrant_rows))

    with open(os.path.join(OUT_DIR, "_processing_report.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(report) + "\n")
    print("\n".join(report))
    print("\n출력 폴더: " + OUT_DIR)


if __name__ == "__main__":
    sys.exit(main())
