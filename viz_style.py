# -*- coding: utf-8 -*-
"""
심사 제출용 통일 시각화 시스템.

기존 그림들의 문제(기본 tab10/YlOrRd 팔레트, 그림마다 다른 색-의미 매핑,
89개 라벨 전부 찍어 뭉갬, 아웃라이어 미처리)를 한 곳에서 교정한다.

팔레트는 dataviz 스킬의 검증된 기본 팔레트를 그대로 채용
(CVD Delta E >= 8 통과 순서). hwp 인쇄를 전제로 light 모드 고정.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager, patheffects
import numpy as np

# ---------------------------------------------------------------- 팔레트
# 카테고리 슬롯(고정 순서 — 절대 순환/재생성 금지)
C = {
    "blue":    "#2a78d6",
    "orange":  "#eb6834",
    "aqua":    "#1baf7a",
    "yellow":  "#eda100",
    "magenta": "#e87ba4",
    "green":   "#008300",
    "violet":  "#4a3aa7",
    "red":     "#e34948",
}
SERIES = [C["blue"], C["orange"], C["aqua"], C["yellow"]]

# 순서형(ordinal) 파랑 램프 — Tier 등 등급형에만
BLUE = {
    100: "#cde2fb", 150: "#b7d3f6", 200: "#9ec5f4", 250: "#86b6ef",
    300: "#6da7ec", 350: "#5598e7", 400: "#3987e5", 450: "#2a78d6",
    500: "#256abf", 550: "#1c5cab", 600: "#184f95", 650: "#104281", 700: "#0d366b",
}
# 등급 램프는 surface 대비 2:1 확보를 위해 250부터 시작
TIER_RAMP = [BLUE[700], BLUE[550], BLUE[400], BLUE[250]]

# 상태색(고정 — 시리즈로 재사용 금지)
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}

# 크롬 / 잉크
INK  = "#0b0b0b"   # 주 텍스트
INK2 = "#52514e"   # 보조 텍스트
MUTE = "#898781"   # 축/라벨
GRID = "#e1e0d9"   # 격자(실선 헤어라인)
AXIS = "#c3c2b7"   # 축선
SURF = "#fcfcfb"   # 차트 표면
PLANE = "#f9f9f7"  # 페이지 면

# 의미 고정 매핑 — 모든 그림에서 동일하게 쓴다 (기존 그림들의 최대 결함 교정)
QUAD_COLOR = {
    "가속 워케이션형": C["blue"],
    "떠오르는 잠재지": C["orange"],
    "성숙·정체":     C["aqua"],
    "저잠재":        MUTE,
}
QUAD_TINT = {   # 사분면 배경 음영(아주 옅게)
    "가속 워케이션형": "#eaf2fd",
    "떠오르는 잠재지": "#fdf0ea",
    "성숙·정체":     "#e9f7f2",
    "저잠재":        "#f4f4f2",
}
TIER_COLOR = {
    "Tier 1 (즉시 투자)":            BLUE[700],
    "Tier 1- (즉시, 인구감소 완만)":  BLUE[550],
    "Tier 2 (선제 육성)":            BLUE[400],
    "Tier 3 (유지·재활성화)":        BLUE[250],
    "관찰":                          "#d9d8d2",
}
ACCENT = C["orange"]   # 워케이션 지정지 강조(링)


# ---------------------------------------------------------------- 폰트
def _pick_font():
    want = ["Malgun Gothic", "맑은 고딕", "NanumGothic", "AppleGothic", "Gulim"]
    have = {f.name for f in font_manager.fontManager.ttflist}
    for w in want:
        if w in have:
            return w
    return "DejaVu Sans"


FONT = _pick_font()


def apply():
    """전역 rcParams. 모든 그림 스크립트가 맨 위에서 한 번 호출."""
    plt.rcParams.update({
        "font.family": FONT,
        "axes.unicode_minus": False,
        "figure.facecolor": SURF,
        "axes.facecolor": SURF,
        "savefig.facecolor": SURF,
        "savefig.dpi": 200,
        "figure.dpi": 110,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.18,

        "axes.edgecolor": AXIS,
        "axes.linewidth": 0.8,
        "axes.labelcolor": INK2,
        "axes.titlecolor": INK,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.titlepad": 12,
        "axes.labelsize": 10.5,
        "axes.labelpad": 7,
        "axes.spines.top": False,
        "axes.spines.right": False,

        "xtick.color": MUTE, "ytick.color": MUTE,
        "xtick.labelsize": 9.5, "ytick.labelsize": 9.5,
        "xtick.major.size": 0, "ytick.major.size": 0,
        "xtick.major.pad": 5, "ytick.major.pad": 5,

        # 격자는 실선 헤어라인 (파선 금지 — 파선은 '임계값'으로 오독됨)
        "grid.color": GRID, "grid.linewidth": 0.7, "grid.linestyle": "-", "grid.alpha": 1.0,
        "axes.grid": False,

        "legend.frameon": False,
        "legend.fontsize": 9.5,
        "legend.labelcolor": INK2,
        "legend.handlelength": 1.1,
        "legend.handletextpad": 0.6,
        "legend.columnspacing": 1.4,

        "lines.linewidth": 2.0,
        "lines.solid_capstyle": "round",
        "patch.linewidth": 0,
    })


# ---------------------------------------------------------------- 헬퍼
def title(ax, main, sub=None, subsize=9.6):
    """제목 + 부제. 부제는 축 바로 위, 제목은 그 위 — 겹치지 않도록 pad 를 넉넉히.

    pad 는 포인트 단위, 부제 위치는 축 높이 대비 비율이라 단위가 다르다.
    부제를 축에 바짝(1.008) 붙이고 제목 pad 를 부제 높이 이상으로 잡아 분리한다.
    """
    ax.set_title(main, loc="left", fontsize=12.5, fontweight="bold", color=INK,
                 pad=(subsize * 2.6 if sub else 10))
    if sub:
        ax.text(0, 1.008, sub, transform=ax.transAxes, fontsize=subsize,
                color=INK2, va="bottom", ha="left")


def grid_y(ax):
    ax.set_axisbelow(True)
    ax.grid(axis="y", which="major")
    ax.spines["left"].set_visible(False)


def grid_xy(ax):
    ax.set_axisbelow(True)
    ax.grid(axis="both", which="major")


def halo(txt, lw=2.6, color=SURF):
    """라벨이 마크 위에 얹힐 때 표면색 후광 — 테두리 대신 쓰는 2px 간격 대용."""
    txt.set_path_effects([patheffects.withStroke(linewidth=lw, foreground=color)])
    return txt


def clip_outlier(s, q=0.98):
    """단일 극단값이 축을 잡아먹는 것을 막는다(울릉군 문제).
    반환: (표시용 시리즈, 클립 상한, 클립된 인덱스)"""
    hi = s.quantile(q)
    clipped = s > hi
    return s.clip(upper=hi), hi, clipped


def footnote(fig, text, y=-0.02):
    fig.text(0.005, y, text, fontsize=8.6, color=MUTE, ha="left", va="top")


# Malgun Gothic 에 없는 글리프 — 쓰면 네모(tofu)로 렌더된다.
# 확인 결과 사용 가능: ● ★ ◆ ▲ ▶ → ↓ ⊥ × ÷ ≠ ≥ ≤ ∙ · ※ ◎ ○ □ ■
BAD_GLYPHS = "≈↻↺−✔✓✕✖☑✅❌⚠➜⇒∞≪≫"


def check_glyphs(fig):
    """저장 직전 호출. 폰트에 없는 문자가 남아 있으면 즉시 잡는다."""
    bad = set()
    for t in fig.findobj(match=lambda o: hasattr(o, "get_text")):
        for ch in (t.get_text() or ""):
            if ch in BAD_GLYPHS:
                bad.add(ch)
    if bad:
        raise ValueError(
            f"폰트에 없는 글리프 사용: {sorted(bad)} — 네모로 렌더됨. "
            f"대체: ≈→'0 수준' / −→'-' / ✕→× / ✔→■ / ↻→◆"
        )


def save(fig, path):
    check_glyphs(fig)
    fig.savefig(path)
    plt.close(fig)
    print("  saved:", path)
