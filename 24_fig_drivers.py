# -*- coding: utf-8 -*-
"""
그림: 성장 동인 — 무엇이 체류 성장을 밀고, 무엇이 막는가.

기존 shap_01_summary_bar.png 의 결함 교정:
  · 피처명이 날것(y_rollmean_12, y_yoy, 월_cos) → 심사자가 읽을 수 있는 한글명
  · 평균 |SHAP| 막대라 촉진/억제 '방향'이 사라짐 → 타깃과의 순위상관 부호로 방향 표시
  · 상위 20개는 과다 → 상위 12개로 압축
  · x축 0.000~0.007 절대 스케일(의미 없음) → 상대 중요도 %
"""
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy.stats import spearmanr
import viz_style as V

V.apply()
FIG = "outputs/figures"
TOPN = 12

# ---- 타깃 g12 재구성 (06_forecast_model.py 와 동일 정의) ------------------
df = pd.read_csv("processed/master_modeling_table.csv", low_memory=False)
df = df.sort_values(["지역명_full", "기준연월"]).reset_index(drop=True)
lvl = df.pivot_table(index="기준연월", columns="지역명_full", values="y")
idx = list(lvl.index)
pos = {m: i for i, m in enumerate(idx)}


def wsum(origin, lo, hi, region):
    i = pos.get(origin)
    if i is None or i + lo < 0 or i + hi >= len(idx):
        return np.nan
    return float(lvl.iloc[i + lo:i + hi + 1][region].sum())


o, r = df["기준연월"], df["지역명_full"]
bwd = np.array([wsum(a, -11, 0, b) for a, b in zip(o, r)], float)
fwd = np.array([wsum(a, 1, 12, b) for a, b in zip(o, r)], float)
df["g12"] = fwd / bwd - 1

# ---- 중요도 + 방향 --------------------------------------------------------
imp = pd.read_csv("outputs/tables/importance_triangulation.csv").rename(
    columns={"Unnamed: 0": "feature"})
imp = imp.nlargest(TOPN, "SHAP").copy()
imp["중요도_pct"] = imp["SHAP"] / imp["SHAP"].sum() * 100

d = df[df["g12"].notna()]
rho = []
for f in imp["feature"]:
    if f in d.columns:
        s = d[[f, "g12"]].dropna()
        rho.append(spearmanr(s[f], s["g12"])[0] if len(s) > 30 else np.nan)
    else:
        rho.append(np.nan)
imp["rho"] = rho

# ---- 사람이 읽는 이름 ------------------------------------------------------
NAME = {
    "숙박방문자비율_전국평균": "숙박 방문자 비율 (전국평균 대비)",
    "체류시간분_전국평균": "평균 체류시간 (전국평균 대비)",
    "y_rollmean_12": "최근 12개월 평균 방문자 규모",
    "외지인_숙박관심비율": "외지인의 숙박 검색 관심도",
    "체류시간_roll6": "체류시간 6개월 이동평균",
    "분기_평균체류시간": "분기 평균 체류시간",
    "y_yoy": "방문자 전년 동월 대비 증감",
    "거주_광역HHI": "방문객 출신지 집중도 (HHI·높을수록 단일 지역 편중)",
    "지역화폐_소비_비중": "지역화폐 소비 비중",
    "숙박관심_외지인현지인차": "숙박 관심도 외지인-현지인 격차",
    "지역화폐_소비액_천원": "지역화폐 소비액",
    "방문자수_증감률": "방문자수 증감률",
    "유입기초수": "유입 기초 지자체 수 (방문객 출신지 다양성)",
    "거주_역외최대광역_비중": "역외 최대 광역 비중",
    "인구감소율_12개월": "최근 12개월 인구감소율",
    "소비_식음료업_비중": "식음료업 소비 비중",
}
imp["label"] = [NAME.get(f, f) for f in imp["feature"]]

imp = imp.sort_values("중요도_pct")
ypos = np.arange(len(imp))
cols = [V.C["blue"] if (not np.isnan(x)) and x > 0 else V.ACCENT for x in imp["rho"]]

fig, ax = plt.subplots(figsize=(12.6, 6.8))
ax.barh(ypos, imp["중요도_pct"], height=0.62, color=cols)
for yy, vv, rr in zip(ypos, imp["중요도_pct"], imp["rho"]):
    ax.text(vv + 0.4, yy, f"{vv:.1f}%", va="center", ha="left",
            fontsize=9.6, color=V.INK2, fontweight="bold")

ax.set_yticks(ypos)
ax.set_yticklabels(imp["label"], fontsize=10.2)
ax.set_xlim(0, imp["중요도_pct"].max() * 1.20)
ax.set_xlabel("상대 중요도 (상위 12개 피처의 평균 |SHAP| 합 = 100%)")
ax.set_axisbelow(True)
ax.grid(axis="x")
ax.spines["left"].set_visible(False)
ax.tick_params(axis="y", length=0)

ax.legend(handles=[
    Line2D([], [], marker="s", ls="", ms=10, mfc=V.C["blue"], mec="none",
           label="촉진 — 값이 클수록 이후 12개월 성장률이 높음"),
    Line2D([], [], marker="s", ls="", ms=10, mfc=V.ACCENT, mec="none",
           label="억제 — 값이 클수록 이후 12개월 성장률이 낮음"),
], loc="lower right", fontsize=9.6)

fig.text(0.005, 0.985,
         "성장을 미는 것과 막는 것 — 이미 성숙한 체류는 오히려 성장을 억제한다",
         fontsize=15.5, fontweight="bold", color=V.INK, va="top", ha="left")
fig.text(0.005, 0.936,
         "LightGBM(6개 기법 중 최고) SHAP 중요도 · 색은 해당 피처와 타깃의 순위상관 부호 · "
         "타깃 = 향후 12개월 방문자 합 ÷ 직전 12개월 합 - 1",
         fontsize=10, color=V.INK2, va="top", ha="left")
fig.text(0.005, 0.012,
         "중요도 3종(gain · SHAP · permutation) 순위상관 0.82~0.85로 일치 → 특정 지표에 의존한 결과가 아님",
         fontsize=8.6, color=V.MUTE, va="bottom", ha="left")

fig.subplots_adjust(left=0.345, right=0.985, top=0.875, bottom=0.115)
V.save(fig, os.path.join(FIG, "sub_05_drivers.png"))
