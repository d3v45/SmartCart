import time
import pprint 

# This file now simulates scraping and returns a fixed list of coupons.
# This allows you to build your feature without fighting anti-bot security.
# The 'headless=True' argument is kept so it matches what app.py expects,
# but it doesn't do anything in this simulated version.

def scrape_myntra_coupons(headless=True):
    """Simulates scraping coupons for Myntra."""
    print("THREAD: Simulating Myntra coupon scrape...")
    time.sleep(1) # Simulate network delay
    return [
        {"store": "Myntra", "code": "MYNTRA20", "description": "Flat 20% Off On First Order"},
        {"store": "Myntra", "code": "STYLEUP", "description": "Get Rs. 200 Off On 1499+"}
    ]

def scrape_nike_coupons(headless=True):
    """Simulates scraping coupons for Nike."""
    print("THREAD: Simulating Nike coupon scrape...")
    time.sleep(1)
    return [
        {"store": "Nike", "code": "JUSTDOIT", "description": "15% Off Running Shoes"},
        {"store": "Nike", "code": "FREESHIP", "description": "Free Shipping On All Orders"}
    ]

def scrape_snapdeal_coupons(headless=True):
    """Simulates scraping coupons for Snapdeal."""
    print("THREAD: Simulating Snapdeal coupon scrape...")
    time.sleep(1)
    return [
        {"store": "Snapdeal", "code": "SNAP50", "description": "Flat Rs. 50 Off Electronics"}
    ]

def scrape_max_fashion_coupons(headless=True):
    """Simulates scraping coupons for Max Fashion."""
    print("THREAD: Simulating Max Fashion scrape...")
    time.sleep(1)
    return [
        {"store": "Max Fashion", "code": "MAXSTYLE", "description": "Buy 1 Get 1 Free on T-Shirts"}
    ]

# --- Test Block ---
if __name__ == "__main__":
    print("--- STARTING SCRAPER TEST (SIMULATION) ---")
    
    coupons = scrape_myntra_coupons() 
    
    print("\n--- RESULTS ---")
    pprint.pprint(coupons)
    print("--- TEST COMPLETE ---")