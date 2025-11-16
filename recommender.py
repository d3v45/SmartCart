import pandas as pd
import numpy as np
import tensorflow as tf
import sqlite3

# --- Imports for Content-Based Similarity ---
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
# ------------------------------------------------

from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Embedding, LSTM, Dense, Dropout
from tensorflow.keras.preprocessing.sequence import pad_sequences

# --- Content-Based Recommender (Brought Back) ---
def get_recommendations(title, df):
    """
    Gets simple content-based recommendations based on name similarity.
    """
    if df.empty or title not in df['Product Name'].values:
        return pd.DataFrame()
    
    # Check if we have enough data to build a matrix
    if df.shape[0] < 2:
        return pd.DataFrame()
        
    tfidf = TfidfVectorizer(stop_words='english')
    # Use fit_transform on the 'Product Name' column
    tfidf_matrix = tfidf.fit_transform(df['Product Name'].values.astype('U'))

    cosine_sim = linear_kernel(tfidf_matrix, tfidf_matrix)
    
    try:
        idx = df[df['Product Name'] == title].index[0]
        sim_scores = list(enumerate(cosine_sim[idx]))
        sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)
        sim_scores = sim_scores[1:6] # Get top 5
        product_indices = [i[0] for i in sim_scores]
        return df.iloc[product_indices]
    except (IndexError, KeyError):
        return pd.DataFrame()

# --- AI Model Training (With Dropout to reduce bias) ---
def train_dl_model(all_products_df):
    """
    Trains the Deep Learning model based on all user interactions
    (clicks and wishlist).
    """
    try:
        conn = sqlite3.connect('user_history.db')
        query = """
        SELECT user_id, product_name FROM clicks
        UNION ALL
        SELECT user_id, product_name FROM wishlist
        """
        db_df = pd.read_sql_query(query, conn)
        conn.close()
    except sqlite3.Error as e:
        print(f"Database read error: {e}")
        return None, None, None

    if len(db_df) < 5:
        print(f"Not enough interaction data to train DL model. Need 5, have {len(db_df)}")
        return None, None, None

    all_product_names = all_products_df['Product Name'].tolist()
    historical_names = db_df['product_name'].unique().tolist()
    combined_vocabulary = list(set(all_product_names + historical_names))
    
    product_to_id = {name: i + 1 for i, name in enumerate(combined_vocabulary)}
    vocab_size = len(product_to_id) + 1
    
    user_sessions_of_names = db_df.groupby('user_id')['product_name'].apply(list).tolist()
    
    sequences = []
    for session in user_sessions_of_names:
        seq = [product_to_id[name] for name in session if name in product_to_id]
        if seq:
            sequences.append(seq)

    X, y = [], []
    for seq in sequences:
        if len(seq) > 1:
            for i in range(1, len(seq)):
                X.append(seq[:i])
                y.append(seq[i])
    
    if not X:
        print("No valid sequences generated for DL model.")
        return None, None, None

    max_length = max(len(x) for x in X)
    X = pad_sequences(X, maxlen=max_length, padding='pre')
    y = np.array(y)

    print(f"Training DL model with vocab_size={vocab_size}, total_sequences={len(X)}")

    # --- Model with Dropout ---
    model = Sequential([
        Embedding(vocab_size, 20, input_length=max_length),
        LSTM(50),
        Dropout(0.2), # Add dropout after the LSTM layer
        Dense(vocab_size, activation='softmax')
    ])
    # -------------------------------
    
    model.compile(optimizer='adam', loss='sparse_categorical_crossentropy')
    
    model.fit(X, y, epochs=50, verbose=0)
    
    print("DL Model training complete.")
    return model, product_to_id, max_length

# --- AI Model Prediction (NEW: Using Embedding Similarity) ---
def get_dl_recommendation_from_trained_model(selected_product_name, df, model, product_to_id, max_length):
    """
    Uses the model's learned Embeddings to find conceptually similar items.
    """
    
    print(f"\n[DEBUG] Finding AI similarity for: {selected_product_name}")
    
    if model is None or selected_product_name not in product_to_id:
        print("[DEBUG] Model is None or selected product is not in vocab.")
        return pd.DataFrame()
        
    try:
        # 1. Get all embedding vectors from the model
        # This is a matrix where row 'i' is the vector for product ID 'i'
        embedding_matrix = model.layers[0].get_weights()[0]
        
        # 2. Get the ID and vector for the product we clicked
        input_id = product_to_id.get(selected_product_name)
        if not input_id:
            print("[DEBUG] Could not find input_id for product.")
            return pd.DataFrame()
        
        input_vector = embedding_matrix[input_id]
        
        # 3. Calculate cosine similarity between our input vector and ALL other vectors
        # This gives a similarity score for every product in the vocab
        sim_scores = linear_kernel(input_vector.reshape(1, -1), embedding_matrix)[0]

        # 4. Get the Top 6 indices (Top 1 will be the item itself)
        top_indices = np.argsort(sim_scores)[-6:][::-1]
        
        # 5. Create reverse mapping
        id_to_product = {i: name for name, i in product_to_id.items()}
        
        print("[DEBUG] AI Top 5 Similar (by vector):")
        
        relevant_predictions = []
        
        for i, product_id in enumerate(top_indices):
            # 0 is padding, ignore
            if product_id == 0:
                continue
                
            predicted_name = id_to_product.get(product_id)
            
            # Ignore the item we just clicked (which will be Rank 1)
            if not predicted_name or predicted_name == selected_product_name:
                continue
            
            print(f"  - (Rank {i}) '{predicted_name}' (Score: {sim_scores[product_id]:.4f})")

            # Check if this prediction is in our current search results
            if predicted_name in df['Product Name'].values:
                print(f"[DEBUG] Found a relevant prediction: '{predicted_name}'")
                relevant_predictions.append(predicted_name)
        
        if not relevant_predictions:
            print("[DEBUG] Top 5 similar products were all filtered out.")
            return pd.DataFrame()
            
        print(f"[DEBUG] Success. Returning {len(relevant_predictions)} AI recommendations.")
        # Return a DataFrame of all unique relevant predictions
        return df[df['Product Name'].isin(list(set(relevant_predictions)))]
            
    except (ValueError, IndexError) as e:
        print(f"[DEBUG] Error during DL prediction: {e}")
        return pd.DataFrame()
        
    return pd.DataFrame()