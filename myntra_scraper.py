import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re

def clean_myntra_price(price_str):
    match = re.search(r'Rs\.\s*([\d,]+)', price_str)
    if match:
        return int(match.group(1).replace(',', ''))
    # Handle cases where price might be just a number
    match = re.search(r'([\d,]+)', price_str)
    if match:
        return int(match.group(1).replace(',', ''))
    return 0

def scrape_myntra(product_name):
    print(f"Scraping Myntra for '{product_name}'...")
    url = f'https://www.myntra.com/{product_name}'

    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    options.add_argument('--start-maximized')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    products_found = []
    try:
        driver.get(url)
        time.sleep(3)

        wait = WebDriverWait(driver, 20)
        results_container = wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'results-base')))
        containers = results_container.find_elements(By.CLASS_NAME, "product-base")

        for item in containers:
            try:
                brand_element = item.find_element(By.CLASS_NAME, 'product-brand')
                product_desc_element = item.find_element(By.CLASS_NAME, 'product-product')
                price_element = item.find_element(By.CSS_SELECTOR, 'span.product-discountedPrice, div.product-price')
                image_element = item.find_element(By.TAG_NAME, 'img')
                
                # --- THIS IS THE ONLY NEW PART ---
                # Get the product's unique page URL from the 'a' tag
                link_element = item.find_element(By.TAG_NAME, 'a')
                product_url = link_element.get_attribute('href')
                # --- END OF NEW PART ---

                full_name = f"{brand_element.text.strip()} - {product_desc_element.text.strip()}"
                cleaned_price = clean_myntra_price(price_element.text.strip())
                image_url = image_element.get_attribute('src')

                products_found.append({
                    'Product Name': full_name,
                    'Price': cleaned_price,
                    'Image URL': image_url,
                    'Product URL': product_url, # Add the product URL to our data
                    'Store': 'Myntra'
                })
            except Exception:
                continue
    except Exception as e:
        print(f"An error occurred while scraping Myntra: {e}")
    finally:
        driver.quit()

    return products_found

