import json
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_session import Session
import pandas as pd
import numpy as np
import atexit

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

# Global cache for trained models
model_cache = {}

# Global cache for product search results (DataFrames)
product_cache = {}

# Global cache for entire search results (DataFrame + Filters)
# This will be keyed by the search query (e.g., "shoe")
global_search_cache = {}

# --- Smart Category Filtering (Feature 5) ---
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

# --- Authentication Routes ---
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

# --- Main App Routes ---
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("index.html", username=session.get("username"))

# --- Feature 4: User Profile Page ---
@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    user_id = session['user_id']
    wishlist = db_models.get_wishlist(user_id)
    tracked_items = db_models.get_tracked_items(user_id)
    history = db_models.get_click_history(user_id, limit=20)
    
    return render_template("profile.html", 
                           username=session.get("username"),
                           wishlist=wishlist,
                           tracked_items=tracked_items,
                           click_history=history)

# --- API Routes ---

# --- MODIFIED: Synchronous Scraping ---
@app.route("/api/search")
def api_search():
    """
    This is now a SLOW, SYNCHRONOUS route.
    It runs all scrapers and waits for them to finish.
    The frontend will show a loader and wait.
    """
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    query = request.args.get("q")
    if not query:
        return jsonify({"error": "No query provided"}), 400
    
    session['last_query'] = query

    # --- NEW: CHECK GLOBAL CACHE FIRST ---
    if query in global_search_cache:
        print(f"User {session['user_id']} got CACHE HIT for query: {query}")
        
        # Retrieve the cached DataFrame and filter options
        df, filter_options = global_search_cache[query]
        
        # VERY IMPORTANT: We must still update the *user's* cache
        # so the /api/recommend route knows what data to use.
        product_cache[session['user_id']] = df
        
        # Return the cached data immediately
        return jsonify({
            "products": df.to_dict(orient='records'),
            "filters": filter_options,
            "message": f"Found {len(df)} unique products (from cache)."
        })
    # --- END OF CACHE CHECK ---
    
    print(f"User {session['user_id']} got CACHE MISS. Starting SYNCHRONOUS search for: {query}")

    # --- THIS IS THE SLOW PART ---
    # The server will "freeze" here until they are all done
    myntra_results = scrape_myntra(query)
    snapdeal_results = scrape_snapdeal(query)
    nike_results = scrape_nike(query)
    max_fashion_results = scrape_max_fashion(query)
    
    all_data = myntra_results + snapdeal_results + nike_results + max_fashion_results
    # --- END OF SLOW PART ---
    
    if not all_data:
        return jsonify({"error": "No products found."}), 404

    df = pd.DataFrame(all_data)
    df.drop_duplicates(subset=['Product Name'], inplace=True)
    if 'Price' not in df.columns: df['Price'] = 0
    df = df[df['Price'] > 0]
    df.reset_index(drop=True, inplace=True)
    
    # Feature 5: Smarter Category Filtering
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
    
    # Train or Get AI Model
    print(f"Training model for query: {query}")
    model, tokenizer, max_length = train_dl_model(df)
    model_cache[query] = (model, tokenizer, max_length)
    
# Store dataframe for later in our new server-side cache
    # We use the user's ID as the key
    product_cache[session['user_id']] = df
    
    # --- NEW: SAVE TO GLOBAL CACHE ---
    # Save the results for *all* users to re-use
    print(f"Saving new search to global cache: {query}")
    global_search_cache[query] = (df, filter_options)
    # ---------------------------------
    
    print(f"Search complete. Found {len(df)} items.")
    return jsonify({
        "products": df.to_dict(orient='records'),
        "filters": filter_options,
        "message": f"Found {len(df)} unique products."
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
        # Read the DataFrame from our new server-side cache
        df = product_cache[session['user_id']]
    except KeyError:
        return jsonify({"error": "No search data found. Please search first."}), 400
        
    # 1. Get Content-Based
    rec_names_df = get_recommendations(product_name, df)
    rec_products = [] if rec_names_df.empty else rec_names_df.to_dict(orient='records')

    # 2. Get AI-Based (DL)
    dl_products = []
    query = session.get('last_query', 'default')
    
    if query in model_cache:
        model, tokenizer, max_length = model_cache[query]
        if model:
            dl_names_df = get_dl_recommendation_from_trained_model(product_name, df, model, tokenizer, max_length)
            if not dl_names_df.empty:
                dl_products = dl_names_df.to_dict(orient='records')

    return jsonify({
        "similar": rec_products,
        "ai_powered": dl_products
    })

# --- Feature 2 & 3: Wishlist & Price Track API (No Changes) ---
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

# --- Run the App ---
if __name__ == "__main__":
    app.run(debug=True, port=5001)