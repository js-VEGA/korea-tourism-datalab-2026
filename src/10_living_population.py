# -*- coding: utf-8 -*-
"""
단계 10 — 생활인구 지역 단면 피처 생성 + 기존 분석축과의 관계 진단.

입력:
  processed/living_population_89regions.csv   (89 × 27개월: 생활인구 계 + 연령대)
  population_89regions.csv                    (주민등록 총인구, 월별)
  outputs/tables/region_typology.csv          (2×2 사분면·체류성숙도·성장모멘텀)
  outputs/tables/policy_priority.csv          (Tier·우선순위)

출력:
  processed/living_population_features.csv    (89행 지역 단면 피처)
  outputs/tables/living_population_diagnostic.csv  (기존축과 상관)
  outputs/tables/policy_priority_v2.csv       (생활인구 반영 우선순위 재산출 + before/after)
  outputs/figures/living_01_multiple.png
  outputs/figures/living_02_vs_axes.png
"""
import csv, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

BASE = os.path.dirname(os.path.abspath(__file__))
P = lambda *a: os.path.join(BASE, *a)
os.makedirs(P("outputs", "figures"), exist_ok=True)
os.makedirs(P("outputs", "tables"), exist_ok=True)

# ---------- load ----------
lp = pd.read_csv(P("processed", "living_population_89regions.csv"), dtype={"기준연월": str})
pop = pd.read_csv(P("population_89regions.csv"), dtype={"기준연월": str})
pop = pop.rename(columns={"지역명": "지역명_full", "총인구수": "주민등록"})
lp = lp.rename(columns={"지역명": "지역명_full"})

df = lp.merge(pop[["지역명_full", "기준연월", "주민등록"]], on=["지역명_full", "기준연월"], how="left")
df["주민등록"] = pd.to_numeric(df["주민등록"], errors="coerce")
df["생활인구_계"] = pd.to_numeric(df["생활인구_계"], errors="coerce")
df["배수"] = df["생활인구_계"] / df["주민등록"]
df["체류인구"] = df["생활인구_계"] - df["주민등록"]        # 순유입 체류 규모(등록외국인 포함 근사)
df["청년비중"] = pd.to_numeric(df["생활인구_청년비중"], errors="coerce")

months = sorted(df["기준연월"].unique())
t_idx = {m: i for i, m in enumerate(months)}
df["t"] = df["기준연월"].map(t_idx)

# ---------- region-level features ----------
rows = []
for reg, g in df.groupby("지역명_full"):
    g = g.sort_values("t")
    mult = g["배수"].to_numpy()
    tot = g["생활인구_계"].to_numpy()
    tt = g["t"].to_numpy()
    # 배수 추세: 연율 기울기 (선형회귀 slope * 12)
    slope = np.polyfit(tt, mult, 1)[0] * 12 if len(tt) > 3 else np.nan
    rows.append({
        "지역명_full": reg,
        "생활인구_배수_평균": round(np.nanmean(mult), 3),
        "생활인구_배수_최근3M": round(np.nanmean(mult[-3:]), 3),
        "생활인구_배수_추세_연율": round(slope, 4),
        "생활인구_청년비중_평균": round(np.nanmean(g["청년비중"]), 4),
        "생활인구_변동계수": round(np.nanstd(tot) / np.nanmean(tot), 4),   # 성수기 rush vs 꾸준한 체류
        "체류인구_평균": int(np.nanmean(g["체류인구"])),
        "생활인구_계_평균": int(np.nanmean(tot)),
    })
feat = pd.DataFrame(rows)
feat.to_csv(P("processed", "living_population_features.csv"), index=False, encoding="utf-8-sig")
print(f"[피처] {len(feat)}개 지역 → processed/living_population_features.csv")
print(feat.sort_values("생활인구_배수_평균", ascending=False).head(12).to_string(index=False))

# ---------- diagnostic vs existing axes ----------
typ = pd.read_csv(P("outputs", "tables", "region_typology.csv"))
pol = pd.read_csv(P("outputs", "tables", "policy_priority.csv"))
m = feat.merge(typ[["지역명_full", "사분면", "체류성숙도", "성장모멘텀", "v1c_100", "인구감소율_12개월"]],
               on="지역명_full", how="left")
m = m.merge(pol[["지역명_full", "Tier", "우선순위_100", "인구감소율_장기", "워케이션_지정_확인"]],
            on="지역명_full", how="left")

def sp(a, b):
    s = m[[a, b]].dropna()
    return s[a].rank().corr(s[b].rank())

diag = []
for col in ["생활인구_배수_평균", "생활인구_배수_추세_연율", "생활인구_청년비중_평균", "생활인구_변동계수"]:
    diag.append({
        "피처": col,
        "vs 체류성숙도": round(sp(col, "체류성숙도"), 3),
        "vs 성장모멘텀": round(sp(col, "성장모멘텀"), 3),
        "vs v1c지수": round(sp(col, "v1c_100"), 3),
        "vs 인구감소율_장기": round(sp(col, "인구감소율_장기"), 3),
        "vs 우선순위_100": round(sp(col, "우선순위_100"), 3),
    })
diag = pd.DataFrame(diag)
diag.to_csv(P("outputs", "tables", "living_population_diagnostic.csv"), index=False, encoding="utf-8-sig")
print("\n[진단] 생활인구 피처 vs 기존 분석축 (Spearman)")
print(diag.to_string(index=False))

# ---------- policy v2: 생활인구는 '추세'만 우선순위에 반영 (수준(배수)은 검증·서술용) ----------
# 진단 결과: 생활인구 배수(수준)는 기존 우선순위와 음(-)의 상관(-0.43).
#   → 배수 최상위(양양15.5·고성14.6·가평13.2)는 이미 성숙한 계절관광·세컨하우스 벨트
#     (변동계수 0.30+ = 성수기 rush). '워케이션 투자 우선지'가 아님.
#   → 우선순위에는 **배수 추세(연율)** 만 결합(성장모멘텀과 독립적으로 +0.50 일치 = 외부검증).
#   → 배수 수준·청년비중·변동계수는 결과표에 '체류 질' 서술 컬럼으로만.
med_cv = m["생활인구_변동계수"].median()
def _quality(r):
    if pd.isna(r["생활인구_배수_추세_연율"]):
        return "데이터부족"
    rising = r["생활인구_배수_추세_연율"] > 0
    steady = r["생활인구_변동계수"] < med_cv
    if rising and steady:
        return "워케이션형 성장(추세+·안정)"
    if rising and not steady:
        return "관광수요 성장(추세+·계절변동)"
    if not rising and steady:
        return "체류 정체(안정)"
    return "계절관광 성숙(추세-·변동)"
m["체류질_구분"] = m.apply(_quality, axis=1)

def z(col):
    s = pd.to_numeric(m[col], errors="coerce")
    return (s - s.mean()) / s.std(ddof=0)

m["_z_old"] = z("우선순위_100")
m["_z_multslope"] = z("생활인구_배수_추세_연율")
m["우선순위_v2_raw"] = 0.85 * m["_z_old"] + 0.25 * m["_z_multslope"]
lo, hi = m["우선순위_v2_raw"].min(), m["우선순위_v2_raw"].max()
m["우선순위_v2_100"] = ((m["우선순위_v2_raw"] - lo) / (hi - lo) * 100).round(1)
m["순위_v1"] = m["우선순위_100"].rank(ascending=False).astype(int)
m["순위_v2"] = m["우선순위_v2_100"].rank(ascending=False).astype(int)
m["순위변동"] = m["순위_v1"] - m["순위_v2"]

out = m[["지역명_full", "사분면", "Tier", "체류질_구분",
         "우선순위_100", "우선순위_v2_100", "순위_v1", "순위_v2", "순위변동",
         "생활인구_배수_평균", "생활인구_배수_추세_연율", "생활인구_청년비중_평균", "생활인구_변동계수",
         "워케이션_지정_확인"]].copy()
out = out.sort_values("우선순위_v2_100", ascending=False)
out.to_csv(P("outputs", "tables", "policy_priority_v2.csv"), index=False, encoding="utf-8-sig")
print("\n[정책 v2] 생활인구 추세 반영 우선순위 상위 15")
print(out.head(15).to_string(index=False))
print("\n[순위변동] 상승 상위 / 하락 상위")
print(out.sort_values("순위변동", ascending=False).head(6)[["지역명_full", "순위_v1", "순위_v2", "순위변동", "생활인구_배수_추세_연율", "체류질_구분"]].to_string(index=False))
print(out.sort_values("순위변동").head(6)[["지역명_full", "순위_v1", "순위_v2", "순위변동", "생활인구_배수_추세_연율", "체류질_구분"]].to_string(index=False))

print("\n[체류질_구분 분포]")
print(m["체류질_구분"].value_counts().to_string())
print("\n[확인된 워케이션 지정지의 체류질 구분]")
print(m[m["워케이션_지정_확인"] == "O"][["지역명_full", "사분면", "체류질_구분", "생활인구_배수_평균", "생활인구_배수_추세_연율"]].to_string(index=False))

# ---------- figures ----------
fig, ax = plt.subplots(figsize=(10, 7))
top = feat.sort_values("생활인구_배수_평균", ascending=False).head(20).iloc[::-1]
ax.barh(top["지역명_full"], top["생활인구_배수_평균"], color="#2b8cbe")
ax.set_xlabel("생활인구 배수 (생활인구 ÷ 주민등록인구, 27개월 평균)")
ax.set_title("인구감소지역 생활인구 배수 상위 20")
ax.axvline(feat["생활인구_배수_평균"].median(), color="grey", ls="--", lw=1, label=f"중앙값 {feat['생활인구_배수_평균'].median():.2f}")
ax.legend()
fig.tight_layout()
fig.savefig(P("outputs", "figures", "living_01_multiple.png"), dpi=130)
plt.close(fig)

fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
for ax, xcol, xlab in [(axes[0], "체류성숙도", "체류 성숙도 (기존 A축)"),
                       (axes[1], "성장모멘텀", "성장 모멘텀 (예측 g12)")]:
    s = m[[xcol, "생활인구_배수_평균", "사분면"]].dropna()
    for q, c in zip(sorted(s["사분면"].unique()),
                    ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00"]):
        ss = s[s["사분면"] == q]
        ax.scatter(ss[xcol], ss["생활인구_배수_평균"], s=28, alpha=.8, label=q, color=c)
    rho = s[xcol].rank().corr(s["생활인구_배수_평균"].rank())
    ax.set_xlabel(xlab); ax.set_ylabel("생활인구 배수 (평균)")
    ax.set_title(f"생활인구 배수 vs {xlab}  (Spearman {rho:.2f})")
    ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(P("outputs", "figures", "living_02_vs_axes.png"), dpi=130)
plt.close(fig)
print("\n[그림] outputs/figures/living_01_multiple.png, living_02_vs_axes.png")
