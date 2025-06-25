import os
import json
import logging
import time
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS # 1. 導入 CORS
from datetime import datetime
import pytz
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# --- Flask App Initialization ---
app = Flask(__name__, static_folder=None)

# 2. 初始化 CORS，允許所有來源的請求
# 這會自動為你所有的 API 端點加上必要的 'Access-Control-Allow-Origin' 標頭
CORS(app)

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
VERSION_ID = "XM6252-SMART-SILENT-PROD"
HKT = pytz.timezone('Asia/Hong_Kong')
UPDATE_INTERVAL_SECONDS = 60

def get_hkt_time_iso():
    return datetime.now(HKT).isoformat()

# --- Core Scraping Logic (The "Worker") ---
def get_flight_info(mode):
    if mode == 'departures':
        page_url = 'https://www.hongkongairport.com/en/flights/departures/passenger.page'
        output_file = os.path.join(DATA_DIR, "live_departures.json")
        log_prefix = "Departures"
        column_map = {'location': 'destData', 'location_secondary': 'checkInData', 'gate': 'gateData'}
    elif mode == 'arrivals':
        page_url = 'https://www.hongkongairport.com/en/flights/arrivals/passenger.page'
        output_file = os.path.join(DATA_DIR, "live_arrivals.json")
        log_prefix = "Arrivals"
        column_map = {'location': 'originData', 'location_secondary': 'beltData', 'gate': 'parkingData'}
    else:
        return False

    logging.info(f"[{log_prefix}] Starting scrape task.")
    
    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    driver = None
    try:
        logging.info(f"[{log_prefix}] Initializing headless Chrome driver...")
        driver = uc.Chrome(options=options, use_subprocess=True)
        
        logging.info(f"[{log_prefix}] Navigating to {page_url}")
        driver.get(page_url)
        
        wait = WebDriverWait(driver, 45)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "tbody tr, .flight-row")))
        time.sleep(8)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        flight_rows = [row for row in soup.select("tbody tr, table tr") if row.select('.flightNo, [class*="flight"]')]
        if not flight_rows:
            raise RuntimeError("No flight data rows found in HTML")

        logging.info(f"[{log_prefix}] Processing {len(flight_rows)} flight rows...")
        
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
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
        
        logging.info(f"[{log_prefix}] SUCCESS! Extracted {len(flights)} flights.")
        return True

    except Exception as e:
        logging.error(f"[{log_prefix}] CRITICAL ERROR during scraping: {e}")
        empty_data = {"version": VERSION_ID, "last_updated_hkt": get_hkt_time_iso(), "mode": mode, "flight_count": 0, "error": str(e), "flights": []}
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(empty_data, f, ensure_ascii=False, indent=4)
        return False
            
    finally:
        if driver:
            driver.quit()

# --- Intelligent Update Logic (The "Manager") ---
def check_and_update(mode):
    log_prefix = mode.capitalize()
    filepath = os.path.join(DATA_DIR, f"live_{mode}.json")

    if not os.path.exists(filepath):
        logging.info(f"[{log_prefix}] Data file not found. Triggering initial scrape.")
        get_flight_info(mode)
        return

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        last_updated_str = data.get('last_updated_hkt')
        if not last_updated_str:
            raise ValueError("last_updated_hkt key not found in JSON.")

        last_updated_dt = datetime.fromisoformat(last_updated_str)
        time_since_update = (datetime.now(HKT) - last_updated_dt).total_seconds()

        if time_since_update >= UPDATE_INTERVAL_SECONDS:
            logging.info(f"[{log_prefix}] Data is stale (updated {int(time_since_update)}s ago).")
            get_flight_info(mode)
        else:
            logging.info(f"[{log_prefix}] Data is fresh (updated {int(time_since_update)}s ago). Skipping update.")

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logging.warning(f"[{log_prefix}] Could not read valid timestamp from {filepath} due to '{e}'. Forcing update.")
        get_flight_info(mode)

# --- API Endpoints ---
@app.route('/api/departures')
def get_departures():
    check_and_update('departures')
    return send_from_directory(DATA_DIR, 'live_departures.json')

@app.route('/api/arrivals')
def get_arrivals():
    check_and_update('arrivals')
    return send_from_directory(DATA_DIR, 'live_arrivals.json')

@app.route('/')
def index():
    return jsonify({"status": "ok", "version": VERSION_ID})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)