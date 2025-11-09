import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re

def clean_snapdeal_price(price_str):
    """Cleans the price string from Snapdeal."""
    match = re.search(r'([\d,]+)', price_str)
    if match:
        return int(match.group(1).replace(',', ''))
    return 0

def scrape_snapdeal(product_name):
    """
    Scrapes Snapdeal by simulating scrolling to load all products.
    """
    print(f"Scraping Snapdeal for '{product_name}'...")
    url = f'https://www.snapdeal.com/search?keyword={product_name}'

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
        
        print("Page loaded. Simulating user scroll to load all products...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        while scroll_attempts < 5:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            scroll_attempts += 1
        
        print("Scrolling complete. Extracting product data...")

        containers = driver.find_elements(By.CLASS_NAME, "product-tuple-listing")
            
        print(f"Snapdeal: Found {len(containers)} products.")

        for item in containers:
            try:
                name_element = item.find_element(By.CLASS_NAME, 'product-title')
                price_element = item.find_element(By.CLASS_NAME, 'product-price')
                image_element = item.find_element(By.TAG_NAME, 'img')
                link_element = item.find_element(By.CLASS_NAME, 'dp-widget-link')
                
                image_url = image_element.get_attribute('src')
                if not image_url or 'grey' in image_url:
                    image_url = image_element.get_attribute('data-src')

                product_url = link_element.get_attribute('href')
                full_name = name_element.text.strip()
                cleaned_price = clean_snapdeal_price(price_element.text.strip())

                if full_name and cleaned_price > 0 and image_url:
                    products_found.append({
                        'Product Name': full_name,
                        'Price': cleaned_price,
                        'Image URL': image_url,
                        'Product URL': product_url,
                        'Store': 'Snapdeal'
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"An error occurred while scraping Snapdeal: {e}")
    finally:
        driver.quit()
        
    return products_found

