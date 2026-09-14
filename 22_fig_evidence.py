# -*- coding: utf-8 -*-
"""
그림: 핵심 발견 3종 증거.

(A) 인프라 공백 — 전국 공유오피스 905개 중 인구감소지역 89곳 소재 0개
(B) 생활인구 배수의 역설 — '수준'은 우선순위와 음, '추세'만 양
(C) 워케이션 지정의 집계 효과 — 처치·통제 구분 불가(DiD p >> 0.1)

기존 그림들이 저지른 실수(막대 2개짜리 차트, 자기 주장을 반박하는 패널,
방향성이 사라진 |SHAP| 막대)를 피하고 '주장 → 증거'가 1:1로 붙게 만든다.
"""
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import viz_style as V

V.apply()
FIG = "outputs/figures"

fig, axes = plt.subplots(1, 3, figsize=(15.6, 5.4))

# ===================================================== (A) 인프라 공백
ax = axes[0]
office = pd.read_csv(
    r"C:\Users\imjin\Downloads\한국문화정보원_전국 공유 오피스 시설 데이터_20221116.csv",
    encoding="cp949")
vc = office["시도 명칭"].value_counts()
top = vc.head(5)
etc = vc.iloc[5:].sum()
labels = list(top.index) + ["그 외 8개 시·도", "인구감소지역 89곳"]
vals = list(top.values) + [etc, 0]

ypos = np.arange(len(labels))[::-1]
colors = [V.BLUE[250]] * 6 + [V.ACCENT]
bars = ax.barh(ypos, vals, height=0.62, color=colors)
ax.set_yticks(ypos)
ax.set_yticklabels(labels, fontsize=10)
ax.get_yticklabels()[-1].set_color(V.ACCENT)
ax.get_yticklabels()[-1].set_fontweight("bold")
for yy, vv in zip(ypos, vals):
    if vv > 0:
        ax.text(vv + 12, yy, f"{vv:,}", va="center", ha="left",
                fontsize=10, color=V.INK2, fontweight="bold")
ax.text(12, ypos[-1], "0 개", va="center", ha="left",
        fontsize=13, color=V.ACCENT, fontweight="bold")
ax.set_xlim(0, 620)
ax.set_xlabel("공유오피스 시설 수 (개)")
ax.set_axisbelow(True)
ax.grid(axis="x")
ax.spines["left"].set_visible(False)
ax.tick_params(axis="y", length=0)
V.title(ax, "A. 민간이 통째로 건너뛴 지역",
        "전국 공유오피스 905개 · 수도권 808개(89.3%)")

# ===================================================== (B) 배수의 역설
ax = axes[1]
diag = pd.read_csv("outputs/tables/living_population_diagnostic.csv")
diag = diag.set_index("피처")
rows = [
    ("배수 '수준'\n→ 투자 우선순위", diag.loc["생활인구_배수_평균", "vs 우선순위_100"]),
    ("배수 '수준'\n→ 성장 모멘텀", diag.loc["생활인구_배수_평균", "vs 성장모멘텀"]),
    ("배수 '추세'\n→ 투자 우선순위", diag.loc["생활인구_배수_추세_연율", "vs 우선순위_100"]),
    ("배수 '추세'\n→ 성장 모멘텀", diag.loc["생활인구_배수_추세_연율", "vs 성장모멘텀"]),
]
names = [r[0] for r in rows]
vals = [float(r[1]) for r in rows]
ypos = np.arange(len(rows))[::-1]
cols = [V.ACCENT if v < 0 else V.C["blue"] for v in vals]
ax.barh(ypos, vals, height=0.58, color=cols)
ax.axvline(0, color=V.AXIS, lw=1.0)
ax.set_yticks(ypos)
ax.set_yticklabels(names, fontsize=9.4)
for yy, vv in zip(ypos, vals):
    ax.text(vv + (0.035 if vv > 0 else -0.035), yy, f"{vv:+.2f}",
            va="center", ha="left" if vv > 0 else "right",
            fontsize=10.5, fontweight="bold",
            color=V.C["blue"] if vv > 0 else V.ACCENT)
ax.set_xlim(-0.72, 0.72)
ax.set_ylim(-0.62, 3.75)
ax.set_xlabel("순위상관 ρ  (생활인구 배수 = 생활인구 ÷ 주민등록인구)")
ax.set_axisbelow(True)
ax.grid(axis="x")
ax.spines["left"].set_visible(False)
ax.tick_params(axis="y", length=0)
ax.text(-0.68, 3.46, "수준은 반대로 간다", fontsize=9.6, color=V.ACCENT,
        fontweight="bold", ha="left")
ax.text(0.68, 1.52, "추세만 같은 방향", fontsize=9.6, color=V.C["blue"],
        fontweight="bold", ha="right")
V.title(ax, "B. 생활인구 배수의 역설",
        "배수가 큰 곳은 성수기 계절관광지 → '수준'은 폐기, '추세'만 채택")

# ===================================================== (C) 지정 효과
ax = axes[2]
did = pd.read_csv("outputs/tables/event_study_did.csv")
metrics = did["지표"].tolist()
treat = did["처치 Δ(post-pre)"].astype(float).values
ctrl = did["통제 Δ"].astype(float).values

xpos = np.arange(len(metrics))
wdt = 0.3
ax.bar(xpos - wdt / 2 - 0.012, treat, wdt, color=V.C["blue"],
       label="워케이션 지정 지역 (9곳)")
ax.bar(xpos + wdt / 2 + 0.012, ctrl, wdt, color="#c9c8c2",
       label="비지정 지역 (62곳)")
ax.axhline(0, color=V.AXIS, lw=1.0)
ax.set_xticks(xpos)
ax.set_xticklabels(metrics, fontsize=10.5)
ax.set_ylabel("지정 전후 변화 (계절조정, 지역평균=1)")
ax.set_axisbelow(True)
ax.grid(axis="y")
ax.spines["left"].set_visible(False)
ax.legend(loc="lower left", fontsize=9.2)

for i, r in did.iterrows():
    hi = max(treat[i], ctrl[i], 0)
    ax.annotate(f"차이 {float(r['DiD']):+.3f}\np = {float(r['순열 p']):.2f}",
                xy=(i, hi), xytext=(i, hi + 0.022),
                ha="center", va="bottom", fontsize=9.6,
                color=V.INK2, fontweight="bold", linespacing=1.5)
ax.set_ylim(min(treat.min(), ctrl.min()) - 0.022, 0.062)
V.title(ax, "C. 지정만으로는 움직이지 않는다",
        "이중차분·고정효과 모두 효과 검출 안 됨 → 인프라 투자 병행 필요")

fig.text(0.005, 0.985,
         "세 가지 증거 — 문제는 실재하고, 통념은 틀렸으며, 지정은 충분조건이 아니다",
         fontsize=15.5, fontweight="bold", color=V.INK, va="top", ha="left")
fig.text(0.005, 0.012,
         "A: 공공데이터포털 한국문화정보원 전국 공유오피스(2022.11) · "
         "B: KOSIS 생활인구(2024.01~2026.03, 89지역×27개월) + 데이터랩 체류지표 · "
         "C: 데이터랩 89지역×54개월 패널, 순열검정 2,000회 + 지역·월 고정효과",
         fontsize=8.5, color=V.MUTE, va="bottom", ha="left")

fig.subplots_adjust(left=0.105, right=0.985, top=0.795, bottom=0.145, wspace=0.62)
V.save(fig, os.path.join(FIG, "sub_03_evidence.png"))
