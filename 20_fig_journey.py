# -*- coding: utf-8 -*-
"""
그림: 분석 설계 여정 — 문제 인식 → 가설 → 검증 → (기각/재정의) → 재설계.

기존 서식4의 최대 약점은 "발견 3개 나열"이라 '왜 이 설계를 택했는가'가
안 드러난다는 점. devlog 01~19에 남아 있는 실제 시행착오(지수 v0 폐기 /
예측모델 역할 재정의 / 생활인구 배수 수준 폐기)를 한 장으로 복원한다.

주황 = 검증 결과로 설계를 바꾼 지점(3회), 파랑 = 채택·확정.
"""
import os
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import viz_style as V

V.apply()
FIG = "outputs/figures"
os.makedirs(FIG, exist_ok=True)

# (단계, 가설/시도, 검증 지표, 판정, 판정종류)
STAGES = [
    ("문제 인식",
     "인구감소지역 89곳 중\n어디에 체류 인프라를\n먼저 투자할 것인가",
     "전국 공유오피스 905개 중\n89곳 소재 = 0개",
     "● 투자 근거 부재", "start"),

    ("1차 설계",
     "가설 ①\n워케이션 잠재력은\n단일 지수로 순위화 가능",
     "가중합 지수 vs PCA 지수\n순위상관 ρ = 0.22",
     "× 기각\n가중치 임의성 → 지수 v0 폐기", "reject"),

    ("2차 설계",
     "가설 ②\n성장률을 예측해\n지역을 줄 세운다",
     "6개 기법 비교(LightGBM 최고)\n시간분할 R² 0 수준\n지역분할 R² 0.12 · 방향 0.69",
     "◆ 역할 재정의\n정밀예측 → 동인 규명·상대 랭킹", "revise"),

    ("전환점",
     "SHAP 해석 중 발견\n두 축의 관계를 측정",
     "체류 성숙도 ⊥ 성장 모멘텀\nρ = -0.15 (p = 0.17)",
     "★ 한 줄 순위 불가\n→ 2×2 프레임으로 전환", "pivot"),

    ("3차 검증",
     "가설 ③\n외부 데이터로\n프레임을 검증한다",
     "생활인구 배수 '수준' ρ = -0.43\n생활인구 배수 '추세' ρ = +0.50\nDiD 지정효과 p = 0.93",
     "× '수준' 폐기 · '추세'만 채택\n'지정 ≠ 성과' 논리 확보", "reject"),

    ("산출물",
     "89곳 전수 진단\nTier 1~3 + 실행 시나리오",
     "궤적군집이 정적 프레임의\n사각지대 7곳 추가 포착",
     "■ 진단 대시보드\n투자 우선순위", "final"),
]

COLOR = {
    "start":  V.MUTE,
    "reject": V.C["orange"],
    "revise": V.C["orange"],
    "pivot":  V.C["blue"],
    "final":  V.C["blue"],
}

fig, ax = plt.subplots(figsize=(15.6, 5.5))
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis("off")

n = len(STAGES)
gap = 1.4
w = (100 - gap * (n - 1)) / n

HEAD_TOP, HEAD_H = 96, 8.5          # 단계 헤더
CARD_TOP, CARD_BOT = 85.5, 4        # 본문 카드
HYP_Y = CARD_TOP - 4.5              # 가설 텍스트 시작
RULE_Y = 46                         # 구분 헤어라인
TEST_LBL_Y, TEST_Y = 43, 38.5       # 검증
BADGE_Y, BADGE_H = 7, 13            # 판정 배지

for i, (stage, hyp, test, verdict, kind) in enumerate(STAGES):
    x = i * (w + gap)
    col = COLOR[kind]

    # 단계 헤더
    ax.add_patch(FancyBboxPatch((x, HEAD_TOP - HEAD_H), w, HEAD_H,
                                boxstyle="round,pad=0,rounding_size=1.4",
                                facecolor=col, edgecolor="none",
                                alpha=1.0 if kind != "start" else 0.5))
    ax.text(x + w / 2, HEAD_TOP - HEAD_H / 2, stage, ha="center", va="center",
            fontsize=12, fontweight="bold", color="white")

    # 본문 카드
    ax.add_patch(FancyBboxPatch((x, CARD_BOT), w, CARD_TOP - CARD_BOT,
                                boxstyle="round,pad=0,rounding_size=1.4",
                                facecolor="#f6f6f4", edgecolor=V.GRID, linewidth=0.9))

    # 가설 / 시도
    ax.text(x + w / 2, HYP_Y, hyp, ha="center", va="top",
            fontsize=9.8, color=V.INK, linespacing=1.6)

    # 구분 헤어라인
    ax.plot([x + 2.6, x + w - 2.6], [RULE_Y, RULE_Y],
            color=V.GRID, lw=0.9, solid_capstyle="butt")

    # 검증
    ax.text(x + w / 2, TEST_LBL_Y, "검증", ha="center", va="top",
            fontsize=8.4, color=V.MUTE, fontweight="bold")
    ax.text(x + w / 2, TEST_Y, test, ha="center", va="top",
            fontsize=8.9, color=V.INK2, linespacing=1.55)

    # 판정 배지 (아이콘을 텍스트 안에 인라인으로 — 겹침 방지)
    ax.add_patch(FancyBboxPatch((x + 1.5, BADGE_Y), w - 3.0, BADGE_H,
                                boxstyle="round,pad=0,rounding_size=1.1",
                                facecolor=col, edgecolor="none", alpha=0.15))
    ax.text(x + w / 2, BADGE_Y + BADGE_H / 2, verdict, ha="center", va="center",
            fontsize=9.1, color=col, fontweight="bold", linespacing=1.5)

    # 단계 간 화살표
    if i < n - 1:
        ax.add_patch(FancyArrowPatch((x + w + 0.2, 46), (x + w + gap - 0.2, 46),
                                     arrowstyle="-|>", mutation_scale=12,
                                     color=V.AXIS, lw=1.5, shrinkA=0, shrinkB=0))

fig.text(0.005, 0.985,
         "분석 설계 여정 — 세 번의 검증 실패가 프레임을 만들었다",
         fontsize=15.5, fontweight="bold", color=V.INK, va="top", ha="left")
fig.text(0.005, 0.928,
         "가설을 세우고 데이터로 검증해 기각·재정의한 과정. 주황(× ◆)은 검증 결과에 따라 설계를 바꾼 지점.",
         fontsize=10.2, color=V.INK2, va="top", ha="left")
fig.text(0.005, 0.015,
         "데이터: 한국관광 데이터랩(방문자·숙박/체류시간·관광소비 3개 탭 전 지표, 89지역×54개월) · "
         "KOSIS(인구감소지역·주민등록인구·생활인구·5세별 연령구조) · 공공데이터포털(전국 공유오피스)",
         fontsize=8.6, color=V.MUTE, va="bottom", ha="left")

fig.subplots_adjust(left=0.004, right=0.996, top=0.855, bottom=0.075)
V.save(fig, os.path.join(FIG, "sub_01_journey.png"))
