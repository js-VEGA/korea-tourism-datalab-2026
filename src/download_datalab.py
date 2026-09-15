"""
한국관광 데이터랩 - 89개 인구감소지역 자동 다운로드 스크립트 (v3)
=================================================================

【v3 변경점】
- (핵심) "전체 다운로드" 는 로그인 세션이 필요하다. 사이트가 중간에 세션을
  풀어버리면 이후 모든 요청이 alert "로그인 후 이용이 가능합니다." 로 실패한다.
  → 실행 시작 시 크롬 창에서 **직접 로그인**한 뒤 콘솔에서 Enter 를 누르면
    그 세션으로 이어서 받는다 (MANUAL_LOGIN).
  → 실행 도중 다시 로그인 alert 이 뜨면 그 지점에서 멈추고 재로그인을 요청한 뒤
    해당 지역부터 다시 시도한다 (NeedLoginError 처리).
- (안정성) 모든 상호작용 전에 밀린 alert 을 전부 비운다(drain_alerts).
  방치된 alert 하나가 이후 chromedriver 호출을 연쇄 크래시시키던 문제 제거.

【v2 에서 이어짐】
- 로딩 오버레이(#loading/#loadingSpin) 대기 후 클릭, 실패 시 재시도 + JS 폴백
- 다운로드 완료 판정: 최종 .zip 이 나타나고 크기가 2회 연속 동일할 때까지 대기
  (.tmp / .crdownload 는 진행 중으로 간주)
- 지역마다 _log.csv append (중간에 죽어도 남음)
- 실행 중 윈도우 절전/화면꺼짐 억제
- datalab_raw/ 에 최종 .zip 이 있으면 그 조합은 건너뜀 (resume)
"""

import csv
import ctypes
import os
import re
import shutil
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoAlertPresentException,
    TimeoutException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
    UnexpectedAlertPresentException,
)

# ============ 설정 ============

BASE_URL = "https://datalab.visitkorea.or.kr/datalab/portal/loc/getAreaDataForm.do"
LOGIN_URL = "https://datalab.visitkorea.or.kr/datalab/portal/main/getMainForm.do"

TABS = ["방문자", "숙박/체류시간", "관광소비"]

DATE_RANGES = [
    ("202201", "202306"),
    ("202307", "202412"),
    ("202501", "202606"),
]

REGIONS_CSV = "regions.csv"
CHROME_DOWNLOAD_DIR = str(Path.home() / "Downloads")
OUTPUT_DIR = "./datalab_raw"
LOG_PATH = os.path.join(OUTPUT_DIR, "_log.csv")

HEADLESS = False
MANUAL_LOGIN = True            # 시작 시 크롬 창에서 직접 로그인 후 Enter
WAIT_SECONDS = 20
LOADING_WAIT_SECONDS = 40
DOWNLOAD_WAIT_SECONDS = 45
SLEEP_BETWEEN_REQUESTS = 3
TAB_CLICK_RETRIES = 4

LOADING_SELECTORS = ["#loading", "#loadingSpin", "div.loading", "#loadingImg"]
LOGIN_ALERT_HINT = "로그인"


class NeedLoginError(Exception):
    """사이트가 로그인 세션을 요구함 (alert: '로그인 후 이용이 가능합니다.')."""


# ============ 절전 방지 (윈도우) ============

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def prevent_sleep():
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
        )
        print("[절전방지] 시스템 절전/화면꺼짐 억제 ON")
    except Exception as e:
        print(f"[절전방지] 설정 실패(무시): {e}")


def restore_sleep():
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except Exception:
        pass


# ============ 유틸 ============

def load_regions(csv_path):
    regions = []
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            regions.append((row["지역명"].strip(), row["SGG_CD"].strip()))
    return regions


def sanitize(name):
    return re.sub(r"[^\w가-힣]+", "_", name).strip("_")


def build_driver():
    options = Options()
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1400,1000")
    options.add_experimental_option("prefs", {
        "download.default_directory": CHROME_DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    })
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(40)
    return driver


def drain_alerts(driver, max_rounds=6):
    """밀린 alert 을 모두 accept 하고 텍스트 목록을 반환.
    로그인 요구 alert 이 섞여 있으면 NeedLoginError 를 던진다."""
    texts = []
    for _ in range(max_rounds):
        try:
            al = driver.switch_to.alert
            t = (al.text or "").strip()
            al.accept()
            texts.append(t)
            time.sleep(0.2)
        except NoAlertPresentException:
            break
    if any(LOGIN_ALERT_HINT in t for t in texts):
        raise NeedLoginError("; ".join(texts))
    return texts


def cleanup_temp_files():
    removed = 0
    for folder in {OUTPUT_DIR, CHROME_DOWNLOAD_DIR}:
        if not os.path.isdir(folder):
            continue
        for fn in os.listdir(folder):
            if fn.endswith((".tmp", ".crdownload")):
                try:
                    os.remove(os.path.join(folder, fn))
                    removed += 1
                except OSError:
                    pass
    if removed:
        print(f"[정리] 남은 임시파일 {removed}개 삭제")


def wait_loading_gone(driver, timeout=LOADING_WAIT_SECONDS):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            drain_alerts(driver)
        except NeedLoginError:
            raise
        visible = False
        for sel in LOADING_SELECTORS:
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, sel):
                    if el.is_displayed():
                        visible = True
                        break
            except StaleElementReferenceException:
                visible = True
            if visible:
                break
        if not visible:
            return True
        time.sleep(0.4)
    return False


def set_date_range(driver, wait, start_ym, end_ym):
    drain_alerts(driver)
    start_input = wait.until(EC.presence_of_element_located((By.ID, "monthStart")))
    end_input = driver.find_element(By.ID, "monthEnd")
    for elem, value in [(start_input, start_ym), (end_input, end_ym)]:
        driver.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));"
            "arguments[0].dispatchEvent(new Event('blur', {bubbles:true}));",
            elem, value,
        )
    time.sleep(1)
    wait_loading_gone(driver)


def click_tab(driver, wait, tab_name):
    xpath = (
        "//*[self::a or self::li or self::button or self::span]"
        f"[normalize-space(text())='{tab_name}']"
    )
    last_err = None
    for _ in range(TAB_CLICK_RETRIES):
        try:
            wait_loading_gone(driver)
            tab = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab)
            try:
                tab.click()
            except (ElementClickInterceptedException, StaleElementReferenceException) as e:
                last_err = e
                wait_loading_gone(driver)
                tab = driver.find_element(By.XPATH, xpath)
                driver.execute_script("arguments[0].click();", tab)
            time.sleep(1.5)
            wait_loading_gone(driver)
            return
        except UnexpectedAlertPresentException as e:
            last_err = e
            drain_alerts(driver)
        except (TimeoutException, StaleElementReferenceException) as e:
            last_err = e
            time.sleep(1.5)
    raise last_err if last_err else RuntimeError("tab click failed")


def click_download_and_wait(driver, wait, before_files):
    """#download 클릭 후 완성된 .zip 이 나타나고 크기가 안정될 때까지 대기.
    반환: (완료파일명 or None, 알림텍스트 or None). 로그인 alert 이면 NeedLoginError."""
    wait_loading_gone(driver)
    download_btn = wait.until(EC.element_to_be_clickable((By.ID, "download")))
    try:
        download_btn.click()
    except ElementClickInterceptedException:
        wait_loading_gone(driver)
        driver.execute_script("arguments[0].click();", download_btn)

    deadline = time.time() + DOWNLOAD_WAIT_SECONDS
    last_size = -1
    stable_hits = 0
    seen_alert = None
    while time.time() < deadline:
        alerts = drain_alerts(driver)          # 로그인 alert 이면 여기서 NeedLoginError
        if alerts:
            seen_alert = "; ".join(a for a in alerts if a)
            return None, seen_alert

        diff = set(os.listdir(CHROME_DOWNLOAD_DIR)) - before_files
        done_zip = [f for f in diff if f.lower().endswith(".zip")]
        if done_zip:
            name = sorted(done_zip)[-1]
            path = os.path.join(CHROME_DOWNLOAD_DIR, name)
            try:
                size = os.path.getsize(path)
            except OSError:
                size = -1
            if size > 0 and size == last_size:
                stable_hits += 1
                if stable_hits >= 2:
                    return name, None
            else:
                stable_hits = 0
            last_size = size
        time.sleep(0.6)
    return None, seen_alert


def append_log(row):
    new_file = not os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["지역명", "탭", "기간", "상태", "비고"])
        w.writerow(row)


def pause_for_relogin(driver):
    print("\n" + "=" * 64)
    print("  [로그인 세션 만료] 사이트가 다시 로그인을 요구합니다.")
    print("  크롬 창에서 데이터랩에 다시 로그인한 뒤, 여기서 Enter 를 누르세요.")
    print("=" * 64)
    try:
        input("  로그인 완료 후 Enter > ")
    except EOFError:
        time.sleep(30)


def download_one(driver, wait, region_name, tab_name, start_ym, end_ym, dst, ri, n_reg):
    """(지역, 탭, 기간) 1건 처리. 성공 시 True. NeedLoginError 는 위로 전파."""
    click_tab(driver, wait, tab_name)
    before_files = set(os.listdir(CHROME_DOWNLOAD_DIR))
    new_file, alert_txt = click_download_and_wait(driver, wait, before_files)
    period = f"{start_ym}~{end_ym}"
    if new_file is None:
        note = f"alert: {alert_txt}" if alert_txt else "새 zip 감지 못함"
        print(f"[경고] {region_name} {tab_name} {period} → {note}")
        append_log([region_name, tab_name, period, "NO_NEW_FILE", note[:200]])
        return False
    src = os.path.join(CHROME_DOWNLOAD_DIR, new_file)
    shutil.move(src, dst)
    print(f"[완료] ({ri}/{n_reg}) {os.path.basename(dst)}")
    append_log([region_name, tab_name, period, "OK", os.path.basename(dst)])
    time.sleep(SLEEP_BETWEEN_REQUESTS)
    return True


def main():
    regions = load_regions(REGIONS_CSV)
    total = len(regions) * len(TABS) * len(DATE_RANGES)
    print(f"총 {len(regions)}개 지역 x {len(TABS)}개 탭 x {len(DATE_RANGES)}개 기간 = {total}회")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    cleanup_temp_files()
    prevent_sleep()

    driver = build_driver()
    wait = WebDriverWait(driver, WAIT_SECONDS)

    if MANUAL_LOGIN:
        driver.get(LOGIN_URL)
        print("\n" + "=" * 64)
        print("  크롬 창에서 데이터랩에 로그인하세요 (전체 다운로드는 로그인 필요).")
        print("  로그인 완료 후 여기서 Enter 를 누르면 다운로드를 시작합니다.")
        print("=" * 64)
        try:
            input("  로그인 완료 후 Enter > ")
        except EOFError:
            print("  (입력 불가 환경 → 40초 대기 후 진행)")
            time.sleep(40)

    done_cnt = skip_cnt = fail_cnt = 0
    try:
        for ri, (region_name, sgg_cd) in enumerate(regions, 1):
            url = f"{BASE_URL}?SGG_CD={sgg_cd}"
            try:
                driver.get(url)
                time.sleep(2)
                wait_loading_gone(driver)
            except NeedLoginError:
                pause_for_relogin(driver)
                driver.get(url)
                time.sleep(2)
            except Exception as e:
                print(f"[실패] {region_name} 페이지 로딩: {e}")
                append_log([region_name, "", "", "PAGE_LOAD_FAIL", str(e)[:200]])
                fail_cnt += 1
                continue

            for start_ym, end_ym in DATE_RANGES:
                pending_tabs = []
                for tab_name in TABS:
                    dst = os.path.join(
                        OUTPUT_DIR,
                        f"{sanitize(region_name)}__{sanitize(tab_name)}__{start_ym}_{end_ym}.zip",
                    )
                    if os.path.exists(dst):
                        skip_cnt += 1
                    else:
                        pending_tabs.append((tab_name, dst))
                if not pending_tabs:
                    continue

                try:
                    set_date_range(driver, wait, start_ym, end_ym)
                except NeedLoginError:
                    pause_for_relogin(driver)
                    driver.get(url)
                    time.sleep(2)
                    try:
                        set_date_range(driver, wait, start_ym, end_ym)
                    except Exception as e:
                        append_log([region_name, "", f"{start_ym}~{end_ym}", "DATE_SET_FAIL", str(e)[:200]])
                        fail_cnt += 1
                        continue
                except Exception as e:
                    print(f"[실패] {region_name} {start_ym}~{end_ym} 날짜설정: {str(e)[:120]}")
                    drain_alerts_safe(driver)
                    append_log([region_name, "", f"{start_ym}~{end_ym}", "DATE_SET_FAIL", str(e)[:200]])
                    fail_cnt += 1
                    continue

                for tab_name, dst in pending_tabs:
                    period = f"{start_ym}~{end_ym}"
                    try:
                        ok = download_one(driver, wait, region_name, tab_name,
                                          start_ym, end_ym, dst, ri, len(regions))
                        if ok:
                            done_cnt += 1
                    except NeedLoginError:
                        pause_for_relogin(driver)
                        driver.get(url)
                        time.sleep(2)
                        try:
                            set_date_range(driver, wait, start_ym, end_ym)
                            ok = download_one(driver, wait, region_name, tab_name,
                                              start_ym, end_ym, dst, ri, len(regions))
                            if ok:
                                done_cnt += 1
                        except Exception as e:
                            print(f"[실패] {region_name} {tab_name} {period} 재시도: {str(e)[:120]}")
                            append_log([region_name, tab_name, period, "RETRY_FAIL", str(e)[:200]])
                            fail_cnt += 1
                    except Exception as e:
                        print(f"[실패] {region_name} {tab_name} {period}: {str(e)[:120]}")
                        drain_alerts_safe(driver)
                        append_log([region_name, tab_name, period, "TAB_OR_DL_FAIL", str(e)[:200]])
                        fail_cnt += 1

    finally:
        driver.quit()
        restore_sleep()
        print(f"\n종료. 신규완료 {done_cnt} / 기존건너뜀 {skip_cnt} / 실패 {fail_cnt}")
        print(f"로그: {LOG_PATH}  (다시 실행하면 이어받음)")


def drain_alerts_safe(driver):
    try:
        drain_alerts(driver)
    except NeedLoginError:
        pass
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
