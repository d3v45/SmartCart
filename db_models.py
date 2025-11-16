import sqlite3
import hashlib
import json
from datetime import datetime

# --- User Auth (from user_auth.py) ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_tables():
    """Creates all tables needed for the app."""
    conn = sqlite3.connect('user_history.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Users Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
    ''')
    
    # Clicks Table (with new timestamp column)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS clicks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        product_name TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    ''')

    # --- Feature 2: Wishlist Table ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS wishlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        product_name TEXT,
        product_url TEXT UNIQUE,
        image_url TEXT,
        store TEXT,
        price REAL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    ''')
    
    # --- Feature 3: Price Tracking Tables ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS price_tracking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        product_url TEXT,
        store TEXT,
        desired_price REAL,
        UNIQUE(user_id, product_url),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_url TEXT,
        store TEXT,
        price REAL,
        date DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    
    # ... (after price_history table)
    
    # --- NEW: Coupon Table ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS coupons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        store TEXT NOT NULL,
        code TEXT NOT NULL,
        description TEXT,
        last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(store, code)
    )
    ''')
    

    conn.commit()
    conn.close()

def register_user(username, password):
    conn = sqlite3.connect('user_history.db', check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                       (username, hash_password(password)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def authenticate_user(username, password):
    conn = sqlite3.connect('user_history.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT id, password FROM users WHERE username=?", (username,))
    result = cursor.fetchone()
    conn.close()
    if result and result[1] == hash_password(password):
        return result[0]
    return None

def log_click(user_id, product_name):
    """Logs a product click event."""
    try:
        conn = sqlite3.connect('user_history.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO clicks (user_id, product_name, timestamp) VALUES (?, ?, ?)",
            (user_id, product_name, datetime.now())
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error (log_click): {e}")
    finally:
        if conn:
            conn.close()

def get_click_history(user_id, limit=20):
    """Gets the user's most recent click history."""
    try:
        conn = sqlite3.connect('user_history.db', check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT product_name, timestamp FROM clicks WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit)
        )
        history = [dict(row) for row in cursor.fetchall()]
        return history
    except sqlite3.Error as e:
        print(f"Database error (get_click_history): {e}")
        return []
    finally:
        if conn:
            conn.close()

# --- Wishlist Functions (Feature 2) ---

def add_to_wishlist(user_id, product):
    """Adds a product to the user's wishlist."""
    try:
        conn = sqlite3.connect('user_history.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO wishlist (user_id, product_name, product_url, image_url, store, price) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, product['Product Name'], product['Product URL'], product['Image URL'], product['Store'], product['Price'])
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False # Item already in wishlist
    except sqlite3.Error as e:
        print(f"Database error (add_to_wishlist): {e}")
        return False
    finally:
        if conn:
            conn.close()

def remove_from_wishlist(user_id, product_url):
    """Removes a product from the user's wishlist."""
    try:
        conn = sqlite3.connect('user_history.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM wishlist WHERE user_id = ? AND product_url = ?",
            (user_id, product_url)
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error (remove_from_wishlist): {e}")
    finally:
        if conn:
            conn.close()

def get_wishlist(user_id):
    """Retrieves all products from a user's wishlist."""
    try:
        conn = sqlite3.connect('user_history.db', check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM wishlist WHERE user_id = ?", (user_id,))
        wishlist = [dict(row) for row in cursor.fetchall()]
        return wishlist
    except sqlite3.Error as e:
        print(f"Database error (get_wishlist): {e}")
        return []
    finally:
        if conn:
            conn.close()

# --- Price Tracking Functions (Feature 3) ---

def track_price(user_id, product):
    """Adds a product to the user's price tracking list."""
    desired_price = product['Price'] * 0.9 # e.g., notify at 10% drop
    
    try:
        conn = sqlite3.connect('user_history.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO price_tracking (user_id, product_url, store, desired_price) VALUES (?, ?, ?, ?)",
            (user_id, product['Product URL'], product['Store'], desired_price)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass # Already tracking
    except sqlite3.Error as e:
        print(f"Database error (track_price): {e}")
    finally:
        if conn:
            conn.close()

def log_price(product):
    """Logs the current price of a product to history."""
    try:
        conn = sqlite3.connect('user_history.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO price_history (product_url, store, price, date) VALUES (?, ?, ?, ?)",
            (product['Product URL'], product['Store'], product['Price'], datetime.now())
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error (log_price): {e}")
    finally:
        if conn:
            conn.close()

def get_tracked_items(user_id):
    """Retrieves all products a user is tracking."""
    try:
        conn = sqlite3.connect('user_history.db', check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM price_tracking WHERE user_id = ?", (user_id,))
        tracked_items = [dict(row) for row in cursor.fetchall()]
        return tracked_items
    except sqlite3.Error as e:
        print(f"Database error (get_tracked_items): {e}")
        return []
    finally:
        if conn:
            conn.close()
            
            # --- NEW: Coupon Functions ---

def add_coupon(store, code, description):
    """Adds a new coupon, or updates 'last_updated' if it exists."""
    try:
        conn = sqlite3.connect('user_history.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO coupons (store, code, description, last_updated) 
            VALUES (?, ?, ?, ?)
            ON CONFLICT(store, code) DO UPDATE SET 
            last_updated=excluded.last_updated, description=excluded.description
            """,
            (store, code, description, datetime.now())
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error (add_coupon): {e}")
    finally:
        if conn:
            conn.close()

def get_all_coupons():
    """Retrieves all active coupons, grouped by store."""
    try:
        conn = sqlite3.connect('user_history.db', check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # Get all coupons, most recent first
        cursor.execute("SELECT * FROM coupons ORDER BY store, last_updated DESC")
        
        # Group them by store
        coupons_by_store = {}
        for row in cursor.fetchall():
            item = dict(row)
            store = item['store']
            if store not in coupons_by_store:
                coupons_by_store[store] = []
            coupons_by_store[store].append(item)
            
        return coupons_by_store
    except sqlite3.Error as e:
        print(f"Database error (get_all_coupons): {e}")
        return {}
    finally:
        if conn:
            conn.close()