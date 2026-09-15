# -*- coding: utf-8 -*-
"""
단계 11-D — 체류 궤적 클러스터링 (54개월 시계열 자체를 군집).

기존 08_clustering.py 는 '정적 특성'(평균값)으로 군집 → 연속 스펙트럼(silhouette 0.24).
여기서는 '궤적의 모양'(추세·가속·변동·초기대비후기)으로 89개 지역을 유형화한다.

방법 2가지 비교:
  (A) shape 피처 + KMeans/Ward  — 해석 가능, 정책 서술용
  (B) DTW 거리 + tslearn KMeans  — 시계열 형태 직접 비교
두 결과의 일치도(ARI)를 보고, 대표 유형론을 택한다.

대상 시계열: 체류시간(분), 평균 숙박일수  (계절조정 후)
출력: outputs/tables/trajectory_clusters.csv,
      outputs/figures/traj_01_mean_paths.png, traj_02_crosstab.png
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans, AgglomerativeClustering
from sklearn.metrics import silhouette_score, adjusted_rand_score
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

BASE = os.path.dirname(os.path.abspath(__file__))
P = lambda *a: os.path.join(BASE, *a)
os.makedirs(P("outputs", "figures"), exist_ok=True)

panel = pd.read_csv(P("processed", "master_modeling_table.csv"), dtype={"기준연월": str})
typ = pd.read_csv(P("outputs", "tables", "region_typology.csv"))
try:
    pol = pd.read_csv(P("outputs", "tables", "policy_priority_v2.csv"))
except FileNotFoundError:
    pol = pd.read_csv(P("outputs", "tables", "policy_priority.csv"))

COLS = ["체류시간(분)", "평균 숙박일수"]
panel = panel[["지역명_full", "기준연월"] + COLS].copy()
panel["ym"] = pd.to_datetime(panel["기준연월"], format="%Y%m")
panel["month"] = panel["ym"].dt.month
panel = panel.sort_values(["지역명_full", "ym"])
for c in COLS:
    panel[c] = pd.to_numeric(panel[c], errors="coerce")
    mm = panel.groupby(["지역명_full", "month"])[c].transform("mean")
    panel[c + "_dsn"] = panel[c] / mm            # 계절조정 (지역평균=1)

regions = sorted(panel["지역명_full"].unique())
months = sorted(panel["ym"].unique())
T = len(months)
print(f"지역 {len(regions)} · 개월 {T}")

# 지역 × 시간 행렬 (계절조정)
mats = {}
for c in COLS:
    M = np.full((len(regions), T), np.nan)
    piv = panel.pivot_table(index="지역명_full", columns="ym", values=c + "_dsn")
    piv = piv.reindex(index=regions, columns=months)
    M = piv.to_numpy(copy=True).astype(float)
    # 결측 보간
    for i in range(len(regions)):
        row = M[i]
        if np.isnan(row).any():
            idx = np.arange(T)
            good = ~np.isnan(row)
            row[~good] = np.interp(idx[~good], idx[good], row[good])
        M[i] = row
    mats[c] = M

# ---------- (A) shape 피처 ----------
def shape_feats(row):
    """계절조정 시계열(지역평균≈1)의 모양 특징. 수준은 이미 정규화됨."""
    idx = np.arange(len(row))
    cv = row.std() / (row.mean() + 1e-9)                 # 원단위 변동계수
    z = (row - row.mean()) / (row.std() + 1e-9)
    a2 = np.polyfit(idx, z, 2)[0]                        # 곡률(가속)
    slope = np.polyfit(idx, z, 1)[0]                     # 추세(z/월)
    early, late = row[:12].mean(), row[-12:].mean()
    return [slope * 12, a2 * 100, cv, (late - early) / (early + 1e-9),
            np.mean(np.abs(np.diff(row))) / (row.mean() + 1e-9)]

FEAT_NM = ["추세_연율z", "가속", "변동계수", "후기초기_상대차", "월변동_상대"]
X = []
for i in range(len(regions)):
    f = []
    for c in COLS:
        f += shape_feats(mats[c][i])
    X.append(f)
X = np.array(X)
Xs = StandardScaler().fit_transform(X)

bake = []
for k in range(3, 7):
    km = KMeans(n_clusters=k, n_init=20, random_state=0).fit(Xs)
    wd = AgglomerativeClustering(n_clusters=k, linkage="ward").fit(Xs)
    bake.append({"k": k,
                 "KMeans_sil": round(silhouette_score(Xs, km.labels_), 3),
                 "Ward_sil": round(silhouette_score(Xs, wd.labels_), 3)})
bdf = pd.DataFrame(bake)
print("\n[shape 피처 군집 실루엣]")
print(bdf.to_string(index=False))
K = int(bdf.sort_values("KMeans_sil", ascending=False).iloc[0]["k"])
kmA = KMeans(n_clusters=K, n_init=30, random_state=0).fit(Xs)
labA = kmA.labels_
print(f"채택 k = {K}")

# ---------- (B) DTW ----------
try:
    from tslearn.clustering import TimeSeriesKMeans
    from tslearn.utils import to_time_series_dataset
    Xd = to_time_series_dataset(np.stack([np.column_stack([mats[c][i] for c in COLS])
                                          for i in range(len(regions))]))
    dtw = TimeSeriesKMeans(n_clusters=K, metric="dtw", max_iter=10,
                           random_state=0, n_init=2).fit(Xd)
    labB = dtw.labels_
    ari = adjusted_rand_score(labA, labB)
    print(f"[DTW k={K}] shape군집과 ARI = {ari:.3f}")
except Exception as e:
    labB = labA
    ari = float("nan")
    print("DTW 스킵:", e)

# ---------- 명명 & 크로스탭 ----------
res = pd.DataFrame({"지역명_full": regions, "궤적군집": labA})
# 피처 인덱스: [체류: 0추세 1가속 2변동 3후기초기 4월변동] [숙박: 5..9]
prof = []
for g in range(K):
    m = labA == g
    prof.append({
        "군집": g, "n": int(m.sum()),
        "체류_추세z": round(X[m, 0].mean(), 3),
        "체류_후기초기차": round(X[m, 3].mean(), 3),
        "체류_변동계수": round(X[m, 2].mean(), 3),
        "숙박_추세z": round(X[m, 5].mean(), 3),
        "숙박_후기초기차": round(X[m, 8].mean(), 3),
        "숙박_변동계수": round(X[m, 7].mean(), 3),
    })
prof = pd.DataFrame(prof)
print("\n[궤적군집 프로파일]  (계절조정, 상대변화율)")
print(prof.to_string(index=False))

# 전 지역 공통으로 체류시간(분)은 2022→2026 하락(코로나기 장기체류 정상화).
# 변별축 = ① 체류시간 하락을 얼마나 버텼나(체류_추세z) ② 숙박일수를 심화했나(숙박_추세z).
# 규칙 기반 명명(정렬 위치 아님).
names = {}
sd_med = prof["숙박_추세z"].median()
for _, r in prof.iterrows():
    g = int(r["군집"])
    held = r["체류_추세z"] > -0.15                       # 체류시간 하락을 버팀
    sd_strong = r["숙박_추세z"] >= prof["숙박_추세z"].max() - 1e-6
    both_crash = (r["체류_추세z"] < -0.48) and (r["숙박_추세z"] < 0) and r["n"] <= 6
    if both_crash:
        names[g] = "급속 약화형"
    elif held and r["숙박_추세z"] > sd_med:
        names[g] = "체류 강화형(체류유지·숙박심화)"
    elif r["숙박_추세z"] > sd_med:
        names[g] = "숙박 전환 진행형"
    else:
        names[g] = "동반 정체·하락형"
# 이름 충돌 시 접미(안전장치)
seen = {}
for g, nm in list(names.items()):
    if nm in seen:
        names[g] = nm + f"({g})"
    seen[nm] = g
res["궤적유형"] = res["궤적군집"].map(names)
prof["유형명"] = prof["군집"].map(names)

res = res.merge(typ[["지역명_full", "사분면"]], on="지역명_full", how="left")
res = res.merge(pol[["지역명_full", "Tier"]], on="지역명_full", how="left")
res.to_csv(P("outputs", "tables", "trajectory_clusters.csv"), index=False, encoding="utf-8-sig")
prof.to_csv(P("outputs", "tables", "trajectory_profiles.csv"), index=False, encoding="utf-8-sig")

print("\n[궤적유형 × 2×2 사분면]")
print(pd.crosstab(res["궤적유형"], res["사분면"]).to_string())
print("\n[궤적유형 × Tier]")
print(pd.crosstab(res["궤적유형"], res["Tier"]).to_string())
print("\n각 유형 예시 지역:")
for nm in res["궤적유형"].unique():
    ex = res[res["궤적유형"] == nm]["지역명_full"].str.split().str[-1].head(8).tolist()
    print(f"  {nm}: {', '.join(ex)}")

# ---------- 그림 ----------
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
xm = [pd.Timestamp(m) for m in months]
for ax, c in zip(axes, COLS):
    for g in range(K):
        mean_path = mats[c][labA == g].mean(axis=0)
        ax.plot(xm, mean_path, label=f"{names[g]} (n={int((labA==g).sum())})", lw=2)
    ax.axhline(1.0, color="grey", lw=0.8, ls=":")
    ax.set_title(f"{c} — 궤적군집 평균 (계절조정, 지역평균=1)")
    ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(P("outputs", "figures", "traj_01_mean_paths.png"), dpi=130)
plt.close(fig)

fig, ax = plt.subplots(figsize=(8, 4.5))
ct = pd.crosstab(res["궤적유형"], res["사분면"])
im = ax.imshow(ct.values, cmap="Blues")
ax.set_xticks(range(len(ct.columns))); ax.set_xticklabels(ct.columns, rotation=30, ha="right", fontsize=9)
ax.set_yticks(range(len(ct.index))); ax.set_yticklabels(ct.index, fontsize=9)
for i in range(ct.shape[0]):
    for j in range(ct.shape[1]):
        ax.text(j, i, ct.values[i, j], ha="center", va="center")
ax.set_title("궤적유형 × 2×2 사분면")
fig.tight_layout()
fig.savefig(P("outputs", "figures", "traj_02_crosstab.png"), dpi=130)
plt.close(fig)
print("\n[그림] traj_01_mean_paths.png, traj_02_crosstab.png")
