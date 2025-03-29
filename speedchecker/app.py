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

# Global lock for accessing test history and config
history_lock = threading.Lock()
config_lock = threading.Lock()

# Track active tests for status reporting
active_tests = {}
active_tests_lock = threading.Lock()

def register_active_test(provider, start_time=None):
    """Register a test as active"""
    with active_tests_lock:
        if start_time is None:
            start_time = datetime.now(timezone.utc)
        active_tests[provider] = {
            "start_time": start_time,
            "timestamp": start_time.timestamp()
        }
        print(f"[{datetime.now(timezone.utc).isoformat()}] Registered active test: {provider}")

def unregister_active_test(provider):
    """Mark a test as complete"""
    with active_tests_lock:
        if provider in active_tests:
            del active_tests[provider]
            print(f"[{datetime.now(timezone.utc).isoformat()}] Unregistered test: {provider}")

def get_active_tests():
    """Get a copy of active tests"""
    with active_tests_lock:
        return dict(active_tests)

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
    # Skip if result is None or has an error
    if result is None or (isinstance(result, dict) and "error" in result):
        print(f"Not adding erroneous result to history: {result}")
        return None
        
    history = load_history()
    
    # Ensure timestamp is in UTC
    timestamp = datetime.now(timezone.utc).isoformat()
    
    try:
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
    except (KeyError, ValueError, TypeError) as e:
        print(f"Error updating history with result from {provider}: {e}")
        print(f"Problematic result: {result}")
        return None

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
    
    # Register this test as active
    register_active_test(provider)
    
    try:
        # Run the test directly
        result = run_specific_test(provider)
        return jsonify(result)
    finally:
        # Always unregister the test
        unregister_active_test(provider)

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

# Function to run a specific test provider
def run_specific_test(provider):
    """Run a specific test provider and log results."""
    print(f"[{datetime.now(timezone.utc).isoformat()}] Running test for provider: {provider}")
    
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
        
        # Update history only if no error
        if "error" not in result:
            entry = update_history(result, provider)
            if entry:
                print(f"Test for {provider} completed successfully, added to history")
            else:
                print(f"Test for {provider} completed but not added to history")
        else:
            print(f"Test for {provider} failed: {result.get('error')}")
        
        return result
    except Exception as e:
        print(f"Exception during test for {provider}: {e}")
        return {"error": str(e)}

# Updated API endpoint for sequential testing (old school)
@app.route('/api/speedtest/schedule/run-now', methods=['POST'])
def run_scheduled_test_now():
    """API endpoint to run speed tests sequentially."""
    
    with config_lock:
        local_run_both = RUN_BOTH_TESTS
        local_provider = AUTO_TEST_PROVIDER
    
    print(f"[{datetime.now(timezone.utc).isoformat()}] Running test based on configuration")
    
    # Start a thread to handle the tests sequentially
    thread = threading.Thread(
        target=run_tests_sequentially,
        args=(local_run_both, local_provider)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "success": True,
        "message": "Test(s) scheduled to run sequentially"
    })

def run_tests_sequentially(run_both, provider):
    """Run tests in a truly sequential manner."""
    try:
        if run_both:
            # Run OpenSpeedTest first
            print(f"[{datetime.now(timezone.utc).isoformat()}] Starting OpenSpeedTest...")
            
            # Register and run first test
            register_active_test("openspeedtest")
            ost_result = run_specific_test("openspeedtest")
            unregister_active_test("openspeedtest")
            
            if "error" in ost_result:
                print(f"OpenSpeedTest failed: {ost_result.get('error')}")
            else:
                print("OpenSpeedTest completed successfully")
            
            # Wait between tests - fixed 120 second delay as requested
            print(f"[{datetime.now(timezone.utc).isoformat()}] Waiting 120 seconds before running SpeedSmart...")
            time.sleep(120)  # Fixed 120 second delay
            
            # Run SpeedSmart next
            print(f"[{datetime.now(timezone.utc).isoformat()}] Starting SpeedSmart...")
            
            # Register and run second test
            register_active_test("speedsmart")
            ss_result = run_specific_test("speedsmart")
            unregister_active_test("speedsmart")
            
            if "error" in ss_result:
                print(f"SpeedSmart failed: {ss_result.get('error')}")
            else:
                print("SpeedSmart completed successfully")
            
            print(f"[{datetime.now(timezone.utc).isoformat()}] All scheduled tests complete")
        
        else:
            # Run a single test
            print(f"[{datetime.now(timezone.utc).isoformat()}] Starting single test: {provider}")
            
            register_active_test(provider)
            result = run_specific_test(provider)
            unregister_active_test(provider)
            
            if "error" in result:
                print(f"Test for {provider} failed: {result.get('error')}")
            else:
                print(f"Test for {provider} completed successfully")
    
    except Exception as e:
        print(f"Exception in sequential test run: {e}")
        # Clean up any active test markers
        unregister_active_test("openspeedtest")
        unregister_active_test("speedsmart")

# Function to save/update configuration
def update_config():
    """Save current configuration to file."""
    with config_lock:
        config = {
            "autoTestEnabled": AUTO_TEST_ENABLED,
            "autoTestInterval": int(AUTO_TEST_INTERVAL),
            "autoTestProvider": AUTO_TEST_PROVIDER,
            "runBothTests": RUN_BOTH_TESTS,
            "delayBetweenTests": DELAY_BETWEEN_TESTS
        }
    
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

# API endpoint to get configuration
@app.route('/api/config', methods=['GET'])
def get_config():
    """API endpoint to retrieve configuration."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            return jsonify(config)
    else:
        with config_lock:
            config = {
                "autoTestEnabled": AUTO_TEST_ENABLED,
                "autoTestInterval": int(AUTO_TEST_INTERVAL),
                "autoTestProvider": AUTO_TEST_PROVIDER,
                "runBothTests": RUN_BOTH_TESTS,
                "delayBetweenTests": DELAY_BETWEEN_TESTS
            }
        
        return jsonify(config)

# API endpoint to update configuration
@app.route('/api/config', methods=['POST'])
def update_config_api():
    """API endpoint to update configuration."""
    global AUTO_TEST_ENABLED, AUTO_TEST_INTERVAL, AUTO_TEST_PROVIDER, RUN_BOTH_TESTS, DELAY_BETWEEN_TESTS
    
    data = request.json
    
    with config_lock:
        if 'autoTestEnabled' in data:
            AUTO_TEST_ENABLED = data['autoTestEnabled']
        
        if 'autoTestInterval' in data:
            AUTO_TEST_INTERVAL = str(data['autoTestInterval'])
        
        if 'autoTestProvider' in data:
            AUTO_TEST_PROVIDER = data['autoTestProvider']
            RUN_BOTH_TESTS = AUTO_TEST_PROVIDER.lower() == 'both'
        
        if 'delayBetweenTests' in data:
            DELAY_BETWEEN_TESTS = data['delayBetweenTests']
    
    # Update config file
    update_config()
    
    return jsonify({"success": True, "message": "Configuration updated"})

@app.route('/api/scheduler/status', methods=['GET'])
def get_scheduler_status():
    """Get the current status of the scheduler and active tests."""
    active = get_active_tests()
    
    status = {
        "autoTestEnabled": AUTO_TEST_ENABLED,
        "activeTests": active,
        "hasActiveTests": len(active) > 0,
        "currentTime": datetime.now(timezone.utc).isoformat(),
        "currentTimestamp": datetime.now(timezone.utc).timestamp()
    }
    
    return jsonify(status)

if __name__ == '__main__':
    # Make sure the index.html file exists in the static folder
    static_dir = Path("/app/static")
    static_dir.mkdir(exist_ok=True)
    
    index_file = static_dir / "index.html"
    if not index_file.exists():
        # If index.html doesn't exist, create a basic file that redirects to the dashboard
        with open(index_file, "w") as f:
            f.write("<meta http-equiv='refresh' content='0;url=/static/dashboard.html'>")
    
    # Initialize configuration
    update_config()
    
    try:
        app.run(host='0.0.0.0', port=3667)
    except KeyboardInterrupt:
        print("Shutting down application...")
