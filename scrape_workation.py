# -*- coding: utf-8 -*-
"""
대한민국 구석구석 '워케이션' 테마관에서 워케이션 프로그램 목록을 수집한다.
연도 태그(#2023/#2024/#2025)별로 지역·프로그램명을 뽑아 검증 라벨로 사용.

출력: processed/workation_programs_raw.csv  (연도, 제목, 지역텍스트, 링크)
      processed/workation_designated_regions.csv  (89개 매칭: 지역명, 지정연도들)

사용:  python scrape_workation.py            # headless
       python scrape_workation.py --show     # 브라우저 표시(디버그)
"""
import argparse, csv, json, os, re, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "processed")
LIST_URL = ("https://korean.visitkorea.or.kr/other/other_list.do"
            "?otdid=1ad1f833-2d01-11ee-95cd-0050569dc2b9")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")


def make_driver(show):
    o = Options()
    if not show:
        o.add_argument("--headless=new")
    o.add_argument("--window-size=1400,2000")
    o.add_argument("--lang=ko-KR")
    o.add_argument(f"--user-agent={UA}")
    o.add_argument("--disable-blink-features=AutomationControlled")
    o.add_experimental_option("excludeSwitches", ["enable-automation"])
    d = webdriver.Chrome(options=o)
    d.set_page_load_timeout(60)
    d.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"})
    return d


def get_with_retry(d, url, tries=6):
    for i in range(tries):
        d.get(url)
        time.sleep(4 + i * 4)
        if "서비스 지연" not in d.page_source and len(d.page_source) > 2000:
            return True
        print(f"  throttle/빈페이지 재시도 {i + 1}/{tries} (len={len(d.page_source)})")
        time.sleep(15 + i * 10)
    return False


def dump_dom(d, tag):
    p = os.path.join(OUT, f"_workation_dom_{tag}.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(d.page_source)
    print("  DOM 저장:", p)


def scrape(show=False):
    os.makedirs(OUT, exist_ok=True)
    d = make_driver(show)
    rows = []
    try:
        if not get_with_retry(d, LIST_URL):
            dump_dom(d, "initial")
            print("  구석구석 throttle 지속 — 스크래핑 포기, 수기 목록 사용 필요.")
            return
        time.sleep(3)
        dump_dom(d, "initial")

        # 총 건수 파악
        total = None
        m = re.search(r"총<span>(\d+)</span>건", d.page_source)
        if m:
            total = int(m.group(1))
        print("  총 건수:", total)

        # 무한 스크롤: li 수가 안 늘 때까지 바닥으로 스크롤
        SEL = "ul.list_thumType > li"
        prev = 0
        for k in range(60):
            n = len(d.find_elements(By.CSS_SELECTOR, SEL))
            if total and n >= total:
                break
            if n == prev and k > 3:
                # 살짝 위로 갔다가 다시 바닥 (lazyload 트리거)
                d.execute_script("window.scrollBy(0,-600);")
                time.sleep(0.5)
            d.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.2)
            if n == prev and k > 8:
                break
            prev = n
        print(f"  스크롤 종료: li {len(d.find_elements(By.CSS_SELECTOR, SEL))}개")
        dump_dom(d, "loaded")

        # 카드 파싱 (page_source 정규식)
        html = d.page_source
        blocks = re.split(r'<li class="bdr_nor">', html)[1:]
        for b in blocks:
            tm = re.search(r'class="tit">\s*<a[^>]*>(.*?)</a>', b, re.S)
            title = re.sub(r"<[^>]+>", " ", tm.group(1)).strip() if tm else ""
            # .tit 다음 첫 <p> = 지역
            pm = re.search(r'</div>\s*<p>(.*?)</p>', b, re.S)
            area = re.sub(r"<[^>]+>", " ", pm.group(1)).strip() if pm else ""
            tags = re.findall(r'<span>#([^<]+)</span>', b)
            idm = re.search(r'goDetail\(&quot;([0-9a-f-]+)&quot;', b)
            cid = idm.group(1) if idm else ""
            rows.append({"연도": "", "제목": title, "지역텍스트": area,
                         "태그": " ".join(tags), "contentId": cid})
    finally:
        d.quit()

    raw = os.path.join(OUT, "workation_programs_raw.csv")
    with open(raw, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["연도", "제목", "지역텍스트", "태그", "contentId"])
        w.writeheader(); w.writerows(rows)
    print(f"\n{len(rows)}건 → {raw}")
    if rows:
        for x in rows:
            print(f"  [{x['지역텍스트']:<12}] {x['제목'][:50]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    scrape(a.show)
