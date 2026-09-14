# -*- coding: utf-8 -*-
"""
단계 6: 방문자 중기 성장 예측모델 (LightGBM).

왜 12개월 성장률인가
--------------------
- 월별 방문자수: 계절성 지배 → seasonal-naive 를 못 이김 (사전 백테스트 MASE 1.1~1.4).
- 6개월 선행 성장률: 창이 계절을 가로질러(직전=성수기 / 이후=비수기) 성장률이 계절
  artifact 에 지배됨 (persistence 상관 -0.94, 기계적 평균회귀).
- **12개월 선행 성장률 g12 = (다음 12개월 방문자 합) / (직전 12개월 방문자 합) - 1**
  → 앞뒤 창이 각각 1년치라 계절이 상쇄되고 "지역의 실제 중기 추세" 만 남는다.
  이게 관광 성장률의 표준 측정 단위이고, 정책 판단("이 인구감소지역이 뜨는 중인가")에 직결.

학습단위: (지역, 원점월). g12 가 정의되는 원점 = 202301~202506 (직전12M·다음12M 모두 실측).
검증: 시간 분할 (train 원점 <= 202412 / test 원점 202501~202506) + 지역 GroupKFold(견고성).
대조군: persist12 (직전 12개월 성장률), flat(0).

출력:
  outputs/tables/forecast_metrics.csv          시간분할 + GroupKFold 지표
  outputs/tables/forecast_predictions.csv       test 지역별 실측 vs 예측
  outputs/tables/forecast_forward.csv           원점 202506 → 2026.07~2027.06 전 지역 예측
  outputs/figures/model_01_pred_vs_actual.png / model_02_growth_ranking.png
  outputs/models/lgbm_g12.txt / outputs/tables/feature_list.txt
"""

import os
import warnings
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupKFold
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
MOD = os.path.join(BASE, "outputs", "models")
for d in (FIG, TAB, MOD):
    os.makedirs(d, exist_ok=True)

TRAIN_MAX_ORIGIN = 202412
TEST_ORIGINS = (202501, 202506)
FORWARD_ORIGIN = 202506       # 다음 12개월 = 2026.07~2027.06

DROP_EXACT = {
    "지역명", "지역명_full", "SGG_CD", "기준연월", "연",
    "정적_기준기간", "period_bucket", "외국인_1위국가", "거주_역외최대광역",
    "동일광역_최대유입기초", "y", "방문자수_연인원", "y_lead_mean_1_6", "glog_mean_1_6",
    "방문_2030_비중", "방문_60세이상_비중", "방문_남성_비중",
    "외국인_1위국가_비중", "외국인_상위3_비중합", "외국인_중국_비중", "외국인_일본_비중",
    "base12_fwd", "base12_bwd", "g12", "persist12",
}
DROP_PREFIX = ("y_lead_", "glog_", "resid_")


def month_add(ym, k):
    y, m = divmod(int(ym), 100)
    m += k
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return y * 100 + m


def build_features(df):
    out = []
    for c in df.columns:
        if c in DROP_EXACT or c.startswith(DROP_PREFIX):
            continue
        if c == "광역지자체명" or pd.api.types.is_numeric_dtype(df[c]):
            out.append(c)
    return out


LGB_PARAMS = dict(objective="regression_l1", n_estimators=350, learning_rate=0.03,
                  num_leaves=15, min_child_samples=40, subsample=0.8, subsample_freq=1,
                  colsample_bytree=0.7, reg_lambda=3.0, n_jobs=-1, verbose=-1)


def score(name, act, pred):
    ok = np.isfinite(pred) & np.isfinite(act)
    a, q = act[ok], pred[ok]
    ss = np.sum((a - a.mean()) ** 2)
    return dict(model=name, n=int(ok.sum()),
                MAE=np.mean(np.abs(a - q)),
                RMSE=np.sqrt(np.mean((a - q) ** 2)),
                상관=np.corrcoef(a, q)[0, 1] if ok.sum() > 2 else np.nan,
                방향정확도=np.mean(np.sign(q) == np.sign(a)),
                R2=1 - np.sum((a - q) ** 2) / ss if ss > 0 else np.nan)


def main():
    df = pd.read_csv(MT).sort_values(["지역명_full", "기준연월"]).reset_index(drop=True)
    df["광역지자체명"] = df["광역지자체명"].astype("category")

    lvl = df.pivot_table(index="기준연월", columns="지역명_full", values="y")

    def wsum(origin, lo, hi, region):
        yms = [month_add(origin, j) for j in range(lo, hi + 1)]
        if any(y not in lvl.index for y in yms):
            return np.nan
        return float(lvl.loc[yms, region].sum())

    o, r = df["기준연월"], df["지역명_full"]
    df["base12_bwd"] = [wsum(a, -11, 0, b) for a, b in zip(o, r)]
    df["base12_fwd"] = [wsum(a, 1, 12, b) for a, b in zip(o, r)]
    df["g12"] = df["base12_fwd"] / df["base12_bwd"] - 1
    prev12 = np.array([wsum(a, -23, -12, b) for a, b in zip(o, r)], float)
    df["persist12"] = df["base12_bwd"] / prev12 - 1

    feats = build_features(df)
    with open(os.path.join(TAB, "feature_list.txt"), "w", encoding="utf-8") as f:
        f.write("피처 %d개\n\n%s\n" % (len(feats), "\n".join(feats)))

    d = df[df["g12"].notna()].copy()

    # ---- (1) 시간 분할 검증 ------------------------------------------- #
    tr = d[d["기준연월"] <= TRAIN_MAX_ORIGIN]
    te = d[(d["기준연월"] >= TEST_ORIGINS[0]) & (d["기준연월"] <= TEST_ORIGINS[1])]
    print("시간분할: 학습 %d행(원점 %d~%d) / 검증 %d행(원점 %d~%d)" %
          (len(tr), tr["기준연월"].min(), tr["기준연월"].max(),
           len(te), te["기준연월"].min(), te["기준연월"].max()))

    m = lgb.LGBMRegressor(**LGB_PARAMS)
    m.fit(tr[feats], tr["g12"], categorical_feature=["광역지자체명"])
    p_lgb = m.predict(te[feats])

    numc = tr[feats].select_dtypes("number").columns
    med = tr[numc].median()
    sc = StandardScaler().fit(tr[numc].fillna(med).fillna(0))
    rg = Ridge(alpha=10.0).fit(sc.transform(tr[numc].fillna(med).fillna(0)), tr["g12"])
    p_rg = rg.predict(sc.transform(te[numc].fillna(med).fillna(0)))

    act = te["g12"].values
    rows = [score("LightGBM(시간분할)", act, p_lgb),
            score("Ridge(시간분할)", act, p_rg),
            score("persistence(시간분할)", act, te["persist12"].values),
            score("flat_0(시간분할)", act, np.zeros(len(te)))]

    # ---- (2) 지역 GroupKFold 견고성 검증 --------------------------- #
    gkf = GroupKFold(n_splits=5)
    oof = np.full(len(d), np.nan)
    Xall, yall, grp = d[feats], d["g12"].values, d["지역명_full"].values
    for a_ix, b_ix in gkf.split(Xall, yall, grp):
        mm = lgb.LGBMRegressor(**LGB_PARAMS)
        mm.fit(Xall.iloc[a_ix], yall[a_ix], categorical_feature=["광역지자체명"])
        oof[b_ix] = mm.predict(Xall.iloc[b_ix])
    rows.append(score("LightGBM(지역GroupKFold)", yall, oof))
    rows.append(score("persistence(전체)", yall, d["persist12"].values))

    mets = pd.DataFrame(rows)
    mets.to_csv(os.path.join(TAB, "forecast_metrics.csv"), index=False, encoding="utf-8-sig")

    pr = te[["지역명_full", "기준연월", "g12", "persist12"]].copy()
    pr["pred_lgb"] = p_lgb
    pr["pred_ridge"] = p_rg
    pr.to_csv(os.path.join(TAB, "forecast_predictions.csv"), index=False, encoding="utf-8-sig")

    # ---- (3) 최종 모델 + 전방 예측 (원점 202506) ------------------- #
    mf = lgb.LGBMRegressor(**LGB_PARAMS)
    mf.fit(d[feats], d["g12"], categorical_feature=["광역지자체명"])
    with open(os.path.join(MOD, "lgbm_g12.txt"), "w", encoding="utf-8") as fh:
        fh.write(mf.booster_.model_to_string())

    fwd = df[df["기준연월"] == FORWARD_ORIGIN].copy()
    fwd["pred_g12"] = mf.predict(fwd[feats])
    fo = fwd[["지역명_full", "광역지자체명", "persist12", "pred_g12", "g12"]].rename(
        columns={"g12": "실측_g12_202506원점"}).sort_values("pred_g12", ascending=False)
    fo.to_csv(os.path.join(TAB, "forecast_forward.csv"), index=False, encoding="utf-8-sig")

    # ---- 그림 -------------------------------------------------------- #
    ok = np.isfinite(p_lgb) & np.isfinite(act)
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.scatter(act[ok] * 100, p_lgb[ok] * 100, alpha=0.55, s=26, color="#3b6ea5")
    lim = [min(act[ok].min(), p_lgb[ok].min()) * 100 - 2, max(act[ok].max(), p_lgb[ok].max()) * 100 + 2]
    ax.plot(lim, lim, "--", color="#999")
    ax.axhline(0, color="#ddd", lw=.7); ax.axvline(0, color="#ddd", lw=.7)
    ax.set_xlabel("실측 12개월 성장률 (%)"); ax.set_ylabel("예측 12개월 성장률 (%)")
    ax.set_title("12개월 선행 방문자 성장률: 예측 vs 실측\n(검증 원점 2025.01~06, LightGBM 시간분할)")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "model_01_pred_vs_actual.png")); plt.close(fig)

    top = fo.head(20).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 8))
    ax.barh(range(len(top)), top["pred_g12"] * 100, color="#2e7d54")
    ax.set_yticks(range(len(top))); ax.set_yticklabels([n.split(" ")[-1] for n in top["지역명_full"]], fontsize=9)
    ax.set_xlabel("예측 12개월 방문자 성장률 (%) — 원점 2025.06 → 2026.07~2027.06")
    ax.set_title("모델 예측: 향후 12개월 방문자 성장 상위 20 지역")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "model_02_growth_ranking.png")); plt.close(fig)

    # ---- 콘솔 ------------------------------------------------------ #
    print("\n=== 검증 지표 ===")
    print(mets.round(4).to_string(index=False))
    imp = pd.Series(mf.feature_importances_, index=feats).sort_values(ascending=False)
    print("\n=== LightGBM 피처 중요도 상위 15 ===")
    print(imp.head(15).to_string())
    print("\n=== 전방 예측(원점 2025.06) 성장 상위 12 ===")
    print(fo.head(12)[["지역명_full", "pred_g12", "persist12", "실측_g12_202506원점"]].round(3).to_string(index=False))
    print("\n=== 하위 8 ===")
    print(fo.tail(8)[["지역명_full", "pred_g12", "persist12", "실측_g12_202506원점"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
