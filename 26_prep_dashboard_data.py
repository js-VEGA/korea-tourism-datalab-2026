# -*- coding: utf-8 -*-
"""
지자체 공유용 대시보드 데이터 생성.

기존 진단대시보드는 89곳 '전체 지도'라 지자체 담당자가 "우리 지역은?"에
바로 답을 못 얻는다. 여기서는 지역 단위 진단 카드에 필요한 것을 모두 만든다.
  · 지표별 백분위(89곳 중 위치)
  · 체류 3종 지표의 최근 추이 스파크라인(12개월 이동평균, 계절성 제거)
  · Tier 1 지역의 기대효과 3시나리오
  · 권고 액션 · 투자 패키지 · 분기 추적 KPI

출력: report/dashboard_data.json
"""
import json
import os
import numpy as np
import pandas as pd

OUT = "report/dashboard_data.json"

v3 = pd.read_csv("processed/region_features_v3.csv")
panel = pd.read_csv("processed/tourism_panel.csv", low_memory=False)
ip = pd.read_csv("outputs/tables/impact_projection.csv")

# 패널 지역명 → v3 지역명_full 매핑
key = {r.split()[-1]: r for r in v3["지역명_full"]}
panel["full"] = panel["지역명"].map(lambda s: key.get(str(s).split()[-1]))
panel = panel[panel["full"].notna()].sort_values(["full", "기준연월"])

# ---------------------------------------------------------------- 스파크라인
SPARK = {
    "체류시간(분)": "stay",
    "평균 숙박일수": "nights",
    "숙박자 비율": "lodge",
}
spark = {}
months = sorted(panel["기준연월"].unique())
for col, kk in SPARK.items():
    piv = panel.pivot_table(index="기준연월", columns="full", values=col)
    piv = piv.reindex(months)
    # 계절성 완화 — 12개월 중심이동평균 후 뒤쪽 42개월만 사용
    sm = piv.rolling(12, center=True, min_periods=6).mean()
    sm = sm.iloc[6:]
    for region in sm.columns:
        s = sm[region].astype(float)
        vals = [None if pd.isna(x) else round(float(x), 4) for x in s]
        spark.setdefault(region, {})[kk] = vals
spark_months = [str(m) for m in sm.index]

# ---------------------------------------------------------------- 최근 12개월 집계
last12 = panel[panel["기준연월"] >= int(months[-12])]
agg = last12.groupby("full").agg(
    소비_외지인_천원=("관광소비_외지인_천원", "sum"),
    방문자_연인원=("방문자수_연인원", "sum"),
    체류시간_평균=("체류시간(분)", "mean"),
    숙박일수_평균=("평균 숙박일수", "mean"),
    숙박자비율_평균=("숙박자 비율", "mean"),
).reset_index()

# ---------------------------------------------------------------- 기대효과
imp = ip.pivot_table(index="지역명_full", columns="시나리오",
                     values="Δ관광소비_천원", aggfunc="sum") / 1e5   # 억원
stay = ip.pivot_table(index="지역명_full", columns="시나리오",
                      values="Δ체류인구", aggfunc="sum")

# ---------------------------------------------------------------- 권고 액션
ACTION = {
    "Tier 1 (즉시 투자)": {
        "label": "즉시 투자",
        "what": "공유오피스·중장기 숙박 등 체류 인프라를 직접 조성",
        "why": "이미 워케이션형 체류 구조를 갖췄고 수요도 성장 중 — 공간만 없다",
    },
    "Tier 1- (즉시, 인구감소 완만)": {
        "label": "즉시 투자 (긴급도 한 단계 뒤)",
        "what": "Tier 1과 동일한 인프라 투자",
        "why": "체류·성장 조건은 Tier 1급이나 인구감소 긴급도가 상대적으로 낮음",
    },
    "Tier 2 (선제 육성)": {
        "label": "선제 육성",
        "what": "워케이션 패키지(업무공간+숙박+프로그램)를 신규 설계",
        "why": "체류 성숙도는 아직 낮지만 수요가 빠르게 유입 중 — 지금이 진입 시점",
    },
    "Tier 3 (유지·재활성화)": {
        "label": "유지·재활성화",
        "what": "재방문·장기체류 마케팅. 숙박 심화가 관측되면 소규모 마중물 투자",
        "why": "체류 여건은 좋으나 성장이 둔화 — 신규 조성보다 기존 자산 활용이 효율적",
    },
    "관찰": {
        "label": "관찰",
        "what": "선행지표(생활인구 배수 추세·외지인 숙박관심) 분기 모니터링",
        "why": "두 축 모두 하위 — 지금 투자하면 회수 가능성이 낮다",
    },
}
KPI = ["생활인구 배수 (KOSIS, 월간)", "평균 숙박일수 (데이터랩)",
       "숙박자 비율 (데이터랩)", "비수기 숙박 비중 · 계절 변동계수"]

PACKAGE = {   # 실행 시나리오를 작성해 둔 3곳
    "전남광주통합특별시 완도군":
        "유휴시설 리모델형 공유오피스 40~50석 + 중장기 숙박 15~20실 + 해양치유 연계 (조성비 10~15억)",
    "충청남도 부여군":
        "한옥형 공유오피스 30~40석 + '한 달 살기' 20실 (조성비 12~18억)",
    "강원특별자치도 영월군":
        "중장기 체류 트랙 신설 + 비수기 평일 숙박비 지원 (조성비 8~12억)",
}


def pct(series, value):
    return round(float((series < value).mean() * 100), 1)


regions = []
v3 = v3.merge(agg, left_on="지역명_full", right_on="full", how="left")

for _, r in v3.iterrows():
    full = r["지역명_full"]
    short = full.split()[-1]
    tier = r["Tier"]
    row = {
        "full": full,
        "name": short,
        "sido": r["광역지자체명"],
        "quad": r["사분면"],
        "tier": tier,
        "tierLabel": ACTION[tier]["label"],
        "traj": r["궤적유형"],
        "wk": bool(r["워케이션_여부"]),
        "wkLabel": (None if pd.isna(r["워케이션_라벨"]) else str(r["워케이션_라벨"])),

        "x": round(float(r["체류성숙도"]), 4),
        "y": round(float(r["성장모멘텀"]) * 100, 3),
        "score": round(float(r["우선순위_v2_100"]), 1),
        "rank": None,                                   # 아래에서 채움

        "pctX": pct(v3["체류성숙도"], r["체류성숙도"]),
        "pctY": pct(v3["성장모멘텀"], r["성장모멘텀"]),
        "pctScore": pct(v3["우선순위_v2_100"], r["우선순위_v2_100"]),

        "stay": round(float(r["체류시간_평균"]), 0) if pd.notna(r["체류시간_평균"]) else None,
        "nights": round(float(r["숙박일수_평균"]), 3) if pd.notna(r["숙박일수_평균"]) else None,
        "lodge": round(float(r["숙박자비율_평균"]), 2) if pd.notna(r["숙박자비율_평균"]) else None,
        "pctStay": pct(v3["체류시간_평균"], r["체류시간_평균"]),
        "pctNights": pct(v3["숙박일수_평균"], r["숙박일수_평균"]),
        "pctLodge": pct(v3["숙박자비율_평균"], r["숙박자비율_평균"]),

        "mult": round(float(r["생활인구_배수_평균"]), 2),
        "multTrend": round(float(r["생활인구_배수_추세_연율"]), 3),
        "pctMultTrend": pct(v3["생활인구_배수_추세_연율"], r["생활인구_배수_추세_연율"]),
        "cv": round(float(r["생활인구_변동계수"]), 3),
        "stayPop": int(r["체류인구_평균"]) if pd.notna(r["체류인구_평균"]) else None,

        "aged": round(float(r["고령화율_65"]) * 100, 1) if pd.notna(r["고령화율_65"]) else None,
        "youth": round(float(r["청년비중"]) * 100, 1) if pd.notna(r["청년비중"]) else None,
        "declineY": round(float(r["인구감소율_12개월"]) * 100, 2),

        "spend12": round(float(r["소비_외지인_천원"]) / 1e5, 0) if pd.notna(r["소비_외지인_천원"]) else None,
        "visit12": int(r["방문자_연인원"]) if pd.notna(r["방문자_연인원"]) else None,

        "what": ACTION[tier]["what"],
        "why": ACTION[tier]["why"],
        "package": PACKAGE.get(full),
        "kpi": KPI,
        "spark": spark.get(full, {}),
    }
    if full in imp.index:
        row["impact"] = {
            "min": round(float(imp.loc[full, "보수 시나리오"]) * 0.5, 0),
            "base": round(float(imp.loc[full, "보수 시나리오"]), 0),
            "mid": round(float(imp.loc[full, "중심 시나리오"]), 0),
            "popMin": int(stay.loc[full, "보수 시나리오"] * 0.5),
            "popMid": int(stay.loc[full, "중심 시나리오"]),
        }
    regions.append(row)

order = sorted(range(len(regions)), key=lambda i: -regions[i]["score"])
for rank, i in enumerate(order, 1):
    regions[i]["rank"] = rank

meta = {
    "n": len(regions),
    "period": f"{months[0]}~{months[-1]}",
    "sparkMonths": spark_months,
    "medianX": round(float(v3["체류성숙도"].median()), 4),
    "medianY": round(float(v3["성장모멘텀"].median()) * 100, 3),
    "quadCounts": v3["사분면"].value_counts().to_dict(),
    "tierCounts": v3["Tier"].value_counts().to_dict(),
    "medStay": round(float(v3["체류시간_평균"].median()), 0),
    "medNights": round(float(v3["숙박일수_평균"].median()), 3),
    "medLodge": round(float(v3["숙박자비율_평균"].median()), 2),
    "medMult": round(float(v3["생활인구_배수_평균"].median()), 2),
    "medMultTrend": round(float(v3["생활인구_배수_추세_연율"].median()), 3),
}

os.makedirs("report", exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump({"meta": meta, "regions": regions}, f, ensure_ascii=False, separators=(",", ":"))

print("saved:", OUT, f"{os.path.getsize(OUT)/1024:.0f} KB")
print("regions:", len(regions), "| spark months:", len(spark_months),
      f"({spark_months[0]}~{spark_months[-1]})")
print("Tier1 with impact:", sum(1 for r in regions if "impact" in r))
