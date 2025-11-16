import json
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_session import Session
import pandas as pd
import numpy as np
import atexit
import time  # <--- ADD THIS

# --- 1. NEW IMPORTS for Asynchronous Tasks (No Celery/Redis) ---
import concurrent.futures
import threading
import uuid
# -------------------------------------------------------------

# --- NEW: Import your coupon scrapers ---
from coupon_scrapers import (
    scrape_myntra_coupons, 
    scrape_snapdeal_coupons, 
    scrape_nike_coupons, 
    scrape_max_fashion_coupons
)

# --- Your Project's Code ---
# We still use db_models for our database logic
import db_models
from recommender import get_recommendations, train_dl_model, get_dl_recommendation_from_trained_model
from myntra_scraper import scrape_myntra
from snapdeal_scraper import scrape_snapdeal
from nike_scraper import scrape_nike
from max_scraper import scrape_max_fashion

# --- App Configuration ---
app = Flask(__name__)
app.config["SECRET_KEY"] = "your_super_secret_key_change_this"
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
Session(app)

# Ensure all new tables are created on startup
db_models.create_tables()

# ... (after db_models.create_tables())

# --- NEW: Background Thread Function ---

def run_coupon_scraper_loop():
    """
    This function runs in a separate thread and periodically scrapes for coupons.
    """
    print("Starting background coupon scraper thread...")
    # Run once on startup, then loop
    while True:
        try:
            print("THREAD: Running nightly coupon check...")
            
            # 1. Scrape for coupons (these are the simulated functions)
            all_coupons = []
            all_coupons.extend(scrape_myntra_coupons())
            all_coupons.extend(scrape_snapdeal_coupons())
            all_coupons.extend(scrape_nike_coupons())
            all_coupons.extend(scrape_max_fashion_coupons())

            # 2. Add them to the database
            for coupon in all_coupons:
               db_models.add_coupon(coupon['store'], coupon['code'], coupon['description'])
            
            print("THREAD: Coupon check complete. Sleeping for 4 hours.")
            
            # Sleep for 4 hours (4 * 60 * 60 seconds)
            time.sleep(4 * 3600) 

        except Exception as e:
            print(f"THREAD: Error in coupon scraper loop: {e}. Retrying in 1 hour.")
            time.sleep(3600) # Wait an hour if something breaks

# --- 2. MODIFIED: Global Caches & Threading ---

# Global cache for trained models
model_cache = {}

# Global cache for product search results (DataFrames)
product_cache = {}

# Global cache for entire search results (DataFrame + Filters)
global_search_cache = {}

# This replaces Celery/Redis for managing job state
task_cache = {}
# We use a lock to safely read/write to task_cache from multiple threads
task_cache_lock = threading.Lock()

# --- MODIFIED: Use 2 workers to prevent memory crashes but still get some parallelism ---
executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
# -----------------------------------------------

# --- Smart Category Filtering (Unchanged) ---
def categorize_product(name):
    """Simple heuristic to categorize a product."""
    name = name.lower()
    if any(k in name for k in ['shoe', 'sneaker', 'boot', 'sandal', 'heel', 'loafe']):
        return 'Footwear'
    if any(k in name for k in ['shirt', 't-shirt', 'top', 'kurta', 'kurti', 'polo']):
        return 'Apparel (Top)'
    if any(k in name for k in ['pant', 'jeans', 'trouser', 'legging', 'skirt']):
        return 'Apparel (Bottom)'
    if any(k in name for k in ['dress', 'gown', 'jumpsuit']):
        return 'Apparel (Full)'
    if any(k in name for k in ['watch']):
        return 'Accessory'
    if any(k in name for k in ['bag', 'backpack', 'handbag']):
        return 'Bags'
    return 'Other'

# --- Authentication Routes (Unchanged) ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user_id = db_models.authenticate_user(username, password)
        if user_id:
            session["user_id"] = user_id
            session["username"] = username
            return redirect(url_for("index"))
        else:
            return render_template("login.html", error="Invalid username or password.", is_login=True)
    return render_template("login.html", is_login=True)

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if not username or not password:
            return render_template("login.html", error="Please fill all fields.", is_login=False)
        if db_models.register_user(username, password):
            user_id = db_models.authenticate_user(username, password)
            if user_id:
                session["user_id"] = user_id
                session["username"] = username
                return redirect(url_for("index"))
            else:
                return render_template("login.html", error="Account created, but login failed.", is_login=True)
        else:
            return render_template("login.html", error="Username already exists.", is_login=False)
    return render_template("login.html", is_login=False)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --- Main App Routes (Unchanged) ---
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("index.html", username=session.get("username"))

# --- Feature 4: User Profile Page (Unchanged) ---
@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    user_id = session['user_id']
    wishlist = db_models.get_wishlist(user_id)
    tracked_items = db_models.get_tracked_items(user_id)
    history = db_models.get_click_history(user_id, limit=100)
    
    return render_template("profile.html", 
                           username=session.get("username"),
                           wishlist=wishlist,
                           tracked_items=tracked_items,
                           click_history=history)

# --- API Routes ---

# --- 3. NEW HELPER FUNCTION: Runs the final processing ---
def process_final_data(task_id, query):
    """
    This runs in a background thread *after* all scrapers are done.
    It performs the expensive data processing and AI training.
    """
    print(f"THREADED JOB {task_id}: All scrapers finished. Processing final data...")
    try:
        with task_cache_lock:
            # Get all collected products
            task = task_cache[task_id]
            all_products = task["all_products"]

        if not all_products:
            raise Exception("No products found by any scraper.")

        # --- This is all your processing logic ---
        df = pd.DataFrame(all_products)
        df.drop_duplicates(subset=['Product Name'], inplace=True)
        if 'Price' not in df.columns: df['Price'] = 0
        df = df[df['Price'] > 0]
        df.reset_index(drop=True, inplace=True)
        
        if df.empty:
            raise Exception("No valid products found after filtering (e.g., price=0).")

        df['Category'] = df['Product Name'].apply(categorize_product)

        # Extract Filters
        unique_stores = sorted(df['Store'].unique().tolist())
        unique_brands = sorted(df['Product Name'].apply(lambda x: x.split(' ')[0]).unique().tolist())
        unique_categories = sorted(df['Category'].unique().tolist())
        min_price = int(df['Price'].min())
        max_price = int(df['Price'].max())
        
        filter_options = {
            "stores": unique_stores,
            "brands": unique_brands,
            "categories": unique_categories,
            "minPrice": min_price,
            "maxPrice": max_price
        }
        
        # Train AI Model
        print(f"THREADED JOB {task_id}: Training model for query: {query}")
        model, tokenizer, max_length = train_dl_model(df)
        
        # --- Update shared caches ---
        model_cache[query] = (model, tokenizer, max_length)
        global_search_cache[query] = (df, filter_options) # Save final *processed* data
        
        # --- Store the final result in the task_cache ---
        with task_cache_lock:
            task = task_cache[task_id]
            task["status"] = "SUCCESS"
            task["all_products"] = df.to_dict('records') # Store final, cleaned list
            task["filters"] = filter_options
        
        print(f"THREADED JOB {task_id}: Finished processing.")

    except Exception as e:
        print(f"THREADED JOB {task_id}: FAILED during final processing. {e}")
        with task_cache_lock:
            task_cache[task_id] = {"status": "ERROR", "message": str(e)}

# --- 4. NEW HELPER FUNCTION: Runs ONE scraper ---
def run_one_scraper(task_id, store_name, scraper_func, query):
    """
    This function runs one scraper in a background thread.
    It updates the task_cache with its partial results.
    """
    print(f"THREADED JOB {task_id}: Starting scraper '{store_name}' for '{query}'")
    try:
        # Run the actual scraper function
        results = scraper_func(query)
        print(f"THREADED JOB {task_id}: Scraper '{store_name}' finished, found {len(results)} items.")
        
        if results:
            with task_cache_lock:
                task = task_cache[task_id]
                # Add to the master list *and* the "new" queue
                task["all_products"].extend(results)
                task["new_products_queue"].extend(results)

    except Exception as e:
        print(f"THREADED JOB {task_id}: Scraper '{store_name}' FAILED: {e}")
        # Don't add any results, just log the failure
        pass # We still want other scrapers to run

    finally:
        # This block *always* runs, even if the scraper failed
        with task_cache_lock:
            task = task_cache[task_id]
            task["remaining_scrapers"] -= 1
            print(f"THREADED JOB {task_id}: '{store_name}' done. {task['remaining_scrapers']} scrapers remaining.")
            
            # If this is the *last* scraper to finish, trigger the final processing
            if task["remaining_scrapers"] == 0:
                task["status"] = "PROCESSING" # Tell frontend to wait
                executor.submit(process_final_data, task_id, query)

# --- 5. MODIFIED: /api/search ---
@app.route("/api/search")
def api_search():
    """
    This is now a FAST, ASYNCHRONOUS route.
    It dispatches 4 background jobs and returns a task ID.
    """
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    query = request.args.get("q")
    if not query:
        return jsonify({"error": "No query provided"}), 400
    
    session['last_query'] = query

    # --- CHECK GLOBAL CACHE FIRST (Unchanged) ---
    if query in global_search_cache:
        print(f"User {session['user_id']} got CACHE HIT for query: {query}")
        df, filter_options = global_search_cache[query]
        product_cache[session['user_id']] = df
        return jsonify({
            "status": "SUCCESS", 
            "products": df.to_dict('records'),
            "filters": filter_options,
            "message": f"Found {len(df)} unique products (from cache)."
        })
    # --- END OF CACHE CHECK ---
    
    print(f"User {session['user_id']} got CACHE MISS. Dispatching 4 THREADED jobs for: {query}")

    # --- THIS IS THE NEW PART ---
    task_id = str(uuid.uuid4())
    
    # Create the shared task object
    with task_cache_lock:
        task_cache[task_id] = {
            "status": "PENDING", # PENDING, PROCESSING, SUCCESS, ERROR
            "remaining_scrapers": 4, # A counter
            "all_products": [], # Master list of *all* products found
            "new_products_queue": [], # Products to be sent to client
            "filters": None
        }
    
    # Submit 4 separate jobs to the thread pool
    # The executor will run them based on max_workers (e.g., 2 at a time)
    executor.submit(run_one_scraper, task_id, "Myntra", scrape_myntra, query)
    executor.submit(run_one_scraper, task_id, "Snapdeal", scrape_snapdeal, query)
   # executor.submit(run_one_scraper, task_id, "Nike", scrape_nike, query)
    executor.submit(run_one_scraper, task_id, "MaxFashion", scrape_max_fashion, query)
    
    # Immediately return the task ID
    return jsonify({
        "status": "PENDING",
        "task_id": task_id
    })

# --- 6. MODIFIED: /api/search-status ---
@app.route("/api/search-status/<task_id>")
def api_search_status(task_id):
    """
    Checks the status of a job.
    If "PENDING", it returns any new products.
    If "SUCCESS", it returns the final processed data.
    """
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    with task_cache_lock:
        task = task_cache.get(task_id)

    if not task:
        return jsonify({"status": "ERROR", "message": "Task not found"}), 404
    
    if task["status"] == "SUCCESS":
        # Final success state: return all data and clear task
        with task_cache_lock:
            if task_id in task_cache:
                del task_cache[task_id] # Clean up
        
        # Set the user's personal cache
        query = session.get('last_query')
        if query and query in global_search_cache:
             df, _ = global_search_cache[query]
             product_cache[session['user_id']] = df

        return jsonify({
            "status": "SUCCESS",
            "products": task["all_products"],
            "filters": task["filters"]
        })

    elif task["status"] == "PROCESSING":
        # Scrapers are done, but final processing (AI) is running.
        return jsonify({"status": "PROCESSING", "new_products": []})

    elif task["status"] == "ERROR":
        # An error occurred during final processing
        with task_cache_lock:
            if task_id in task_cache:
                del task_cache[task_id]
        return jsonify(task), 500 # task contains the error message

    elif task["status"] == "PENDING":
        # Scrapers are still running. Send any new products.
        new_products_to_send = []
        with task_cache_lock:
            task = task_cache[task_id] # Re-get task inside lock
            # Send everything in the queue and clear it
            new_products_to_send = task["new_products_queue"]
            task["new_products_queue"] = []
        
        return jsonify({
            "status": "PENDING",
            "new_products": new_products_to_send
        })

@app.route("/api/recommend")
def api_recommend():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    product_name = request.args.get("product_name")
    if not product_name:
        return jsonify({"error": "No product name provided"}), 400
        
    db_models.log_click(session["user_id"], product_name)
    
    try:
        df = product_cache[session['user_id']]
    except KeyError:
        return jsonify({"error": "No search data found. Please search first."}), 400
    
    # --- Combined Recommendation Logic ---
    
    final_recs_list = []
    seen_urls = set()

    # 1. Get AI-Based (DL)
    query = session.get('last_query', 'default')
    if query in model_cache:
        model, product_to_id, max_length = model_cache[query]
        if model:
            dl_names_df = get_dl_recommendation_from_trained_model(product_name, df, model, product_to_id, max_length)
            if not dl_names_df.empty:
                for rec in dl_names_df.to_dict(orient='records'):
                    if rec['Product URL'] not in seen_urls:
                        
                        # --- THIS IS THE NEW LINE ---
                        rec['rec_type'] = 'ai' # Tag as AI
                        
                        final_recs_list.append(rec)
                        seen_urls.add(rec['Product URL'])

    # 2. Get Content-Based (Similar Name)
    rec_names_df = get_recommendations(product_name, df)
    if not rec_names_df.empty:
        for rec in rec_names_df.to_dict(orient='records'):
            if rec['Product URL'] not in seen_urls:
                
                # --- THIS IS THE NEW LINE ---
                rec['rec_type'] = 'name' # Tag as Name-Based
                
                final_recs_list.append(rec)
                seen_urls.add(rec['Product URL'])

    # Return a single combined list
    return jsonify({
        "similar": [], 
        "ai_powered": final_recs_list
    })
    
# --- Feature 2 & 3: Wishlist & Price Track API (Unchanged) ---
@app.route("/api/wishlist/add", methods=["POST"])
def api_add_to_wishlist():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    product = request.json
    success = db_models.add_to_wishlist(session['user_id'], product)
    if success:
        return jsonify({"success": True, "message": "Added to wishlist."})
    else:
        return jsonify({"success": False, "message": "Item already in wishlist."})

@app.route("/api/wishlist/remove", methods=["POST"])
def api_remove_from_wishlist():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    product_url = request.json.get('product_url')
    db_models.remove_from_wishlist(session['user_id'], product_url)
    return jsonify({"success": True, "message": "Removed from wishlist."})

@app.route("/api/track_price", methods=["POST"])
def api_track_price():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    product = request.json
    db_models.track_price(session['user_id'], product)
    db_models.log_price(product)
    return jsonify({"success": True, "message": "Price tracking enabled."})

# --- NEW: API Endpoint for Coupons ---

@app.route("/api/coupons")
def api_get_coupons():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    coupons = db_models.get_all_coupons()
    return jsonify(coupons)


# ... (after the new @app.route("/api/coupons") function)

# --- NEW: Start the background thread ---
# We set daemon=True so the thread automatically exits when the main app stops
coupon_thread = threading.Thread(target=run_coupon_scraper_loop, daemon=True)
coupon_thread.start()
# ------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5001)

    
    