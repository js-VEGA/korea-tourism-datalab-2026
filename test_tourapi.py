"""
한국관광공사 관광빅데이터 API (기초 지자체 지역방문자수) 호출 스크립트
==================================================================

사용 전:
  pip install requests --break-system-packages

인증키는 코드에 직접 넣지 말고 환경변수로 설정해서 씁니다.
  Windows(cmd):      set TOUR_API_KEY=발급받은_인증키(Encoding버전)
  Windows(PowerShell): $env:TOUR_API_KEY="발급받은_인증키(Encoding버전)"
  macOS/Linux:       export TOUR_API_KEY="발급받은_인증키(Encoding버전)"

주의: 인증키는 "Encoding" 버전(문자열에 %2F, %3D 같은 게 포함된 형태)을 그대로 써야 합니다.
      requests의 params={} 방식으로 넘기면 이중 인코딩되어 인증 실패(에러코드 30)가 나므로,
      아래처럼 URL 문자열에 직접 삽입하는 방식을 씁니다.
"""

import os
import time
import csv
import requests

API_KEY = os.environ.get("TOUR_API_KEY", "")
if not API_KEY:
    raise SystemExit("환경변수 TOUR_API_KEY 가 설정되지 않았습니다. 위 안내를 참고해 설정 후 다시 실행하세요.")

BASE_URL = "http://apis.data.go.kr/B551011/DataLabService/locgoRegnVisitrDDList"

REGIONS_CSV = "regions_with_api_code.csv"  # 89개 지역 (지역명, SGG_CD, API_SGG_CD)
# API_SGG_CD: TourAPI가 실제로 쓰는 코드. 대부분 SGG_CD와 같지만, 전남 16개 지역은
# 전남광주통합특별시 신설 이전 "전라남도" 시절 구코드를 API가 아직 쓰고 있어서 다름.
# (2026-08-30 확인: 담양군 12710->46710, 곡성군 12720->46720 등, build_crosswalk.py 참고)


def load_target_codes(path):
    codes = {}
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            api_code = row["API_SGG_CD"].strip()
            codes[api_code] = row["지역명"].strip()
    return codes


def call_api(start_ymd, end_ymd, page_no=1, num_of_rows=1000):
    """일별 방문자수 API 1회 호출. 응답은 JSON으로 요청."""
    url = (
        f"{BASE_URL}?serviceKey={API_KEY}"
        f"&pageNo={page_no}&numOfRows={num_of_rows}"
        f"&MobileOS=ETC&MobileApp=TourismDataLab"
        f"&startYmd={start_ymd}&endYmd={end_ymd}"
        f"&_type=json"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def test_call():
    """가장 먼저: 인증키가 정상 동작하는지 하루치 데이터로만 테스트."""
    data = call_api("20260601", "20260601", page_no=1, num_of_rows=10)
    header = data.get("response", {}).get("header", {})
    print("resultCode:", header.get("resultCode"), "/ resultMsg:", header.get("resultMsg"))

    if header.get("resultCode") != "0000":
        print("인증 실패 또는 다른 오류입니다. 에러 메시지를 확인하세요.")
        print(data)
        return False

    body = data.get("response", {}).get("body", {})
    total_count = body.get("totalCount")
    items = body.get("items", {})
    print("totalCount (해당 기간 전체 행 수):", total_count)
    print("샘플 item:", items)
    return True


def fetch_range_for_targets(start_ymd, end_ymd, target_codes, num_of_rows=1000, sleep_sec=0.3):
    """start_ymd~end_ymd 구간 전체를 페이지네이션으로 수집한 뒤,
    target_codes(89개 SGG_CD)에 해당하는 행만 걸러서 반환."""
    page_no = 1
    collected = []
    while True:
        data = call_api(start_ymd, end_ymd, page_no=page_no, num_of_rows=num_of_rows)
        header = data.get("response", {}).get("header", {})
        if header.get("resultCode") != "0000":
            print(f"[경고] {start_ymd}~{end_ymd} page {page_no} 오류: {header}")
            break

        body = data.get("response", {}).get("body", {})
        total_count = int(body.get("totalCount", 0))
        raw_items = body.get("items", {})
        item_list = raw_items.get("item", []) if isinstance(raw_items, dict) else []
        if isinstance(item_list, dict):  # 결과가 1건이면 dict로 오는 경우가 있어 보정
            item_list = [item_list]

        for item in item_list:
            if item.get("signguCode") in target_codes:
                collected.append(item)

        print(f"  {start_ymd}~{end_ymd} page {page_no}/{-(-total_count // num_of_rows)} "
              f"(누적 매칭 {len(collected)}건)")

        if page_no * num_of_rows >= total_count:
            break
        page_no += 1
        time.sleep(sleep_sec)

    return collected


if __name__ == "__main__":
    print("=== 1) 인증키 테스트 ===")
    ok = test_call()
    if not ok:
        raise SystemExit("테스트 실패. 인증키 발급 후 약 30분 대기가 필요할 수 있습니다 (매뉴얼 안내).")

    print("\n=== 2) 89개 지역만 필터링해서 하루치 수집 테스트 ===")
    target_codes = load_target_codes(REGIONS_CSV)
    print(f"대상 지역 코드 {len(target_codes)}개 로드됨")

    rows = fetch_range_for_targets("20260601", "20260601", target_codes)
    print(f"\n89개 지역에 해당하는 행: {len(rows)}건")
    for r in rows[:5]:
        print(r)

    print("\n=== 3) 빠진 지역 진단 ===")
    matched_codes = {r["signguCode"] for r in rows}
    missing_codes = set(target_codes.keys()) - matched_codes
    print(f"매칭된 지역 코드 수: {len(matched_codes)} / 89")
    print(f"빠진 지역 코드 수: {len(missing_codes)}")
    for code in sorted(missing_codes):
        print(f"  - {code} : {target_codes[code]}")

    if missing_codes:
        print("\n=== 4) 빠진 지역, 이름 기준으로 역매칭 ===")
        # 빠진 지역들의 "짧은 이름"(예: 담양군)만 추출
        missing_short_names = {
            code: target_codes[code].split()[-1]  # "전남광주통합특별시 담양군" -> "담양군"
            for code in missing_codes
        }

        # 그 날짜 전체 원자료를 다시 받아서(필터링 없이) 이름으로 매칭
        page_no = 1
        all_items = []
        while True:
            data = call_api("20260601", "20260601", page_no=page_no, num_of_rows=1000)
            body = data.get("response", {}).get("body", {})
            total_count = int(body.get("totalCount", 0))
            raw_items = body.get("items", {})
            item_list = raw_items.get("item", []) if isinstance(raw_items, dict) else []
            if isinstance(item_list, dict):
                item_list = [item_list]
            all_items.extend(item_list)
            if page_no * 1000 >= total_count:
                break
            page_no += 1

        found_via_name = {}
        for item in all_items:
            for code, short_name in missing_short_names.items():
                if item.get("signguNm") == short_name and code not in found_via_name:
                    found_via_name[code] = (item.get("signguCode"), item.get("signguNm"))

        print("우리 코드 -> API 실제 코드 매핑 (이름 기준 확인):")
        for code, short_name in missing_short_names.items():
            api_result = found_via_name.get(code)
            if api_result:
                print(f"  {code} ({short_name}) -> API 코드 {api_result[0]} ({api_result[1]})")
            else:
                print(f"  {code} ({short_name}) -> 이름으로도 못 찾음 (완전 결측 가능성)")