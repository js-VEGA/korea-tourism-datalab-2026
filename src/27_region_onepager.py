# -*- coding: utf-8 -*-
"""
지자체 발송용 '지역 진단 1장' 생성 (HTML → 헤드리스 Chrome → PDF).

관공서 메일 환경에서 외부 링크가 차단되는 경우가 있어, 대시보드 링크와 별개로
첨부 가능한 A4 1장짜리 PDF 를 만든다. matplotlib 대신 HTML 로 조판해
활자·여백 품질을 확보하고 Chrome 의 print-to-PDF 로 출력한다.

사용:  python 27_region_onepager.py 완도군 부여군 영월군
출력:  dist/onepager/진단요약_<지역명>.pdf
"""
import base64
import io
import json
import os
import sys
import time

DATA = json.load(io.open("report/dashboard_data.json", encoding="utf-8"))
M, R = DATA["meta"], DATA["regions"]
OUT = "dist/onepager"
os.makedirs(OUT, exist_ok=True)

TIER_SHORT = {
    "Tier 1 (즉시 투자)": ("Tier 1", "#0d366b"),
    "Tier 1- (즉시, 인구감소 완만)": ("Tier 1-", "#1c5cab"),
    "Tier 2 (선제 육성)": ("Tier 2", "#2a78d6"),
    "Tier 3 (유지·재활성화)": ("Tier 3", "#5598e7"),
    "관찰": ("관찰", "#7b8794"),
}

CSS = """
@page{size:A4;margin:14mm 14mm 12mm}
*{box-sizing:border-box}
body{margin:0;font-family:"IBM Plex Sans KR","Malgun Gothic",sans-serif;
  font-size:9.6pt;line-height:1.55;color:#0f1720;background:#fff}
.mono{font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
.head{display:flex;justify-content:space-between;align-items:flex-start;
  border-bottom:2px solid #0f1720;padding-bottom:8px;margin-bottom:12px}
.eyebrow{font-size:7.8pt;letter-spacing:.02em;color:#7b8794;margin:0 0 3px;font-weight:500}
h1{font-size:19pt;font-weight:600;margin:0;letter-spacing:-.02em}
.sub{font-size:8.6pt;color:#48545f;margin-top:2px}
.badges{text-align:right}
.tier{display:inline-block;font-size:8.6pt;font-weight:600;color:#fff;
  padding:4px 10px;border-radius:3px;white-space:nowrap}
.rank{font-family:"IBM Plex Mono",monospace;font-size:17pt;font-weight:600;margin-top:6px}
.rank small{font-size:9pt;color:#7b8794;font-weight:400}
.rank .k{display:block;font-family:"IBM Plex Sans KR",sans-serif;
  font-size:7.6pt;color:#7b8794;font-weight:400}

.strip{display:grid;grid-template-columns:repeat(4,1fr);gap:0;
  border:1px solid #dde3e8;border-radius:3px;margin-bottom:13px}
.cell{padding:8px 10px;border-right:1px solid #eaeff2}
.cell:last-child{border-right:0}
.cell .k{font-size:7.8pt;letter-spacing:.02em;color:#7b8794;display:block;margin-bottom:3px;font-weight:500}
.cell .v{font-family:"IBM Plex Mono",monospace;font-size:15pt;font-weight:600;line-height:1.15}
.cell .v u{font-size:9pt;font-weight:400;color:#48545f;text-decoration:none;margin-left:2px}
.cell .s{font-size:7.6pt;color:#7b8794;margin-top:2px;line-height:1.4}

h2{font-family:"IBM Plex Sans KR",sans-serif;font-size:8.2pt;letter-spacing:.02em;
  color:#7b8794;margin:0 0 7px;font-weight:600}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:13px}

.cmprow{margin-bottom:9px}
.cmprow .t{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:3px}
.cmprow .nm{font-size:8.6pt;color:#48545f}
.cmprow .val{font-family:"IBM Plex Mono",monospace;font-size:9pt;font-weight:600}
.track{position:relative;height:6px;background:#eaeff2;border-radius:2px}
.fill{position:absolute;left:0;top:0;bottom:0;background:#2a78d6;border-radius:2px}
.med{position:absolute;top:-2px;bottom:-2px;left:50%;width:1.6px;background:#0f1720;opacity:.5}
.cmprow .sb{display:flex;justify-content:space-between;font-size:7.4pt;color:#7b8794;margin-top:2px}

.rec{border-left:3px solid #0d366b;padding:1px 0 1px 10px;margin-bottom:9px}
.rec .w{font-size:10pt;font-weight:500;line-height:1.5;margin-bottom:3px}
.rec .y{font-size:8.4pt;color:#48545f}
.pkg{border:1px solid #dde3e8;border-radius:3px;padding:8px 10px;font-size:8.4pt;
  line-height:1.55;margin-bottom:9px;background:#f6f8f9}
table.imp{width:100%;border-collapse:collapse;margin-bottom:6px}
.imp th,.imp td{padding:4px 3px;font-size:8.4pt;border-bottom:1px solid #dde3e8;text-align:right}
.imp th{font-size:7.4pt;letter-spacing:.02em;color:#7b8794;font-weight:600}
.imp td:first-child,.imp th:first-child{text-align:left}
.imp td.n{font-family:"IBM Plex Mono",monospace;font-weight:600}
.imp tr:last-child td{border-bottom:0}
ul.kpi{margin:0;padding-left:14px;font-size:8.4pt;color:#48545f}
ul.kpi li{margin-bottom:2px}

.map{border:1px solid #dde3e8;border-radius:3px;padding:9px 12px 6px;margin-bottom:11px;
  display:grid;grid-template-columns:330px 1fr;gap:16px;align-items:center}
.map .why{font-size:8.2pt;color:#48545f;line-height:1.6}
.map .why b{color:#0f1720}
.foot{border-top:1px solid #dde3e8;padding-top:8px;font-size:7.4pt;color:#7b8794;line-height:1.65}
.foot b{color:#48545f}
"""


def fmt(v, d=0):
    if v is None:
        return "—"
    return f"{v:,.{d}f}"


def spark_svg(vals, w=150, h=26, color="#2a78d6"):
    pts = [(i, v) for i, v in enumerate(vals or []) if v is not None]
    if len(pts) < 2:
        return ""
    ys = [p[1] for p in pts]
    lo, hi = min(ys), max(ys)
    pad = (hi - lo) * 0.18 or abs(hi) * 0.05 or 1
    y0, y1 = lo - pad, hi + pad
    n = len(vals) - 1
    X = lambda i: (i / n) * (w - 3) + 1.5
    Y = lambda v: h - 2 - ((v - y0) / (y1 - y0)) * (h - 4)
    d = " ".join(("L" if i else "M") + f"{X(p[0]):.1f} {Y(p[1]):.1f}" for i, p in enumerate(pts))
    col = color if pts[-1][1] >= pts[0][1] else "#d0561f"
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<path d="{d}" fill="none" stroke="{col}" stroke-width="1.4" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{X(pts[-1][0]):.1f}" cy="{Y(pts[-1][1]):.1f}" r="2.1" fill="{col}"/></svg>')


def mini_map(r):
    """89곳 산점도 축소판 — 해당 지역만 강조."""
    w, h = 300, 158
    ml, mr, mt, mb = 26, 8, 10, 20
    pw, ph = w - ml - mr, h - mt - mb
    xs = [x["x"] for x in R]
    ys = [x["y"] for x in R]
    x0, x1 = -1.05, 1.20
    y0, y1 = min(ys) - 1, max(ys) + 1
    SX = lambda v: ml + (min(v, 1.10) - x0) / (x1 - x0) * pw
    SY = lambda v: mt + ph - (v - y0) / (y1 - y0) * ph
    mx, my = SX(M["medianX"]), SY(M["medianY"])
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" height="auto">']
    out.append(f'<rect x="{mx}" y="{mt}" width="{ml+pw-mx:.1f}" height="{my-mt:.1f}" fill="#2a78d6" opacity=".05"/>')
    out.append(f'<line x1="{mx}" x2="{mx}" y1="{mt}" y2="{mt+ph}" stroke="#c3c9ce" stroke-width="1"/>')
    out.append(f'<line x1="{ml}" x2="{ml+pw}" y1="{my}" y2="{my}" stroke="#c3c9ce" stroke-width="1"/>')
    for o in R:
        if o["full"] == r["full"]:
            continue
        c = TIER_SHORT[o["tier"]][1]
        out.append(f'<circle cx="{SX(o["x"]):.1f}" cy="{SY(o["y"]):.1f}" r="2.2" fill="{c}" opacity=".5"/>')
    out.append(f'<circle cx="{SX(r["x"]):.1f}" cy="{SY(r["y"]):.1f}" r="5" '
               f'fill="{TIER_SHORT[r["tier"]][1]}" stroke="#0f1720" stroke-width="1.6"/>')
    out.append(f'<text x="{SX(r["x"])+8:.1f}" y="{SY(r["y"])-5:.1f}" font-size="9" '
               f'font-weight="600" fill="#0f1720">{r["name"]}</text>')
    out.append(f'<text x="{ml+pw}" y="{mt+9}" text-anchor="end" font-size="7.4" fill="#7b8794">가속 워케이션형</text>')
    out.append(f'<text x="{ml}" y="{mt+ph+13}" font-size="7.4" fill="#7b8794">← 체류 성숙도 →</text>')
    out.append(f'<text x="{10}" y="{mt+ph/2}" font-size="7.4" fill="#7b8794" '
               f'transform="rotate(-90 10 {mt+ph/2})" text-anchor="middle">← 성장 모멘텀 →</text>')
    out.append("</svg>")
    return "".join(out)


def cmp_row(nm, val, unit, pctl, med, dec):
    p = max(2, min(100, pctl))
    return (f'<div class="cmprow"><div class="t"><span class="nm">{nm}</span>'
            f'<span class="val">{fmt(val,dec)} <span style="font-weight:400;color:#48545f">{unit}</span></span></div>'
            f'<div class="track"><div class="fill" style="width:{p}%"></div><div class="med"></div></div>'
            f'<div class="sb"><span>89곳 중 상위 {fmt(100-pctl,0)}%</span>'
            f'<span>중앙값 {fmt(med,dec)} {unit}</span></div></div>')


def build(r, link):
    short, col = TIER_SHORT[r["tier"]]
    hours = r["stay"] / 60 if r["stay"] else None
    if r.get("impact"):
        im = r["impact"]
        impact = f"""<h2>투자 대비 기대효과 — 3년차</h2>
        <table class="imp"><thead><tr><th>시나리오</th><th>배수 상승</th>
        <th>추가 연 관광소비</th><th>추가 체류인구/월</th></tr></thead><tbody>
        <tr><td>최소</td><td class="n">+0.10</td><td class="n">{fmt(im['min'])}억</td><td class="n">{fmt(im['popMin'])}명</td></tr>
        <tr><td>보수</td><td class="n">+0.20</td><td class="n">{fmt(im['base'])}억</td><td class="n">{fmt(round(im['popMid']*0.2/0.35))}명</td></tr>
        <tr><td>중심</td><td class="n">+0.35</td><td class="n">{fmt(im['mid'])}억</td><td class="n">{fmt(im['popMid'])}명</td></tr>
        </tbody></table>"""
    else:
        impact = ('<h2>참고</h2><p style="font-size:8.4pt;color:#48545f;margin:0 0 8px">'
                  '기대효과 시나리오는 즉시 투자를 권고하는 Tier 1 13곳에 대해서만 산출했습니다.</p>')

    pkg = f'<div class="pkg"><b>투자 패키지(예시)</b><br>{r["package"]}</div>' if r.get("package") else ""

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>{CSS}</style></head><body>

<div class="head">
  <div>
    <p class="eyebrow">인구감소지역 89곳 워케이션 잠재력 진단</p>
    <h1>{r['name']}</h1>
    <div class="sub">{r['sido']} · {r['quad']} · {r['traj']}</div>
  </div>
  <div class="badges">
    <span class="tier" style="background:{col}">{short} · {r['tierLabel']}</span>
    <div class="rank">{r['rank']}<small>/89</small><span class="k">투자 우선순위</span></div>
  </div>
</div>

<div class="strip">
  <div class="cell"><span class="k">체류 성숙도</span>
    <div class="v">{fmt(r['pctX'],0)}<u>%ile</u></div>
    <div class="s">체류시간·숙박일수·숙박자 비율</div></div>
  <div class="cell"><span class="k">성장 모멘텀</span>
    <div class="v">{'+' if r['y']>=0 else ''}{fmt(r['y'],1)}<u>%</u></div>
    <div class="s">향후 12개월 방문자 예측</div></div>
  <div class="cell"><span class="k">생활인구 배수</span>
    <div class="v">{fmt(r['mult'],2)}<u>배</u></div>
    <div class="s">추세 {'+' if r['multTrend']>=0 else ''}{fmt(r['multTrend'],2)}/년 · 중앙값 {fmt(M['medMult'],2)}배</div></div>
  <div class="cell"><span class="k">인구감소율</span>
    <div class="v">{'−' if r['declineY']>=0 else '+'}{fmt(abs(r['declineY']),2)}<u>%</u></div>
    <div class="s">최근 12개월 · 고령화율 {fmt(r['aged'],1)}%</div></div>
</div>

<div class="two">
  <div>
    <h2>체류의 질 — 89곳 대비 위치</h2>
    {cmp_row("평균 체류시간", hours, "시간", r["pctStay"], M["medStay"]/60, 1)}
    {cmp_row("평균 숙박일수", r["nights"], "박", r["pctNights"], M["medNights"], 2)}
    {cmp_row("숙박자 비율", r["lodge"], "%", r["pctLodge"], M["medLodge"], 1)}
    <h2 style="margin-top:11px">최근 추이 (12개월 이동평균)</h2>
    <table style="width:100%;font-size:8.2pt;border-collapse:collapse">
      <tr><td style="color:#48545f;width:74px">체류시간</td><td>{spark_svg(r['spark'].get('stay'))}</td>
          <td class="mono" style="text-align:right;color:#7b8794">{fmt(hours,1)}시간</td></tr>
      <tr><td style="color:#48545f">평균 숙박일수</td><td>{spark_svg(r['spark'].get('nights'))}</td>
          <td class="mono" style="text-align:right;color:#7b8794">{fmt(r['nights'],2)}박</td></tr>
      <tr><td style="color:#48545f">숙박자 비율</td><td>{spark_svg(r['spark'].get('lodge'))}</td>
          <td class="mono" style="text-align:right;color:#7b8794">{fmt(r['lodge'],1)}%</td></tr>
    </table>
  </div>
  <div>
    <h2>권고 액션</h2>
    <div class="rec" style="border-left-color:{col}">
      <div class="w">{r['what']}</div><div class="y">{r['why']}</div>
    </div>
    {pkg}
    {impact}
    <h2>분기 추적 KPI</h2>
    <ul class="kpi">{''.join(f'<li>{k}</li>' for k in r['kpi'])}</ul>
  </div>
</div>

<div class="map">
  <div>{mini_map(r)}</div>
  <div class="why">
    <b>89곳 중 {r['name']}의 위치</b><br>
    가로는 이미 워케이션형인 정도, 세로는 향후 12개월 체류 수요의 성장세입니다.
    두 축의 순위상관은 −0.15(p=0.17)로 <b>서로 독립</b>이라, 하나의 순위표로 줄 세우는 대신
    사분면으로 나눠 진단합니다. 오른쪽 위(가속 워케이션형)일수록 체류 여건과 성장세가
    동시에 갖춰진 지역입니다.
  </div>
</div>

<div class="foot">
  <b>이 자료에 대하여</b> — 개인 연구자가 공개 데이터만으로 수행한 분석이며 공공기관의 공식 진단·평가 결과가 아닙니다.
  기대효과는 인과 추정이 아니라 생활인구 배수 상승폭을 가정한 시나리오입니다.
  Tier 1 13곳이 자력으로 내고 있는 배수 추세는 3년 환산 중앙값 +0.10, 89곳 전체는 −0.25(하락)이므로
  +0.20/+0.35 는 보수적 가정이 아니라 상위권 수준이며 최소(+0.10)가 하한선입니다.<br>
  <b>데이터</b> — 한국관광 데이터랩 지역별 관광 현황 3개 탭(방문자·숙박/체류시간·관광소비) 89곳 × {M['period'][:4]}.{M['period'][4:6]}~{M['period'][7:11]}.{M['period'][11:13]} 전 지표 ·
  KOSIS 인구감소지역 생활인구 및 주민등록인구 · 공공데이터포털 한국문화정보원 전국 공유 오피스 시설(2022.11).<br>
  <b>89곳 전체 진단(인터랙티브)</b> — {link}
</div>
</body></html>"""


def main():
    names = sys.argv[1:] or ["완도군", "부여군", "영월군"]
    link = os.environ.get("DASH_URL", "(대시보드 링크)")
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    o = Options()
    o.add_argument("--headless=new")
    o.add_argument("--window-size=1000,1400")
    d = webdriver.Chrome(options=o)
    tmp = os.path.abspath(os.path.join(OUT, "_tmp.html"))

    for nm in names:
        r = next((x for x in R if x["name"] == nm), None)
        if not r:
            print("  없음:", nm)
            continue
        io.open(tmp, "w", encoding="utf-8").write(build(r, link))
        d.get("file:///" + tmp.replace("\\", "/"))
        time.sleep(1.6)
        res = d.execute_cdp_cmd("Page.printToPDF", {
            "printBackground": True, "paperWidth": 8.27, "paperHeight": 11.69,
            "marginTop": 0, "marginBottom": 0, "marginLeft": 0, "marginRight": 0,
            "preferCSSPageSize": True,
        })
        path = os.path.join(OUT, f"진단요약_{nm}.pdf")
        with open(path, "wb") as f:
            f.write(base64.b64decode(res["data"]))
        print(f"  saved: {path}  ({os.path.getsize(path)/1024:.0f} KB)")

    d.quit()
    if os.path.exists(tmp):
        os.remove(tmp)


if __name__ == "__main__":
    main()
