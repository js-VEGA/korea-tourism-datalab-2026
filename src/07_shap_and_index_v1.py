# -*- coding: utf-8 -*-
"""
단계 7: (A) 회귀기법 비교 → (B) SHAP 해석 → (C) 중요도 3종 삼각검증 →
        (D) 워케이션 잠재력 지수 v1 (여러 방식) → v0 대비 비교.

입력: processed/master_modeling_table.csv, outputs/tables/wcation_index_v0.csv
출력:
  outputs/tables/model_bakeoff.csv           g12 예측 기법 비교 (GroupKFold)
  outputs/tables/importance_triangulation.csv gain vs permutation vs SHAP
  outputs/tables/wcation_index_v1.csv          v0 + v1a/v1b/v1c + 순위/비교
  outputs/tables/index_version_compare.csv     버전 간 스피어만·top10 겹침
  outputs/figures/shap_01_summary_bar.png / shap_02_beeswarm.png / shap_03_dependence.png
  outputs/figures/index_03_v0_vs_v1.png
"""

import os
import warnings
import numpy as np
import pandas as pd
import lightgbm as lgb
import shap
from sklearn.ensemble import RandomForestRegressor, ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import ElasticNetCV
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupKFold
from sklearn.inspection import permutation_importance
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 120

BASE = os.path.dirname(os.path.abspath(__file__))
MT = os.path.join(BASE, "processed", "master_modeling_table.csv")
FIG = os.path.join(BASE, "outputs", "figures")
TAB = os.path.join(BASE, "outputs", "tables")
for d in (FIG, TAB):
    os.makedirs(d, exist_ok=True)

DROP_EXACT = {
    "지역명", "지역명_full", "SGG_CD", "기준연월", "연", "정적_기준기간", "period_bucket",
    "외국인_1위국가", "거주_역외최대광역", "동일광역_최대유입기초",
    "y", "방문자수_연인원", "y_lead_mean_1_6", "glog_mean_1_6",
    "방문_2030_비중", "방문_60세이상_비중", "방문_남성_비중",
    "외국인_1위국가_비중", "외국인_상위3_비중합", "외국인_중국_비중", "외국인_일본_비중",
    "base12_fwd", "base12_bwd", "g12", "persist12",
}
DROP_PREFIX = ("y_lead_", "glog_", "resid_")
LGB_PARAMS = dict(objective="regression_l1", n_estimators=350, learning_rate=0.03,
                  num_leaves=15, min_child_samples=40, subsample=0.8, subsample_freq=1,
                  colsample_bytree=0.7, reg_lambda=3.0, n_jobs=-1, verbose=-1)


def month_add(ym, k):
    y, m = divmod(int(ym), 100)
    m += k
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return y * 100 + m


def r2(a, p):
    a, p = np.asarray(a), np.asarray(p)
    ss = np.sum((a - a.mean()) ** 2)
    return 1 - np.sum((a - p) ** 2) / ss if ss > 0 else np.nan


def load():
    df = pd.read_csv(MT).sort_values(["지역명_full", "기준연월"]).reset_index(drop=True)
    df["광역지자체명"] = df["광역지자체명"].astype("category")
    lvl = df.pivot_table(index="기준연월", columns="지역명_full", values="y")

    def wsum(o, lo, hi, r):
        yms = [month_add(o, j) for j in range(lo, hi + 1)]
        if any(y not in lvl.index for y in yms):
            return np.nan
        return float(lvl.loc[yms, r].sum())

    o, r = df["기준연월"], df["지역명_full"]
    df["base12_bwd"] = [wsum(a, -11, 0, b) for a, b in zip(o, r)]
    df["base12_fwd"] = [wsum(a, 1, 12, b) for a, b in zip(o, r)]
    df["g12"] = df["base12_fwd"] / df["base12_bwd"] - 1
    prev = np.array([wsum(a, -23, -12, b) for a, b in zip(o, r)], float)
    df["persist12"] = df["base12_bwd"] / prev - 1
    feats = [c for c in df.columns if c not in DROP_EXACT and not c.startswith(DROP_PREFIX)
             and (c == "광역지자체명" or pd.api.types.is_numeric_dtype(df[c]))]
    return df, feats


def main():
    df, feats = load()
    d = df[df["g12"].notna()].copy()
    numf = [f for f in feats if f != "광역지자체명"]
    X, y, grp = d[feats], d["g12"].values, d["지역명_full"].values
    Xn = d[numf].copy()
    med = Xn.median()
    Xn = Xn.fillna(med).fillna(0)
    gkf = GroupKFold(n_splits=5)

    # ---------- (A) 기법 비교 (GroupKFold OOF) ---------------------------- #
    models = {
        "LightGBM": ("lgb", lgb.LGBMRegressor(**LGB_PARAMS)),
        "RandomForest": ("num", RandomForestRegressor(n_estimators=400, min_samples_leaf=5,
                                                      max_features=0.5, n_jobs=-1, random_state=0)),
        "ExtraTrees": ("num", ExtraTreesRegressor(n_estimators=500, min_samples_leaf=5,
                                                  max_features=0.5, n_jobs=-1, random_state=0)),
        "HistGBR": ("num", HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05,
                                                         max_iter=400, l2_regularization=1.0,
                                                         random_state=0)),
        "ElasticNet": ("scale", ElasticNetCV(l1_ratio=[.2, .5, .8], cv=3,
                                             max_iter=5000, random_state=0)),
    }
    bake = []
    oof_store = {}
    for name, (kind, est) in models.items():
        oof = np.full(len(d), np.nan)
        for a_ix, b_ix in gkf.split(Xn, y, grp):
            if kind == "lgb":
                m = lgb.LGBMRegressor(**LGB_PARAMS)
                m.fit(X.iloc[a_ix], y[a_ix], categorical_feature=["광역지자체명"])
                oof[b_ix] = m.predict(X.iloc[b_ix])
            elif kind == "scale":
                sc = StandardScaler().fit(Xn.iloc[a_ix])
                m = est.__class__(**est.get_params())
                m.fit(sc.transform(Xn.iloc[a_ix]), y[a_ix])
                oof[b_ix] = m.predict(sc.transform(Xn.iloc[b_ix]))
            else:
                m = est.__class__(**est.get_params())
                m.fit(Xn.iloc[a_ix], y[a_ix])
                oof[b_ix] = m.predict(Xn.iloc[b_ix])
        oof_store[name] = oof
        bake.append(dict(model=name, MAE=np.mean(np.abs(y - oof)),
                         RMSE=np.sqrt(np.mean((y - oof) ** 2)),
                         상관=np.corrcoef(y, oof)[0, 1], R2=r2(y, oof),
                         방향정확도=np.mean(np.sign(oof) == np.sign(y))))
    # 앙상블(트리 3종 평균)
    ens = np.mean([oof_store[k] for k in ("LightGBM", "RandomForest", "HistGBR")], axis=0)
    bake.append(dict(model="앙상블(LGB+RF+HistGBR)", MAE=np.mean(np.abs(y - ens)),
                     RMSE=np.sqrt(np.mean((y - ens) ** 2)), 상관=np.corrcoef(y, ens)[0, 1],
                     R2=r2(y, ens), 방향정확도=np.mean(np.sign(ens) == np.sign(y))))
    bakedf = pd.DataFrame(bake).sort_values("R2", ascending=False)
    bakedf.to_csv(os.path.join(TAB, "model_bakeoff.csv"), index=False, encoding="utf-8-sig")
    print("=== (A) g12 예측 기법 비교 (지역 GroupKFold) ===")
    print(bakedf.round(4).to_string(index=False))

    # ---------- (B) SHAP (LightGBM, 숫자 피처만 — 범주형은 SHAP 호환 이슈) - #
    m_full = lgb.LGBMRegressor(**LGB_PARAMS)
    m_full.fit(Xn, y)
    expl = shap.TreeExplainer(m_full)
    sv = expl.shap_values(Xn)
    shap_imp = pd.Series(np.abs(sv).mean(0), index=numf).sort_values(ascending=False)
    Xshap = Xn

    fig, ax = plt.subplots(figsize=(8, 8))
    top = shap_imp.head(20).iloc[::-1]
    ax.barh(range(len(top)), top.values, color="#3b6ea5")
    ax.set_yticks(range(len(top))); ax.set_yticklabels(top.index, fontsize=9)
    ax.set_xlabel("평균 |SHAP| (g12 기여도)")
    ax.set_title("SHAP 피처 중요도 — 12개월 방문자 성장 (상위 20)")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "shap_01_summary_bar.png")); plt.close(fig)

    try:
        shap.summary_plot(sv, Xshap, feature_names=numf, max_display=18, show=False)
        plt.title("SHAP beeswarm — g12")
        plt.tight_layout(); plt.savefig(os.path.join(FIG, "shap_02_beeswarm.png")); plt.close()
    except Exception as e:
        print("beeswarm 스킵:", e)

    top4 = shap_imp.head(4).index.tolist()
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    for ax, fname in zip(axes.ravel(), top4):
        j = numf.index(fname)
        ax.scatter(Xshap[fname], sv[:, j], s=10, alpha=0.4, color="#3b6ea5")
        ax.axhline(0, color="#999", lw=.7)
        ax.set_xlabel(fname); ax.set_ylabel("SHAP")
    fig.suptitle("SHAP 의존도 — 상위 4 피처")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "shap_03_dependence.png")); plt.close(fig)

    # ---------- (C) 중요도 삼각검증 ------------------------------------- #
    gain = pd.Series(m_full.feature_importances_, index=numf)
    perm = permutation_importance(
        (lambda mm: mm.fit(Xn, y) or mm)(HistGradientBoostingRegressor(
            max_depth=3, learning_rate=0.05, max_iter=400, l2_regularization=1.0, random_state=0)),
        Xn, y, n_repeats=10, random_state=0, n_jobs=-1)
    perm_s = pd.Series(perm.importances_mean, index=numf)
    tri = pd.DataFrame({"gain": gain, "SHAP": shap_imp, "permutation": perm_s})
    for c in tri.columns:
        tri[c + "_rank"] = tri[c].rank(ascending=False)
    tri = tri.sort_values("SHAP", ascending=False)
    tri.to_csv(os.path.join(TAB, "importance_triangulation.csv"), encoding="utf-8-sig")
    rk = tri[["gain_rank", "SHAP_rank", "permutation_rank"]].dropna()
    print("\n=== (C) 중요도 3종 순위 상관 (스피어만) ===")
    print(rk.corr(method="spearman").round(3).to_string())
    print("\n상위 12 (SHAP 기준):")
    print(tri.head(12)[["gain", "SHAP", "permutation"]].round(4).to_string())

    # ---------- (D) 지수 v1 ------------------------------------------- #
    v0 = pd.read_csv(os.path.join(TAB, "wcation_index_v0.csv"))
    # 지역별: 최신 원점(202506) 예측 성장성향 + 체류구조 z
    latest = df[df["기준연월"] == 202506].copy()
    latest["pred_g12"] = m_full.predict(latest[numf].fillna(med).fillna(0))
    reg_snap = latest.set_index("지역명_full")

    idx = v0[["지역명_full", "광역지자체명", "소계_A", "소계_B", "소계_C",
              "지수_가중합_100", "인구감소율_12개월"]].copy()
    idx = idx.rename(columns={"지수_가중합_100": "v0_100"})
    idx["pred_g12"] = idx["지역명_full"].map(reg_snap["pred_g12"])

    def to100(s):
        s = pd.to_numeric(s, errors="coerce")
        return (100 * (s - s.min()) / (s.max() - s.min())).round(1)

    # v1a: 모델 예측 성장성향만
    idx["v1a_100"] = to100(idx["pred_g12"])
    # v1b: SHAP 상위 구조 동인 가중합 (체류·인구·검색·거주 계열에서 방향 정한 것)
    drivers = {  # 컬럼: 부호 (성장에 +/-)
        "분기_평균체류시간": +1, "체류시간_전국대비차": +1, "평균 숙박일수": +1,
        "숙박관심_외지인현지인차": +1, "내비검색_yoy": +1, "관광소비_외지인_yoy": +1,
        "거주_동일광역_비중": -1, "인구감소율_12개월": -1,
    }
    reg_last = df.sort_values("기준연월").groupby("지역명_full").last()
    w = shap_imp.reindex(drivers.keys()).fillna(0)
    w = w / w.sum()
    zc = []
    for col, sgn in drivers.items():
        v = pd.to_numeric(reg_last[col], errors="coerce").reindex(idx["지역명_full"]).values
        z = (v - np.nanmean(v)) / np.nanstd(v)
        zc.append(np.clip(z, -3, 3) * sgn * w[col])
    idx["v1b_raw"] = np.nansum(np.vstack(zc), axis=0)
    idx["v1b_100"] = to100(idx["v1b_raw"])
    # v1c: 체류구조(v0 소계_A) + 예측성장 블렌드
    za = (idx["소계_A"] - idx["소계_A"].mean()) / idx["소계_A"].std()
    zg = (idx["pred_g12"] - idx["pred_g12"].mean()) / idx["pred_g12"].std()
    idx["v1c_100"] = to100(0.5 * za + 0.5 * zg)

    for c in ["v0_100", "v1a_100", "v1b_100", "v1c_100"]:
        idx[c.replace("_100", "_순위")] = idx[c].rank(ascending=False).astype(int)
    idx = idx.sort_values("v1c_100", ascending=False)
    idx.to_csv(os.path.join(TAB, "wcation_index_v1.csv"), index=False, encoding="utf-8-sig")

    # 버전 비교
    vers = ["v0_100", "v1a_100", "v1b_100", "v1c_100"]
    cmp = idx[vers].corr(method="spearman").round(3)
    def top10(c): return set(idx.nlargest(10, c)["지역명_full"])
    ov = pd.DataFrame(index=vers, columns=vers, dtype=object)
    for a in vers:
        for b in vers:
            ov.loc[a, b] = len(top10(a) & top10(b))
    cmp.to_csv(os.path.join(TAB, "index_version_compare.csv"), encoding="utf-8-sig")
    print("\n=== (D) 지수 버전 간 스피어만 상관 ===")
    print(cmp.to_string())
    print("\nTop-10 겹침 개수:")
    print(ov.to_string())
    print("\n=== v1c 상위 15 ===")
    print(idx.head(15)[["지역명_full", "v1c_100", "v0_100", "v1a_100", "v1b_100",
                        "pred_g12"]].round(2).to_string(index=False))

    # 그림: v0 vs v1c 순위 변화
    fig, ax = plt.subplots(figsize=(7, 9))
    a = idx.set_index("지역명_full")["v0_순위"]
    b = idx.set_index("지역명_full")["v1c_순위"]
    common = idx["지역명_full"]
    for name in common:
        ax.plot([0, 1], [a[name], b[name]], color="#bbb", lw=.6)
    ax.scatter([0] * len(common), a.reindex(common), s=10, color="#d98c5f")
    ax.scatter([1] * len(common), b.reindex(common), s=10, color="#2e7d54")
    mv = (a - b).abs().sort_values(ascending=False).head(8).index
    for name in mv:
        ax.text(-0.02, a[name], name.split(" ")[-1], ha="right", fontsize=7, va="center")
        ax.text(1.02, b[name], name.split(" ")[-1], ha="left", fontsize=7, va="center")
    ax.set_xticks([0, 1]); ax.set_xticklabels(["v0 (z가중합)", "v1c (체류+예측성장)"])
    ax.set_ylabel("순위 (위=상위)"); ax.invert_yaxis()
    ax.set_title("워케이션 지수 v0 → v1c 순위 변화")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "index_03_v0_vs_v1.png")); plt.close(fig)

    print("\n→ outputs/tables/model_bakeoff.csv, importance_triangulation.csv,")
    print("  wcation_index_v1.csv, index_version_compare.csv + 그림 4개")


if __name__ == "__main__":
    main()
