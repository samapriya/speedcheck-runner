import json
import time

from playwright.sync_api import Playwright, sync_playwright

result_dict = {}

def run(playwright: Playwright) -> None:
    """
    This function runs a speed test on speedsmart.net using the Playwright library.
    It navigates to the website, starts the test, waits for completion, extracts the speed, ping, jitter, ISP, and server information,
    and prints the results in JSON format.

    Parameters:
    playwright (Playwright): An instance of the Playwright library.

    Returns:
    None
    """
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    try:
        # Navigate to the page
        page.goto("https://speedsmart.net/", timeout=60000)

        # Click the "Start Test" button
        page.locator('button.button_start#start_button').click()

        # Print animation while waiting for test completion
        animation = "|/-\\"
        animation_index = 0
        while not page.locator('#restart_button').is_visible():
            print(f"{animation[animation_index]} Running speed test...", end="\r")
            animation_index = (animation_index + 1) % len(animation)
            time.sleep(0.1)

        # Extract values after the test completes
        print("\n"+"Test completed!"+"\n")
        result_dict['download_speed'] = float(page.locator('#finished_download').inner_text())
        result_dict['upload_speed'] = float(page.locator('#finished_upload').inner_text())
        result_dict['ping_speed'] = int(page.locator('#mobile_final_ping').inner_text())
        result_dict['jitter'] = float(page.locator('#mobile_final_jitter').inner_text())
        result_dict['isp_name'] = page.locator('#current_isp_name_hover').inner_text()
        result_dict['server_name'] = page.locator('#current_server_name_hover').inner_text()


    finally:
        context.close()
        browser.close()

        json_result = json.dumps(result_dict, indent=2)
        print(json_result)
def speedsmart_speed_test():
    """
    This function runs a speed test on speedsmart.net using the Playwright library.
    It navigates to the website, starts the test, waits for completion, extracts the speed, ping, jitter, ISP, and server information,
    and prints the results in JSON format.
    """
    print("\nRunning SpeedSmart.net Speed Test (speedsmart.net)"+"\n")
    with sync_playwright() as playwright:
        run(playwright)

#speedsmart_test()
