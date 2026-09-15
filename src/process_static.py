# -*- coding: utf-8 -*-
"""
단계 2b: 데이터랩 방문자·관광소비 탭의 "스냅샷"(월별 시계열 아님) 파일들에서
지역당 1행 정적 피처를 뽑아 processed/region_static_features.csv 를 확장한다.

기존 region_static_features.csv (process_datalab.py 산출 = 숙박 목적지 유입 집중도)에
아래 컬럼을 붙인다. 조인 키: (광역지자체명, 지역명).

스냅샷은 기간 파일마다 1개씩 있으므로 **가장 최근 기간(202501_202606)** 을 우선 쓰고,
없으면 이전 기간으로 폴백한다. 어떤 지역이 어떤 멤버를 못 가졌는지 리포트에 남긴다.

표준 라이브러리만 사용.
"""

import csv
import datetime as dt
import glob
import io
import os
import re
import sys
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE, "datalab_raw")
OUT_DIR = os.path.join(BASE, "processed")
STATIC_CSV = os.path.join(OUT_DIR, "region_static_features.csv")

PERIODS = ["202501_202606", "202307_202412", "202201_202306"]  # 우선순위

PROV_ALIASES = {
    "강원특별자치도": {"강원특별자치도", "강원도"},
    "전북특별자치도": {"전북특별자치도", "전라북도"},
    "전남광주통합특별시": {"전남광주통합특별시", "전라남도", "광주광역시"},
}
CAPITAL_AREA = {"서울특별시", "경기도", "인천광역시"}

NEW_COLS = [
    "정적_기준기간",
    "거주_수도권_비중", "거주_동일광역_비중", "거주_광역HHI",
    "거주_역외최대광역", "거주_역외최대광역_비중",
    "방문_30km미만_비중", "방문_190km이상_비중",
    "방문_2030_비중", "방문_60세이상_비중", "방문_남성_비중",
    "외국인_1위국가", "외국인_1위국가_비중", "외국인_상위3_비중합",
    "외국인_중국_비중", "외국인_일본_비중",
    "외지인_숙박관심비율", "숙박관심_외지인현지인차",
    "소비_숙박업_비중", "소비_식음료업_비중", "소비_쇼핑업_비중", "소비_여가서비스업_비중",
    "소비_2030_비중", "소비_60세이상_비중",
]


def dec(raw):
    for e in ("cp949", "euc-kr"):
        try:
            return raw.encode("cp437").decode(e)
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return raw


def norm(n):
    b = os.path.basename(n)
    b = re.sub(r"^\d{14}_", "", b)
    b = re.sub(r"\.csv$", "", b, flags=re.I)
    return b.replace(" ", "")


def to_f(s):
    try:
        return float(str(s).strip())
    except (ValueError, AttributeError):
        return None


def fmt(x, nd=1):
    return "" if x is None else ("%." + str(nd) + "f") % x


def load_members(zpath):
    out = {}
    try:
        zf = zipfile.ZipFile(zpath)
    except zipfile.BadZipFile:
        return out
    for info in zf.infolist():
        if info.is_dir():
            continue
        rows = [r for r in csv.reader(io.StringIO(zf.read(info).decode("utf-8-sig", errors="replace")))
                if any(c.strip() for c in r)]
        if len(rows) > 1:
            out[norm(dec(info.filename))] = rows
    return out


def get_member(cache, prov, region, tab, member):
    """가장 최근 기간부터 훑어 해당 member 가 있는 (rows, period) 반환. 없으면 (None, None)."""
    for per in PERIODS:
        key = (prov, region, tab, per)
        if key not in cache:
            g = glob.glob(os.path.join(RAW_DIR, f"{prov}_{region}__{tab}__{per}.zip"))
            cache[key] = load_members(g[0]) if g else {}
        if member in cache[key]:
            return cache[key][member], per
    return None, None


def feat_origin(rows, prov):
    """방문자거주지분포: 거주지명 앞토큰=광역. 광역별 값 dedup 후 분포 피처."""
    idx = {h.strip(): i for i, h in enumerate(rows[0])}
    vc = idx.get("광역지자체 비율(%)", 1)
    prov_share = {}
    for r in rows[1:]:
        p = r[0].split(" ")[0].strip()
        v = to_f(r[vc])
        if v is not None:
            prov_share.setdefault(p, v)
    if not prov_share:
        return {}
    aliases = PROV_ALIASES.get(prov, {prov})
    same = sum(v for p, v in prov_share.items() if p in aliases)
    cap = sum(v for p, v in prov_share.items() if p in CAPITAL_AREA)
    hhi = sum((v / 100.0) ** 2 for v in prov_share.values())
    ext = sorted(((v, p) for p, v in prov_share.items() if p not in aliases), reverse=True)
    return {
        "거주_수도권_비중": fmt(cap),
        "거주_동일광역_비중": fmt(same),
        "거주_광역HHI": fmt(hhi, 4),
        "거주_역외최대광역": ext[0][1] if ext else "",
        "거주_역외최대광역_비중": fmt(ext[0][0]) if ext else "",
    }


def feat_distance(rows):
    idx = {h.strip(): i for i, h in enumerate(rows[0])}
    bc = idx.get("거리구분명", 0)
    rc = idx.get("방문자비율", 2)
    d = {}
    for r in rows[1:]:
        v = to_f(r[rc])
        if v is not None:
            d[r[bc].strip()] = v
    near = d.get("30km 미만", 0.0)
    far = d.get("190km 이상 240km 미만", 0.0) + d.get("240km 이상", 0.0)
    return {"방문_30km미만_비중": fmt(near), "방문_190km이상_비중": fmt(far)}


def feat_agesex_visitor(rows):
    idx = {h.strip(): i for i, h in enumerate(rows[0])}
    mc = idx.get("방문자 비율(남성)", 1)
    fc = idx.get("방문자 비율(여성)", 2)
    tot = m_tot = y2030 = o60 = 0.0
    for r in rows[1:]:
        lab = r[0].strip()
        mv, fv = to_f(r[mc]) or 0.0, to_f(r[fc]) or 0.0
        tot += mv + fv
        m_tot += mv
        if lab in ("20~29세", "30~39세"):
            y2030 += mv + fv
        if lab in ("60~69세", "70세 이상"):
            o60 += mv + fv
    if tot <= 0:
        return {}
    return {
        "방문_2030_비중": fmt(100 * y2030 / tot),
        "방문_60세이상_비중": fmt(100 * o60 / tot),
        "방문_남성_비중": fmt(100 * m_tot / tot),
    }


def feat_foreign(rows):
    idx = {h.strip(): i for i, h in enumerate(rows[0])}
    vc = idx.get("비율(%)", 1)
    pairs = []
    cn = jp = 0.0
    for r in rows[1:]:
        v = to_f(r[vc])
        if v is None:
            continue
        nm = r[0].strip()
        pairs.append((v, nm))
        if nm == "중국":
            cn = v
        elif nm == "일본":
            jp = v
    if not pairs:
        return {}
    pairs.sort(reverse=True)
    return {
        "외국인_1위국가": pairs[0][1],
        "외국인_1위국가_비중": fmt(pairs[0][0]),
        "외국인_상위3_비중합": fmt(sum(v for v, _ in pairs[:3])),
        "외국인_중국_비중": fmt(cn),
        "외국인_일본_비중": fmt(jp),
    }


def feat_navlocal(rows):
    idx = {h.strip(): i for i, h in enumerate(rows[0])}
    lc = idx.get("현지인 검색비율", 1)
    ec = idx.get("외지인 검색비율", 2)
    for r in rows[1:]:
        if r[0].strip() == "숙박":
            e, l = to_f(r[ec]), to_f(r[lc])
            if e is None:
                return {}
            return {
                "외지인_숙박관심비율": fmt(e),
                "숙박관심_외지인현지인차": fmt(e - (l or 0.0)),
            }
    return {}


def feat_consume_industry(rows):
    idx = {h.strip(): i for i, h in enumerate(rows[0])}
    gc = idx.get("업종대분류명", 0)
    rc = idx.get("업종대분류 비율(%)", 2)
    share = {}
    for r in rows[1:]:
        v = to_f(r[rc])
        if v is not None:
            share.setdefault(r[gc].strip(), v)
    if not share:
        return {}
    return {
        "소비_숙박업_비중": fmt(share.get("숙박업", 0.0)),
        "소비_식음료업_비중": fmt(share.get("식음료업", 0.0)),
        "소비_쇼핑업_비중": fmt(share.get("쇼핑업", 0.0)),
        "소비_여가서비스업_비중": fmt(share.get("여가서비스업", 0.0)),
    }


def feat_consume_agesex(rows):
    idx = {h.strip(): i for i, h in enumerate(rows[0])}
    mc = idx.get("비율(남성)", 1)
    fc = idx.get("비율(여성)", 2)
    tot = y2030 = o60 = 0.0
    for r in rows[1:]:
        lab = r[0].strip()
        mv, fv = to_f(r[mc]) or 0.0, to_f(r[fc]) or 0.0
        tot += mv + fv
        if lab in ("20대", "30대"):
            y2030 += mv + fv
        if lab in ("60대", "70대", "80대"):
            o60 += mv + fv
    if tot <= 0:
        return {}
    return {"소비_2030_비중": fmt(100 * y2030 / tot),
            "소비_60세이상_비중": fmt(100 * o60 / tot)}


def main():
    if not os.path.exists(STATIC_CSV):
        print("region_static_features.csv 없음. 먼저 process_datalab.py 실행.")
        return 1
    with open(STATIC_CSV, encoding="utf-8-sig") as f:
        base_rows = list(csv.DictReader(f))
    base_cols = list(base_rows[0].keys()) if base_rows else \
        ["광역지자체명", "지역명", "기준기간", "유입광역수", "유입기초수", "동일광역_기초수",
         "동일광역_최대유입기초", "동일광역_최대유입기초_비율", "동일광역_상위3비율합", "동일광역_HHI"]

    # zip 이름에서 (prov, region) 목록
    regions = sorted(set(
        tuple(os.path.basename(p).split("__")[0].split("_", 1))
        for p in glob.glob(os.path.join(RAW_DIR, "*__방문자__*.zip"))
    ))

    cache = {}
    report = ["단계 2b 정적 피처 리포트", "실행: " + dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ""]
    member_missing = {}
    feats_by_region = {}

    SPECS = [
        ("방문자", "방문자거주지분포", "origin", feat_origin),
        ("방문자", "거리별방문자분포", "dist", feat_distance),
        ("방문자", "방문자성연령별분포", "agesex_v", feat_agesex_visitor),
        ("방문자", "외국인방문현황", "foreign", feat_foreign),
        ("방문자", "내비게이션검색현지인_외지인관심지점비교", "navlocal", feat_navlocal),
        ("관광소비", "관광소비_내국인", "cons_ind", feat_consume_industry),
        ("관광소비", "성연령별내국인관광소비분포", "cons_age", feat_consume_agesex),
    ]

    for prov, region in regions:
        feats = {}
        periods_used = set()
        for tab, member, tag, fn in SPECS:
            rows, per = get_member(cache, prov, region, tab, member)
            if rows is None:
                member_missing.setdefault(member, []).append(region)
                continue
            periods_used.add(per)
            if tag == "origin":
                feats.update(fn(rows, prov))
            else:
                feats.update(fn(rows))
        feats["정적_기준기간"] = (
            "202501_202606" if "202501_202606" in periods_used
            else (sorted(periods_used)[-1] if periods_used else "")
        )
        feats_by_region[(prov, region)] = feats

    out_cols = base_cols + [c for c in NEW_COLS if c not in base_cols]
    out_rows = []
    for br in base_rows:
        key = (br["광역지자체명"], br["지역명"])
        merged = dict(br)
        for c in NEW_COLS:
            merged[c] = feats_by_region.get(key, {}).get(c, "")
        out_rows.append(merged)

    # base 에 없던 지역(있으면) 추가
    base_keys = {(r["광역지자체명"], r["지역명"]) for r in base_rows}
    for (prov, region), feats in feats_by_region.items():
        if (prov, region) not in base_keys:
            row = {c: "" for c in out_cols}
            row["광역지자체명"], row["지역명"] = prov, region
            for c in NEW_COLS:
                row[c] = feats.get(c, "")
            out_rows.append(row)

    out_rows.sort(key=lambda r: (r["광역지자체명"], r["지역명"]))
    with open(STATIC_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=out_cols)
        w.writeheader()
        w.writerows(out_rows)

    # ---- 리포트 ----
    report.append("지역수: %d" % len(out_rows))
    report.append("추가 컬럼: %d개" % len(NEW_COLS))
    report.append("")
    n = len(out_rows)
    report.append("[신규 컬럼 채움률]")
    for c in NEW_COLS:
        filled = sum(1 for r in out_rows if r.get(c, "") not in ("", None))
        report.append("  %-22s %3d/%d" % (c, filled, n))
    report.append("")
    report.append("[스냅샷 멤버 부재 지역]")
    for m, lst in member_missing.items():
        report.append("  %s : %d개 지역" % (m, len(lst)))
        report.append("    " + ", ".join(lst))
    if not member_missing:
        report.append("  없음")

    with open(os.path.join(OUT_DIR, "_static_report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")
    print("\n".join(report))
    print("\n갱신: " + STATIC_CSV)
    return 0


if __name__ == "__main__":
    sys.exit(main())
