import json
import re
import time

from playwright.sync_api import Playwright, sync_playwright


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    try:
        # Navigate to the speed test page
        page.goto("https://openspeedtest.com/?run")

        # Wait for the page to navigate to the results page
        page.wait_for_url(re.compile(r"https://openspeedtest.com/results/.*"), timeout=60000)

        # Initialize results dictionary
        results_dict = {}

        animation = "|/-\\"
        animation_index = 0

        # Animation loop while waiting for results
        while not page.locator('symbol#downResultC1 text.rtextnum').first.is_visible():
            print(f"{animation[animation_index]} Running speed test...", end="\r")
            animation_index = (animation_index + 1) % len(animation)
            time.sleep(0.1)

        # Extract download speed
        download_element = page.locator('symbol#downResultC1 text.rtextnum')
        download_speed = download_element.evaluate('(element) => element.textContent')
        results_dict['Download Speed'] = f"{download_speed} Mbps"

        # Extract upload speed
        upload_element = page.locator('symbol#upResultC2 text.rtextnum')
        upload_speed = upload_element.evaluate('(element) => element.textContent')
        results_dict['Upload Speed'] = f"{upload_speed} Mbps"

        # Extract ping
        ping_element = page.locator('symbol#pingResultC3 text.rtextnum')
        ping = ping_element.evaluate('(element) => element.textContent')
        results_dict['Ping'] = f"{ping} ms"

        # Extract jitter
        jitter_element = page.locator('symbol#jitterResultC3 text.rtextnum')
        jitter = jitter_element.evaluate('(element) => element.textContent')
        results_dict['Jitter'] = f"{jitter} ms"

        # Extract server location
        server_location_element = page.locator('text#isp-Name')
        server_location = server_location_element.evaluate('(element) => element.textContent.trim()')
        results_dict['Server Location'] = server_location

        # Extract server name
        server_name_element = page.locator('symbol#ServerName text.rtextnum tspan')
        server_name = server_name_element.evaluate('(element) => element.textContent.trim()')
        results_dict['Server Name'] = server_name

        # Print results as JSON
        print(json.dumps(results_dict, indent=2))

    finally:
        # Close the browser
        context.close()
        browser.close()

def openspeedtest_speed_test():
    """
    This function runs a speed test on openspeedtest.com using the Playwright library.
    It navigates to the website, starts the test, waits for completion, extracts the speed, ping, jitter, ISP, and server information,
    and prints the results in JSON format.
    """
    print("\nRunning Open Speed Test (openspeedtest.com)"+"\n")
    with sync_playwright() as playwright:
        run(playwright)

#ost_test()
