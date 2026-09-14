# -*- coding: utf-8 -*-
"""
단계 11 — 추가 데이터(연령구조 + 워케이션 큐레이션 라벨) 통합 & 프레임 검증.

입력:
  outputs/tables/region_typology.csv        (2×2·체류성숙도·성장모멘텀·v1c)
  outputs/tables/policy_priority_v2.csv      (Tier·우선순위·체류질)
  processed/age_population_89regions.csv     (연령구조 2스냅샷)
  processed/living_population_features.csv   (생활인구 배수/추세)
  processed/workation_designated_regions.csv (큐레이션 워케이션 라벨)

출력:
  processed/region_features_v3.csv           (89행 통합 피처)
  outputs/tables/validation_tier_vs_workation.csv
  outputs/tables/age_diagnostic.csv
  outputs/figures/validate_01_tier_recall.png
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
os.makedirs(P("outputs", "figures"), exist_ok=True)

typ = pd.read_csv(P("outputs", "tables", "region_typology.csv"))
pol = pd.read_csv(P("outputs", "tables", "policy_priority_v2.csv"))
age = pd.read_csv(P("processed", "age_population_89regions.csv"))
liv = pd.read_csv(P("processed", "living_population_features.csv"))
wk = pd.read_csv(P("processed", "workation_designated_regions.csv"))

age_latest = age[age["기준연월"] == age["기준연월"].max()].copy()
age_cols = ["지역명", "청년비중", "고령화율_65", "생산가능비중_15_64", "노령화지수",
            "청년비중_변화_24_26", "청년인구_증감률_24_26"]
age_latest = age_latest[age_cols].rename(columns={"지역명": "지역명_full"})

df = (typ.merge(pol[["지역명_full", "Tier", "우선순위_v2_100", "체류질_구분"]], on="지역명_full", how="left")
         .merge(age_latest, on="지역명_full", how="left")
         .merge(liv, on="지역명_full", how="left"))

wk_hi = set(wk.loc[wk["확실도"] == "높음", "지역명_full"])
wk_all = set(wk["지역명_full"])
df["워케이션_라벨"] = np.where(df["지역명_full"].isin(wk_hi), "높음",
                       np.where(df["지역명_full"].isin(wk_all), "중간이하", ""))
df["워케이션_여부"] = df["지역명_full"].isin(wk_all)

df.to_csv(P("processed", "region_features_v3.csv"), index=False, encoding="utf-8-sig")
print(f"[통합] region_features_v3.csv  {df.shape[0]}행 × {df.shape[1]}열")

# ---------- A. Tier vs 워케이션 라벨 검증 ----------
print("\n[검증 A] Tier별 워케이션 지정지 포함 (큐레이션 라벨)")
rows = []
tier_order = ["Tier 1 (즉시 투자)", "Tier 1- (즉시, 인구감소 완만)", "Tier 2 (선제 육성)",
              "Tier 3 (유지·재활성화)", "관찰"]
for t in tier_order:
    sub = df[df["Tier"] == t]
    n = len(sub)
    n_all = sub["워케이션_여부"].sum()
    n_hi = sub["지역명_full"].isin(wk_hi).sum()
    rows.append({"Tier": t, "지역수": n, "워케이션_전체": int(n_all),
                 "워케이션_확실도높음": int(n_hi),
                 "지정_비율": round(n_all / n, 2) if n else 0})
vt = pd.DataFrame(rows)
print(vt.to_string(index=False))
vt.to_csv(P("outputs", "tables", "validation_tier_vs_workation.csv"), index=False, encoding="utf-8-sig")

# 상위 Tier(1,1-,2) 가 잡아낸 지정지 재현율
top = df[df["Tier"].isin(tier_order[:3])]
rec_all = top["워케이션_여부"].sum() / df["워케이션_여부"].sum()
rec_hi = top["지역명_full"].isin(wk_hi).sum() / max(1, len(wk_hi & set(df["지역명_full"])))
prec_all = top["워케이션_여부"].sum() / len(top)
print(f"\n상위3 Tier(1·1-·2, n={len(top)}) → 지정지 재현율 전체 {rec_all:.2f} · 확실도높음 {rec_hi:.2f} · 정밀도 {prec_all:.2f}")

# 우선순위 상위 20 vs 지정지
df_s = df.sort_values("우선순위_v2_100", ascending=False)
top20 = df_s.head(20)
print(f"우선순위 상위 20 중 워케이션 지정지: {top20['워케이션_여부'].sum()}개 "
      f"({', '.join(top20.loc[top20['워케이션_여부'],'지역명_full'].str.split().str[-1])})")
print("\n미지정인데 우선순위 상위 10 (신규 후보):")
print(top20.loc[~top20["워케이션_여부"], "지역명_full"].str.split().str[-1].head(10).tolist())

# ---------- B. 연령구조 진단 ----------
def sp(a, b):
    s = df[[a, b]].dropna()
    return round(s[a].rank().corr(s[b].rank()), 3)

diag = []
for c in ["청년비중", "고령화율_65", "생산가능비중_15_64", "청년인구_증감률_24_26", "청년비중_변화_24_26"]:
    diag.append({"피처": c, "vs 체류성숙도": sp(c, "체류성숙도"),
                 "vs 성장모멘텀": sp(c, "성장모멘텀"), "vs v1c지수": sp(c, "v1c_100"),
                 "vs 우선순위v2": sp(c, "우선순위_v2_100"),
                 "vs 생활인구배수추세": sp(c, "생활인구_배수_추세_연율")})
dg = pd.DataFrame(diag)
print("\n[진단 B] 연령구조 vs 기존 축 (Spearman)")
print(dg.to_string(index=False))
dg.to_csv(P("outputs", "tables", "age_diagnostic.csv"), index=False, encoding="utf-8-sig")

# 워케이션 지정지 vs 비지정 평균 비교
print("\n[대조] 워케이션 지정지 vs 비지정 — 주요 지표 평균")
for c in ["체류성숙도", "성장모멘텀", "생활인구_배수_평균", "생활인구_배수_추세_연율",
          "청년비중", "청년인구_증감률_24_26", "우선순위_v2_100"]:
    a = df.loc[df["워케이션_여부"], c].mean()
    b = df.loc[~df["워케이션_여부"], c].mean()
    print(f"  {c:24s} 지정 {a:8.3f}  vs  비지정 {b:8.3f}")

# ---------- figure ----------
fig, ax = plt.subplots(figsize=(9, 5))
x = np.arange(len(vt))
ax.bar(x - 0.2, vt["지역수"], 0.4, label="지역 수", color="#cbd5e1")
ax.bar(x + 0.2, vt["워케이션_전체"], 0.4, label="워케이션 지정지(큐레이션)", color="#2b8cbe")
ax.bar(x + 0.2, vt["워케이션_확실도높음"], 0.4, label="확실도 높음", color="#08519c")
ax.set_xticks(x); ax.set_xticklabels([t.split(" ")[0] + t.split(" ")[1][:2] if " " in t else t
                                      for t in vt["Tier"]], fontsize=9)
ax.set_title("Tier별 워케이션 지정지 포함 (프레임 검증)")
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(P("outputs", "figures", "validate_01_tier_recall.png"), dpi=130)
plt.close(fig)
print("\n[그림] outputs/figures/validate_01_tier_recall.png")
