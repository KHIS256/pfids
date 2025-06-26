import os
import redis
import json
import logging
import time
from app import scrape_flight_info # We import the function from our existing app.py

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='[WORKER] [%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Connect to Redis using the environment variable provided by Render
# This is more secure and flexible than hardcoding the URL
REDIS_URL = os.getenv('REDIS_URL')
if not REDIS_URL:
    raise RuntimeError("REDIS_URL environment variable not set. Please link the Redis instance.")

r = redis.from_url(REDIS_URL)
logging.info("Successfully connected to Redis.")

# --- Main Worker Loop ---
def main():
    while True:
        try:
            # Scrape Departures
            logging.info("Starting new scrape cycle for DEPARTURES.")
            departures_data = scrape_flight_info('departures')
            # Store the result in Redis as a JSON string
            # We set an expiry of 10 minutes, so if the worker dies, the data becomes stale
            r.set('flight_data:departures', json.dumps(departures_data), ex=600)
            logging.info(f"Successfully scraped and cached {departures_data.get('flight_count', 0)} departures.")

            time.sleep(5) # Small delay between scrapes

            # Scrape Arrivals
            logging.info("Starting new scrape cycle for ARRIVALS.")
            arrivals_data = scrape_flight_info('arrivals')
            r.set('flight_data:arrivals', json.dumps(arrivals_data), ex=600)
            logging.info(f"Successfully scraped and cached {arrivals_data.get('flight_count', 0)} arrivals.")

        except Exception as e:
            logging.error(f"An error occurred in the main worker loop: {e}", exc_info=True)
        
        # Wait for 60 seconds before the next full cycle
        logging.info("Scrape cycle complete. Waiting for 60 seconds.")
        time.sleep(60)

if __name__ == "__main__":
    main()