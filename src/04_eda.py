# -*- coding: utf-8 -*-
"""
단계 4: EDA. master_modeling_table.csv 기반 핵심 그림 + 요약 텍스트.

출력:
  outputs/figures/eda_01_quadrant_latest.png   체류시간×숙박일수 사분면 (최근 분기)
  outputs/figures/eda_02_quadrant_shift.png     사분면 이동 (2022상 → 2025~26상)
  outputs/figures/eda_03_visitor_trend.png      방문자수 지수(202201=100) 오버레이 + 중앙값
  outputs/figures/eda_04_target_corr.png        후보 피처 vs 예측타깃 상관
  outputs/tables/eda_summary.txt
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 120

BASE = os.path.dirname(os.path.abspath(__file__))
MT = os.path.join(BASE, "processed", "master_modeling_table.csv")
FIG = os.path.join(BASE, "outputs", "figures")
TAB = os.path.join(BASE, "outputs", "tables")
os.makedirs(FIG, exist_ok=True)
os.makedirs(TAB, exist_ok=True)

QUAD = os.path.join(BASE, "processed", "quadrant_snapshots.csv")
REG = os.path.join(BASE, "regions.csv")


def main():
    df = pd.read_csv(MT)
    quad = pd.read_csv(QUAD, dtype={"지역코드": str})
    reg = pd.read_csv(REG, dtype={"SGG_CD": str})
    quad = quad.merge(reg.rename(columns={"지역명": "지역명_full"}), left_on="지역코드",
                      right_on="SGG_CD", how="left")
    for c in ["평균체류시간", "평균숙박일수"]:
        quad[c] = pd.to_numeric(quad[c], errors="coerce")

    lines = ["EDA 요약", "=" * 60, ""]

    # ---- 그림 1: 최근 분기 사분면 --------------------------------------- #
    late = quad[quad["기간"] == "202501_202606"].dropna(subset=["평균체류시간", "평균숙박일수"])
    mx, my = late["평균체류시간"].median(), late["평균숙박일수"].median()
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.scatter(late["평균체류시간"], late["평균숙박일수"], s=42, alpha=0.75,
               color="#3b6ea5", edgecolor="white", linewidth=0.5)
    ax.axvline(mx, color="#999", ls="--", lw=1)
    ax.axhline(my, color="#999", ls="--", lw=1)
    # 우상단(체류시간·숙박일수 둘 다 중앙값 이상) 라벨
    topright = late[(late["평균체류시간"] >= mx) & (late["평균숙박일수"] >= my)]
    for _, r in topright.iterrows():
        ax.annotate(str(r["지역명_full"]).split(" ")[-1],
                    (r["평균체류시간"], r["평균숙박일수"]),
                    fontsize=8, xytext=(3, 3), textcoords="offset points")
    ax.set_xlabel("평균 체류시간 (분)")
    ax.set_ylabel("평균 숙박일수 (일)")
    ax.set_title("체류시간 × 숙박일수 사분면 (2025.01~2026.06)\n우상단 = 체류형(워케이션 잠재) 후보")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "eda_01_quadrant_latest.png"))
    plt.close(fig)
    lines += ["[사분면 우상단 = 체류시간·숙박일수 모두 중앙값 이상] %d개 지역" % len(topright),
              "  중앙값: 체류시간 %.0f분 / 숙박일수 %.2f일" % (mx, my),
              "  " + ", ".join(sorted(topright["지역명_full"].astype(str))), ""]

    # ---- 그림 2: 사분면 이동 ------------------------------------------- #
    early = quad[quad["기간"] == "202201_202306"].set_index("지역명_full")
    late_i = late.set_index("지역명_full")
    common = early.index.intersection(late_i.index)
    fig, ax = plt.subplots(figsize=(10, 8))
    moved_to_stay = []
    for name in common:
        x0, y0 = early.loc[name, "평균체류시간"], early.loc[name, "평균숙박일수"]
        x1, y1 = late_i.loc[name, "평균체류시간"], late_i.loc[name, "평균숙박일수"]
        if pd.isna(x0) or pd.isna(x1):
            continue
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="->", color="#b0b0b0", lw=0.7))
        if (x1 - x0) > 0 and (y1 - y0) > 0:
            moved_to_stay.append((name, (x1 - x0), (y1 - y0)))
    ax.scatter(late["평균체류시간"], late["평균숙박일수"], s=30, color="#3b6ea5",
               zorder=3, label="2025~26상")
    ax.scatter(early["평균체류시간"], early["평균숙박일수"], s=18, color="#d98c5f",
               zorder=3, label="2022상")
    ax.axvline(mx, color="#ccc", ls="--", lw=1)
    ax.axhline(my, color="#ccc", ls="--", lw=1)
    ax.set_xlabel("평균 체류시간 (분)")
    ax.set_ylabel("평균 숙박일수 (일)")
    ax.set_title("사분면 이동: 2022상 → 2025~26상 (화살표=지역별 이동)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "eda_02_quadrant_shift.png"))
    plt.close(fig)
    moved_to_stay.sort(key=lambda t: t[1] + t[2] * 100, reverse=True)
    lines += ["[체류시간·숙박일수 둘 다 증가한 지역] %d개 (체류시간 증가폭 기준 상위 15)" % len(moved_to_stay)]
    for name, dx, dy in moved_to_stay[:15]:
        lines.append("  %-22s 체류시간 +%.0f분 / 숙박일수 +%.2f일" % (str(name), dx, dy))
    lines.append("")

    # ---- 그림 3: 방문자수 지수 시계열 -------------------------------- #
    piv = df.pivot_table(index="기준연월", columns="지역명_full", values="방문자수_연인원")
    idx100 = piv.div(piv.iloc[0]).mul(100)
    fig, ax = plt.subplots(figsize=(12, 6))
    for c in idx100.columns:
        ax.plot(idx100.index.astype(str), idx100[c], color="#cccccc", lw=0.5, alpha=0.6)
    ax.plot(idx100.index.astype(str), idx100.median(axis=1), color="#c0392b", lw=2.5,
            label="89개 지역 중앙값")
    ax.set_xticks(range(0, len(idx100.index), 6))
    ax.set_xticklabels([str(x) for x in idx100.index[::6]], rotation=45)
    ax.set_ylabel("방문자수 지수 (2022.01 = 100)")
    ax.set_title("인구감소지역 방문자수 추이 (지역별 회색 + 중앙값 적색)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "eda_03_visitor_trend.png"))
    plt.close(fig)

    # 계절성: 월별 평균
    seas = df.groupby("월")["방문자수_연인원"].mean()
    seas_idx = seas / seas.mean() * 100
    lines += ["[방문자수 월별 계절성] 전체 지역 평균 (연평균=100)"]
    for m, v in seas_idx.items():
        lines.append("  %2d월: %5.1f" % (m, v))
    lines.append("")

    # ---- 그림 4: 후보 피처 vs 예측타깃 상관 -------------------------- #
    cand = ["체류시간(분)", "평균 숙박일수", "숙박자 비율", "체류시간_전국대비차",
            "숙박자비율_전국대비차", "y_yoy", "y_trend_6", "외지인소비_비중",
            "1인당_외지인관광소비_천원", "관광소비_외지인_yoy", "내비검색_yoy",
            "거주_수도권_비중", "거주_동일광역_비중", "방문_190km이상_비중",
            "외지인_숙박관심비율", "인구감소율_12개월", "인구_로그"]
    cand = [c for c in cand if c in df.columns]
    sub = df[cand + ["glog_mean_1_6"]].apply(pd.to_numeric, errors="coerce")
    corr = sub.corr()["glog_mean_1_6"].drop("glog_mean_1_6").sort_values()
    fig, ax = plt.subplots(figsize=(8, 7))
    colors = ["#c0392b" if v < 0 else "#2e7d54" for v in corr.values]
    ax.barh(range(len(corr)), corr.values, color=colors)
    ax.set_yticks(range(len(corr)))
    ax.set_yticklabels(corr.index, fontsize=9)
    ax.axvline(0, color="#333", lw=0.8)
    ax.set_xlabel("피어슨 상관계수")
    ax.set_title("후보 피처 vs 예측타깃(glog_mean_1_6 = 다음 6개월 로그성장)")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "eda_04_target_corr.png"))
    plt.close(fig)
    lines += ["[예측타깃(glog_mean_1_6) 과의 상관 — 절대값 상위]"]
    for k, v in corr.reindex(corr.abs().sort_values(ascending=False).index).items():
        lines.append("  %-24s %+.3f" % (k, v))
    lines.append("")

    # ---- 체류/성장 상위 지역 --------------------------------------- #
    lines += ["[최근 분기 평균 체류시간 상위 10]"]
    for _, r in late.nlargest(10, "평균체류시간").iterrows():
        lines.append("  %-22s %.0f분 / 숙박 %.2f일" %
                     (str(r["지역명_full"]), r["평균체류시간"], r["평균숙박일수"]))
    lines.append("")
    recent = df[df["기준연월"].between(202407, 202506)].groupby("지역명_full")["방문자수_연인원"].sum()
    prev = df[df["기준연월"].between(202307, 202406)].groupby("지역명_full")["방문자수_연인원"].sum()
    grow = (recent / prev - 1).sort_values(ascending=False)
    lines += ["[방문자수 최근 12개월 증가율 상위 10] (202407~202506 vs 202307~202406)"]
    for name, v in grow.head(10).items():
        lines.append("  %-22s %+.1f%%" % (str(name), v * 100))
    lines.append("")

    with open(os.path.join(TAB, "eda_summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\n그림 4개 → outputs/figures/ , 요약 → outputs/tables/eda_summary.txt")


if __name__ == "__main__":
    main()
