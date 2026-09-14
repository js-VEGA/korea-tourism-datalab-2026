# -*- coding: utf-8 -*-
"""
단계 8: 지역 유형화.

주(主) 유형론 = 2×2 사분면 [체류 성숙도 × 성장 모멘텀]  (단계 7 결론: 두 축이 거의 직교)
보조 = 관광 행태 클러스터링 (KMeans/Ward/GMM 비교). 단, 인구감소지역 89개는
       자연 군집이 약함(silhouette ~0.15) → "이산적 유형" 이 아니라 연속 스펙트럼임을
       보여주는 근거로 제시하고, k=4 는 기술적 기술(記述)용으로만 사용.

출력:
  outputs/tables/clustering_bakeoff.csv
  outputs/tables/cluster_profiles.csv
  outputs/tables/region_typology.csv          (지역 × 사분면 × 행태군집 × v1c)
  outputs/figures/cluster_01_method_selection.png
  outputs/figures/cluster_02_profile_heatmap.png
  outputs/figures/cluster_03_two_axis.png
  outputs/figures/cluster_04_dendrogram.png
"""

import os
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, dendrogram, fcluster
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.mixture import GaussianMixture
from sklearn.metrics import silhouette_score, calinski_harabasz_score
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 120

BASE = os.path.dirname(os.path.abspath(__file__))
MT = os.path.join(BASE, "processed", "master_modeling_table.csv")
TAB = os.path.join(BASE, "outputs", "tables")
FIG = os.path.join(BASE, "outputs", "figures")


def ts_shape(df):
    rows = []
    for name, g in df.sort_values("기준연월").groupby("지역명_full"):
        y = g["방문자수_연인원"].to_numpy(float)
        ln = np.log(np.where(y > 0, y, np.nan))
        mo = g["월"].to_numpy()
        clim = pd.Series(y).groupby(mo).mean()
        t = np.arange(len(ln)); okm = np.isfinite(ln)
        slope = np.polyfit(t[okm][-30:], ln[okm][-30:], 1)[0] * 12 if okm.sum() >= 12 else np.nan
        A = np.column_stack([pd.get_dummies(mo).to_numpy(float), t])
        beta, *_ = np.linalg.lstsq(A[okm], ln[okm], rcond=None)
        resid = ln[okm] - A[okm] @ beta
        rows.append(dict(지역명_full=name, 계절성_강도=clim.std() / clim.mean(),
                         추세_연율=slope, 잔차변동성=resid.std()))
    return pd.DataFrame(rows)


def main():
    df = pd.read_csv(MT)
    snap = pd.read_csv(os.path.join(TAB, "wcation_snapshot.csv"))
    v1 = pd.read_csv(os.path.join(TAB, "wcation_index_v1.csv"))
    rsf = pd.read_csv(os.path.join(BASE, "processed", "region_static_features.csv"))
    rsf["지역명_full"] = rsf["광역지자체명"] + " " + rsf["지역명"]
    feat = snap.merge(ts_shape(df), on="지역명_full").merge(
        v1[["지역명_full", "소계_A", "pred_g12", "v1c_100"]], on="지역명_full").merge(
        rsf[["지역명_full", "거주_광역HHI", "소비_숙박업_비중", "소비_식음료업_비중",
             "거주_수도권_비중"]].rename(columns={"거주_수도권_비중": "_rsf_수도권"}),
        on="지역명_full")

    # 행태 클러스터링용 특징 (성장/모멘텀 계열은 제외 — 2축의 축2와 순환 방지)
    BEHAV = ["평균체류시간", "평균숙박일수", "숙박자비율_최근12M", "체류시간_전국대비차_최근12M",
             "방문_190km이상_비중", "거주_수도권_비중", "거주_동일광역_비중", "거주_광역HHI",
             "외지인_숙박관심비율", "외지인소비비중_최근12M", "소비_숙박업_비중",
             "인구_로그", "계절성_강도"]
    X = feat[BEHAV].apply(pd.to_numeric, errors="coerce")
    X = X.fillna(X.median())
    Z = StandardScaler().fit_transform(X)

    # ---------- (B) 기법·k 비교 ------------------------------------- #
    rows = []
    for k in range(3, 8):
        km = KMeans(n_clusters=k, n_init=20, random_state=0).fit(Z)
        rows.append(dict(method="KMeans", k=k, silhouette=silhouette_score(Z, km.labels_),
                         CH=calinski_harabasz_score(Z, km.labels_), BIC=np.nan))
        wl = fcluster(linkage(Z, "ward"), k, "maxclust")
        rows.append(dict(method="Ward", k=k, silhouette=silhouette_score(Z, wl),
                         CH=calinski_harabasz_score(Z, wl), BIC=np.nan))
        gm = GaussianMixture(n_components=k, covariance_type="diag", random_state=0).fit(Z)
        gl = gm.predict(Z)
        rows.append(dict(method="GMM", k=k,
                         silhouette=silhouette_score(Z, gl) if len(set(gl)) > 1 else np.nan,
                         CH=calinski_harabasz_score(Z, gl) if len(set(gl)) > 1 else np.nan,
                         BIC=gm.bic(Z)))
    bake = pd.DataFrame(rows)
    bake.to_csv(os.path.join(TAB, "clustering_bakeoff.csv"), index=False, encoding="utf-8-sig")
    print("=== (B) 클러스터링 기법 비교 ===")
    print(bake.round(3).to_string(index=False))
    print("\n최고 silhouette = %.3f → 0.25 미만: 뚜렷한 자연 군집 없음(연속 스펙트럼)."
          % bake["silhouette"].max())

    # 기술용 고정: KMeans k=4
    K = 4
    km = KMeans(n_clusters=K, n_init=50, random_state=0).fit(Z)
    feat["행태군집"] = km.labels_
    prof = feat.groupby("행태군집")[BEHAV].mean()
    prof["n"] = feat.groupby("행태군집").size()

    # 프로파일 기반 명명 (지배 특성 1개로 라벨)
    ov = feat[BEHAV].mean()
    sd = feat[BEHAV].std()
    pz = (prof[BEHAV] - ov) / sd
    label = {}
    for c in pz.index:
        row = pz.loc[c]
        if row["평균체류시간"] > 2.0:                      # 극단 outlier (울릉 등)
            label[c] = "도서 고립·초장기체류형"
        elif row["거주_수도권_비중"] > 0.5 and row["소비_숙박업_비중"] > 0.3:
            label[c] = "수도권 근교 체류형"
        elif row["거주_동일광역_비중"] > 0.4 and row["숙박자비율_최근12M"] < -0.3:
            label[c] = "지역민 밀착·당일형"
        else:
            label[c] = "광역 관광 소도시형"
    used = {}
    for c in list(label):
        if label[c] in used.values():
            label[c] += f" #{c}"
        used[c] = label[c]
    feat["행태유형"] = feat["행태군집"].map(label)
    prof.rename(index=label).to_csv(os.path.join(TAB, "cluster_profiles.csv"), encoding="utf-8-sig")

    # ---------- (C) 2×2 주 유형론 --------------------------------- #
    feat["체류성숙도"] = feat["소계_A"]
    feat["성장모멘텀"] = feat["pred_g12"]
    mx, my = feat["체류성숙도"].median(), feat["성장모멘텀"].median()
    feat["사분면"] = np.select(
        [(feat["체류성숙도"] >= mx) & (feat["성장모멘텀"] >= my),
         (feat["체류성숙도"] < mx) & (feat["성장모멘텀"] >= my),
         (feat["체류성숙도"] >= mx) & (feat["성장모멘텀"] < my)],
        ["가속 워케이션형", "떠오르는 잠재지", "성숙·정체"], default="저잠재")

    keep = ["지역명_full", "광역지자체명", "사분면", "행태유형", "체류성숙도", "성장모멘텀",
            "v1c_100", "평균체류시간", "숙박자비율_최근12M", "추세_연율", "인구감소율_12개월",
            "방문자수성장률"]
    feat[keep].sort_values(["사분면", "v1c_100"], ascending=[True, False]).to_csv(
        os.path.join(TAB, "region_typology.csv"), index=False, encoding="utf-8-sig")

    # ---------- 그림 --------------------------------------------- #
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    for mth, s in bake.groupby("method"):
        ax[0].plot(s["k"], s["silhouette"], marker="o", label=mth)
    ax[0].axhline(0.25, color="#c0392b", ls=":", label="0.25 (약한 군집 기준)")
    ax[0].set_title("Silhouette vs k"); ax[0].set_xlabel("k"); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3)
    g = bake[bake.method == "GMM"]
    ax[1].plot(g["k"], g["BIC"], marker="s", color="#c0392b")
    ax[1].set_title("GMM BIC vs k"); ax[1].set_xlabel("k"); ax[1].grid(alpha=.3)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "cluster_01_method_selection.png")); plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 7))
    im = ax.imshow(pz.rename(index=label).T.values, aspect="auto", cmap="RdBu_r", vmin=-2, vmax=2)
    ax.set_xticks(range(K)); ax.set_xticklabels([label[c] for c in pz.index], rotation=15, ha="right")
    ax.set_yticks(range(len(BEHAV))); ax.set_yticklabels(BEHAV, fontsize=9)
    for i in range(K):
        for j in range(len(BEHAV)):
            ax.text(i, j, f"{pz.rename(index=label).T.values[j, i]:.1f}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, label="표준화 평균 (전체 지역 대비)")
    ax.set_title("행태 클러스터 프로파일 (k=4, z-score) — 참고용")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "cluster_02_profile_heatmap.png")); plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 8.5))
    cmap = plt.cm.tab10
    for i, (nm, s) in enumerate(feat.groupby("사분면")):
        ax.scatter(s["체류성숙도"], s["성장모멘텀"] * 100, s=55, color=cmap(i), label=nm,
                   edgecolor="white", lw=.5)
    ax.axvline(mx, color="#bbb", ls="--"); ax.axhline(my * 100, color="#bbb", ls="--")
    for _, r in feat.iterrows():
        ax.annotate(r["지역명_full"].split(" ")[-1], (r["체류성숙도"], r["성장모멘텀"] * 100),
                    fontsize=7, xytext=(2, 2), textcoords="offset points")
    ax.set_xlabel("체류 성숙도  (체류시간·숙박일수·숙박자비율 z 합)")
    ax.set_ylabel("성장 모멘텀  (모델 예측 12개월 방문자 성장률, %)")
    ax.set_title("주 유형론: 체류 성숙도 × 성장 모멘텀 (2×2)\n"
                 "우상=가속 워케이션형 / 좌상=떠오르는 잠재지 / 우하=성숙·정체 / 좌하=저잠재")
    ax.legend(fontsize=9, loc="lower left")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "cluster_03_two_axis.png")); plt.close(fig)

    fig, ax = plt.subplots(figsize=(14, 5))
    dendrogram(linkage(Z, "ward"), labels=[n.split(" ")[-1] for n in feat["지역명_full"]],
               leaf_font_size=7, ax=ax, color_threshold=0)
    ax.set_title("Ward 계층 클러스터링 덴드로그램 (행태 특징)")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "cluster_04_dendrogram.png")); plt.close(fig)

    # ---------- 콘솔 ------------------------------------------------ #
    print("\n=== 행태 클러스터 (k=4, 참고) ===")
    print(feat.groupby("행태유형").size().to_string())
    print("\n=== 2×2 사분면 분포 ===")
    print(feat["사분면"].value_counts().to_string())
    for q in ["가속 워케이션형", "떠오르는 잠재지"]:
        sub = feat[feat["사분면"] == q].sort_values("성장모멘텀", ascending=False)
        print(f"\n=== [{q}] {len(sub)}개 ===")
        print(sub[["지역명_full", "행태유형", "체류성숙도", "성장모멘텀", "v1c_100",
                   "인구감소율_12개월"]].round(3).to_string(index=False))
    print("\n→ region_typology.csv, cluster_profiles.csv, clustering_bakeoff.csv + 그림 4개")


if __name__ == "__main__":
    main()
