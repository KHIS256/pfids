import os
import json
import logging
import time
from flask import Flask, jsonify, render_template # 導入 render_template
import pytz
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from datetime import datetime

# --- Flask App Initialization ---
# 這次我們使用標準的 Flask 初始化方式
# Flask 會自動在 'static' 和 'templates' 資料夾中尋找檔案
app = Flask(__name__)

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
# 我們不再將 JSON 存成檔案，而是直接存在記憶體中
VERSION_ID = "XM6252-SMART-SILENT-INTEGRATED"
HKT = pytz.timezone('Asia/Hong_Kong')
UPDATE_INTERVAL_SECONDS = 60 # 60 秒更新一次

# --- In-memory Cache ---
# 我們用一個字典來快取爬取到的資料和時間戳
flight_data_cache = {
    'departures': {'data': None, 'timestamp': 0},
    'arrivals': {'data': None, 'timestamp': 0}
}

def get_hkt_time_iso():
    """Returns the current time in HKT as an ISO 8601 formatted string."""
    return datetime.now(HKT).isoformat()

# --- Core Scraping Logic (The "Worker") ---
# 這個函數的邏輯不變，但它現在會回傳資料而不是寫入檔案
def scrape_flight_info(mode):
    if mode == 'departures':
        page_url = 'https://www.hongkongairport.com/en/flights/departures/passenger.page'
        log_prefix = "Departures"
        column_map = {'location': 'destData', 'location_secondary': 'checkInData', 'gate': 'gateData'}
    elif mode == 'arrivals':
        page_url = 'https://www.hongkongairport.com/en/flights/arrivals/passenger.page'
        log_prefix = "Arrivals"
        column_map = {'location': 'originData', 'location_secondary': 'beltData', 'gate': 'parkingData'}
    else:
        return {"error": "Invalid mode"}

    logging.info(f"[{log_prefix}] Starting scrape task.")
    
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    # --- REVISED SECTION FOR DOCKER ---
    # In our Docker container, the path to the Chrome executable is fixed and known.
    chrome_executable_path = "/usr/bin/google-chrome-stable"
    options.binary_location = chrome_executable_path
    logging.info(f"Using Docker environment. Set Chrome binary location to: {chrome_executable_path}")
    # --- END OF REVISION ---

    driver = None
    try:
        driver = uc.Chrome(options=options, use_subprocess=True)
        driver.get(page_url)
        
        wait = WebDriverWait(driver, 45)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "tbody tr, .flight-row")))
        time.sleep(8)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        flight_rows = [row for row in soup.select("tbody tr, table tr") if row.select('.flightNo, [class*="flight"]')]
        if not flight_rows:
            raise RuntimeError("No flight data rows found in HTML")

        flights = []
        for row in flight_rows:
            try:
                flight_no_elements = row.select('.flightNo')
                flight_numbers = [elem.get_text(strip=True) for elem in flight_no_elements if elem.get_text(strip=True)]
                if not flight_numbers: continue

                def safe_extract(selectors, default='N/A'):
                    for selector in selectors if isinstance(selectors, list) else [selectors]:
                        elem = row.select_one(selector)
                        if elem and elem.get_text(strip=True): return elem.get_text(strip=True)
                    return default
                
                secondary_elems = row.select(f'.{column_map["location_secondary"]} span') or row.select(f'.{column_map["location_secondary"]}')
                
                flight_data = {
                    'time': safe_extract(['.timeData span', '.timeData']),
                    'flight_numbers_only': flight_numbers,
                    'location': safe_extract([f'.{column_map["location"]} span', f'.{column_map["location"]}']),
                    'terminal': safe_extract(['.terminalData span', '.terminalData'], '-'),
                    'location_secondary': " ".join(elem.get_text(strip=True) for elem in secondary_elems) if secondary_elems else 'N/A',
                    'gate': safe_extract([f'.{column_map["gate"]} span', f'.{column_map["gate"]}']),
                    'status': safe_extract(['.statusData span', '.statusData'])
                }
                flights.append(flight_data)
            except Exception as e:
                logging.warning(f"[{log_prefix}] Error processing a row: {e}")
                continue

        if not flights:
            raise RuntimeError(f"No valid flight data could be extracted")

        output_data = {"version": VERSION_ID, "last_updated_hkt": get_hkt_time_iso(), "mode": mode, "flight_count": len(flights), "flights": flights}
        logging.info(f"[{log_prefix}] SUCCESS! Extracted {len(flights)} flights.")
        return output_data

    except Exception as e:
        logging.error(f"[{log_prefix}] CRITICAL ERROR during scraping: {e}", exc_info=True)
        return {"version": VERSION_ID, "last_updated_hkt": get_hkt_time_iso(), "mode": mode, "flight_count": 0, "error": str(e), "flights": []}
            
    finally:
        if driver:
            driver.quit()

# --- API Endpoints ---

@app.route('/')
def index():
    """Serves the main HTML page."""
    # 這會去 'templates' 資料夾中尋找 'index.html' 並回傳
    return render_template('index.html')

def get_cached_or_fresh_data(mode):
    """Checks cache first, if stale, triggers a new scrape."""
    cache = flight_data_cache[mode]
    now = time.time()
    
    if (now - cache['timestamp'] > UPDATE_INTERVAL_SECONDS) or not cache['data']:
        logging.info(f"Data for '{mode}' is stale or missing. Triggering new scrape.")
        fresh_data = scrape_flight_info(mode)
        cache['data'] = fresh_data
        cache['timestamp'] = now
    else:
        logging.info(f"Serving fresh data for '{mode}' from cache.")
        
    return cache['data']

@app.route('/api/departures')
def get_departures():
    data = get_cached_or_fresh_data('departures')
    return jsonify(data)

@app.route('/api/arrivals')
def get_arrivals():
    data = get_cached_or_fresh_data('arrivals')
    return jsonify(data)

# --- Main execution for local development ---
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)