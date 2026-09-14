# -*- coding: utf-8 -*-
"""
단계 11-C — 워케이션 지정 효과 이벤트 스터디 / 이중차분(DiD).

목표: '지정 후' 체류시간·숙박일수가 (비지정 인구감소지역 대비) 유의하게 늘었나?

설계:
  - 처치군: workation_designated_regions.csv 확실도 '높음' 11곳 (추정 시작연도 사용).
  - 통제군: 나머지 인구감소지역(워케이션 라벨 전혀 없는 곳).
  - 패널 202201~202606. 시작연도 2021 코호트는 pre 기간 없음 → 제외.
  - 계절성 제거: 지역별 '월(1~12) 평균'으로 나눈 계절조정값(dsn). 추가로 YoY도 산출.
  - (1) 이벤트타임 플롯: 지정월 t=0 정렬, 코호트 평균 vs 통제군 동일달력 평균.
  - (2) 요약 DiD: (지정 후 12개월 평균 − 지정 전 12개월 평균), 처치 vs 통제 차이.
  - (3) 양방향 고정효과 회귀: y_dsn ~ treatpost + C(지역) + C(연월), 지역 클러스터 SE(근사).

주의: 처치 유효표본 ~9곳 + 추정 시작연도 → 검정력 낮음. 방향성 참고용.
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

panel = pd.read_csv(P("processed", "master_modeling_table.csv"), dtype={"기준연월": str})
wk = pd.read_csv(P("processed", "workation_designated_regions.csv"))

OUTCOMES = {"체류시간(분)": "체류시간", "평균 숙박일수": "숙박일수"}
panel = panel[["지역명_full", "기준연월"] + list(OUTCOMES)].copy()
panel["ym"] = pd.to_datetime(panel["기준연월"], format="%Y%m")
panel["month"] = panel["ym"].dt.month
panel = panel.sort_values(["지역명_full", "ym"])

# 계절조정: 지역×월 평균으로 나눔
for c in OUTCOMES:
    panel[c] = pd.to_numeric(panel[c], errors="coerce")
    mm = panel.groupby(["지역명_full", "month"])[c].transform("mean")
    panel[c + "_dsn"] = panel[c] / mm
    panel[c + "_yoy"] = panel.groupby("지역명_full")[c].pct_change(12)

hi = wk[wk["확실도"] == "높음"][["지역명_full", "추정_시작연도"]].copy()
treated = dict(zip(hi["지역명_full"], hi["추정_시작연도"]))
labelled = set(wk["지역명_full"])
control = [r for r in panel["지역명_full"].unique() if r not in labelled]
print(f"처치 후보 {len(treated)}곳, 통제군 {len(control)}곳")

# 시작연도별 처치월 (연도 중반=7월로 가정)
def start_ym(y):
    return pd.Timestamp(int(y), 7, 1)

use_treated = {r: y for r, y in treated.items() if int(y) >= 2023}  # pre기간 확보
print("유효 처치(2023+):", {r.split()[-1]: y for r, y in use_treated.items()})

# ---------- (1) 이벤트타임 ----------
def series(reg, col):
    s = panel[panel["지역명_full"] == reg].set_index("ym")[col]
    return s

ET = range(-12, 13)
et_treat = {c: [] for c in OUTCOMES}
et_ctrl = {c: [] for c in OUTCOMES}
for col in OUTCOMES:
    dcol = col + "_dsn"
    tstack, cstack = [], []
    for reg, y in use_treated.items():
        t0 = start_ym(y)
        s = series(reg, dcol)
        row = [s.get(t0 + pd.DateOffset(months=k), np.nan) for k in ET]
        tstack.append(row)
        # 통제군: 같은 달력 시점 평균
        crows = []
        for cr in control:
            sc = series(cr, dcol)
            crows.append([sc.get(t0 + pd.DateOffset(months=k), np.nan) for k in ET])
        cstack.append(np.nanmean(np.array(crows), axis=0))
    et_treat[col] = np.nanmean(np.array(tstack), axis=0)
    et_ctrl[col] = np.nanmean(np.array(cstack), axis=0)

fig, axes = plt.subplots(1, 2, figsize=(13, 5))
for ax, (col, nm) in zip(axes, OUTCOMES.items()):
    ax.plot(list(ET), et_treat[col], "o-", label="지정 지역(확실도높음)", color="#08519c")
    ax.plot(list(ET), et_ctrl[col], "s--", label="비지정 인구감소지역", color="#999999")
    ax.axvline(0, color="red", lw=1, ls=":")
    ax.set_xlabel("지정 시점 대비 개월"); ax.set_ylabel(f"{nm} (계절조정, 지역평균=1)")
    ax.set_title(f"{nm} — 이벤트 스터디")
    ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(P("outputs", "figures", "event_01_study.png"), dpi=130)
plt.close(fig)

# ---------- (2) 요약 DiD ----------
rows = []
for col in OUTCOMES:
    dcol = col + "_dsn"
    tv, cv = [], []
    for reg, y in use_treated.items():
        t0 = start_ym(y)
        s = series(reg, dcol)
        pre = np.nanmean([s.get(t0 + pd.DateOffset(months=k), np.nan) for k in range(-12, 0)])
        post = np.nanmean([s.get(t0 + pd.DateOffset(months=k), np.nan) for k in range(1, 13)])
        tv.append(post - pre)
        cc = []
        for cr in control:
            sc = series(cr, dcol)
            prec = np.nanmean([sc.get(t0 + pd.DateOffset(months=k), np.nan) for k in range(-12, 0)])
            postc = np.nanmean([sc.get(t0 + pd.DateOffset(months=k), np.nan) for k in range(1, 13)])
            cc.append(postc - prec)
        cv.append(np.nanmean(cc))
    tv, cv = np.array(tv), np.array(cv)
    did = np.nanmean(tv) - np.nanmean(cv)
    # 순열검정: 처치/통제 라벨 섞어 did 분포
    alld = np.concatenate([tv, cv])
    rng = np.random.default_rng(0)
    perm = []
    for _ in range(2000):
        rng.shuffle(alld)
        perm.append(np.nanmean(alld[:len(tv)]) - np.nanmean(alld[len(tv):]))
    p = np.mean(np.abs(perm) >= abs(did))
    rows.append({"지표": OUTCOMES[col], "처치 Δ(post-pre)": round(np.nanmean(tv), 4),
                 "통제 Δ": round(np.nanmean(cv), 4), "DiD": round(did, 4),
                 "순열 p": round(p, 3), "n_처치": len(tv)})
did_df = pd.DataFrame(rows)
print("\n[요약 DiD] (계절조정, 지역평균=1 기준)")
print(did_df.to_string(index=False))
did_df.to_csv(P("outputs", "tables", "event_study_did.csv"), index=False, encoding="utf-8-sig")

# ---------- (3) 양방향 FE (간이) ----------
try:
    import statsmodels.formula.api as smf
    d = panel[panel["지역명_full"].isin(list(use_treated) + control)].copy()
    d["treat"] = d["지역명_full"].isin(use_treated).astype(int)
    d["post"] = 0
    for reg, y in use_treated.items():
        d.loc[(d["지역명_full"] == reg) & (d["ym"] >= start_ym(y)), "post"] = 1
    d["treatpost"] = d["treat"] * d["post"]
    for col in OUTCOMES:
        dd = d.dropna(subset=[col + "_dsn"])
        m = smf.ols(f"Q('{col}_dsn') ~ treatpost + C(지역명_full) + C(기준연월)", data=dd).fit(
            cov_type="cluster", cov_kwds={"groups": dd["지역명_full"]})
        b = m.params.get("treatpost", np.nan)
        se = m.bse.get("treatpost", np.nan)
        pv = m.pvalues.get("treatpost", np.nan)
        print(f"  [FE] {OUTCOMES[col]}: treatpost = {b:+.4f}  (SE {se:.4f}, p {pv:.3f})")
except Exception as e:
    print("  FE 회귀 스킵:", e)

print("\n[그림] outputs/figures/event_01_study.png")
