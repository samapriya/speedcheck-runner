import json
import os
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from flask import Flask, request, jsonify, send_from_directory, Response
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from speedtest_openspeedtest import openspeedtest_speed_test
from speedtest_speedsmart import speedsmart_speed_test

app = Flask(__name__)

# Configuration from environment variables with defaults
AUTO_TEST_ENABLED = os.environ.get('AUTO_TEST_ENABLED', 'true').lower() == 'true'
AUTO_TEST_INTERVAL = os.environ.get('AUTO_TEST_INTERVAL', '86400')  # Default: daily in seconds
AUTO_TEST_PROVIDER = os.environ.get('AUTO_TEST_PROVIDER', 'both')  # Default to run both tests
RUN_BOTH_TESTS = os.environ.get('AUTO_TEST_PROVIDER', 'both').lower() == 'both'
DELAY_BETWEEN_TESTS = int(os.environ.get('DELAY_BETWEEN_TESTS', '300'))  # 5 minutes lag by default
NEXT_SCHEDULED_TEST = None  # Will be set when scheduled

# Data directory
DATA_DIR = Path("/app/data")
DATA_DIR.mkdir(exist_ok=True)

# Path to the log files
HISTORY_JSON = DATA_DIR / "speedtest_history.json"
HISTORY_PARQUET = DATA_DIR / "speedtest_history.parquet"

# Store configuration in a file for the frontend to read
CONFIG_FILE = DATA_DIR / "config.json"

# Initialize history files if they don't exist
if not HISTORY_JSON.exists():
    with open(HISTORY_JSON, "w") as f:
        json.dump([], f)

# Global lock for accessing test history
history_lock = threading.Lock()

def load_history():
    """Load test history from JSON file."""
    with history_lock:
        try:
            with open(HISTORY_JSON, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

def save_history(history):
    """Save test history to both JSON and Parquet files."""
    with history_lock:
        # Save to JSON
        with open(HISTORY_JSON, "w") as f:
            json.dump(history, f, indent=2)
        
        # Save to Parquet if we have data
        if history:
            df = pd.DataFrame(history)
            df.to_parquet(HISTORY_PARQUET, index=False)

def update_history(result, provider):
    """Add a new test result to the history."""
    history = load_history()
    
    # Ensure timestamp is in UTC
    timestamp = datetime.now(timezone.utc).isoformat()
    
    if provider == "openspeedtest":
        # Extract values from the OpenSpeedTest result format
        download = float(result["Download Speed"].split()[0])
        upload = float(result["Upload Speed"].split()[0])
        ping = float(result["Ping"].split()[0])
        jitter = float(result["Jitter"].split()[0])
        isp = result["Server Location"]
        server = result["Server Name"]
    else:  # speedsmart
        # Use SpeedSmart result format
        download = result["download_speed"]
        upload = result["upload_speed"]
        ping = result["ping_speed"]
        jitter = result["jitter"]
        isp = result["isp_name"]
        server = result["server_name"]
    
    entry = {
        "timestamp": timestamp,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "provider": provider,
        "download": download,
        "upload": upload,
        "ping": ping,
        "jitter": jitter,
        "isp": isp,
        "server": server
    }
    
    history.append(entry)
    save_history(history)
    
    return entry

@app.route('/')
def index():
    """Serve the main application."""
    return send_from_directory('static', 'index.html')

# Function to create a session with retry capability
def create_session_with_retry():
    session = requests.Session()
    retry_strategy = Retry(
        total=3,  # Total number of retries
        status_forcelist=[500, 502, 503, 504],  # Status codes to retry on
        backoff_factor=1,  # Factor to apply between retry attempts
        method_whitelist=["HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE", "PATCH"]  # Allowed methods for retry
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

@app.route('/api/speedtest', methods=['POST'])
def run_speedtest():
    """API endpoint to run a speed test."""
    provider = request.args.get('provider', 'openspeedtest')
    
    # Function to capture stdout during test run
    def run_test_with_capture():
        import io
        import sys
        from contextlib import redirect_stdout
        
        # Try up to 3 times
        for attempt in range(3):
            try:
                f = io.StringIO()
                with redirect_stdout(f):
                    if provider == "openspeedtest":
                        openspeedtest_speed_test()
                    else:
                        speedsmart_speed_test()
                
                output = f.getvalue()
                
                # Try to extract JSON from the output
                json_start = output.find('{')
                json_end = output.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = output[json_start:json_end]
                    return json.loads(json_str)
                else:
                    if attempt < 2:  # If not the last attempt
                        print(f"No JSON found in output, retrying (attempt {attempt+1})")
                        time.sleep(2)  # Wait before retry
                        continue
                    return {"error": "No JSON found in output"}
                    
            except json.JSONDecodeError:
                if attempt < 2:  # If not the last attempt
                    print(f"Failed to parse JSON from output, retrying (attempt {attempt+1})")
                    time.sleep(2)  # Wait before retry
                    continue
                return {"error": "Failed to parse JSON from output", "output": output}
            except Exception as e:
                if attempt < 2:  # If not the last attempt
                    print(f"Error during test: {str(e)}, retrying (attempt {attempt+1})")
                    time.sleep(2)  # Wait before retry
                    continue
                return {"error": f"Test failed: {str(e)}"}
        
        # If we get here, all attempts failed
        return {"error": "All retry attempts failed"}
    
    # Run the test
    result = run_test_with_capture()
    
    # Update history
    update_history(result, provider)
    
    return jsonify(result)

@app.route('/api/history')
def get_history():
    """API endpoint to retrieve test history."""
    history = load_history()
    return jsonify(history)

@app.route('/api/history/download', methods=['GET'])
def download_history():
    """API endpoint to download test history."""
    format_type = request.args.get('format', 'json')
    
    if format_type == 'json':
        history = load_history()
        return Response(
            json.dumps(history, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment;filename=speedtest_history.json'}
        )
    elif format_type == 'csv':
        if not HISTORY_PARQUET.exists():
            return jsonify({"error": "No history data available"}), 404
        
        # Load from Parquet and convert to CSV
        df = pd.read_parquet(HISTORY_PARQUET)
        csv_data = df.to_csv(index=False)
        
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment;filename=speedtest_history.csv'}
        )
    else:
        return jsonify({"error": f"Unsupported format: {format_type}"}), 400

# Updated DELETE method to clear history by writing empty files
@app.route('/api/history', methods=['DELETE'])
def clear_history():
    """API endpoint to clear test history by writing empty files."""
    try:
        with history_lock:
            # Clear the JSON file by writing an empty array
            with open(HISTORY_JSON, "w") as f:
                json.dump([], f)
            
            # Create an empty DataFrame and write to Parquet
            empty_df = pd.DataFrame()
            empty_df.to_parquet(HISTORY_PARQUET, index=False)
        
        return jsonify({"success": True, "message": "History cleared successfully"})
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error clearing history: {str(e)}\n{error_details}")
        return jsonify({"success": False, "message": f"Error clearing history: {str(e)}"}), 500

# Add a debug endpoint to check file permissions
@app.route('/api/debug/permissions', methods=['GET'])
def check_permissions():
    """Debug endpoint to check file permissions."""
    import os
    import stat
    
    results = {
        "data_dir": {
            "exists": DATA_DIR.exists(),
            "is_dir": DATA_DIR.is_dir() if DATA_DIR.exists() else False,
            "permissions": oct(stat.S_IMODE(os.stat(DATA_DIR).st_mode)) if DATA_DIR.exists() else None,
            "owner": os.stat(DATA_DIR).st_uid if DATA_DIR.exists() else None,
            "group": os.stat(DATA_DIR).st_gid if DATA_DIR.exists() else None
        },
        "json_file": {
            "exists": HISTORY_JSON.exists(),
            "is_file": HISTORY_JSON.is_file() if HISTORY_JSON.exists() else False,
            "permissions": oct(stat.S_IMODE(os.stat(HISTORY_JSON).st_mode)) if HISTORY_JSON.exists() else None,
            "owner": os.stat(HISTORY_JSON).st_uid if HISTORY_JSON.exists() else None,
            "group": os.stat(HISTORY_JSON).st_gid if HISTORY_JSON.exists() else None
        },
        "parquet_file": {
            "exists": HISTORY_PARQUET.exists(),
            "is_file": HISTORY_PARQUET.is_file() if HISTORY_PARQUET.exists() else False,
            "permissions": oct(stat.S_IMODE(os.stat(HISTORY_PARQUET).st_mode)) if HISTORY_PARQUET.exists() else None,
            "owner": os.stat(HISTORY_PARQUET).st_uid if HISTORY_PARQUET.exists() else None,
            "group": os.stat(HISTORY_PARQUET).st_gid if HISTORY_PARQUET.exists() else None
        }
    }
    
    return jsonify(results)

# Function to run scheduled speed test
def run_scheduled_speedtest():
    global NEXT_SCHEDULED_TEST
    
    if RUN_BOTH_TESTS:
        print(f"Running scheduled speedtest for both providers with {DELAY_BETWEEN_TESTS} seconds delay")
        
        # Run OpenSpeedTest first
        print("Running OpenSpeedTest...")
        run_specific_test("openspeedtest")
        
        # Wait for specified delay
        print(f"Waiting {DELAY_BETWEEN_TESTS} seconds before running SpeedSmart...")
        time.sleep(DELAY_BETWEEN_TESTS)
        
        # Run SpeedSmart next
        print("Running SpeedSmart...")
        run_specific_test("speedsmart")
    else:
        print(f"Running scheduled speedtest using {AUTO_TEST_PROVIDER} provider")
        run_specific_test(AUTO_TEST_PROVIDER)
    
    # Update next scheduled time
    if AUTO_TEST_ENABLED:
        NEXT_SCHEDULED_TEST = datetime.now(timezone.utc).timestamp() + int(AUTO_TEST_INTERVAL)
        update_config()

def run_specific_test(provider):
    """Run a specific test provider and log results."""
    # Function to capture stdout during test run with retry logic
    def run_test_with_capture():
        import io
        import sys
        from contextlib import redirect_stdout
        
        # Try up to 3 times
        for attempt in range(3):
            try:
                f = io.StringIO()
                with redirect_stdout(f):
                    if provider == "openspeedtest":
                        openspeedtest_speed_test()
                    else:
                        speedsmart_speed_test()
                
                output = f.getvalue()
                
                # Try to extract JSON from the output
                json_start = output.find('{')
                json_end = output.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = output[json_start:json_end]
                    return json.loads(json_str)
                else:
                    if attempt < 2:  # If not the last attempt
                        print(f"No JSON found in output, retrying (attempt {attempt+1})")
                        time.sleep(2)  # Wait before retry
                        continue
                    return {"error": "No JSON found in output"}
                    
            except json.JSONDecodeError:
                if attempt < 2:  # If not the last attempt
                    print(f"Failed to parse JSON from output, retrying (attempt {attempt+1})")
                    time.sleep(2)  # Wait before retry
                    continue
                return {"error": "Failed to parse JSON from output", "output": output}
            except Exception as e:
                if attempt < 2:  # If not the last attempt
                    print(f"Error during test: {str(e)}, retrying (attempt {attempt+1})")
                    time.sleep(2)  # Wait before retry
                    continue
                return {"error": f"Test failed: {str(e)}"}
        
        # If we get here, all attempts failed
        return {"error": "All retry attempts failed"}
    
    # Run the test
    try:
        result = run_test_with_capture()
        
        # Update history
        update_history(result, provider)
        
        print(f"Scheduled speedtest for {provider} completed successfully")
        return result
    except Exception as e:
        print(f"Error during scheduled speedtest for {provider}: {e}")
        return {"error": str(e)}

# Function to save/update configuration
def update_config():
    config = {
        "autoTestEnabled": AUTO_TEST_ENABLED,
        "autoTestInterval": int(AUTO_TEST_INTERVAL),
        "autoTestProvider": AUTO_TEST_PROVIDER,
        "runBothTests": RUN_BOTH_TESTS,
        "delayBetweenTests": DELAY_BETWEEN_TESTS,
        "nextScheduledTest": NEXT_SCHEDULED_TEST
    }
    
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

# API endpoint to get configuration
@app.route('/api/config', methods=['GET'])
def get_config():
    """API endpoint to retrieve configuration."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return jsonify(json.load(f))
    else:
        config = {
            "autoTestEnabled": AUTO_TEST_ENABLED,
            "autoTestInterval": int(AUTO_TEST_INTERVAL),
            "autoTestProvider": AUTO_TEST_PROVIDER,
            "runBothTests": RUN_BOTH_TESTS,
            "delayBetweenTests": DELAY_BETWEEN_TESTS,
            "nextScheduledTest": NEXT_SCHEDULED_TEST
        }
        return jsonify(config)

# API endpoint to update configuration
@app.route('/api/config', methods=['POST'])
def update_config_api():
    """API endpoint to update configuration."""
    global AUTO_TEST_ENABLED, AUTO_TEST_INTERVAL, AUTO_TEST_PROVIDER, NEXT_SCHEDULED_TEST, RUN_BOTH_TESTS, DELAY_BETWEEN_TESTS
    
    data = request.json
    
    if 'autoTestEnabled' in data:
        AUTO_TEST_ENABLED = data['autoTestEnabled']
    
    if 'autoTestInterval' in data:
        AUTO_TEST_INTERVAL = str(data['autoTestInterval'])
    
    if 'autoTestProvider' in data:
        AUTO_TEST_PROVIDER = data['autoTestProvider']
        RUN_BOTH_TESTS = AUTO_TEST_PROVIDER.lower() == 'both'
    
    if 'delayBetweenTests' in data:
        DELAY_BETWEEN_TESTS = data['delayBetweenTests']
    
    # Reschedule if needed
    if AUTO_TEST_ENABLED:
        NEXT_SCHEDULED_TEST = datetime.now(timezone.utc).timestamp() + int(AUTO_TEST_INTERVAL)
    else:
        NEXT_SCHEDULED_TEST = None
    
    # Update config file
    update_config()
    
    return jsonify({"success": True, "message": "Configuration updated"})

# Background thread for scheduling
def scheduler_thread():
    """Background thread for running scheduled tests."""
    while True:
        if AUTO_TEST_ENABLED and NEXT_SCHEDULED_TEST:
            current_time = datetime.now(timezone.utc).timestamp()
            if current_time >= NEXT_SCHEDULED_TEST:
                run_scheduled_speedtest()
        
        # Check every minute
        time.sleep(60)

if __name__ == '__main__':
    # Make sure the index.html file exists in the static folder
    static_dir = Path("/app/static")
    static_dir.mkdir(exist_ok=True)
    
    index_file = static_dir / "index.html"
    if not index_file.exists():
        # If index.html doesn't exist, create a basic file that redirects to the dashboard
        with open(index_file, "w") as f:
            f.write("<meta http-equiv='refresh' content='0;url=/static/dashboard.html'>")
    
    # Initialize configuration and next scheduled test
    if AUTO_TEST_ENABLED:
        NEXT_SCHEDULED_TEST = datetime.now(timezone.utc).timestamp() + int(AUTO_TEST_INTERVAL)
    update_config()
    
    # Start scheduler in background thread
    scheduler = threading.Thread(target=scheduler_thread, daemon=True)
    scheduler.start()
    
    app.run(host='0.0.0.0', port=3667)
