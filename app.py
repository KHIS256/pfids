import os
import json
import logging
import time
from flask import Flask, jsonify, render_template
import pytz
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from datetime import datetime
import redis # Import redis

# --- Flask App Initialization, Configuration etc. (Keep as is) ---
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='[WEB] [%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
VERSION_ID = "XM6252-SMART-SILENT-INTEGRATED-V2"
HKT = pytz.timezone('Asia/Hong_Kong')

# --- Connect to Redis ---
REDIS_URL = os.getenv('REDIS_URL')
if not REDIS_URL:
    # This will be false in the web service, so we need a fallback for local dev or error
    logging.warning("REDIS_URL not found, web service might not be able to fetch data.")
    r = None
else:
    r = redis.from_url(REDIS_URL)
    logging.info("Successfully connected to Redis.")


# --- IMPORTANT: Keep the scrape_flight_info function exactly as it is! ---
# The worker.py file needs to import it. Do not delete it.
def scrape_flight_info(mode):
    # ... (THE ENTIRE SCRAPING FUNCTION REMAINS HERE, UNCHANGED)
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
    options.add_argument("--single-process")

    chrome_executable_path = "/usr/bin/google-chrome-stable"
    options.binary_location = chrome_executable_path
    
    driver = None
    try:
        driver = uc.Chrome(
            browser_executable_path=chrome_executable_path,
            options=options,
            use_subprocess=True
        )
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
        
        def get_hkt_time_iso():
            return datetime.now(HKT).isoformat()
            
        output_data = {"version": VERSION_ID, "last_updated_hkt": get_hkt_time_iso(), "mode": mode, "flight_count": len(flights), "flights": flights}
        logging.info(f"[{log_prefix}] SUCCESS! Extracted {len(flights)} flights.")
        return output_data
    except Exception as e:
        logging.error(f"[{log_prefix}] CRITICAL ERROR during scraping: {e}", exc_info=True)
        return {"version": VERSION_ID, "last_updated_hkt": get_hkt_time_iso(), "mode": mode, "flight_count": 0, "error": str(e), "flights": []}
    finally:
        if driver:
            driver.quit()


# --- API Endpoints (NOW READING FROM REDIS) ---
@app.route('/')
def index():
    return render_template('index.html')

def get_data_from_redis(mode):
    if not r:
        return {"error": "Redis connection not available."}
    try:
        data = r.get(f'flight_data:{mode}')
        if data:
            return json.loads(data) # Deserialize the JSON string from Redis
        else:
            # This happens if the worker hasn't run yet
            return {"error": "Data is not available yet. The scraper is warming up. Please try again in a minute."}
    except Exception as e:
        logging.error(f"Could not fetch data from Redis: {e}")
        return {"error": f"Could not fetch data from Redis: {e}"}

@app.route('/api/departures')
def get_departures():
    data = get_data_from_redis('departures')
    return jsonify(data)

@app.route('/api/arrivals')
def get_arrivals():
    data = get_data_from_redis('arrivals')
    return jsonify(data)

# --- Main execution (no changes needed) ---
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)