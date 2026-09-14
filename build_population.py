# -*- coding: utf-8 -*-
"""
KOSIS DT_1B040A3 (행정구역별 총인구, 월별) 원자료에서 89개 인구감소지역의
월별 총인구수를 재추출해 population_89regions.csv 를 재생성한다.

기존 파일의 문제 (2026-09-01 발견):
  - 전남 16개 지역: KOSIS에 "전남광주통합특별시" 블록이 있으나 데이터가 1개월치뿐.
    실제 시계열은 전통 "전라남도" 블록에 있음 → 잘못된 블록에 매칭돼 있었음.
  - 대구 군위군: 2023.07 대구 편입. 경상북도 블록(2021.01~2023.06) +
    대구광역시 블록(2023.07~) 로 분리 → 이어붙여야 함.

원자료 구조: 세로로 시도 마커 행과 시군구 행이 섞인 flat list. 열에 "2021.01 월" ...
"2026.07 월". 항목=총인구수[명] 행만 사용. 시군구명에 광역 접두어 없음 → 블록 추적.
"""

import csv
import os
import re
import sys

import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
KOSIS_SRC = os.environ.get(
    "KOSIS_POP_CSV",
    os.path.join(os.path.expanduser("~"), "Downloads", "101_DT_1B040A3_20260830190223.csv"),
)
REGIONS_CSV = os.path.join(BASE, "regions.csv")
OUT_CSV = os.path.join(BASE, "population_89regions.csv")

SIDO_MARKERS = {
    "전국", "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
    "충청북도", "충청남도", "전북특별자치도", "전라남도", "경상북도", "경상남도",
    "제주특별자치도", "전남광주통합특별시",
}

# 타깃 광역명(regions.csv) -> KOSIS 블록명
PROV_TO_BLOCK = {
    "전남광주통합특별시": "전라남도",   # 통합특별시 블록은 1개월치뿐
}


def load_kosis():
    df = pd.read_csv(KOSIS_SRC, encoding="cp949", dtype=str)
    name_col, item_col = df.columns[0], df.columns[1]
    tot = df[df[item_col].astype(str).str.contains("총인구", na=False)].reset_index(drop=True)

    mon_cols = [c for c in df.columns if re.match(r"\d{4}\.\d{2}", str(c))]
    ym_map = {c: c[:4] + c[5:7] for c in mon_cols}   # "2021.01 월" -> "202101"

    names = tot[name_col].tolist()
    # 블록 경계: 시도 마커가 나오는 인덱스
    marks = [i for i, n in enumerate(names) if n in SIDO_MARKERS]
    blocks = {}   # 블록명 -> (start, end)
    for k, i in enumerate(marks):
        end = marks[k + 1] if k + 1 < len(marks) else len(names)
        blocks[names[i]] = (i + 1, end)   # 마커 다음 행부터

    def row_series(idx):
        r = tot.iloc[idx]
        out = {}
        for c in mon_cols:
            v = pd.to_numeric(r[c], errors="coerce")
            if pd.notna(v):
                out[ym_map[c]] = int(round(v))
        return out

    def find(block_name, region):
        s, e = blocks[block_name]
        for j in range(s, e):
            if names[j].strip() == region:
                return row_series(j)
        return {}

    return blocks, find


def main():
    if not os.path.exists(KOSIS_SRC):
        print("KOSIS 원자료 없음:", KOSIS_SRC)
        print("환경변수 KOSIS_POP_CSV 로 경로 지정 가능")
        return 1

    with open(REGIONS_CSV, encoding="utf-8-sig") as f:
        targets = [row["지역명"].strip() for row in csv.DictReader(f)]

    _, find = load_kosis()

    rows = []
    report = []
    for full in sorted(targets):
        prov, region = full.split(" ", 1)
        block = PROV_TO_BLOCK.get(prov, prov)
        series = find(block, region)

        if full == "대구광역시 군위군":
            # 대구 블록(최근) + 경북 블록(과거) 이어붙이기
            late = find("대구광역시", "군위군")
            early = find("경상북도", "군위군")
            series = dict(early)
            series.update(late)   # 겹치면 대구값 우선

        if not series:
            report.append("  [실패] %s (블록=%s) : 매칭 행 없음" % (full, block))
            continue
        for ym in sorted(series):
            rows.append({"지역명": full, "기준연월": ym, "총인구수": series[ym]})
        report.append("  %-22s 블록=%-10s 개월=%d (%s~%s)" %
                      (full, block, len(series), min(series), max(series)))

    rows.sort(key=lambda r: (r["지역명"], r["기준연월"]))
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["지역명", "기준연월", "총인구수"])
        w.writeheader()
        w.writerows(rows)

    n_reg = len({r["지역명"] for r in rows})
    months = sorted({r["기준연월"] for r in rows})
    print("population_89regions.csv 재생성")
    print("  지역수: %d / %d" % (n_reg, len(targets)))
    print("  월범위: %s ~ %s" % (months[0], months[-1]))
    print("  총 행수: %d" % len(rows))
    cov = {}
    for r in rows:
        cov[r["지역명"]] = cov.get(r["지역명"], 0) + 1
    short = {k: v for k, v in cov.items() if v < len(months)}
    print("  개월 부족 지역: %d" % len(short))
    for k, v in sorted(short.items()):
        print("    %s : %d개월" % (k, v))
    print("\n[지역별]")
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
