# -*- coding: utf-8 -*-
"""
그림: 2×2 진단 프레임 (대표 그림).

기존 cluster_03_two_axis.png 의 결함을 전면 교정한다.
  · 부제 오류('우하=떠오르는 잠재지' → 실제는 좌상) 수정
  · 89개 라벨 전부 찍어 중앙부가 뭉개지던 것 → Tier 1 + 검증 사례만 선별 라벨
  · 울릉군 단일 아웃라이어가 x축 80%를 잡아먹던 것 → 클립 + 주석 처리
  · tab10 기본색 → 전 그림 공통 의미 매핑(viz_style.QUAD_COLOR)
  · 사분면 배경 음영·코너 라벨 추가로 '프레임'이라는 메시지를 즉시 전달
  · 워케이션 지정지(외부 라벨)를 링으로 표시해 외부 검증을 그림 안에서 보여줌
"""
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from adjustText import adjust_text
import viz_style as V

V.apply()
FIG = "outputs/figures"
v3 = pd.read_csv("processed/region_features_v3.csv")

x = v3["체류성숙도"].astype(float)
y = v3["성장모멘텀"].astype(float) * 100          # %
mx, my = x.median(), y.median()

# --- 아웃라이어 클립(울릉군: 체류성숙도 1.74, 2위는 약 1.0) -------------
XHI = 1.05
x_plot = x.clip(upper=XHI)
out = v3.loc[x > XHI, "지역명_full"].tolist()

fig, ax = plt.subplots(figsize=(12.4, 8.0))

xlo, xhi = -1.05, XHI + 0.10
# 하단에 여백을 크게 둔다 — 사분면 코너 라벨이 데이터 점과 겹치지 않도록
ylo, yhi = y.min() - 3.4, y.max() + 1.0
ax.set_xlim(xlo, xhi)
ax.set_ylim(ylo, yhi)

# --- 사분면 배경 + 코너 라벨 -------------------------------------------
QUADS = [
    ("가속 워케이션형", (mx, xhi), (my, yhi), "right", "top",
     "체류도 성숙 · 성장도 빠름\n→ 즉시 투자"),
    ("떠오르는 잠재지", (xlo, mx), (my, yhi), "left", "top",
     "아직 미성숙 · 수요 유입 중\n→ 선제 육성"),
    ("성숙·정체", (mx, xhi), (ylo, my), "right", "bottom",
     "체류는 좋으나 성장 둔화\n→ 재활성화"),
    ("저잠재", (xlo, mx), (ylo, my), "left", "bottom",
     "두 축 모두 하위\n→ 모니터링"),
]
counts = v3["사분면"].value_counts()
for name, (x0, x1), (y0, y1), ha, va, desc in QUADS:
    ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0,
                               facecolor=V.QUAD_TINT[name], edgecolor="none", zorder=0))
    px = x1 - 0.03 * (xhi - xlo) if ha == "right" else x0 + 0.03 * (xhi - xlo)
    py = y1 - 0.03 * (yhi - ylo) if va == "top" else y0 + 0.03 * (yhi - ylo)
    ax.text(px, py, f"{name}  {counts[name]}곳", ha=ha, va=va,
            fontsize=13, fontweight="bold", color=V.QUAD_COLOR[name], zorder=1)
    ax.text(px, py - (0.055 if va == "top" else -0.085) * (yhi - ylo), desc,
            ha=ha, va=va, fontsize=9.2, color=V.INK2, linespacing=1.5, zorder=1)

# 중앙 분할선(실선 헤어라인 — 파선은 '임계값'으로 오독되므로 쓰지 않는다)
ax.axvline(mx, color=V.AXIS, lw=1.0, zorder=1)
ax.axhline(my, color=V.AXIS, lw=1.0, zorder=1)

# --- 점 -----------------------------------------------------------------
is_t1 = v3["Tier"].str.startswith("Tier 1")
is_wk = v3["워케이션_여부"].astype(bool) if v3["워케이션_여부"].dtype != object \
    else v3["워케이션_여부"].isin([True, "True", "TRUE", 1])
size = 42 + (v3["우선순위_v2_100"].fillna(0) / 100) * 150

for q in ["저잠재", "성숙·정체", "떠오르는 잠재지", "가속 워케이션형"]:
    m = v3["사분면"] == q
    ax.scatter(x_plot[m], y[m], s=size[m], c=V.QUAD_COLOR[q],
               alpha=0.90, linewidths=1.6, edgecolors=V.SURF, zorder=3)

# 워케이션 지정·운영 지역 = 주황 링(외부 검증 라벨)
ax.scatter(x_plot[is_wk], y[is_wk], s=size[is_wk] + 115, facecolors="none",
           edgecolors=V.ACCENT, linewidths=1.9, zorder=4)

# --- 선별 라벨: Tier 1 (13곳) ------------------------------------------
short = v3["지역명_full"].str.split().str[-1]
kj_idx = set(v3.index[v3["지역명_full"].str.contains("강진")])
texts = []
for i in v3.index[is_t1]:
    if i in kj_idx:          # 강진군은 아래 콜아웃이 이름을 달고 있으므로 중복 라벨 제외
        continue
    texts.append(ax.text(x_plot[i], y[i], short[i], fontsize=9.6,
                         color=V.INK, fontweight="bold", zorder=6))
for t in texts:
    V.halo(t, lw=2.8)
adjust_text(texts, ax=ax, expand=(1.25, 1.5), force_text=(0.4, 0.6),
            arrowprops=dict(arrowstyle="-", color=V.MUTE, lw=0.8, shrinkA=2, shrinkB=3))

# --- 강진군 콜아웃(2025 대회 대상 수상 지자체) --------------------------
kj = v3.index[v3["지역명_full"].str.contains("강진")]
if len(kj):
    k = kj[0]
    ax.annotate(
        "강진군\n2025 본 대회 대상 수상 지자체\n(반값여행 정책) — 사전 정보 없이\n데이터만으로 Tier 1 분류",
        xy=(x_plot[k], y[k]), xytext=(x_plot[k] - 0.50, y[k] - 3.4),
        fontsize=9.4, color=V.C["blue"], fontweight="bold", ha="left",
        linespacing=1.55, zorder=7,
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#eaf2fd",
                  edgecolor=V.C["blue"], linewidth=1.0),
        arrowprops=dict(arrowstyle="-|>", color=V.C["blue"], lw=1.4,
                        shrinkA=3, shrinkB=5, connectionstyle="arc3,rad=0.18"))

# --- 축 -----------------------------------------------------------------
ax.set_xlabel("체류 성숙도  (평균 체류시간 · 평균 숙박일수 · 숙박자 비율의 표준화 합)")
ax.set_ylabel("성장 모멘텀  (모델 예측 향후 12개월 방문자 성장률, %)")
ax.set_axisbelow(True)
for s in ("left", "bottom"):
    ax.spines[s].set_color(V.AXIS)

note = ""
if out:
    note = f"  ·  {out[0].split()[-1]}(체류 성숙도 1.74)은 단일 극단값이라 오른쪽 끝에 클립해 표시"

leg = [
    Line2D([], [], marker="o", ls="", ms=9, mfc=V.QUAD_COLOR["가속 워케이션형"],
           mec=V.SURF, label="가속 워케이션형"),
    Line2D([], [], marker="o", ls="", ms=9, mfc=V.QUAD_COLOR["떠오르는 잠재지"],
           mec=V.SURF, label="떠오르는 잠재지"),
    Line2D([], [], marker="o", ls="", ms=9, mfc=V.QUAD_COLOR["성숙·정체"],
           mec=V.SURF, label="성숙·정체"),
    Line2D([], [], marker="o", ls="", ms=9, mfc=V.QUAD_COLOR["저잠재"],
           mec=V.SURF, label="저잠재"),
    Line2D([], [], marker="o", ls="", ms=11, mfc="none", mec=V.ACCENT, mew=1.9,
           label="워케이션 지정지(외부 라벨)"),
    Line2D([], [], marker="o", ls="", ms=6, mfc=V.MUTE, mec=V.SURF,
           label="크기 = 우선순위 점수"),
]
ax.legend(handles=leg, loc="upper center", bbox_to_anchor=(0.5, -0.095),
          ncol=6, frameon=False, fontsize=9.2)

fig.text(0.005, 0.985,
         "두 축은 서로 독립이다 — 그래서 한 줄로 줄 세울 수 없다",
         fontsize=16, fontweight="bold", color=V.INK, va="top", ha="left")
fig.text(0.005, 0.938,
         "체류 성숙도와 성장 모멘텀의 순위상관 ρ = -0.15 (p = 0.17, 유의하지 않음)."
         "  ·  인구감소지역 89곳 전수 · 굵은 라벨 = Tier 1(즉시 투자) 13곳",
         fontsize=10.3, color=V.INK2, va="top", ha="left")

fig.text(0.005, 0.006,
         "사분면 경계 = 두 축의 중앙값" + note,
         fontsize=8.6, color=V.MUTE, va="bottom", ha="left")

fig.subplots_adjust(left=0.062, right=0.985, top=0.885, bottom=0.145)
V.save(fig, os.path.join(FIG, "sub_02_frame.png"))
