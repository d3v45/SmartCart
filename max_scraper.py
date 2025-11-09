import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import re

def clean_max_price(price_str):
    """Cleans the price string from Max Fashion."""
    # Remove currency symbols and extract numbers
    match = re.search(r'([\d,]+)', price_str)
    if match:
        return int(match.group(1).replace(',', ''))
    return 0

def scrape_max_fashion(product_name):
    """
    Scrapes Max Fashion by simulating scrolling to load all products.
    """
    print(f"Scraping Max Fashion for '{product_name}'...")
    url = f'https://www.maxfashion.in/in/en/search?q={product_name}'

    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    options.add_argument('--start-maximized')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    products_found = []
    
    try:
        driver.get(url)
        
        print("Page loaded. Waiting for content to render...")
        time.sleep(5)
        
        print("Simulating user scroll to load all products...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        
        while scroll_attempts < 10:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            scroll_attempts += 1
        
        print("Scrolling complete. Extracting product data...")
        
        # Find all product containers with the 'product' class
        containers = driver.find_elements(By.CSS_SELECTOR, "div.product")
        print(f"Max Fashion: Found {len(containers)} products.")

        for idx, item in enumerate(containers, 1):
            try:
                # Get the full text content of the container
                text_content = item.text.strip()
                
                # Extract product link (second link which has the product name)
                links = item.find_elements(By.TAG_NAME, 'a')
                if len(links) < 2:
                    continue
                
                # The second link usually has the product name as text
                product_link = links[1]
                product_url = product_link.get_attribute('href')
                full_name = product_link.text.strip()
                
                # If name is empty, try the image alt text
                if not full_name:
                    try:
                        image_element = item.find_element(By.TAG_NAME, 'img')
                        full_name = image_element.get_attribute('alt')
                    except:
                        pass
                
                # Extract image
                try:
                    image_element = item.find_element(By.TAG_NAME, 'img')
                    image_url = image_element.get_attribute('src')
                except:
                    image_url = None
                
                # Extract price from text content
                # Look for patterns like "₹ 599" or "₹ 1,593"
                # The current/selling price is usually the first price mentioned
                price_matches = re.findall(r'₹\s*([\d,]+)', text_content)
                
                cleaned_price = 0
                if price_matches:
                    # If there are multiple prices (original and discounted), take the first one (current price)
                    cleaned_price = clean_max_price(price_matches[0])
                
                # Validate and add product
                if full_name and cleaned_price > 0 and image_url and product_url:
                    products_found.append({
                        'Product Name': full_name,
                        'Price': cleaned_price,
                        'Image URL': image_url,
                        'Product URL': product_url,
                        'Store': 'Max Fashion'
                    })
                    print(f"✓ Product {len(products_found)}: {full_name} - ₹{cleaned_price}")
                    
            except Exception as e:
                print(f"✗ Error parsing product {idx}: {str(e)}")
                continue
                
    except Exception as e:
        print(f"An error occurred while scraping Max Fashion: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()
        
    return products_found

# Example usage
if __name__ == "__main__":
    product_list = scrape_max_fashion("shirt")
    print(f"\nFound {len(product_list)} products from Max Fashion:\n")
    for idx, product in enumerate(product_list, 1):
        print(f"{idx}. {product['Product Name']} - ₹{product['Price']}")
        print(f"   Link: {product['Product URL']}")
        print(f"   Image: {product['Image URL']}\n")
