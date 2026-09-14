# -*- coding: utf-8 -*-
"""
KOSIS 시군구/5세별 주민등록인구(DT_1B04005N)에서 89개 인구감소지역의
연령 구조(청년비중·고령화율·생산가능인구비중)를 수집한다.

【핵심】
  - objL1(행정구역) 코드가 4,818개(읍면동 포함) → objL1=ALL 불가(40,000셀 초과).
    KOSIS ITM 메타에서 **5자리 시군구 코드**만 추려서 89개만 지정 요청.
  - 전남 16개: regions.csv 는 신코드(12xxx), KOSIS 는 46xxx → **이름 매칭**으로 우회.
    (시도 별칭: 강원특별자치도→강원도, 전북특별자치도→전라북도, 전남광주통합특별시→전라남도)
  - 군위군: KOSIS에 27720(대구)·47720(경북) 둘 다 존재 → 대구(27720) 채택.
  - 엔드포인트: 파라미터 직접조회는 Param/statisticsParameterData.do.

【사용】  python fetch_age_population.py           (KOSIS_API_KEY 환경변수 필요)
출력:    processed/age_population_89regions.csv
"""
import csv, json, os, sys, time, urllib.parse, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "processed")
KEY = os.environ.get("KOSIS_API_KEY", "")
ORG, TBL = "101", "DT_1B04005N"
MONTHS = ["202401", "202606"]          # 시작/끝 스냅샷 (청년 유출 추세 계산용)
META_URL = "https://kosis.kr/openapi/statisticsData.do"
DATA_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

SIDO_ALIAS = {  # regions.csv 표기 → KOSIS 표기
    # KOSIS DT_1B04005N 는 강원특별자치도·전북특별자치도 신명칭을 그대로 씀(별칭 불필요).
    # 전남만 '12 전남광주통합특별시'(데이터 희소) 대신 '46 전라남도' 블록 사용.
    "전남광주통합특별시": "전라남도",
}
# 5세별(B) 코드 → 나이 하한
BAND_LOW = {"5": 0, "10": 5, "15": 10, "20": 15, "25": 20, "30": 25, "35": 30,
            "40": 35, "45": 40, "50": 45, "55": 50, "60": 55, "65": 60, "70": 65,
            "75": 70, "80": 75, "85": 80, "90": 85, "95": 90, "100": 95, "105": 100}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _q(p):
    return "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in p.items())


def main():
    if not KEY:
        print("환경변수 KOSIS_API_KEY 없음"); sys.exit(1)
    os.makedirs(OUT, exist_ok=True)

    # 1) ITM 메타 → 5자리 시군구 코드 {(시도, 시군구): code}
    meta = _get(META_URL + "?" + _q({
        "method": "getMeta", "apiKey": KEY, "format": "json", "jsonVD": "Y",
        "orgId": ORG, "tblId": TBL, "type": "ITM"}))
    A = [r for r in meta if r.get("OBJ_ID") == "A"]
    sido = {r["ITM_ID"]: r["ITM_NM"] for r in A if len(r["ITM_ID"]) == 2}
    code_by_name = {}
    for r in A:
        if len(r["ITM_ID"]) == 5:
            code_by_name[(sido.get(r.get("UP_ITM_ID"), "?"), r["ITM_NM"])] = r["ITM_ID"]

    # 2) 89개 regions.csv → KOSIS 코드
    regions = []
    with open(os.path.join(BASE, "regions.csv"), encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            full = row["지역명"].strip()
            s, g = full.split(" ", 1)
            ks = SIDO_ALIAS.get(s, s)
            code = code_by_name.get((ks, g))
            if g == "군위군":
                code = "27720"                       # 대구 편입 후 코드
            if not code:
                print("  코드 못 찾음:", full, "→", (ks, g)); continue
            regions.append((full, code))
    print(f"KOSIS 코드 매칭: {len(regions)}/89")
    code2full = {c: f for f, c in regions}

    # 3) 데이터 요청 — 이 엔드포인트는 objL1 콤마목록 미지원(err 21) → 지역별 89회 루프
    data = []
    for i, (_, code) in enumerate(regions, 1):
        params = {
            "method": "getList", "apiKey": KEY, "format": "json", "jsonVD": "Y",
            "orgId": ORG, "tblId": TBL,
            "objL1": code, "objL2": "ALL", "itmId": "T2", "prdSe": "M",
            "startPrdDe": MONTHS[0], "endPrdDe": MONTHS[-1],
        }
        d = _get(DATA_URL + "?" + _q(params))
        if isinstance(d, dict) and d.get("errMsg"):
            print(f"  [{code}] 오류:", d); continue
        data.extend(r for r in d if r.get("PRD_DE") in MONTHS)
        if i % 20 == 0:
            print(f"  ...{i}/{len(regions)}")
        time.sleep(0.15)
    print(f"원자료 {len(data)}행")

    # 4) 피벗 → 연령 구조 지표
    #    (지역, 월) -> {band_low: pop}
    acc = {}
    for r in data:
        c = r.get("C1")
        if c not in code2full:
            continue
        low = BAND_LOW.get(r.get("C2"))
        if low is None:                              # '계'(0) 등 스킵
            continue
        try:
            v = float(r.get("DT"))
        except (TypeError, ValueError):
            v = 0.0
        acc.setdefault((code2full[c], r["PRD_DE"]), {})[low] = v

    rows = []
    for (full, ym), bands in sorted(acc.items()):
        tot = sum(bands.values())
        youth = sum(v for lo, v in bands.items() if 20 <= lo <= 35)     # 20~39
        working = sum(v for lo, v in bands.items() if 15 <= lo <= 60)   # 15~64
        aged = sum(v for lo, v in bands.items() if lo >= 65)            # 65+
        child = sum(v for lo, v in bands.items() if lo < 15)            # 0~14
        rows.append({
            "지역명": full, "기준연월": ym, "총인구": int(tot),
            "청년인구_20_39": int(youth),
            "청년비중": round(youth / tot, 4) if tot else None,
            "고령화율_65": round(aged / tot, 4) if tot else None,
            "생산가능비중_15_64": round(working / tot, 4) if tot else None,
            "유소년비중_0_14": round(child / tot, 4) if tot else None,
            "노령화지수": round(aged / child, 2) if child else None,
        })

    # 추세: 두 스냅샷 간 청년비중·청년인구 변화
    by_reg = {}
    for r in rows:
        by_reg.setdefault(r["지역명"], {})[r["기준연월"]] = r
    for full, d in by_reg.items():
        if len(d) == 2:
            a, b = d[MONTHS[0]], d[MONTHS[-1]]
            for r in (a, b):
                r["청년비중_변화_24_26"] = round(b["청년비중"] - a["청년비중"], 4)
                r["청년인구_증감률_24_26"] = round(
                    (b["청년인구_20_39"] - a["청년인구_20_39"]) / a["청년인구_20_39"], 4
                ) if a["청년인구_20_39"] else None

    cols = ["지역명", "기준연월", "총인구", "청년인구_20_39", "청년비중", "고령화율_65",
            "생산가능비중_15_64", "유소년비중_0_14", "노령화지수",
            "청년비중_변화_24_26", "청년인구_증감률_24_26"]
    path = os.path.join(OUT, "age_population_89regions.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in cols})
    print(f"→ {path}  ({len(rows)}행, {len(by_reg)}개 지역)")
    # 요약
    latest = sorted([r for r in rows if r["기준연월"] == MONTHS[-1]],
                    key=lambda x: x["청년비중"] or 0, reverse=True)
    print("\n청년비중 상위 5:", [(r['지역명'].split()[-1], r['청년비중']) for r in latest[:5]])
    print("청년비중 하위 5:", [(r['지역명'].split()[-1], r['청년비중']) for r in latest[-5:]])
    print("고령화율 상위 5:", [(r['지역명'].split()[-1], r['고령화율_65'])
                          for r in sorted(latest, key=lambda x: x['고령화율_65'] or 0, reverse=True)[:5]])


if __name__ == "__main__":
    main()
