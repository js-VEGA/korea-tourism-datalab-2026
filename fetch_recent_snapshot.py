"""
89개 지역 - 최근 1개월 방문자 구성비(현지인/외지인/외국인) 스냅샷
================================================================
test_tourapi.py 와 같은 폴더에서 실행합니다 (거기 정의된 함수를 재사용).

실행 전: test_tourapi.py 실행할 때와 동일하게 TOUR_API_KEY 환경변수 설정 필요.

출력: recent_visitor_composition.csv
  컬럼: 지역명, API_SGG_CD, 기간, 현지인_합계, 외지인_합계, 외국인_합계,
        전체_합계, 외지인_비중(%), 외국인_비중(%)
"""

import csv
from collections import defaultdict

from test_tourapi import call_api, load_target_codes, fetch_range_for_targets

REGIONS_CSV = "regions_with_api_code.csv"
START_YMD = "20260601"
END_YMD = "20260630"
OUTPUT_CSV = "recent_visitor_composition.csv"


def main():
    target_codes = load_target_codes(REGIONS_CSV)  # {API_SGG_CD: 지역명}
    print(f"대상 지역 {len(target_codes)}개 로드됨")

    print(f"\n{START_YMD}~{END_YMD} 구간 수집 중 (페이지네이션 진행상황 아래 표시됩니다)...")
    rows = fetch_range_for_targets(START_YMD, END_YMD, target_codes)
    print(f"\n수집된 행 수: {len(rows)}건")

    # (API_SGG_CD, touDivNm) 별 합계 누적
    sums = defaultdict(lambda: defaultdict(float))
    for r in rows:
        code = r["signguCode"]
        tou_div = r["touDivNm"]  # 현지인(a) / 외지인(b) / 외국인(c)
        try:
            num = float(r["touNum"])
        except (TypeError, ValueError):
            continue
        sums[code][tou_div] += num

    out_rows = []
    for code, region_name in target_codes.items():
        local = sums[code].get("현지인(a)", 0.0)
        visitor = sums[code].get("외지인(b)", 0.0)
        foreign = sums[code].get("외국인(c)", 0.0)
        total = local + visitor + foreign
        out_rows.append({
            "지역명": region_name,
            "API_SGG_CD": code,
            "기간": f"{START_YMD}~{END_YMD}",
            "현지인_합계": round(local, 1),
            "외지인_합계": round(visitor, 1),
            "외국인_합계": round(foreign, 1),
            "전체_합계": round(total, 1),
            "외지인_비중(%)": round(visitor / total * 100, 2) if total else None,
            "외국인_비중(%)": round(foreign / total * 100, 2) if total else None,
        })

    out_rows.sort(key=lambda r: r["지역명"])

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"\n완료: {OUTPUT_CSV} ({len(out_rows)}개 지역)")
    missing = set(target_codes.keys()) - {r["API_SGG_CD"] for r in out_rows if r["전체_합계"] > 0}
    if missing:
        print(f"[참고] 이 기간에 데이터가 전혀 없는 지역 {len(missing)}개: "
              f"{[target_codes[c] for c in missing]}")


if __name__ == "__main__":
    main()