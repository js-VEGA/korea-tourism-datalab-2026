# -*- coding: utf-8 -*-
"""
단계 12-2 — 프레임의 회고(out-of-time) 검증.

질문: "2022년 데이터만으로 이 프레임을 돌렸다면, 이후 실제로 일어난 일을 맞혔나?"

3가지 증거:
  (1) 체류 성숙도(2022) → 2024~26 실제 체류 성장(생활인구 배수 추세)·체류시간/숙박일수 변화 예측력
  (2) 지정 예지력: 2024~25년 신규 워케이션 지정지가 2022 상위권에 있었나
  (3) 모멘텀 프록시(2022말 계절조정 추세) → 2024~26 실제 성장 상관

입력: master_modeling_table.csv, region_features_v3.csv, workation_designated_regions.csv
출력: outputs/tables/backtest_frame.csv, outputs/figures/backtest_01.png
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

BASE = os.path.dirname(os.path.abspath(__file__))
P = lambda *a: os.path.join(BASE, *a)

m = pd.read_csv(P("processed", "master_modeling_table.csv"), dtype={"기준연월": str})
v3 = pd.read_csv(P("processed", "region_features_v3.csv"))
wk = pd.read_csv(P("processed", "workation_designated_regions.csv"))

m["ym"] = pd.to_datetime(m["기준연월"], format="%Y%m")
for c in ["체류시간(분)", "평균 숙박일수", "숙박자 비율", "방문자수_연인원"]:
    m[c] = pd.to_numeric(m[c], errors="coerce")

# ---------- 2022 시점 체류 성숙도 (2022.01~2022.12 평균 z합) ----------
p22 = m[m["기준연월"].between("202201", "202212")]
g22 = p22.groupby("지역명_full").agg(
    체류시간=("체류시간(분)", "mean"),
    숙박일수=("평균 숙박일수", "mean"),
    숙박자비율=("숙박자 비율", "mean"),
).reset_index()
for c in ["체류시간", "숙박일수", "숙박자비율"]:
    g22[c + "_z"] = (g22[c] - g22[c].mean()) / g22[c].std(ddof=0)
g22["체류성숙도_2022"] = g22[["체류시간_z", "숙박일수_z", "숙박자비율_z"]].sum(axis=1)

# ---------- 2022말 모멘텀 프록시: 계절조정 추세(2022 12개월 선형기울기 × 12) ----------
def slope12(s):
    s = s.dropna()
    if len(s) < 6:
        return np.nan
    x = np.arange(len(s))
    return np.polyfit(x, s.to_numpy(), 1)[0] * 12 / (s.mean() + 1e-9)
mom = (p22.sort_values("ym").groupby("지역명_full")["방문자수_연인원"]
       .apply(slope12).rename("모멘텀프록시_2022").reset_index())

# ---------- 이후(2024.01~2026.06) 실제 결과 ----------
post = m[m["기준연월"].between("202401", "202606")]
# 계절조정 체류시간·숙박일수 변화(2024상반기 vs 2026상반기)
def change(sub, col):
    a = sub[sub["기준연월"].between("202401", "202406")][col].mean()
    b = sub[sub["기준연월"].between("202601", "202606")][col].mean()
    return (b - a) / (a + 1e-9)
rows = []
for reg, sub in post.groupby("지역명_full"):
    rows.append({
        "지역명_full": reg,
        "체류시간_변화_24_26": change(sub, "체류시간(분)"),
        "숙박일수_변화_24_26": change(sub, "평균 숙박일수"),
    })
outc = pd.DataFrame(rows)

bt = (g22[["지역명_full", "체류성숙도_2022"]]
      .merge(mom, on="지역명_full")
      .merge(outc, on="지역명_full")
      .merge(v3[["지역명_full", "생활인구_배수_추세_연율", "Tier", "우선순위_v2_100"]], on="지역명_full"))

wk_all = set(wk["지역명_full"])
wk_new = set(wk.loc[wk["추정_시작연도"] >= 2024, "지역명_full"])
bt["워케이션_지정"] = bt["지역명_full"].isin(wk_all)
bt["워케이션_신규_24_25"] = bt["지역명_full"].isin(wk_new)

def sp(a, b):
    s = bt[[a, b]].dropna()
    return round(s[a].rank().corr(s[b].rank()), 3)

print("=== (1) 2022 체류 성숙도 → 이후 실제 결과 (Spearman) ===")
print(f"  vs 생활인구 배수 추세(24~26)  : {sp('체류성숙도_2022','생활인구_배수_추세_연율')}")
print(f"  vs 체류시간 변화(24→26)       : {sp('체류성숙도_2022','체류시간_변화_24_26')}")
print(f"  vs 숙박일수 변화(24→26)       : {sp('체류성숙도_2022','숙박일수_변화_24_26')}")
print(f"  vs 최종 우선순위 v2           : {sp('체류성숙도_2022','우선순위_v2_100')}  (프레임 내적 일관성)")

print("\n=== (2) 지정 예지력 ===")
top30 = set(bt.nlargest(30, "체류성숙도_2022")["지역명_full"])
n_new = len(wk_new)
hit = len(top30 & wk_new)
base = n_new * 30 / len(bt)
print(f"  2024~25 신규 워케이션 지정 {n_new}곳 중 2022 체류성숙도 상위30에 포함: {hit}곳 (우연기대 {base:.1f}곳)")
mmed = bt["체류성숙도_2022"].median()
newdf = bt[bt["워케이션_신규_24_25"]]
print(f"  신규 지정지의 2022 체류성숙도 평균 {newdf['체류성숙도_2022'].mean():.2f}  vs 전체 평균 {bt['체류성숙도_2022'].mean():.2f}")

print("\n=== (3) 2022말 모멘텀 프록시 → 이후 실제 성장 (Spearman) ===")
print(f"  vs 생활인구 배수 추세(24~26)  : {sp('모멘텀프록시_2022','생활인구_배수_추세_연율')}")
print(f"  vs 숙박일수 변화(24→26)       : {sp('모멘텀프록시_2022','숙박일수_변화_24_26')}")

# 상위/하위 그룹 실제 성장 비교
bt["2022_등급"] = pd.qcut(bt["체류성숙도_2022"], 3, labels=["하위", "중위", "상위"])
grp = bt.groupby("2022_등급", observed=True)[["생활인구_배수_추세_연율", "숙박일수_변화_24_26", "체류시간_변화_24_26"]].mean()
print("\n=== 2022 체류성숙도 3분위별 이후(24~26) 실제 성장 평균 ===")
print(grp.round(4).to_string())

bt.to_csv(P("outputs", "tables", "backtest_frame.csv"), index=False, encoding="utf-8-sig")

# 그림
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
ax = axes[0]
s = bt.dropna(subset=["체류성숙도_2022", "생활인구_배수_추세_연율"])
ax.scatter(s["체류성숙도_2022"], s["생활인구_배수_추세_연율"], s=26,
           c=np.where(s["워케이션_지정"], "#d62728", "#7f7f7f"), alpha=.8)
ax.set_xlabel("2022년 체류 성숙도"); ax.set_ylabel("2024~26 생활인구 배수 추세(연율)")
ax.set_title(f"2022 성숙도 → 이후 체류 성장  (Spearman {sp('체류성숙도_2022','생활인구_배수_추세_연율')})\n빨강=워케이션 지정지")
ax = axes[1]
grp_plot = grp["숙박일수_변화_24_26"] * 100
ax.bar(grp_plot.index.astype(str), grp_plot.values, color=["#c6dbef", "#6baed6", "#2171b5"])
ax.set_ylabel("2024→26 숙박일수 변화 (%)")
ax.set_title("2022 체류 성숙도 등급별 이후 숙박일수 성장")
for i, v in enumerate(grp_plot.values):
    ax.text(i, v, f"{v:+.1f}%", ha="center", va="bottom")
fig.tight_layout()
fig.savefig(P("outputs", "figures", "backtest_01.png"), dpi=130)
plt.close(fig)
print("\n[그림] outputs/figures/backtest_01.png  [표] outputs/tables/backtest_frame.csv")
