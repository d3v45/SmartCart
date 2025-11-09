import pandas as pd
import numpy as np
import tensorflow as tf
import sqlite3
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Embedding, LSTM, Dense
from tensorflow.keras.preprocessing.sequence import pad_sequences
from tensorflow.keras.preprocessing.text import Tokenizer

# --- Simple Content-Based Recommender (No Changes) ---
def get_recommendations(title, df):
    if df.empty or title not in df['Product Name'].values:
        return pd.DataFrame()
    tfidf = TfidfVectorizer(stop_words='english')
    tfidf_matrix = tfidf.fit_transform(df['Product Name'])
    cosine_sim = linear_kernel(tfidf_matrix, tfidf_matrix)
    idx = df[df['Product Name'] == title].index[0]
    sim_scores = list(enumerate(cosine_sim[idx]))
    sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)
    sim_scores = sim_scores[1:6]
    product_indices = [i[0] for i in sim_scores]
    return df.iloc[product_indices]

# --- AI Model Training (Updated to use the database) ---
def train_dl_model(all_products_df):
    try:
        conn = sqlite3.connect('user_history.db')
        # Read all clicks into a pandas DataFrame
        db_df = pd.read_sql_query("SELECT * FROM clicks", conn)
        conn.close()
    except sqlite3.Error as e:
        print(f"Database read error: {e}")
        return None, None, None

    # We need a minimum number of clicks to train effectively
    if len(db_df) < 10:
        return None, None, None

    # Group clicks by user to create sessions (sequences of clicks)
    sessions = db_df.groupby('user_id')['product_name'].apply(list).tolist()
    
    # Use all product names from the current search to build a complete vocabulary
    all_product_names = all_products_df['Product Name'].tolist()
    tokenizer = Tokenizer()
    tokenizer.fit_on_texts(all_product_names)
    
    sequences = tokenizer.texts_to_sequences(sessions)
    vocab_size = len(tokenizer.word_index) + 1

    X, y = [], []
    for seq in sequences:
        for i in range(1, len(seq)):
            X.append(seq[:i])
            y.append(seq[i])
    
    if not X:
        return None, None, None

    max_length = max(len(x) for x in X)
    X = pad_sequences(X, maxlen=max_length, padding='pre')
    y = np.array(y)

    model = Sequential([
        Embedding(vocab_size, 20, input_length=max_length),
        LSTM(50),
        Dense(vocab_size, activation='softmax')
    ])
    model.compile(optimizer='adam', loss='sparse_categorical_crossentropy')
    model.fit(X, y, epochs=50, verbose=0)
    
    return model, tokenizer, max_length

# --- AI Model Prediction (No Changes) ---
def get_dl_recommendation_from_trained_model(selected_product_name, df, model, tokenizer, max_length):
    if model is None or selected_product_name not in df['Product Name'].values:
        return pd.DataFrame()
    try:
        input_seq = tokenizer.texts_to_sequences([[selected_product_name]])
        if not input_seq or not input_seq[0]: return pd.DataFrame()
        
        input_seq_padded = pad_sequences(input_seq, maxlen=max_length, padding='pre')
        predicted_probs = model.predict(input_seq_padded, verbose=0)
        predicted_id = np.argmax(predicted_probs, axis=-1)[0]
        
        for name, index in tokenizer.word_index.items():
            if index == predicted_id and name != selected_product_name:
                return get_recommendations(name, df) # Return similar items to the predicted one
    except (ValueError, IndexError):
        return pd.DataFrame()
    return pd.DataFrame()

