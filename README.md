# SpeedCheck Runner

A containerized internet speed testing tool that automatically runs and tracks your connection performance over time.

## Overview

SpeedCheck Tester is a self-hosted Docker solution that performs regular internet speed tests using multiple providers, stores historical results, and displays them in an intuitive dashboard. It helps you track your internet performance over time and identify potential issues with your connection.


<p align="center">
  <img src="https://www.svgrepo.com/show/355484/speed.svg" width="125" alt="Speed Test Dashboard Logo">
</p>

## Features

- **Dual-Provider Testing**: Runs tests through both OpenSpeedTest and SpeedSmart for cross-reference verification
- **Automated Testing**: Schedule tests at customizable intervals (hourly, daily, weekly)
- **Historical Data**: Store and visualize all past test results
- **Interactive Dashboard**: View your performance trends with filterable charts and tables
- **Data Export**: Download your test history in CSV or JSON format
- **Timezone Support**: View data in your preferred timezone
- **Dark Mode Support**: Toggle between light and dark themes
- **Fully Containerized**: Easy to deploy with Docker

## Requirements

- Docker and Docker Compose
- Internet connection
- A system that can run Chrome/Chromium in headless mode (used by the speed test providers)

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/speedcheck-tester.git
   cd speedcheck-tester
   ```

2. Configure your settings in the `docker-compose.yml` file (see Configuration section below)

3. Start the container:
   ```bash
   docker-compose up -d
   ```

4. Access the dashboard at `http://localhost:3667`

## Configuration

You can customize the behavior by modifying the environment variables in `docker-compose.yml`:

```yaml
services:
  speedtest-dashboard:
    build: .
    ports:
      - "3667:3667"
    volumes:
      - ./data:/app/data
    environment:
      - AUTO_TEST_ENABLED=true       # Set to 'false' to disable automatic tests
      - AUTO_TEST_INTERVAL=86400     # Interval in seconds (86400 = daily)
      - AUTO_TEST_PROVIDER=both      # 'openspeedtest', 'speedsmart', or 'both'
      - DELAY_BETWEEN_TESTS=300      # Delay in seconds between tests when running both (5 minutes)
    restart: unless-stopped
```

### Environment Variables

| Variable              | Description                                                 | Default           |
| --------------------- | ----------------------------------------------------------- | ----------------- |
| `AUTO_TEST_ENABLED`   | Enable/disable automatic tests                              | `true`            |
| `AUTO_TEST_INTERVAL`  | Time between tests in seconds                               | `86400` (1 day)   |
| `AUTO_TEST_PROVIDER`  | Which test provider(s) to use                               | `both`            |
| `DELAY_BETWEEN_TESTS` | Delay between consecutive tests when running both providers | `300` (5 minutes) |

## How It Works

SpeedCheck Tester consists of several components:

1. **Flask Backend** (`app.py`): Handles API requests, stores test results, and serves the web interface
2. **Test Schedulers** (`scheduled_tests.py`): Manages automated test scheduling
3. **Test Providers**:
   - `speedtest_openspeedtest.py`: Runs tests via OpenSpeedTest.com
   - `speedtest_speedsmart.py`: Runs tests via SpeedSmart.net
4. **Web Dashboard** (`index.html`): Interactive UI for viewing and managing tests

The system uses headless Chrome/Chromium via Playwright to perform the actual speed tests by loading each provider's website and extracting the results.

### Data Storage

Test results are stored in:
- JSON format (`/app/data/speedtest_history.json`)
- Parquet format (`/app/data/speedtest_history.parquet`)

These persist through container restarts via a Docker volume.

## API Endpoints

The application exposes several REST APIs:

| Endpoint                                  | Method | Description                              |
| ----------------------------------------- | ------ | ---------------------------------------- |
| `/api/speedtest?provider=<provider>`      | POST   | Run a manual speed test                  |
| `/api/history`                            | GET    | Get all test history                     |
| `/api/history`                            | DELETE | Clear all test history                   |
| `/api/history/download?format=<json/csv>` | GET    | Download history in specified format     |
| `/api/config`                             | GET    | Get current configuration                |
| `/api/config`                             | POST   | Update configuration                     |
| `/api/speedtest/schedule/run-now`         | POST   | Run tests based on current configuration |

## Troubleshooting

### Test Failures

If tests are consistently failing:

1. Check your internet connection
2. Ensure the container has sufficient resources (CPU/memory)
3. Verify that headless Chrome can run properly in your environment
4. Check the container logs: `docker-compose logs -f`

### Data Not Saving

If test results aren't being saved:

1. Check that the data volume is correctly mounted
2. Verify permissions on the `./data` directory
3. Use the `/api/debug/permissions` endpoint to check file access

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- [OpenSpeedTest](https://openspeedtest.com/) - One of the test providers
- [SpeedSmart](https://speedsmart.net/) - Another test provider
- [Playwright](https://playwright.dev/) - Used for browser automation
- [Flask](https://flask.palletsprojects.com/) - Web framework
- [Chart.js](https://www.chartjs.org/) - For data visualization
