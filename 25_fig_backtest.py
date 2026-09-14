# -*- coding: utf-8 -*-
"""
그림: 회고 검증 — 2022년 데이터만으로 낸 진단이 이후 정책 선택과 같은 방향인가.

기존 backtest_01.png 의 결함 교정:
  · 울릉군(2022 성숙도 17.4, 2위는 3.7) 때문에 88개가 좌측 1/5에 압축 → 백분위로 변환
  · 우측 패널이 하위 1.5% > 중위 1.7% > 상위 1.3% 로 자기 주장을 반박 → 삭제
  · "5/11 적중, 우연 기대 3.7" 만 제시해 유의성을 흐림
    → 초기하 p=0.29 로 유의하지 않음을 명시하고, 유의한 연속형 검정(p=0.046)을 주력으로

정직한 한계 명시가 과대 포장보다 심사에서 유리하다는 판단.
"""
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import mannwhitneyu, hypergeom
import viz_style as V

V.apply()
FIG = "outputs/figures"
rng = np.random.default_rng(7)

bt = pd.read_csv("outputs/tables/backtest_frame.csv")
bt["pct"] = bt["체류성숙도_2022"].rank(pct=True) * 100
desig = bt["워케이션_지정"] == True
new = bt["워케이션_신규_24_25"] == True

fig, axes = plt.subplots(1, 2, figsize=(14.6, 5.8),
                         gridspec_kw={"width_ratios": [1.0, 1.15]})

# ============================================= (A) 지정지 전체 vs 비지정
ax = axes[0]
groups = [("워케이션 지정·운영\n27곳", bt.loc[desig, "pct"], V.ACCENT),
          ("비지정\n62곳", bt.loc[~desig, "pct"], "#c9c8c2")]
for i, (nm, vals, col) in enumerate(groups):
    jitter = rng.normal(0, 0.075, len(vals))
    ax.scatter(np.full(len(vals), i) + jitter, vals, s=54, color=col,
               alpha=0.85, edgecolors=V.SURF, linewidths=1.2, zorder=3)
    med = vals.median()
    ax.plot([i - 0.26, i + 0.26], [med, med], color=V.INK, lw=2.4,
            solid_capstyle="round", zorder=4)
    ax.text(i + 0.31, med, f"중앙값 {med:.0f}", va="center", ha="left",
            fontsize=9.6, color=V.INK, fontweight="bold")

u, p = mannwhitneyu(bt.loc[desig, "pct"], bt.loc[~desig, "pct"], alternative="greater")
ax.axhline(50, color=V.AXIS, lw=1.0, zorder=1)
ax.text(-0.42, 51.5, "우연 수준 (백분위 50)", fontsize=9, color=V.MUTE, va="bottom")
ax.set_xticks([0, 1])
ax.set_xticklabels([g[0] for g in groups], fontsize=10.5)
ax.set_xlim(-0.45, 2.30)
ax.set_ylim(-4, 108)
ax.set_ylabel("2022년 시점 체류 성숙도 백분위")
ax.set_axisbelow(True)
ax.grid(axis="y")
ax.spines["left"].set_visible(False)
ax.tick_params(axis="x", length=0)
ax.text(0.985, 0.035, f"Mann-Whitney 단측  p = {p:.3f}\n유의 (α = 0.05)",
        transform=ax.transAxes, ha="right", va="bottom", fontsize=9.8,
        color=V.C["blue"], fontweight="bold", linespacing=1.6,
        bbox=dict(boxstyle="round,pad=0.55", facecolor="#eaf2fd",
                  edgecolor=V.C["blue"], linewidth=1.0))
V.title(ax, "A. 구성 타당도 — 지정지가 실제로 더 성숙했다",
        "사후에 확인된 워케이션 지정·운영 지역 27곳")

# ============================================= (B) 신규 지정 11곳 예지력
ax = axes[1]
sub = bt.loc[new, ["지역명_full", "pct"]].sort_values("pct")
names = [s.split()[-1] for s in sub["지역명_full"]]
ypos = np.arange(len(sub))
cols = [V.ACCENT if v >= 100 * (1 - 30 / 89) else "#c9c8c2" for v in sub["pct"]]

ax.barh(ypos, sub["pct"], height=0.55, color=cols)
ax.axvline(50, color=V.AXIS, lw=1.0, zorder=1)
cut = 100 * (1 - 30 / 89)
ax.axvline(cut, color=V.C["blue"], lw=1.4, zorder=2)
ax.text(cut + 1.5, len(sub) - 0.35, "상위 30 컷", fontsize=9.2,
        color=V.C["blue"], fontweight="bold", va="center")
ax.set_yticks(ypos)
ax.set_yticklabels(names, fontsize=10)
ax.set_xlim(0, 116)
ax.set_xlabel("2022년 시점 체류 성숙도 백분위")
ax.set_axisbelow(True)
ax.grid(axis="x")
ax.spines["left"].set_visible(False)
ax.tick_params(axis="y", length=0)

hits = int((sub["pct"] >= cut).sum())
ph = hypergeom.sf(hits - 1, 89, len(sub), 30)
mean_pct = sub["pct"].mean()
ax.text(0.985, 0.035,
        f"상위 30 안에 {hits}/11곳 (우연 기대 3.7)\n"
        f"초기하 p = {ph:.2f}  —  유의하지 않음\n"
        f"평균 백분위 {mean_pct:.0f} (우연 50)",
        transform=ax.transAxes, ha="right", va="bottom", fontsize=9.8,
        color=V.INK2, linespacing=1.6, fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.55", facecolor="#f4f4f2",
                  edgecolor=V.AXIS, linewidth=1.0))
V.title(ax, "B. 예지력 — 방향은 맞지만 표본이 작다",
        "2024~25 신규 지정 11곳의 2022 시점 위치")

fig.text(0.005, 0.985,
         "회고 검증 — 유의한 것과 유의하지 않은 것을 나누어 밝힌다",
         fontsize=15.5, fontweight="bold", color=V.INK, va="top", ha="left")
fig.text(0.005, 0.012,
         "2022년(2022.01~2022.12) 데이터만으로 체류 성숙도를 산출하고, 2024~2026년에 확인된 "
         "워케이션 지정·운영 현황과 대조. 지정지 목록은 공식 공표 자료가 없어 복수 출처를 교차한 "
         "큐레이션 결과이며, 이 표본 한계가 (B)의 검정력을 제한한다.",
         fontsize=8.5, color=V.MUTE, va="bottom", ha="left")

fig.subplots_adjust(left=0.085, right=0.985, top=0.795, bottom=0.155, wspace=0.30)
V.save(fig, os.path.join(FIG, "sub_06_backtest.png"))
