# -*- coding: utf-8 -*-
"""
단계 12-1 — Tier 1 체류 인프라 투자의 기대효과 '규모 추정' (시나리오).

※ 인과 예측이 아니라 "규모 감(sense of magnitude)"을 주기 위한 back-of-envelope.
   가정은 아래 ASSUMPTIONS 에 명시. 심사기준 '효과성·성과창출도' 대응.

논리 사슬:
  인프라 투자 → 생활인구 배수 증가율이 '현재 Tier 1 상위 수준'까지 상승(3년) 가정
  → Δ체류인구 = 주민등록인구 × Δ배수
  → Δ관광소비 = Δ체류인구 × (지역별 1인당 연 관광소비)
  대조 근거: DiD 상 '지정만'으로는 효과 없음 → 인프라가 추세를 바꿔야 한다는 전제.

입력: processed/region_features_v3.csv, processed/master_modeling_table.csv
출력: outputs/tables/impact_projection.csv,
      outputs/figures/impact_01_projection.png
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

# ---------------- ASSUMPTIONS (전부 서식4에 명시) ----------------
YEARS = 3
UNIT_COST_EOK = 15.0        # 지역당 워케이션 거점 조성비 (억원). 범위 10~20 (공공 리모델/신축 실적 개략)
# 인프라 투자로 '생활인구 배수'가 3년간 총 UPLIFT 만큼 추가 상승한다고 가정(현 추세와 무관하게 가산).
#  - 보수 +0.20  /  중심 +0.35  (예: 배수 4.5 → 4.7~4.85)
#  - 근거: 현재 Tier 1 상위 지역(영월 +0.14·해남 +0.16·부여 +0.12 /연)이
#          자력으로 보이는 3년 배수 상승폭(+0.37~0.48)보다 보수적.
UPLIFT = {"보수 시나리오": 0.20, "중심 시나리오": 0.35}
# --------------------------------------------------------------

v3 = pd.read_csv(P("processed", "region_features_v3.csv"))
m = pd.read_csv(P("processed", "master_modeling_table.csv"), dtype={"기준연월": str})

t1_all = v3[v3["Tier"].str.startswith("Tier 1")].copy()
t1 = t1_all[t1_all["Tier"] == "Tier 1 (즉시 투자)"].copy()     # 헤드라인 = Tier 1 (13곳)
print(f"대상: Tier 1(즉시 투자) {len(t1)}곳  [별도로 Tier 1- {len(t1_all)-len(t1)}곳 존재]")

rec = (m[m["기준연월"] >= "202507"]
       .groupby("지역명_full")
       .agg(외지인소비_천원=("관광소비_외지인_천원", "sum"),
            방문자_연인원=("방문자수_연인원", "sum"))
       .reset_index())
for d0 in (t1, t1_all):
    pass
t1 = t1.merge(rec, on="지역명_full", how="left")
t1_all = t1_all.merge(rec, on="지역명_full", how="left")

for d0 in (t1, t1_all):
    d0["주민등록_근사"] = d0["생활인구_계_평균"] / d0["생활인구_배수_평균"]
    d0["1인당_연관광소비_천원"] = d0["외지인소비_천원"] / d0["체류인구_평균"]

def scenario(df, uplift, label, n_label):
    d = df.copy()
    d["Δ배수_3년"] = uplift
    d["Δ체류인구"] = d["주민등록_근사"] * d["Δ배수_3년"]
    d["Δ관광소비_천원"] = d["Δ체류인구"] * d["1인당_연관광소비_천원"]
    tot_people = d["Δ체류인구"].sum()
    tot_eok = d["Δ관광소비_천원"].sum() / 1e5
    invest_eok = len(d) * UNIT_COST_EOK
    print(f"\n[{label}]  ({n_label}, 배수 +{uplift:.2f}/3년)")
    print(f"  3년 후 추가 체류인구(월평균 합) ≈ {tot_people:,.0f} 명")
    print(f"  3년차 추가 연 관광소비 ≈ {tot_eok:,.0f} 억원  (투자 {invest_eok:,.0f}억의 {tot_eok/invest_eok:.1f}배)")
    top = d.sort_values("Δ관광소비_천원", ascending=False).head(6)
    for _, r in top.iterrows():
        print(f"    {r['지역명_full'].split()[-1]:6s} Δ체류인구 {r['Δ체류인구']:>7,.0f}명  Δ소비 {r['Δ관광소비_천원']/1e5:>5,.0f}억")
    d["시나리오"] = label
    return d, tot_people, tot_eok, invest_eok

d_con, p_con, e_con, inv = scenario(t1, UPLIFT["보수 시나리오"], "보수 시나리오", "Tier 1 13곳")
d_mid, p_mid, e_mid, _ = scenario(t1, UPLIFT["중심 시나리오"], "중심 시나리오", "Tier 1 13곳")
_, p_ext, e_ext, inv_ext = scenario(t1_all, UPLIFT["중심 시나리오"], "확장(Tier 1+1-)", f"Tier 1·1- {len(t1_all)}곳")

out = pd.concat([d_con, d_mid])[
    ["시나리오", "지역명_full", "Tier", "우선순위_v2_100", "주민등록_근사",
     "생활인구_배수_평균", "Δ배수_3년", "Δ체류인구",
     "1인당_연관광소비_천원", "Δ관광소비_천원"]]
out.to_csv(P("outputs", "tables", "impact_projection.csv"), index=False, encoding="utf-8-sig")

# 그림
fig, ax = plt.subplots(figsize=(8.5, 5))
labels = ["보수\n(배수+0.20)", "중심\n(배수+0.35)"]
sobi = [e_con, e_mid]
bars = ax.bar(labels, sobi, color=["#9ecae1", "#3182bd"], width=0.45)
ax.axhline(inv, color="#d62728", ls="--", lw=1.5, label=f"투자 규모 약 {inv:.0f}억원 (13곳×15억)")
for i, v in enumerate(sobi):
    ax.text(i, v, f"+{v:,.0f}억원", ha="center", va="bottom", fontweight="bold")
ax.set_ylabel("Tier 1(13곳) 3년차 추가 연 관광소비 (억원)")
ax.set_title("체류 인프라 투자 기대효과 — 규모 추정 시나리오\n(인과 예측 아님. 가정: 생활인구 배수 3년 +0.20~0.35)")
ax.legend()
fig.tight_layout()
fig.savefig(P("outputs", "figures", "impact_01_projection.png"), dpi=130)
plt.close(fig)

print("\n[요약 — 서식4용]")
print(f"  투자: Tier 1 13곳 × 약 15억 = 약 {inv:.0f}억원 (거점 조성비, 범위 10~20억)")
print(f"  3년차 추가 연 관광소비: 보수 +{e_con:,.0f}억 ~ 중심 +{e_mid:,.0f}억원")
print(f"  3년 후 추가 체류인구(월평균): 보수 +{p_con:,.0f} ~ 중심 +{p_mid:,.0f}명")
print(f"  (Tier 1-까지 확장 시 중심 +{e_ext:,.0f}억 / +{p_ext:,.0f}명, 투자 {inv_ext:.0f}억)")
print("\n[그림] outputs/figures/impact_01_projection.png")
print("[표]  outputs/tables/impact_projection.csv")
