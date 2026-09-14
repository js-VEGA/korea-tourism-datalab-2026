# -*- coding: utf-8 -*-
"""
한국문화정보원_전국 공유오피스 시설 데이터(905건, 2022.11) → 89개 인구감소지역별 집계.

입력: ~/Downloads/한국문화정보원_전국 공유 오피스 시설 데이터_20221116.csv  (cp949)
출력: processed/shared_office_89regions.csv
      컬럼: 지역명_full, 공유오피스_수, 공유오피스_있음(0/1), 수용인원_합_상한, 오피스타입수

주의:
  - 2022.11 기준이라 시도명이 구명칭(강원도/전라북도) → regions.csv 신명칭으로 별칭.
  - 군위군: 2022.11 당시 경상북도 → regions.csv "대구광역시 군위군" 으로 매핑.
  - 인구감소지역 대부분 0건 → 89개 전부 채우고 없으면 0.
"""
import csv, os, re

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "processed")
SRC = os.path.expanduser("~/Downloads/한국문화정보원_전국 공유 오피스 시설 데이터_20221116.csv")

SIDO_ALIAS = {
    "강원도": "강원특별자치도",
    "전라북도": "전북특별자치도",
    "전라남도": "전남광주통합특별시",
    "광주광역시": "전남광주통합특별시",
}


def cap_upper(s):
    # "1명 ~ 20명" -> 20 ;  "1명 ~ 1명" -> 1
    nums = re.findall(r"\d+", s or "")
    return int(nums[-1]) if nums else 0


def main():
    reg = {}
    with open(os.path.join(BASE, "regions.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            reg[r["지역명"].strip()] = {"공유오피스_수": 0, "수용인원_합_상한": 0,
                                       "타입들": set()}

    with open(SRC, encoding="cp949") as f:
        rd = csv.DictReader(f)
        hit = 0
        for row in rd:
            sido = (row.get("시도 명칭") or "").strip()
            sgg = (row.get("시군구 명칭") or "").strip()
            sido = SIDO_ALIAS.get(sido, sido)
            full = f"{sido} {sgg}"
            if sgg == "군위군":
                full = "대구광역시 군위군"
            if full not in reg:
                continue
            hit += 1
            reg[full]["공유오피스_수"] += 1
            reg[full]["수용인원_합_상한"] += cap_upper(row.get("수용인원"))
            t = (row.get("오피스 타입") or "").strip()
            if t:
                reg[full]["타입들"].add(t)

    path = os.path.join(OUT, "shared_office_89regions.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["지역명_full", "공유오피스_수", "공유오피스_있음",
                    "수용인원_합_상한", "오피스타입수"])
        for full, d in sorted(reg.items()):
            w.writerow([full, d["공유오피스_수"], int(d["공유오피스_수"] > 0),
                        d["수용인원_합_상한"], len(d["타입들"])])

    n_has = sum(1 for d in reg.values() if d["공유오피스_수"] > 0)
    tot = sum(d["공유오피스_수"] for d in reg.values())
    print(f"매칭된 시설 {hit}건 (전체 905건 중) → 89개 인구감소지역 소재")
    print(f"공유오피스 보유 지역: {n_has}/89, 총 {tot}개")
    print(f"→ {path}")
    top = sorted(reg.items(), key=lambda kv: -kv[1]["공유오피스_수"])[:12]
    for full, d in top:
        if d["공유오피스_수"]:
            print(f"  {full.split()[-1]:8s} {d['공유오피스_수']:3d}개  수용상한합 {d['수용인원_합_상한']}")


if __name__ == "__main__":
    main()
