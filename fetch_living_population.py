# -*- coding: utf-8 -*-
"""
통계청(국가데이터처) '인구감소지역 생활인구' 통계를 KOSIS 공유서비스 OpenAPI 로 수집한다.
89개 인구감소지역 시군구 × 월 × (계 / 연령대별) 생활인구.

【준비】
1. KOSIS OpenAPI 인증키 발급 (무료):
   https://kosis.kr/openapi/  →  "Open API 활용신청"  →  발급된 키 복사
2. 환경변수로 등록 (코드에 하드코딩 금지):
   PowerShell:  setx KOSIS_API_KEY "발급받은키"   (새 터미널부터 적용)

【사용】
  python fetch_living_population.py --search 생활인구       # 통계표 후보 검색 → tblId 확인
  python fetch_living_population.py --meta DT_1YL12002E     # 항목/분류/기간 확인
  python fetch_living_population.py --fetch DT_1YL12002E    # 수집 (아래 기본값으로)
      → processed/living_population_raw.csv        (원자료 long)
      → processed/living_population_89regions.csv  (89개 매칭 wide: 계+연령대별 + 파생)

【확정 정보 (2026-09-02 검증)】
  - 엔드포인트: statisticsData.do 는 userStatsId 필요 → 파라미터 직접조회는
    Param/statisticsParameterData.do 를 써야 한다 (statisticsData.do 는 err 20).
  - DT_1YL12002E "인구감소지역 생활인구: 연령별(시/군/구)", orgId 101, e-지방지표
      * 항목(itmId): T001 계(명), T002 20세미만, T003 20대, T004 30대,
                     T005 40대, T006 50대, T007 60대, T008 70세 이상
      * objL1 = 행정구역별(시군구),  objL2 = 지역구분 (B1 관심 / B2 감소)
      * B2(감소) = 89개 인구감소지역.  월별, 2024.01 ~ 2026.03 (27개월)
      * 89 regions × 8 items × 27 months = 19,224 cell → 1회 요청 가능 (한도 40,000)
  - C1_NM 은 "시도 시군구" 풀네임. 시도명은 regions.csv 와 일치하나
    KOSIS "전라남도" ↔ regions.csv "전남광주통합특별시" 만 매핑 필요.
"""

import argparse
import csv
import json
import os
import sys
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "processed")
KEY = os.environ.get("KOSIS_API_KEY", "")

SEARCH_URL = "https://kosis.kr/openapi/statisticsSearch.do"
META_URL = "https://kosis.kr/openapi/statisticsData.do"
DATA_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"  # 파라미터 직접조회

# KOSIS 시도 표기 → regions.csv 지역명 시도 표기
SIDO_KOSIS_TO_REGION = {
    "전라남도": "전남광주통합특별시",
    "광주광역시": "전남광주통합특별시",
}

# DT_1YL12002E 항목 코드 → 짧은 컬럼명
AGE_ITEMS = {
    "계(명)": "생활인구_계",
    "20세미만": "생활인구_20세미만",
    "20대": "생활인구_20대",
    "30대": "생활인구_30대",
    "40대": "생활인구_40대",
    "50대": "생활인구_50대",
    "60대": "생활인구_60대",
    "70세 이상": "생활인구_70세이상",
}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print("[응답이 JSON 아님 — 앞부분]\n", raw[:800])
        sys.exit(1)


def need_key():
    if not KEY:
        print("환경변수 KOSIS_API_KEY 가 없습니다. 파일 상단 '준비' 안내 참고.")
        sys.exit(1)


def _q(params):
    return "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())


def cmd_search(term):
    need_key()
    url = SEARCH_URL + "?" + _q({
        "method": "getList", "apiKey": KEY, "format": "json", "jsonVD": "Y",
        "searchNm": term, "startCount": 1, "resultCount": 50,
    })
    data = _get(url)
    if isinstance(data, dict) and data.get("errMsg"):
        print("오류:", data)
        return
    print(f"'{term}' 검색 결과 {len(data)}건:\n")
    for d in data:
        print(f"  orgId={d.get('ORG_ID')}  tblId={d.get('TBL_ID')}")
        print(f"    {d.get('TBL_NM')}")
        print(f"    수록기간 {d.get('PRD_DE', '?')}  |  {d.get('STAT_NM', '')}\n")


def cmd_meta(org, tbl):
    need_key()
    for typ in ("ITM", "OBJ", "PRD"):
        url = META_URL + "?" + _q({
            "method": "getMeta", "apiKey": KEY, "format": "json", "jsonVD": "Y",
            "orgId": org, "tblId": tbl, "type": typ,
        })
        print(f"=== META {typ} ===")
        try:
            data = _get(url)
            print(json.dumps(data[:60] if isinstance(data, list) else data,
                             ensure_ascii=False, indent=1)[:4000])
        except SystemExit:
            pass
        print()


def _norm_full(c1_nm):
    parts = c1_nm.split(" ", 1)
    if len(parts) != 2:
        return c1_nm
    sido, sgg = parts
    sido = SIDO_KOSIS_TO_REGION.get(sido, sido)
    return f"{sido} {sgg}"


def cmd_fetch(org, tbl, prd, start, end, objl2):
    need_key()
    os.makedirs(OUT_DIR, exist_ok=True)
    params = {
        "method": "getList", "apiKey": KEY, "format": "json", "jsonVD": "Y",
        "orgId": org, "tblId": tbl,
        "objL1": "ALL", "itmId": "ALL", "prdSe": prd,
        "startPrdDe": start, "endPrdDe": end,
    }
    if objl2:
        params["objL2"] = objl2
    url = DATA_URL + "?" + _q(params)
    data = _get(url)
    if isinstance(data, dict) and data.get("errMsg"):
        print("오류:", data)
        return

    raw_path = os.path.join(OUT_DIR, "living_population_raw.csv")
    keys = sorted({k for row in data for k in row})
    with open(raw_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(data)
    print(f"원자료 {len(data)}행 → {raw_path}")

    # regions.csv 로드
    reg = {}
    with open(os.path.join(BASE, "regions.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            reg[r["지역명"].strip()] = r["SGG_CD"].strip()

    # (지역, 연월) → {짧은컬럼: 값}
    wide = {}
    unmatched = set()
    for row in data:
        full = _norm_full((row.get("C1_NM") or "").strip())
        if full not in reg:
            unmatched.add(row.get("C1_NM"))
            continue
        col = AGE_ITEMS.get((row.get("ITM_NM") or "").strip())
        if not col:
            continue
        ym = row.get("PRD_DE")
        try:
            val = float(row.get("DT")) if row.get("DT") not in (None, "", "-") else None
        except ValueError:
            val = None
        wide.setdefault((full, ym), {})[col] = val

    cols = ["지역명", "SGG_CD", "기준연월"] + list(AGE_ITEMS.values()) + [
        "생활인구_청년비중", "생활인구_고령비중"]
    tidy = os.path.join(OUT_DIR, "living_population_89regions.csv")
    n_reg = set()
    with open(tidy, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for (full, ym), d in sorted(wide.items()):
            n_reg.add(full)
            tot = d.get("생활인구_계")
            you = d.get("생활인구_20대")
            thi = d.get("생활인구_30대")
            old = d.get("생활인구_70세이상")
            rec = {"지역명": full, "SGG_CD": reg[full], "기준연월": ym}
            rec.update({k: d.get(k) for k in AGE_ITEMS.values()})
            rec["생활인구_청년비중"] = round((you + thi) / tot, 4) if tot and you is not None and thi is not None else None
            rec["생활인구_고령비중"] = round(old / tot, 4) if tot and old is not None else None
            w.writerow(rec)
    print(f"89개 매칭: {len(n_reg)}/89  → {tidy}")
    if unmatched:
        print("  매칭 실패 원지역명:", sorted(unmatched))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--search")
    ap.add_argument("--meta")
    ap.add_argument("--fetch")
    ap.add_argument("--org", default="101")
    ap.add_argument("--prd", default="M")
    ap.add_argument("--start", default="202401")
    ap.add_argument("--end", default="202603")
    ap.add_argument("--objl2", default="B2", help="지역구분: B2=감소(89개 인구감소지역), B1=관심")
    a = ap.parse_args()
    if a.search:
        cmd_search(a.search)
    elif a.meta:
        cmd_meta(a.org, a.meta)
    elif a.fetch:
        cmd_fetch(a.org, a.fetch, a.prd, a.start, a.end, a.objl2)
    else:
        ap.print_help()
