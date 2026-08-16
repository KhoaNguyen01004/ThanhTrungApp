import os
import sys
import requests
from playwright.sync_api import sync_playwright
import time
import json
from dotenv import load_dotenv

# Force UTF-8 output on Windows to handle Vietnamese characters
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

# Validate required environment variables for main.py
required_env_vars = [
    "TTAS_LOGIN_URL",
    "TTAS_TRACKING_PAGE_URL",
    "TTAS_TRACKING_API",
    "TTAS_USERNAME",
    "TTAS_PASSWORD"
]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}. Please set them in .env file!")

# All configuration is loaded from .env file
LOGIN_URL = os.getenv("TTAS_LOGIN_URL")
TRACKING_PAGE_URL = os.getenv("TTAS_TRACKING_PAGE_URL")
REPORT_PAGE_URL = os.getenv("TTAS_REPORT_PAGE_URL", "https://dinhvihopquy.vn/baocao/ttas_baocao_tonghop_theongay.aspx")
TRACKING_URL = os.getenv("TTAS_TRACKING_API")
TTAS_USERNAME = os.getenv("TTAS_USERNAME")
TTAS_PASSWORD = os.getenv("TTAS_PASSWORD")

TRACKING_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json; charset=UTF-8",
    "Origin": os.getenv("TTAS_TRACKING_PAGE_URL", ""),
    "Referer": TRACKING_PAGE_URL,
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
}


import datetime


# Fetch TTAS report for a vehicle and date range
# Login and report are done in a single Playwright session to avoid nested contexts
def fetch_report(plate: str, start_date: str, end_date: str):
    """Login to TTAS, navigate to the report page, select vehicle and dates,
    click view, and return the summary row HTML.

    Parameters:
        plate: License plate string (e.g., "50H93915")
        start_date, end_date: dates in format DD/MM/YYYY

    Returns:
        HTML string of the summary <tr> row or None if not found.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Step 1: Login
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        page.fill("input[name='txtUserNameLogin']", TTAS_USERNAME)
        page.fill("input[name='txtPasswordLogin']", TTAS_PASSWORD)
        page.click("input[name='btnlogin']")
        page.wait_for_load_state("networkidle", timeout=30000)
        if "ttas_login" in page.url.lower():
            raise RuntimeError("TTAS login failed")

        # Step 2: Navigate to report page
        page.goto(REPORT_PAGE_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=15000)

        # Step 3: Select vehicle plate using the native <select> element (select2 wraps it)
        # Use JS to find the matching option (fuzzy clean-text matching) and trigger select2
        selected = page.evaluate(f"""(plate) => {{
            const select = document.querySelector('#ttasbaocao_drpchonxe');
            if (!select) return false;
            const cleanTarget = plate.replace(/[^A-Z0-9]/gi, '').toUpperCase();
            for (const opt of select.options) {{
                const cleanText = opt.text.replace(/[^A-Z0-9]/gi, '').toUpperCase();
                if (cleanText === cleanTarget) {{
                    select.value = opt.value;
                    select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    if (typeof $ !== 'undefined' && $.fn && $.fn.select2) {{
                        $(select).trigger('change.select2');
                    }}
                    return true;
                }}
            }}
            return false;
        }}""", plate)
        if not selected:
            # Fallback: try Playwright's select_option with value matching
            try:
                page.select_option("#ttasbaocao_drpchonxe", label=plate)
            except Exception:
                print(f"[fetch_report] Could not select plate '{plate}' in dropdown")
        page.wait_for_timeout(500)

        # Step 4: Fill date range (clear first, then type to avoid datepicker conflicts)
        page.fill("#ttasbaocao_txttungay", "")
        page.fill("#ttasbaocao_txttungay", start_date)
        page.fill("#ttasbaocao_txtdenngay", "")
        page.fill("#ttasbaocao_txtdenngay", end_date)
        # Dismiss any datepicker popup
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # Step 5: Click the "Xem BC" button (confirmed id: ttashtkt_btndealscreen)
        page.click("#ttashtkt_btndealscreen")

        # Step 6: Wait for actual data rows in #tData to appear (AJAX populates this after click)
        try:
            page.wait_for_selector("#tData tr", timeout=20000)
            page.wait_for_timeout(500)
            html = page.inner_html("#tData")
        except Exception as e:
            print(f"[fetch_report] Could not get #tData table: {e}")
            html = None

        browser.close()
        return html

def get_session_cookies():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        
        page.fill("input[name='txtUserNameLogin']", TTAS_USERNAME)
        page.fill("input[name='txtPasswordLogin']", TTAS_PASSWORD)
        page.click("input[name='btnlogin']")
        
        page.wait_for_load_state("networkidle", timeout=30000)
        if "ttas_login" in page.url.lower():
            raise RuntimeError("TTAS login failed")
        
        playwright_cookies = page.context.cookies()
        session_cookies = {c['name']: c['value'] for c in playwright_cookies}
        
        browser.close()
        return session_cookies


def main():
    cookies = get_session_cookies()
    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update(TRACKING_HEADERS)
    # Fetch report for a vehicle
    start_date = "02/07/2026"
    end_date = datetime.datetime.now().strftime("%d/%m/%Y")
    plate = "50H93915"
    report_html = fetch_report(plate, start_date, end_date)
    if report_html:
        print("Report fetched successfully:")
        sys.stdout.buffer.write((report_html + "\n").encode("utf-8", errors="replace"))
    else:
        print("Failed to fetch report")

    print("Tracking started...")
    
    while True:
        try:
            payload = {"Running": 1, "Stop": 1, "LostGPRS": 1, "devname": "", "groupxe": "", "maptype": 2}
            response = session.post(TRACKING_URL, json=payload, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            with open("log.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            vehicles = data.get('d', {}).get('DevList', [])
            print(f"[{time.strftime('%H:%M:%S')}] Found {len(vehicles)} vehicles")
            time.sleep(15)
            
        except Exception as e:
            print(f"Error encountered: {e}")
            print("Re-authenticating in 5s...")
            time.sleep(5)
            cookies = get_session_cookies()
            session = requests.Session()
            session.cookies.update(cookies)
            session.headers.update(TRACKING_HEADERS)


if __name__ == "__main__":
    main()
