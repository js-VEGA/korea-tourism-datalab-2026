# -*- coding: utf-8 -*-
"""
그림: 89곳 → Tier 배분 → Tier 1 지역별 기대효과.

기존 impact_01_projection.png 은 막대 2개짜리(=문장으로 쓰면 될 정보)라
그림 한 장을 낭비했다. 여기서는
  (A) 89곳이 어떤 액션으로 나뉘는지(정책 산출물 구조)
  (B) Tier 1 13곳 각각의 기대 추가 관광소비 범위(보수~중심) + 투자 대비 회수
를 보여 '구체성'과 '규모'를 동시에 전달한다.
"""
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import viz_style as V

V.apply()
FIG = "outputs/figures"

v3 = pd.read_csv("processed/region_features_v3.csv")
ip = pd.read_csv("outputs/tables/impact_projection.csv")

fig, axes = plt.subplots(1, 2, figsize=(15.6, 6.6),
                         gridspec_kw={"width_ratios": [1.0, 1.32]})

# ===================================================== (A) Tier 배분
ax = axes[0]
ORDER = ["Tier 1 (즉시 투자)", "Tier 1- (즉시, 인구감소 완만)", "Tier 2 (선제 육성)",
         "Tier 3 (유지·재활성화)", "관찰"]
ACTION = {
    "Tier 1 (즉시 투자)": "공유오피스 · 중장기 숙박\n체류 인프라 직접 투자",
    "Tier 1- (즉시, 인구감소 완만)": "동일 투자, 인구감소\n긴급도는 한 단계 낮음",
    "Tier 2 (선제 육성)": "워케이션 패키지\n(공간+숙박+프로그램) 신규 설계",
    "Tier 3 (유지·재활성화)": "재방문 · 장기체류 마케팅\n(숙박 심화 중 7곳은 마중물)",
    "관찰": "선행지표 분기 모니터링",
}
RAMP = [V.BLUE[700], V.BLUE[550], V.BLUE[400], V.BLUE[250], "#d9d8d2"]
cnt = v3["Tier"].value_counts()

ypos = np.arange(len(ORDER))[::-1]
vals = [int(cnt[t]) for t in ORDER]
ax.barh(ypos, vals, height=0.56, color=RAMP)
for yy, tname, vv, cc in zip(ypos, ORDER, vals, RAMP):
    ax.text(vv + 0.6, yy + 0.16, f"{vv}곳", va="center", ha="left",
            fontsize=12, fontweight="bold", color=cc if vv > 6 else V.INK2)
    ax.text(vv + 0.6, yy - 0.20, ACTION[tname], va="center", ha="left",
            fontsize=8.6, color=V.INK2, linespacing=1.45)
ax.set_yticks(ypos)
ax.set_yticklabels([t.split(" (")[0] for t in ORDER], fontsize=10.5, fontweight="bold")
ax.set_xlim(0, 46)
ax.set_xlabel("지역 수 (전체 89곳)")
ax.set_axisbelow(True)
ax.grid(axis="x")
ax.spines["left"].set_visible(False)
ax.tick_params(axis="y", length=0)
V.title(ax, "A. 89곳을 5개 액션으로 배분",
        "우선순위 점수 = 성장 모멘텀 + 인구감소율 + 지수 + 숙박관심 + 생활인구 배수 추세")

# ===================================================== (B) Tier 1 기대효과
ax = axes[1]
piv = ip.pivot_table(index="지역명_full", columns="시나리오",
                     values="Δ관광소비_천원", aggfunc="sum")
piv = piv / 1e5                       # 천원 → 억원 (1억원 = 100,000천원)
piv = piv.loc[piv["중심 시나리오"].sort_values().index]
short = [i.split()[-1] for i in piv.index]
ypos = np.arange(len(piv))

lo = piv["보수 시나리오"].values
hi = piv["중심 시나리오"].values

for yy, a, b in zip(ypos, lo, hi):
    ax.plot([a, b], [yy, yy], color=V.BLUE[250], lw=3.4, solid_capstyle="round", zorder=2)
ax.scatter(lo, ypos, s=64, color=V.BLUE[250], zorder=3, edgecolors=V.SURF, linewidths=1.4)
ax.scatter(hi, ypos, s=72, color=V.BLUE[600], zorder=3, edgecolors=V.SURF, linewidths=1.4)

for yy, b in zip(ypos, hi):
    ax.text(b + 3, yy, f"{b:,.0f}", va="center", ha="left",
            fontsize=9.4, color=V.INK2, fontweight="bold")

ax.set_yticks(ypos)
ax.set_yticklabels(short, fontsize=10)
ax.set_xlim(0, max(hi) * 1.20)
ax.set_ylim(-0.75, len(piv) + 1.5)   # 상단 여백 — 범례가 데이터를 가리지 않도록
ax.set_xlabel("3년차 기준 추가 연 관광소비 (억원) — 지역별")
ax.set_axisbelow(True)
ax.grid(axis="x")
ax.spines["left"].set_visible(False)
ax.tick_params(axis="y", length=0)

tot_lo, tot_hi = lo.sum(), hi.sum()
invest = 13 * 15
# 효과는 uplift 에 선형이므로(Δ체류인구 = 주민등록근사 × uplift) 최소 시나리오는 정확히 비례 축소된다.
# 최소 = Tier 1 13곳의 '자력' 배수 추세 중앙값(3년 환산 +0.10)만큼만 추가 상승한다고 볼 때.
tot_min = tot_lo * (0.10 / 0.20)
box = (f"Tier 1  13곳 합계   ·   투자 약 {invest:,}억원 (지역당 15억)\n"
       f"3년차 추가 연 관광소비 / 투자 대비\n"
       f"   최소 (+0.10)   {tot_min:,.0f}억   {tot_min/invest:.1f}배\n"
       f"   보수 (+0.20)   {tot_lo:,.0f}억   {tot_lo/invest:.1f}배\n"
       f"   중심 (+0.35)  {tot_hi:,.0f}억   {tot_hi/invest:.1f}배")
ax.text(0.975, 0.045, box, transform=ax.transAxes, ha="right", va="bottom",
        fontsize=9.8, color=V.INK, linespacing=1.7, fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.7", facecolor="#eaf2fd",
                  edgecolor=V.C["blue"], linewidth=1.1))

ax.legend(handles=[
    Line2D([], [], marker="o", ls="", ms=8, mfc=V.BLUE[250], mec=V.SURF,
           label="보수 시나리오 (생활인구 배수 3년 +0.20)"),
    Line2D([], [], marker="o", ls="", ms=8.5, mfc=V.BLUE[600], mec=V.SURF,
           label="중심 시나리오 (배수 3년 +0.35)"),
], loc="upper right", bbox_to_anchor=(1.0, 0.995), fontsize=9.2)

V.title(ax, "B. Tier 1 13곳 — 지역별 기대 규모",
        "인과 추정이 아니라 가정 기반 시나리오 · 가정의 위치를 아래 각주에 명시")

fig.text(0.005, 0.985,
         "진단에서 끝내지 않는다 — 89곳을 액션으로 나누고, 최우선 13곳의 규모를 계산했다",
         fontsize=15.5, fontweight="bold", color=V.INK, va="top", ha="left")
fig.text(0.005, 0.012,
         "산식: Δ체류인구 = 주민등록인구 근사 × Δ배수 · Δ관광소비 = Δ체류인구 × 1인당 연 관광소비"
         "(데이터랩 외지인 관광소비 최근 12개월 ÷ 체류인구 평균) · 조성비 15억/지역은 가정값\n"
         "가정의 위치: Tier 1 13곳의 '자력' 배수 추세는 3년 환산 -0.86~+0.48(중앙값 +0.10, 75분위 +0.37)이고 "
         "89곳 전체 중앙값은 -0.25 → +0.20/+0.35 는 보수적 가정이 아니라 상위권 수준이며,\n"
         "최소 시나리오(+0.10 = Tier 1 자력 추세 중앙값)가 하한선에 해당한다",
         fontsize=8.5, color=V.MUTE, va="bottom", ha="left", linespacing=1.6)

fig.subplots_adjust(left=0.085, right=0.985, top=0.815, bottom=0.215, wspace=0.30)
V.save(fig, os.path.join(FIG, "sub_04_impact.png"))
