# -*- coding: utf-8 -*-
"""
datalab_raw 의 "숙박_체류시간" zip 파일들을 성격별로 나눠 처리한다.

출력 (processed/):
  - tourism_panel.csv          [A]+[B] : 광역지자체명 + 지역명 + 기준연월 월별 패널
  - national_benchmark.csv     [B] 에서 분리한 "전국 기초지자체별 평균" 시계열
  - region_static_features.csv [C] 숙박 목적지 유입 지역 분포 → "대상 지역이 속한
                                  광역 블록"만 뽑아 그 블록 안의 유입 집중도 지표
  - quadrant_snapshots.csv     [E] 방문자 체류특성 → 지역 x 기간 스냅샷

[C] 주의: 숙박 목적지 유입 지역 분포.csv 는 출발지 광역별로 각각 100% 로 정규화된
여러(약 15개) 블록의 나열이다. 전체 행을 합친 집중도(HHI 등)는 통계적으로 무의미하므로
계산하지 않는다. 대상 지역(예: 고성군)이 속한 광역(예: 강원특별자치도) 블록만 추출해
그 블록 내부에서만 집중도를 계산한다. 동일 광역 매칭은 PROV_ALIASES 를 쓴다.

[E] 주의: quadrant_snapshots.csv 는 지역명이 광역을 넘어 중복될 수 있다
(예: '서구' = 부산 26140 / 대구 27170). 지역명+기간은 유일하지 않으므로 다운스트림
조인은 반드시 '지역코드' 를 키로 한다. 중복 지역명은 리포트에 명시한다.
  - _processing_report.txt     처리 로그 / 경고 / 불일치 리포트
  - _national_benchmark_conflicts.csv  (전국평균 값 불일치가 있을 때만)

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
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE, "datalab_raw")
OUT_DIR = os.path.join(BASE, "processed")

EXPECTED_ZIP_COUNT = 267  # 89 지역 x 3 기간

# zip 내부 멤버 이름(공백/타임스탬프 제거, .csv 제거)을 논리 키로 매핑
MEMBER_KEYS = {
    "순방문자수및숙박비율": "A_visitors",
    "평균숙박일": "A_nights",
    "숙박목적지검색건수": "A_search",
    "숙박유형별방문자비율": "A_type",
    "숙박방문자비율추이": "B_ratio",
    "평균체류시간추이": "B_dwell",
    "숙박목적지유입지역분포": "C_inflow",
    "방문자체류특성": "E_char",
}

NATIONAL_LABEL = "전국 기초지자체별 평균"

STAY_TYPE_COLS = ["1박", "2박", "3박", "4박", "5박", "6박", "7박이상"]
STAY_TYPE_OUT = ["숙박유형_" + c for c in STAY_TYPE_COLS]

# 통합/개편된 광역지자체 명칭 별칭 ([C] 동일광역 블록 매칭용)
PROV_ALIASES = {
    "강원특별자치도": {"강원특별자치도", "강원도"},
    "전북특별자치도": {"전북특별자치도", "전라북도"},
    "전남광주통합특별시": {"전남광주통합특별시", "전라남도", "광주광역시"},
}

# 구조적으로 존재할 수 없는 결측 (누락이 아니라 사유가 명확한 케이스)
KNOWN_MISSING = {
    ("대구광역시_군위군__숙박_체류시간__202201_202306.zip", "C_inflow"):
        "군위군 202201~202306: 대구광역시 편입 전이라 구조상 데이터 없음",
}

PANEL_COLS = (
    ["광역지자체명", "지역명", "기준연월",
     "순 방문자수", "숙박자 비율", "평균 숙박일수", "체류시간(분)",
     "검색건수", "전년동기 검색건수", "전년동기 대비 증감률"]
    + STAY_TYPE_OUT
    + ["숙박방문자비율_추이"]
)

RATIO_DIFF_TOL = 0.05  # 숙박자 비율 vs 숙박방문자비율_추이 허용 오차


# --------------------------------------------------------------------------- #
# 유틸
# --------------------------------------------------------------------------- #
def decode_member_name(raw):
    """zip 헤더에 cp437 로 저장된 한글 파일명을 복원."""
    for enc in ("cp949", "euc-kr"):
        try:
            return raw.encode("cp437").decode(enc)
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return raw


def normalize_member(name):
    base = os.path.basename(name)
    base = re.sub(r"^\d{14}_", "", base)          # 타임스탬프 접두어 제거
    base = re.sub(r"\.csv$", "", base, flags=re.I)
    return base.replace(" ", "")


def parse_zip_name(path):
    """<광역>_<기초>__숙박_체류시간__<start>_<end>.zip → (광역, 지역명, 기간)."""
    stem = os.path.basename(path)
    stem = re.sub(r"\.zip$", "", stem, flags=re.I)
    parts = stem.split("__")
    region_part = parts[0]
    period = parts[-1]                             # 예: 202201_202306
    prov, _, region = region_part.partition("_")   # 첫 '_' 로 광역/기초 분리
    return prov, region, period


def read_csv_member(zf, info):
    text = zf.read(info).decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    rows = [r for r in rows if any(c.strip() for c in r)]  # 빈 줄 제거
    if not rows:
        return [], []
    return rows[0], rows[1:]


def to_float(s):
    try:
        return float(str(s).strip())
    except (ValueError, AttributeError):
        return None


def fmt(x, nd=1):
    if x is None:
        return ""
    return ("%." + str(nd) + "f") % x


# --------------------------------------------------------------------------- #
# 메인 처리
# --------------------------------------------------------------------------- #
def main():
    report = []

    def log(msg=""):
        report.append(msg)

    log("숙박_체류시간 처리 리포트")
    log("실행: " + dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log("RAW_DIR: " + RAW_DIR)
    log("")

    all_zips = glob.glob(os.path.join(RAW_DIR, "**", "*.zip"), recursive=True)
    zips = sorted(p for p in all_zips if "숙박_체류시간" in os.path.basename(p))

    # (1) 개수 확인
    n = len(zips)
    line = "숙박_체류시간 zip: %d개 발견 (기대 %d = 89x3)" % (n, EXPECTED_ZIP_COUNT)
    print(line)
    log(line)
    if n < EXPECTED_ZIP_COUNT:
        warn = "  [경고] 기대치보다 %d개 부족합니다." % (EXPECTED_ZIP_COUNT - n)
        print(warn)
        log(warn)
    log("")

    if not zips:
        print("처리할 zip이 없습니다. 종료.")
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(os.path.join(OUT_DIR, "_processing_report.txt"), "w",
                  encoding="utf-8") as fh:
            fh.write("\n".join(report) + "\n")
        return

    panel_rows = []                 # [A]+[B] 지역 월별 행
    national = {}                   # 기준연월 -> {"ratio":v, "dwell":v}
    national_conflicts = []         # (기준연월, 필드, 첫값, 다른값, zip)
    quadrant_rows = []              # [E]
    inflow_by_region = {}           # (광역, 지역명) -> {period: (헤더, rows)}
    missing_members = []            # (zip, 누락 논리키)
    match_failures = []             # (zip, 설명)

    # 숙박자비율 vs 숙박방문자비율_추이 비교
    ratio_cmp_total = 0
    ratio_cmp_mismatch = 0
    ratio_cmp_maxdiff = 0.0
    ratio_cmp_maxloc = ""

    for zpath in zips:
        prov, region, period = parse_zip_name(zpath)
        zname = os.path.basename(zpath)
        try:
            zf = zipfile.ZipFile(zpath)
        except zipfile.BadZipFile:
            match_failures.append((zname, "손상된 zip - 건너뜀"))
            continue

        members = {}
        for info in zf.infolist():
            if info.is_dir():
                continue
            key = MEMBER_KEYS.get(normalize_member(decode_member_name(info.filename)))
            if key:
                members[key] = info
        for k in MEMBER_KEYS.values():
            if k not in members:
                missing_members.append((zname, k))

        # ---- [A] 4개 파일을 기준연월 dict 로 병합 ----------------------- #
        monthly = {}   # 기준연월 -> {panel col: value}

        def ensure(ym):
            return monthly.setdefault(ym, {})

        if "A_visitors" in members:
            hdr, rows = read_csv_member(zf, members["A_visitors"])
            idx = {h: i for i, h in enumerate(hdr)}
            for r in rows:
                ym = r[idx["기준연월"]].strip()
                d = ensure(ym)
                d["순 방문자수"] = r[idx.get("순 방문자수", 1)].strip()
                d["숙박자 비율"] = r[idx.get("숙박자 비율", 2)].strip()

        if "A_nights" in members:
            hdr, rows = read_csv_member(zf, members["A_nights"])
            idx = {h: i for i, h in enumerate(hdr)}
            for r in rows:
                ym = r[idx["기준연월"]].strip()
                ensure(ym)["평균 숙박일수"] = r[idx.get("평균 숙박일수", 1)].strip()

        if "A_search" in members:
            hdr, rows = read_csv_member(zf, members["A_search"])
            idx = {h: i for i, h in enumerate(hdr)}
            for r in rows:
                ym = r[idx["기준연월"]].strip()
                d = ensure(ym)
                d["검색건수"] = r[idx.get("검색건수", 1)].strip()
                d["전년동기 검색건수"] = r[idx.get("전년동기 검색건수", 2)].strip()
                d["전년동기 대비 증감률"] = r[idx.get("전년동기 대비 증감률", 3)].strip()

        if "A_type" in members:
            hdr, rows = read_csv_member(zf, members["A_type"])
            idx = {h: i for i, h in enumerate(hdr)}
            for r in rows:
                ym = r[idx["기준연월"]].strip()
                d = ensure(ym)
                for src, out in zip(STAY_TYPE_COLS, STAY_TYPE_OUT):
                    if src in idx:
                        d[out] = r[idx[src]].strip()

        # ---- [B] 추이 2개 : 대상 지역 행 + 전국평균 행 ----------------- #
        if "B_ratio" in members:
            hdr, rows = read_csv_member(zf, members["B_ratio"])
            idx = {h: i for i, h in enumerate(hdr)}
            vcol = idx.get("숙박방문자 비율", 2)
            found_target = False
            for r in rows:
                ym = r[idx["기준연월"]].strip()
                nm = r[idx["지역명"]].strip()
                val = r[vcol].strip()
                if nm == region:
                    found_target = True
                    ensure(ym)["숙박방문자비율_추이"] = val
                elif nm == NATIONAL_LABEL:
                    fv = to_float(val)
                    if fv is None:
                        continue
                    slot = national.setdefault(ym, {})
                    if "ratio" not in slot:
                        slot["ratio"] = fv
                    elif abs(slot["ratio"] - fv) > 1e-9:
                        national_conflicts.append((ym, "ratio", slot["ratio"], fv, zname))
            if not found_target:
                match_failures.append((zname, "B_ratio 에서 지역명 '%s' 행 없음" % region))

        if "B_dwell" in members:
            hdr, rows = read_csv_member(zf, members["B_dwell"])
            idx = {h: i for i, h in enumerate(hdr)}
            vcol = idx.get("체류시간(분)", 2)
            found_target = False
            for r in rows:
                ym = r[idx["기준연월"]].strip()
                nm = r[idx["지역명"]].strip()
                val = r[vcol].strip()
                if nm == region:
                    found_target = True
                    ensure(ym)["체류시간(분)"] = val
                elif nm == NATIONAL_LABEL:
                    fv = to_float(val)
                    if fv is None:
                        continue
                    slot = national.setdefault(ym, {})
                    if "dwell" not in slot:
                        slot["dwell"] = fv
                    elif abs(slot["dwell"] - fv) > 1e-9:
                        national_conflicts.append((ym, "dwell", slot["dwell"], fv, zname))
            if not found_target:
                match_failures.append((zname, "B_dwell 에서 지역명 '%s' 행 없음" % region))

        # ---- 숙박자 비율 vs 숙박방문자비율_추이 비교 ------------------- #
        for ym, d in monthly.items():
            a = to_float(d.get("숙박자 비율"))
            b = to_float(d.get("숙박방문자비율_추이"))
            if a is None or b is None:
                continue
            ratio_cmp_total += 1
            diff = abs(a - b)
            if diff > RATIO_DIFF_TOL:
                ratio_cmp_mismatch += 1
            if diff > ratio_cmp_maxdiff:
                ratio_cmp_maxdiff = diff
                ratio_cmp_maxloc = "%s %s %s (A=%s, B=%s)" % (prov, region, ym, a, b)

        # ---- 패널 행 방출 ------------------------------------------------ #
        for ym in sorted(monthly):
            d = monthly[ym]
            row = {"광역지자체명": prov, "지역명": region, "기준연월": ym}
            for c in PANEL_COLS[3:]:
                row[c] = d.get(c, "")
            panel_rows.append(row)

        # ---- [C] 유입 지역 분포 : 지역별로 기간 보관 (뒤에서 최신 선택) - #
        if "C_inflow" in members:
            hdr, rows = read_csv_member(zf, members["C_inflow"])
            inflow_by_region.setdefault((prov, region), {})[period] = (hdr, rows)

        # ---- [E] 방문자 체류특성 : 대상 지역 행만 --------------------- #
        # 지역명은 광역을 넘어 중복될 수 있으므로(예: '서구' 부산/대구) 출력에는
        # 지역코드를 함께 남기고, 조인 키는 지역코드로 한다. (리포트에도 명시)
        if "E_char" in members:
            hdr, rows = read_csv_member(zf, members["E_char"])
            idx = {h: i for i, h in enumerate(hdr)}
            hit = None
            for r in rows:
                if r[idx["지역명"]].strip() == region:
                    hit = r
                    break
            if hit is None:
                match_failures.append((zname, "E_char 에서 지역명 '%s' 행 없음" % region))
            else:
                quadrant_rows.append({
                    "지역코드": hit[idx["지역코드"]].strip(),
                    "지역명": region,
                    "기간": period,
                    "평균체류시간": hit[idx.get("평균 체류시간", 2)].strip(),
                    "평균숙박일수": hit[idx.get("평균 숙박일수", 3)].strip(),
                })

        zf.close()

    # --------------------------------------------------------------------- #
    # [A]+[B] 패널 : (광역, 지역명, 기준연월) 중복 제거 (keep-first)
    # --------------------------------------------------------------------- #
    seen = set()
    dedup_panel = []
    dropped = []
    for row in panel_rows:
        k = (row["광역지자체명"], row["지역명"], row["기준연월"])
        if k in seen:
            dropped.append(k)
            continue
        seen.add(k)
        dedup_panel.append(row)
    dedup_panel.sort(key=lambda r: (r["광역지자체명"], r["지역명"], r["기준연월"]))

    # --------------------------------------------------------------------- #
    # [C] "대상 지역이 속한 광역 블록" 내부의 유입 집중도 : 최신 기간 버킷만 사용
    #
    # 유입 분포 파일 = 출발지 광역별로 각각 100% 정규화된 블록들의 나열.
    # 전체 합산 집중도는 무의미 -> 대상 광역 블록만 떼어내 그 안에서만 계산.
    # --------------------------------------------------------------------- #
    static_rows = []
    c_block_missing = []   # (광역, 지역명, period) : 대상 광역 블록이 파일에 없음
    for (prov, region), by_period in sorted(inflow_by_region.items()):
        period = max(by_period)                       # 202501_202606 > ... 문자열 비교
        hdr, rows = by_period[period]
        idx = {h: i for i, h in enumerate(hdr)}
        pc = idx.get("광역지자체명", 0)
        cc = idx.get("기초지자체명", 1)
        sc = idx.get("기초지자체별 거주 방문자 비율", 2)

        prov_blocks = set()
        recs = []                                     # (출발지광역, 출발지기초, 비율)
        for r in rows:
            s = to_float(r[sc])
            if s is None:
                continue
            sp = r[pc].strip()
            prov_blocks.add(sp)
            recs.append((sp, r[cc].strip(), s))
        if not recs:
            match_failures.append(("(%s %s)" % (prov, region), "C_inflow 유효 행 없음"))
            continue

        aliases = PROV_ALIASES.get(prov, {prov})
        block = [(nm, s) for (sp, nm, s) in recs if sp in aliases]
        if not block:
            c_block_missing.append((prov, region, period))
            continue
        block.sort(key=lambda t: t[1], reverse=True)
        hhi = sum((s / 100.0) ** 2 for _, s in block)  # 블록 합 100 -> 0~1 범위
        static_rows.append({
            "광역지자체명": prov,
            "지역명": region,
            "기준기간": period,
            "유입광역수": str(len(prov_blocks)),
            "유입기초수": str(len(recs)),
            "동일광역_기초수": str(len(block)),
            "동일광역_최대유입기초": block[0][0],
            "동일광역_최대유입기초_비율": fmt(block[0][1], 1),
            "동일광역_상위3비율합": fmt(sum(s for _, s in block[:3]), 1),
            "동일광역_HHI": fmt(hhi, 4),
        })
    static_rows.sort(key=lambda r: (r["광역지자체명"], r["지역명"]))

    # --------------------------------------------------------------------- #
    # national_benchmark
    # --------------------------------------------------------------------- #
    nat_rows = []
    for ym in sorted(national):
        slot = national[ym]
        nat_rows.append({
            "기준연월": ym,
            "숙박방문자비율_전국평균": fmt(slot.get("ratio"), 1),
            "체류시간분_전국평균": fmt(slot.get("dwell"), 1),
        })

    quadrant_rows.sort(key=lambda r: (r["지역명"], r["기간"]))

    # --------------------------------------------------------------------- #
    # 파일 쓰기
    # --------------------------------------------------------------------- #
    os.makedirs(OUT_DIR, exist_ok=True)

    def write_csv(name, cols, rows):
        path = os.path.join(OUT_DIR, name)
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        return path

    write_csv("tourism_panel.csv", PANEL_COLS, dedup_panel)
    write_csv("national_benchmark.csv",
              ["기준연월", "숙박방문자비율_전국평균", "체류시간분_전국평균"], nat_rows)
    write_csv("region_static_features.csv",
              ["광역지자체명", "지역명", "기준기간",
               "유입광역수", "유입기초수", "동일광역_기초수",
               "동일광역_최대유입기초", "동일광역_최대유입기초_비율",
               "동일광역_상위3비율합", "동일광역_HHI"], static_rows)
    write_csv("quadrant_snapshots.csv",
              ["지역코드", "지역명", "기간", "평균체류시간", "평균숙박일수"], quadrant_rows)

    if national_conflicts:
        write_csv("_national_benchmark_conflicts.csv",
                  ["기준연월", "필드", "채택값", "다른값", "출처zip"],
                  [{"기준연월": a, "필드": b, "채택값": c, "다른값": d, "출처zip": e}
                   for (a, b, c, d, e) in national_conflicts])

    # --------------------------------------------------------------------- #
    # 리포트
    # --------------------------------------------------------------------- #
    log("처리한 zip: %d개" % len(zips))
    log("")

    explained_missing = []
    unexplained_missing = []
    for zname, k in missing_members:
        reason = KNOWN_MISSING.get((zname, k))
        if reason:
            explained_missing.append((zname, k, reason))
        else:
            unexplained_missing.append((zname, k))

    log("[누락 CSV - 사유 확인됨, 결측 아님] %d건" % len(explained_missing))
    for zname, k, reason in explained_missing:
        log("  %s" % reason)
        log("    (파일: %s / 누락 항목: %s)" % (zname, k))
    log("")

    log("[누락 CSV - 미확인] %d건" % len(unexplained_missing))
    for zname, k in unexplained_missing:
        log("  %s : %s" % (zname, k))
    log("")

    log("[C] 대상 광역 블록 없음 (해당 지역 스킵) %d건" % len(c_block_missing))
    for cprov, cregion, cperiod in c_block_missing:
        log("  %s %s (%s) : 유입 분포 파일에 '%s' 블록이 없어 산출 불가" %
            (cprov, cregion, cperiod, cprov))
    log("")

    log("[지역명 매칭 실패 / 손상] %d건" % len(match_failures))
    for zname, desc in match_failures:
        log("  %s : %s" % (zname, desc))
    log("")

    log("[전국평균 값 불일치] %d건" % len(national_conflicts))
    for a, b, c, d, e in national_conflicts:
        log("  %s %s : 채택 %s vs %s (%s)" % (a, b, c, d, e))
    if national_conflicts:
        log("  -> _national_benchmark_conflicts.csv 참고")
    log("")

    log("[데이터 정합성 검증: [A] 숙박자 비율 <-> [B] 숙박방문자비율_추이]")
    if ratio_cmp_total > 0 and ratio_cmp_mismatch == 0:
        log("  데이터 정합성 검증: 두 소스 완전 일치")
        log("  (비교 %d행 전부 일치, 불일치 0, 최대차이 %.4f)"
            % (ratio_cmp_total, ratio_cmp_maxdiff))
    else:
        log("  비교 %d행 / 불일치 %d행 (허용오차 %.2f 초과) / 최대차이 %.4f @ %s"
            % (ratio_cmp_total, ratio_cmp_mismatch, RATIO_DIFF_TOL,
               ratio_cmp_maxdiff, ratio_cmp_maxloc or "-"))
    log("  ※ 두 컬럼 모두 tourism_panel.csv 에 계획대로 유지")
    log("")

    qcode_map = defaultdict(set)
    for r in quadrant_rows:
        qcode_map[r["지역명"]].add(r["지역코드"])
    qdup = {n: sorted(v) for n, v in qcode_map.items() if len(v) > 1}
    log("[quadrant_snapshots 지역명 중복 -> 지역코드 기준 조인] %d건" % len(qdup))
    for n, codes in sorted(qdup.items()):
        log("  '%s' : 지역코드 %s" % (n, " / ".join(codes)))
    log("  방침: 지역명+기간은 유일하지 않다. 다운스트림 조인은 반드시 지역코드를 키로 한다.")
    log("")

    log("[패널 중복 제거] (광역, 지역명, 기준연월) 기준 %d건 드롭" % len(dropped))
    for k in dropped[:50]:
        log("  %s" % (k,))
    if len(dropped) > 50:
        log("  ... 외 %d건" % (len(dropped) - 50))
    log("")

    log("[최종 산출물 행수]")
    log("  tourism_panel.csv          : %d" % len(dedup_panel))
    log("  national_benchmark.csv     : %d" % len(nat_rows))
    log("  region_static_features.csv : %d" % len(static_rows))
    log("  quadrant_snapshots.csv     : %d" % len(quadrant_rows))
    log("")

    with open(os.path.join(OUT_DIR, "_processing_report.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(report) + "\n")

    print("\n".join(report[-12:]))
    print("\n출력 폴더: " + OUT_DIR)


if __name__ == "__main__":
    sys.exit(main())
