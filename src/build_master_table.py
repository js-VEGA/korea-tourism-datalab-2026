# -*- coding: utf-8 -*-
"""
단계 3: 마스터 모델링 테이블 구축.

입력 (전부 앞 단계 산출물):
  processed/tourism_panel.csv          지역-월 (숙박/방문자/관광소비 월별)
  processed/national_benchmark.csv     기준연월별 전국평균
  processed/region_static_features.csv 지역당 1행 정적 피처
  processed/quadrant_snapshots.csv     지역코드 x 3기간 (평균 체류시간/숙박일수)
  population_89regions.csv             지역-월 총인구수
  regions.csv                          지역명(full) -> SGG_CD
  (선택) recent_visitor_composition.csv  TourAPI 외지인/외국인 비중 스냅샷

출력:
  processed/master_modeling_table.csv  지역-월 long. 파생 피처 + 예측 타깃 포함
  processed/_master_report.txt

관광소비 관계: 내국인 = 외지인 + 현지인 (실측 확인). 외지인 소비가 관광 신호.
타깃: y = 방문자수_연인원. y_lead_1..6 (수준), glog_1..6 = ln(y_lead_k) - ln(y) (로그성장).
"""

import os
import sys
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(BASE, "processed")


def period_bucket(ym: int) -> str:
    if 202201 <= ym <= 202306:
        return "202201_202306"
    if 202307 <= ym <= 202412:
        return "202307_202412"
    return "202501_202606"


def main():
    panel = pd.read_csv(os.path.join(P, "tourism_panel.csv"))
    natl = pd.read_csv(os.path.join(P, "national_benchmark.csv"))
    stat = pd.read_csv(os.path.join(P, "region_static_features.csv"))
    quad = pd.read_csv(os.path.join(P, "quadrant_snapshots.csv"))
    pop = pd.read_csv(os.path.join(BASE, "population_89regions.csv"))
    reg = pd.read_csv(os.path.join(BASE, "regions.csv"), dtype={"SGG_CD": str})

    rep = ["마스터 테이블 리포트", ""]

    # ---- 키 정리 --------------------------------------------------------- #
    panel["지역명_full"] = panel["광역지자체명"] + " " + panel["지역명"]
    panel["기준연월"] = panel["기준연월"].astype(int)
    panel = panel.merge(reg.rename(columns={"지역명": "지역명_full"})[["지역명_full", "SGG_CD"]],
                        on="지역명_full", how="left")
    assert panel["SGG_CD"].notna().all(), "SGG_CD 매칭 실패"

    pop["기준연월"] = pop["기준연월"].astype(int)
    pop = pop.rename(columns={"지역명": "지역명_full", "총인구수": "총인구수"})
    pop["총인구수"] = pd.to_numeric(pop["총인구수"], errors="coerce")

    natl["기준연월"] = natl["기준연월"].astype(int)

    quad = quad.rename(columns={
        "평균체류시간": "분기_평균체류시간", "평균숙박일수": "분기_평균숙박일수", "기간": "period_bucket"})
    quad["지역코드"] = quad["지역코드"].astype(str)
    for c in ["분기_평균체류시간", "분기_평균숙박일수"]:
        quad[c] = pd.to_numeric(quad[c], errors="coerce")

    stat = stat.drop(columns=[c for c in ["기준기간"] if c in stat.columns])

    # ---- 조인 --------------------------------------------------------------- #
    df = panel.copy()
    df["연"] = df["기준연월"] // 100
    df["월"] = df["기준연월"] % 100
    df["period_bucket"] = df["기준연월"].map(period_bucket)

    df = df.merge(pop[["지역명_full", "기준연월", "총인구수"]], on=["지역명_full", "기준연월"], how="left")
    df = df.merge(natl, on="기준연월", how="left")
    # stat 은 (광역, 지역) 로 조인 — '고성군'(강원/경남), '서구'(부산/대구) 동명이지역 때문
    df = df.merge(stat, on=["광역지자체명", "지역명"], how="left", suffixes=("", "_stat"))
    df = df.merge(quad[["지역코드", "period_bucket", "분기_평균체류시간", "분기_평균숙박일수"]],
                  left_on=["SGG_CD", "period_bucket"], right_on=["지역코드", "period_bucket"], how="left")
    df = df.drop(columns=["지역코드"])

    tourapi = os.path.join(BASE, "recent_visitor_composition.csv")
    if os.path.exists(tourapi):
        tv = pd.read_csv(tourapi)
        key = "지역명" if "지역명" in tv.columns else tv.columns[0]
        df = df.merge(tv, left_on="지역명_full" if key not in ("지역명",) else "지역명",
                      right_on=key, how="left", suffixes=("", "_tourapi"))
        rep.append("recent_visitor_composition.csv 병합됨")
    else:
        rep.append("recent_visitor_composition.csv 없음 → TourAPI 피처 생략 (나중에 재실행 시 자동 병합)")

    df = df.sort_values(["SGG_CD", "기준연월"]).reset_index(drop=True)
    g = df.groupby("SGG_CD", sort=False)

    # ---- 파생: 인구 ------------------------------------------------------- #
    df["인구_로그"] = np.log(df["총인구수"])
    df["인구_전월비"] = g["총인구수"].pct_change(1)
    df["인구_yoy"] = g["총인구수"].pct_change(12)
    df["인구감소율_12개월"] = -df["인구_yoy"]        # 양수 = 감소

    # ---- 파생: 타깃 y = 방문자수_연인원 --------------------------------- #
    y = "방문자수_연인원"
    df["y"] = df[y]
    df["y_log"] = np.log(df["y"].where(df["y"] > 0))
    for k in (1, 3, 6, 12):
        df[f"y_lag_{k}"] = g[y].shift(k)
    df["y_yoy"] = g[y].pct_change(12)
    df["y_rollmean_3"] = g[y].shift(1).rolling(3).mean().reset_index(level=0, drop=True)
    df["y_rollmean_6"] = g[y].shift(1).rolling(6).mean().reset_index(level=0, drop=True)
    df["y_rollmean_12"] = g[y].shift(1).rolling(12).mean().reset_index(level=0, drop=True)
    df["y_rollstd_6"] = g[y].shift(1).rolling(6).std().reset_index(level=0, drop=True)
    df["y_trend_6"] = df["y_rollmean_3"] / df["y_rollmean_6"] - 1

    # 계절
    df["월_sin"] = np.sin(2 * np.pi * df["월"] / 12)
    df["월_cos"] = np.cos(2 * np.pi * df["월"] / 12)

    # ---- 파생: 예측 타깃 (누수 방지 위해 마지막에) --------------------- #
    for k in range(1, 7):
        df[f"y_lead_{k}"] = g[y].shift(-k)
        df[f"glog_{k}"] = np.log(df[f"y_lead_{k}"].where(df[f"y_lead_{k}"] > 0)) - df["y_log"]
    # 6개월 누적/평균 성장
    lead_cols = [f"y_lead_{k}" for k in range(1, 7)]
    df["y_lead_mean_1_6"] = df[lead_cols].mean(axis=1)
    df["glog_mean_1_6"] = np.log(df["y_lead_mean_1_6"].where(df["y_lead_mean_1_6"] > 0)) - df["y_log"]

    # ---- 파생: 체류/숙박 전국대비 ------------------------------------- #
    df["체류시간_전국대비차"] = df["체류시간(분)"] - df["체류시간분_전국평균"]
    df["숙박자비율_전국대비차"] = df["숙박자 비율"] - df["숙박방문자비율_전국평균"]
    df["평균숙박일수_roll6"] = g["평균 숙박일수"].shift(1).rolling(6).mean().reset_index(level=0, drop=True)
    df["체류시간_roll6"] = g["체류시간(분)"].shift(1).rolling(6).mean().reset_index(level=0, drop=True)

    # ---- 파생: 관광소비 ------------------------------------------------- #
    df["외지인소비_비중"] = df["관광소비_외지인_천원"] / df["관광소비_내국인_천원"]
    df["1인당_외지인관광소비_천원"] = df["관광소비_외지인_천원"] / df["총인구수"]
    df["1인당_관광소비_천원"] = df["관광소비_내국인_천원"] / df["총인구수"]
    df["관광소비_외지인_yoy"] = g["관광소비_외지인_천원"].pct_change(12)
    df["지역화폐_소비_비중"] = df["지역화폐_소비액_천원"] / df["관광소비_내국인_천원"]

    # ---- 파생: 검색/내비 --------------------------------------------------- #
    df["내비검색_yoy"] = g["내비_목적지검색량"].pct_change(12)

    # ---- 정리 / 출력 ----------------------------------------------------- #
    front = ["SGG_CD", "광역지자체명", "지역명", "지역명_full", "기준연월", "연", "월",
             "period_bucket", "총인구수", "y", "y_log"]
    cols = front + [c for c in df.columns if c not in front]
    df = df[cols]

    out = os.path.join(P, "master_modeling_table.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")

    # ---- 리포트 --------------------------------------------------------- #
    rep.append("")
    rep.append("shape: %d행 x %d열" % df.shape)
    rep.append("지역수: %d / 월범위: %d ~ %d" %
               (df["SGG_CD"].nunique(), df["기준연월"].min(), df["기준연월"].max()))
    rep.append("")
    rep.append("[핵심 컬럼 결측]")
    for c in ["총인구수", "y", "y_lag_12", "y_yoy", "y_lead_1", "y_lead_6", "glog_mean_1_6",
              "분기_평균체류시간", "체류시간_전국대비차", "외지인소비_비중",
              "인구_yoy", "방문_2030_비중", "지역화폐_소비_비중"]:
        if c in df.columns:
            rep.append("  %-22s 결측 %4d / %d" % (c, df[c].isna().sum(), len(df)))
    rep.append("")
    # 학습 가용 표본 (lag_12 & lead_6 둘 다 있는 행)
    usable = df["y_lag_12"].notna() & df["y_lead_6"].notna() & df["y"].notna()
    rep.append("[학습 가용 표본] y_lag_12 & y_lead_6 & y 모두 존재: %d행 (월 %d~%d)" %
               (usable.sum(),
                df.loc[usable, "기준연월"].min(), df.loc[usable, "기준연월"].max()))
    rep.append("")
    rep.append("[열 목록]")
    rep.append("  " + ", ".join(df.columns))

    with open(os.path.join(P, "_master_report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(rep) + "\n")
    print("\n".join(rep))
    print("\n출력:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
