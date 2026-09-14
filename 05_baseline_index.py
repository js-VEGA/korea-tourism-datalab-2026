# -*- coding: utf-8 -*-
"""
단계 5: 베이스라인 "워케이션 잠재력 지수 v0".

master_modeling_table.csv 에서 지역당 1행 스냅샷(최근값·최근12개월·성장률)을 만들고,
89개 지역에 대해 z-score 가중합 지수를 계산한다. 대안으로 PCA 1주성분 지수도 산출.
인구감소 심각도는 지수에 섞지 않고 따로 둠(단계 9 정책매칭에서 결합).

지수 구성 (부호 = 클수록 워케이션 잠재력 ↑):
  A. 체류 구조 (이미 체류형 조짐)   w=0.45
     + 평균 체류시간, + 평균 숙박일수, + 숙박자 비율(최근12M),
     + 체류시간 전국대비차(최근12M), + 체류시간 추세(2022상→2025~26상)
  B. 수요 성장 (뜨는 곳)            w=0.30
     + 방문자수 성장률(최근12M), + 외지인 관광소비 성장률, + 내비 검색량 성장률
  C. 관광 목적성 (로컬소비 아님)     w=0.25
     + 외지인소비 비중, + 원거리(190km+) 방문 비중, + 외지인 숙박관심비율

출력:
  outputs/tables/wcation_index_v0.csv
  outputs/tables/wcation_snapshot.csv
  outputs/figures/index_01_ranking_top20.png
  outputs/figures/index_02_potential_vs_decline.png
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
QUAD = os.path.join(BASE, "processed", "quadrant_snapshots.csv")
REG = os.path.join(BASE, "regions.csv")
FIG = os.path.join(BASE, "outputs", "figures")
TAB = os.path.join(BASE, "outputs", "tables")
os.makedirs(FIG, exist_ok=True)
os.makedirs(TAB, exist_ok=True)

RECENT_12 = (202507, 202606)
PREV_12 = (202407, 202506)


def zscore(s):
    s = pd.to_numeric(s, errors="coerce")
    return (s - s.mean()) / s.std(ddof=0)


def growth(df, col, a, b):
    r = df[df["기준연월"].between(*a)].groupby("지역명_full")[col].sum()
    p = df[df["기준연월"].between(*b)].groupby("지역명_full")[col].sum()
    return (r / p - 1).rename(col + "_성장률")


def build_snapshot():
    df = pd.read_csv(MT)
    quad = pd.read_csv(QUAD, dtype={"지역코드": str})
    reg = pd.read_csv(REG, dtype={"SGG_CD": str}).rename(columns={"지역명": "지역명_full"})
    quad = quad.merge(reg, left_on="지역코드", right_on="SGG_CD", how="left")
    for c in ["평균체류시간", "평균숙박일수"]:
        quad[c] = pd.to_numeric(quad[c], errors="coerce")

    late = quad[quad["기간"] == "202501_202606"].set_index("지역명_full")
    early = quad[quad["기간"] == "202201_202306"].set_index("지역명_full")

    snap = pd.DataFrame(index=sorted(df["지역명_full"].unique()))
    snap["광역지자체명"] = df.groupby("지역명_full")["광역지자체명"].first()
    snap["평균체류시간"] = late["평균체류시간"]
    snap["평균숙박일수"] = late["평균숙박일수"]
    snap["체류시간_추세"] = late["평균체류시간"] - early["평균체류시간"]

    r12 = df[df["기준연월"].between(*RECENT_12)]
    snap["숙박자비율_최근12M"] = r12.groupby("지역명_full")["숙박자 비율"].mean()
    snap["체류시간_전국대비차_최근12M"] = r12.groupby("지역명_full")["체류시간_전국대비차"].mean()
    snap["외지인소비비중_최근12M"] = r12.groupby("지역명_full")["외지인소비_비중"].mean()

    stat_cols = ["방문_190km이상_비중", "외지인_숙박관심비율", "거주_동일광역_비중",
                 "거주_수도권_비중", "인구감소율_12개월", "인구_로그"]
    for c in stat_cols:
        snap[c] = df.groupby("지역명_full")[c].last()
    snap["총인구수"] = df.groupby("지역명_full")["총인구수"].last()

    snap["방문자수성장률"] = growth(df, "방문자수_연인원", RECENT_12, PREV_12)
    snap["외지인소비성장률"] = growth(df, "관광소비_외지인_천원", RECENT_12, PREV_12)
    snap["검색량성장률"] = growth(df, "내비_목적지검색량", RECENT_12, PREV_12)
    return snap.reset_index(names="지역명_full")


def main():
    snap = build_snapshot()
    snap.to_csv(os.path.join(TAB, "wcation_snapshot.csv"), index=False, encoding="utf-8-sig")

    A = {  # 체류 구조
        "평균체류시간": 1, "평균숙박일수": 1, "숙박자비율_최근12M": 1,
        "체류시간_전국대비차_최근12M": 1, "체류시간_추세": 1,
    }
    B = {"방문자수성장률": 1, "외지인소비성장률": 1, "검색량성장률": 1}
    C = {"외지인소비비중_최근12M": 1, "방문_190km이상_비중": 1, "외지인_숙박관심비율": 1}
    GROUP_W = {"A": 0.45, "B": 0.30, "C": 0.25}

    Z = pd.DataFrame({"지역명_full": snap["지역명_full"], "광역지자체명": snap["광역지자체명"]})
    for grp, spec in [("A", A), ("B", B), ("C", C)]:
        parts = []
        for col, sgn in spec.items():
            z = zscore(snap[col]).clip(-3, 3) * sgn
            Z["z_" + col] = z
            parts.append(z)
        Z["소계_" + grp] = pd.concat(parts, axis=1).mean(axis=1)

    Z["지수_가중합"] = sum(GROUP_W[g] * Z["소계_" + g] for g in ("A", "B", "C"))
    Z["지수_가중합_100"] = (100 * (Z["지수_가중합"] - Z["지수_가중합"].min())
                        / (Z["지수_가중합"].max() - Z["지수_가중합"].min())).round(1)

    # PCA 1주성분 (표준화된 컴포넌트 행렬)
    comp_cols = [f"z_{c}" for c in list(A) + list(B) + list(C)]
    M = Z[comp_cols].fillna(0).values
    M = M - M.mean(axis=0)
    U, S, Vt = np.linalg.svd(M, full_matrices=False)
    pc1 = M @ Vt[0]
    if np.corrcoef(pc1, Z["지수_가중합"])[0, 1] < 0:
        pc1 = -pc1
    Z["지수_PCA1"] = pc1
    Z["지수_PCA1_100"] = (100 * (pc1 - pc1.min()) / (pc1.max() - pc1.min())).round(1)
    Z["PCA1_설명분산비"] = round(float(S[0] ** 2 / (S ** 2).sum()), 3)

    Z["인구감소율_12개월"] = snap["인구감소율_12개월"]
    Z["총인구수"] = snap["총인구수"]
    Z["순위_가중합"] = Z["지수_가중합"].rank(ascending=False).astype(int)
    Z["순위_PCA"] = Z["지수_PCA1"].rank(ascending=False).astype(int)
    Z = Z.sort_values("지수_가중합", ascending=False).reset_index(drop=True)
    Z.to_csv(os.path.join(TAB, "wcation_index_v0.csv"), index=False, encoding="utf-8-sig")

    # ---- 그림 1: 상위 20 ------------------------------------------------ #
    top = Z.head(20).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 8))
    ax.barh(range(len(top)), top["지수_가중합_100"], color="#2e7d54")
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels([n.split(" ")[-1] + "  (" + n.split(" ")[0][:2] + ")" for n in top["지역명_full"]],
                       fontsize=9)
    ax.set_xlabel("워케이션 잠재력 지수 v0 (0~100, 가중합)")
    ax.set_title("워케이션 잠재력 지수 v0 — 상위 20 지역")
    for i, v in enumerate(top["지수_가중합_100"]):
        ax.text(v + 0.5, i, f"{v:.0f}", va="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "index_01_ranking_top20.png"))
    plt.close(fig)

    # ---- 그림 2: 잠재력 vs 인구감소 심각도 ---------------------------- #
    fig, ax = plt.subplots(figsize=(10, 8))
    x = Z["지수_가중합_100"]
    y = pd.to_numeric(Z["인구감소율_12개월"], errors="coerce") * 100
    ax.scatter(x, y, s=40, alpha=0.75, color="#3b6ea5", edgecolor="white", lw=0.5)
    mx, my = x.median(), y.median()
    ax.axvline(mx, color="#bbb", ls="--"); ax.axhline(my, color="#bbb", ls="--")
    pri = Z[(x >= mx) & (y >= my)]
    for _, r in pri.iterrows():
        ax.annotate(r["지역명_full"].split(" ")[-1],
                    (r["지수_가중합_100"], pd.to_numeric(r["인구감소율_12개월"]) * 100),
                    fontsize=8, xytext=(3, 2), textcoords="offset points")
    ax.set_xlabel("워케이션 잠재력 지수 v0 (0~100)")
    ax.set_ylabel("인구감소율 (최근 12개월, %)")
    ax.set_title("정책 우선순위 프레임: 잠재력(→) × 인구감소 심각도(↑)\n우상단 = 투자 1순위 후보")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "index_02_potential_vs_decline.png"))
    plt.close(fig)

    # ---- 콘솔 요약 -------------------------------------------------- #
    print("워케이션 잠재력 지수 v0")
    print("PCA1 설명분산비:", Z["PCA1_설명분산비"].iloc[0],
          " | 가중합↔PCA 순위 상관:",
          round(Z["지수_가중합"].corr(Z["지수_PCA1"], method="spearman"), 3))
    print("\n[상위 15]")
    print(Z.head(15)[["순위_가중합", "지역명_full", "지수_가중합_100", "소계_A", "소계_B", "소계_C",
                      "순위_PCA"]].to_string(index=False))
    print("\n[하위 10]")
    print(Z.tail(10)[["순위_가중합", "지역명_full", "지수_가중합_100"]].to_string(index=False))
    print("\n[정책 우선순위 (잠재력·인구감소 모두 중앙값 이상)]")
    xx = Z["지수_가중합_100"]; yy = pd.to_numeric(Z["인구감소율_12개월"], errors="coerce")
    pr = Z[(xx >= xx.median()) & (yy >= yy.median())].sort_values("지수_가중합_100", ascending=False)
    print(", ".join(pr["지역명_full"].tolist()))
    print("\n→ outputs/tables/wcation_index_v0.csv , 그림 2개")


if __name__ == "__main__":
    main()
