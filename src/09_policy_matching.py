# -*- coding: utf-8 -*-
"""
단계 9: 정책 매칭 / 투자 우선순위표.

2×2 사분면(단계 8) + 인구감소 심각도 + 예측 성장 모멘텀 + SHAP 동인을 결합해
89개 인구감소지역의 워케이션 인프라 투자 우선순위와 권고 액션을 도출한다.

인구감소 심각도: 12개월 yoy 는 노이즈(남해군 이상치 등) → 장기(2021.01→2026.06) 누적
감소율을 주지표로, 12개월을 보조로.

워케이션 지정지(한국관광공사 2025, 부분·미검증): 확인된 지역만 표시. 전체 목록은
devlog 09 수집 대기. "우리 프레임이 정부가 이미 고른 지역을 상위로 잡는가" 정합성 점검용.

출력:
  outputs/tables/policy_priority.csv
  outputs/figures/policy_01_priority_matrix.png
  outputs/figures/policy_02_tier12_regions.png
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
TAB = os.path.join(BASE, "outputs", "tables")
FIG = os.path.join(BASE, "outputs", "figures")

# 한국관광공사 2025 워케이션(및 지자체 자체사업) 확인된 인구감소지역 (부분 목록, 미검증)
# 출처: KNTO 보도자료 / k-workation.com / 지자체 공고 (2026-09 기준). 전체 21개 중 확인분만.
WCATION_CONFIRMED = {
    "경상남도 남해군", "경상남도 함양군", "강원특별자치도 고성군", "강원특별자치도 영월군",
    "전북특별자치도 진안군", "경상남도 하동군", "경상남도 통영시",  # 통영은 89 외일 수 있음
}


def main():
    typ = pd.read_csv(os.path.join(TAB, "region_typology.csv"))
    v1 = pd.read_csv(os.path.join(TAB, "wcation_index_v1.csv"))
    snap = pd.read_csv(os.path.join(TAB, "wcation_snapshot.csv"))
    pop = pd.read_csv(os.path.join(BASE, "population_89regions.csv"))

    # 장기 인구감소율 (2021.01 대비 최신)
    pv = pop.pivot_table(index="지역명", columns="기준연월", values="총인구수")
    first_col = min(pv.columns)
    last_col = max(c for c in pv.columns if c <= 202606)
    longdecl = (1 - pv[last_col] / pv[first_col]).rename("인구감소율_장기")
    longdecl.index.name = "지역명_full"

    df = typ.merge(v1[["지역명_full", "v1a_100", "v1b_100", "소계_B", "소계_C"]],
                   on="지역명_full", how="left")
    df = df.merge(snap[["지역명_full", "외지인_숙박관심비율", "숙박자비율_최근12M",
                        "방문자수성장률"]], on="지역명_full", how="left")
    df = df.merge(longdecl.reset_index(), on="지역명_full", how="left")

    z = lambda s: (s - s.mean()) / s.std(ddof=0)
    # 투자 우선순위 점수: 성장 모멘텀 + 인구감소 심각도(장기) + 체류 전환 여력
    df["우선순위_raw"] = (
        1.0 * z(df["성장모멘텀"])
        + 0.7 * z(df["인구감소율_장기"])
        + 0.5 * z(df["v1c_100"])
        + 0.3 * z(df["외지인_숙박관심비율"].fillna(df["외지인_숙박관심비율"].median()))
    )
    df["우선순위_100"] = (100 * (df["우선순위_raw"] - df["우선순위_raw"].min())
                      / (df["우선순위_raw"].max() - df["우선순위_raw"].min())).round(1)

    # Tier 규칙
    decl_hi = df["인구감소율_장기"] >= df["인구감소율_장기"].median()
    def tier(r):
        if r["사분면"] == "가속 워케이션형":
            return "Tier 1 (즉시 투자)" if r["인구감소율_장기"] >= df["인구감소율_장기"].median() else "Tier 1- (즉시, 인구감소 완만)"
        if r["사분면"] == "떠오르는 잠재지":
            return "Tier 2 (선제 육성)"
        if r["사분면"] == "성숙·정체":
            return "Tier 3 (유지·재활성화)"
        return "관찰"
    df["Tier"] = df.apply(tier, axis=1)

    ACTION = {
        "가속 워케이션형": "공유오피스·중장기숙박 등 체류 인프라 직접 투자 → 방문→체류 전환. "
                     "외지인 숙박관심 높은 곳(SHAP 상위 동인) 우선.",
        "떠오르는 잠재지": "워케이션 패키지(업무공간+숙박+프로그램) 신규 설계. 수요는 유입 중이나 "
                     "체류 전환장치 부재 → 신규 체류시장 창출 여지.",
        "성숙·정체": "기존 체류 인프라 활용도 제고 — 재방문·장기체류 유도 마케팅, 콘텐츠 갱신.",
        "저잠재": "당장 인프라 투자 부적합. 수요 선행지표(검색량·소셜) 모니터링.",
    }
    df["권고_액션"] = df["사분면"].map(ACTION)
    df["워케이션_지정_확인"] = df["지역명_full"].isin(WCATION_CONFIRMED).map({True: "O", False: ""})

    cols = ["지역명_full", "광역지자체명", "사분면", "행태유형", "Tier", "우선순위_100",
            "v1c_100", "성장모멘텀", "체류성숙도", "인구감소율_장기", "인구감소율_12개월",
            "외지인_숙박관심비율", "워케이션_지정_확인", "권고_액션"]
    out = df[cols].sort_values(["Tier", "우선순위_100"], ascending=[True, False])
    out.to_csv(os.path.join(TAB, "policy_priority.csv"), index=False, encoding="utf-8-sig")

    # ---- 정합성 점검 ---- #
    conf = df[df["워케이션_지정_확인"] == "O"]
    print("=== 확인된 워케이션 지정지의 사분면 위치 (프레임 정합성 점검) ===")
    print(conf[["지역명_full", "사분면", "Tier", "우선순위_100", "v1c_100"]].to_string(index=False))
    print("\n=== Tier별 지역 수 ===")
    print(out["Tier"].value_counts().to_string())

    # ---- 그림 1: 우선순위 매트릭스 ---- #
    fig, ax = plt.subplots(figsize=(11, 8.5))
    sizes = 40 + 260 * (df["인구감소율_장기"] - df["인구감소율_장기"].min()) / \
        (df["인구감소율_장기"].max() - df["인구감소율_장기"].min())
    sc = ax.scatter(df["체류성숙도"], df["성장모멘텀"] * 100, s=sizes,
                    c=df["우선순위_100"], cmap="YlOrRd", edgecolor="#555", lw=.5)
    ax.axvline(df["체류성숙도"].median(), color="#bbb", ls="--")
    ax.axhline(df["성장모멘텀"].median() * 100, color="#bbb", ls="--")
    for _, r in df.iterrows():
        ax.annotate(r["지역명_full"].split(" ")[-1], (r["체류성숙도"], r["성장모멘텀"] * 100),
                    fontsize=6.5, xytext=(2, 2), textcoords="offset points")
    fig.colorbar(sc, label="투자 우선순위 점수 (0~100)")
    ax.set_xlabel("체류 성숙도"); ax.set_ylabel("성장 모멘텀 (예측 12M 성장률, %)")
    ax.set_title("투자 우선순위 매트릭스\n(색=우선순위 점수, 크기=장기 인구감소율)")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "policy_01_priority_matrix.png")); plt.close(fig)

    # ---- 그림 2: Tier 1~2 상위 지역 ---- #
    t12 = out[out["Tier"].str.startswith(("Tier 1", "Tier 2"))].nlargest(20, "우선순위_100").iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 8))
    colors = ["#b5651d" if "Tier 1" in t else "#2e7d54" for t in t12["Tier"]]
    ax.barh(range(len(t12)), t12["우선순위_100"], color=colors)
    ax.set_yticks(range(len(t12)))
    ax.set_yticklabels([f"{n.split(' ')[-1]}" for n in t12["지역명_full"]], fontsize=9)
    ax.set_xlabel("투자 우선순위 점수")
    ax.set_title("워케이션 인프라 투자 우선순위 — Tier 1(주황)·Tier 2(초록) 상위 20")
    for i, (v, w) in enumerate(zip(t12["우선순위_100"], t12["워케이션_지정_확인"])):
        ax.text(v + 0.5, i, ("★ " if w == "O" else "") + f"{v:.0f}", va="center", fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "policy_02_tier12_regions.png")); plt.close(fig)

    print("\n=== Tier 1 (즉시 투자) 전체 ===")
    t1 = out[out["Tier"].str.startswith("Tier 1")].sort_values("우선순위_100", ascending=False)
    print(t1[["지역명_full", "우선순위_100", "v1c_100", "인구감소율_장기", "워케이션_지정_확인"]].round(3).to_string(index=False))
    print("\n=== Tier 2 (선제 육성) 상위 12 ===")
    t2 = out[out["Tier"] == "Tier 2 (선제 육성)"].sort_values("우선순위_100", ascending=False).head(12)
    print(t2[["지역명_full", "우선순위_100", "성장모멘텀", "인구감소율_장기"]].round(3).to_string(index=False))
    print("\n→ outputs/tables/policy_priority.csv + 그림 2개")


if __name__ == "__main__":
    main()
