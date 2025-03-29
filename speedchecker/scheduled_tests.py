#!/usr/bin/env python3
import json
import os
import time
import datetime
import requests
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/app/data/scheduler.log')
    ]
)
logger = logging.getLogger('scheduler')

# Configuration
API_BASE_URL = "http://localhost:3667/api"  # For running in the same container
CONFIG_FILE = Path("/app/data/config.json")  # Path to the config file
LAST_RUN_FILE = Path("/app/data/last_run.txt")  # File to track the last run time

def load_config():
    """Load configuration from the config.json file."""
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        else:
            logger.error(f"Config file not found at {CONFIG_FILE}")
            return None
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return None

def check_active_tests():
    """Check if there are any active tests running."""
    try:
        response = requests.get(f"{API_BASE_URL}/scheduler/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("hasActiveTests", False)
        logger.error(f"Failed to check active tests: {response.status_code}")
        return False
    except Exception as e:
        logger.error(f"Error checking active tests: {e}")
        return False

def run_speedtest():
    """Run a speed test using the API."""
    try:
        # Use the run-now endpoint which handles running both tests if configured
        response = requests.post(f"{API_BASE_URL}/speedtest/schedule/run-now", timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Test started successfully: {result}")
            
            # Record the time we started this test
            save_last_run_time()
            
            # Add a small delay to let the tests start
            time.sleep(2)
            
            return True
        else:
            logger.error(f"Failed to start test: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error running speed test: {e}")
        return False

def get_last_run_time():
    """Get the timestamp of the last test run."""
    try:
        if not LAST_RUN_FILE.exists():
            return 0
            
        with open(LAST_RUN_FILE, "r") as f:
            timestamp = float(f.read().strip())
            return timestamp
    except Exception as e:
        logger.error(f"Error reading last run time: {e}")
        return 0

def save_last_run_time():
    """Save the current time as the last run time."""
    try:
        timestamp = datetime.datetime.now(datetime.timezone.utc).timestamp()
        with open(LAST_RUN_FILE, "w") as f:
            f.write(str(timestamp))
    except Exception as e:
        logger.error(f"Error saving last run time: {e}")

def should_run_test(config):
    """Determine if a test should be run based on configuration and interval."""
    if not config or not config.get("autoTestEnabled", False):
        logger.info("Automatic testing is disabled")
        return False
    
    # Don't run if tests are already in progress
    if check_active_tests():
        logger.info("Tests already in progress, skipping")
        return False
    
    # Check if enough time has passed since last run
    interval = int(config.get("autoTestInterval", 300))
    last_run = get_last_run_time()
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    time_since_last_run = now - last_run
    
    if time_since_last_run < interval:
        logger.info(f"Not enough time passed since last run ({time_since_last_run:.1f} < {interval} seconds)")
        time_until_next = interval - time_since_last_run
        logger.info(f"Next test should run in approximately {time_until_next:.1f} seconds")
        return False
        
    return True

def main():
    """Main function - check if a test should be run and run it if needed."""
    logger.info("Checking if test should be run...")
    
    config = load_config()
    if config is None:
        logger.error("Cannot load configuration. Exiting.")
        return
    
    if should_run_test(config):
        logger.info("Running scheduled test...")
        success = run_speedtest()
        if success:
            logger.info("Test initiated successfully.")
        else:
            logger.info("Failed to run test or test already in progress.")
    else:
        logger.info("No test needed at this time.")

if __name__ == "__main__":
    main()
