"""Data loading and preprocessing."""

from __future__ import annotations

#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  📚 Book Recommendation System — ML Algorithm Comparison                   ║
║  Tests 9+ algorithms, evaluates with metrics, generates radar/bar charts   ║
║  Integrates with Library Management System                                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

Algorithms Tested:
  1. Content-Based Filtering (Cosine Similarity)
  2. KNN (k-Nearest Neighbors)
  3. K-Means Clustering
  4. DBSCAN (Density-Based Clustering)
  5. PCA + K-Means (Dimensionality Reduction + Clustering)
  6. t-SNE + K-Means (Non-linear Reduction + Clustering)
  7. Truncated SVD (Matrix Factorization)
  8. XGBoost Regression (Rating Prediction)
  9. Hybrid Model (Content + Collaborative)
 10. Neural Network (Simple MLP)
"""

# Fix Windows console encoding
import io
import os
import sys
import warnings
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Visualization
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
from sklearn.feature_extraction.text import TfidfVectorizer

# Scikit-learn
from sklearn.preprocessing import LabelEncoder, StandardScaler
import logging

logger = logging.getLogger(__name__)


try:
    import xgboost as xgb

    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

try:
    import plotly.graph_objects as go

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

warnings.filterwarnings("ignore")

# CONFIGURATION

# Paths
SCRIPT_DIR = Path(__file__).parent.absolute()
# Repo root: Model -> ml -> recommendations -> services -> app -> repo root
PROJECT_ROOT = SCRIPT_DIR.parents[4]
DATASET_DIR = SCRIPT_DIR.parent / "Dataset"
DATA_PATH = DATASET_DIR / "books.csv"
# Generated benchmark outputs live under the gitignored data/ tree, not in source
OUTPUT_DIR = PROJECT_ROOT / "data" / "generated" / "comparison_output"

# Ensure output dir exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Model params
N_CLUSTERS = 7
N_NEIGHBORS = 10
TEST_SIZE = 0.2
RANDOM_STATE = 42
TOP_N_RECS = 10

ALGORITHM_COLORS = {
    "Content-Based": "#4CAF50",
    "KNN": "#2196F3",
    "K-Means": "#FF9800",
    "DBSCAN": "#9C27B0",
    "PCA+K-Means": "#00BCD4",
    "t-SNE+K-Means": "#E91E63",
    "SVD": "#607D8B",
    "XGBoost": "#F44336",
    "Hybrid": "#3F51B5",
    "Neural Net": "#009688",
    "Agglomerative": "#795548",
}

plt.rcParams.update(
    {
        "figure.figsize": (14, 8),
        "figure.dpi": 120,
        "font.size": 12,
        "axes.titlesize": 14,
        "axes.labelsize": 12,
        "legend.fontsize": 10,
        "figure.facecolor": "white",
        "axes.facecolor": "#f8f9fa",
    }
)


# 1. DATA LOADING & PREPROCESSING


def load_and_preprocess_data(path: str = str(DATA_PATH)) -> pd.DataFrame:
    """Load books dataset with robust error handling."""
    logger.info("=" * 70)
    logger.info("  📥 LOADING & PREPROCESSING DATA")
    logger.info("=" * 70)

    if not os.path.exists(path):
        logger.warning(f"  ❌ Dataset not found at: {path}")
        logger.info(f"  💡 Expected at: {DATA_PATH}")
        return pd.DataFrame()

    df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
    logger.info(f"  ✅ Loaded {len(df):,} rows, {len(df.columns)} columns")

    # Clean column names
    df.columns = df.columns.str.strip()

    # Drop unnecessary columns
    drop_cols = ["isbn", "isbn13", "bookID"]
    for col in drop_cols:
        if col in df.columns:
            df.drop(columns=[col], inplace=True)

    # Handle missing values
    df.dropna(subset=["title", "authors"], inplace=True)
    df["average_rating"] = pd.to_numeric(df["average_rating"], errors="coerce").fillna(0)
    df["ratings_count"] = pd.to_numeric(df["ratings_count"], errors="coerce").fillna(0)
    df["text_reviews_count"] = pd.to_numeric(df["text_reviews_count"], errors="coerce").fillna(0)
    # Column '  num_pages' has leading spaces in CSV, stripped to 'num_pages'
    pages_col = "num_pages"
    if pages_col not in df.columns:
        # Try the original name with spaces
        for c in df.columns:
            if "num_pages" in c.lower().replace(" ", ""):
                pages_col = c
                break

    df[pages_col] = pd.to_numeric(df[pages_col], errors="coerce").fillna(0)

    # Feature: normalize ratings_count
    df["log_ratings"] = np.log1p(df["ratings_count"])
    df["log_reviews"] = np.log1p(df["text_reviews_count"])
    df["log_pages"] = np.log1p(df[pages_col].clip(0))

    # Feature: rating popularity score
    df["popularity_score"] = (
        df["average_rating"] * 0.4
        + (df["ratings_count"] / df["ratings_count"].max()) * 0.3
        + (df["text_reviews_count"] / df["text_reviews_count"].max()) * 0.3
    )

    # Feature: language encoding
    if "language_code" in df.columns:
        le = LabelEncoder()
        df["lang_encoded"] = le.fit_transform(df["language_code"].fillna("eng"))
    else:
        df["lang_encoded"] = 0

    # Feature: author count
    df["author_count"] = df["authors"].str.split("/").str.len()

    # Feature: title length
    df["title_length"] = df["title"].str.len()

    # Feature: text features for content-based
    df["text_features"] = (
        df["authors"].fillna("") + " " + df["publisher"].fillna("") + " " + df["title"].fillna("")
    )

    logger.info(f"  ✅ After cleaning: {len(df):,} rows")
    logger.info(f"  📊 Features: {', '.join(df.select_dtypes(include=[np.number]).columns)}")
    return df


def get_numerical_features(df: pd.DataFrame) -> np.ndarray:
    """Extract scaled numerical features for ML models."""
    feature_cols = [
        "average_rating",
        "log_ratings",
        "log_reviews",
        "log_pages",
        "popularity_score",
        "lang_encoded",
        "author_count",
        "title_length",
    ]
    available = [c for c in feature_cols if c in df.columns]
    X = df[available].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    return X_scaled, available


def get_tfidf_features(df: pd.DataFrame) -> np.ndarray:
    """Extract TF-IDF features from text fields."""
    if "text_features" not in df.columns:
        return np.zeros((len(df), 1))

    vectorizer = TfidfVectorizer(
        max_features=500, stop_words="english", ngram_range=(1, 2), sublinear_tf=True
    )
    X_tfidf = vectorizer.fit_transform(df["text_features"].fillna(""))
    return X_tfidf.toarray()


# 2. MODEL DEFINITIONS


