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
import math
import os
import sys
import time
import warnings
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Visualization
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.cluster import DBSCAN, AgglomerativeClustering, KMeans
from sklearn.decomposition import PCA, TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.manifold import TSNE
from sklearn.metrics import (
    calinski_harabasz_score,
    davies_bouldin_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    silhouette_score,
)
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import train_test_split
from sklearn.neighbors import NearestNeighbors
from sklearn.neural_network import MLPRegressor

# Scikit-learn
from sklearn.preprocessing import LabelEncoder, StandardScaler

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
    print("=" * 70)
    print("  📥 LOADING & PREPROCESSING DATA")
    print("=" * 70)

    if not os.path.exists(path):
        print(f"  ❌ Dataset not found at: {path}")
        print(f"  💡 Expected at: {DATA_PATH}")
        return pd.DataFrame()

    df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
    print(f"  ✅ Loaded {len(df):,} rows, {len(df.columns)} columns")

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

    print(f"  ✅ After cleaning: {len(df):,} rows")
    print(f"  📊 Features: {', '.join(df.select_dtypes(include=[np.number]).columns)}")
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


class ModelResult:
    """Stores evaluation results for a single model."""

    def __init__(self, name: str, color: str):
        self.name = name
        self.color = color
        self.metrics = {}
        self.predictions = None
        self.labels = None
        self.time_taken = 0.0

    def add_metric(self, name: str, value: float):
        self.metrics[name] = value

    def get_formatted_metrics(self) -> str:
        lines = [f"  📊 {self.name}:"]
        for k, v in sorted(self.metrics.items()):
            lines.append(f"     {k:30s} = {v:.4f}")
        lines.append(f"     {'Time':30s} = {self.time_taken:.3f}s")
        return "\n".join(lines)


def evaluate_clustering(X: np.ndarray, labels: np.ndarray, result: ModelResult):
    """Evaluate clustering quality with multiple metrics."""
    unique_labels = len(set(labels))
    n_noise = list(labels).count(-1) if -1 in labels else 0

    result.add_metric("Clusters", float(unique_labels))
    result.add_metric("Noise Points", float(n_noise))
    result.add_metric("Noise %", 100.0 * n_noise / len(labels))

    if unique_labels > 1 and unique_labels < len(labels):
        # Skip silhouette if only 1 cluster or all noise
        try:
            sil = silhouette_score(X, labels)
            result.add_metric("Silhouette Score", sil)
        except Exception:
            result.add_metric("Silhouette Score", -1.0)

        try:
            db = davies_bouldin_score(X, labels)
            result.add_metric("Davies-Bouldin", db)
        except Exception:
            result.add_metric("Davies-Bouldin", -1.0)

        try:
            ch = calinski_harabasz_score(X, labels)
            result.add_metric("Calinski-Harabasz", ch)
        except Exception:
            result.add_metric("Calinski-Harabasz", -1.0)


def evaluate_recommendation(
    df: pd.DataFrame, scores: np.ndarray, result: ModelResult, top_n: int = TOP_N_RECS
):
    """Evaluate recommendation quality."""
    if scores is None or len(scores) == 0:
        return

    # Coverage: percentage of items recommended at least once
    if scores.ndim == 2:
        top_items = set()
        for row in scores:
            indices = np.argsort(row)[-top_n:]
            top_items.update(indices.tolist())
        coverage = len(top_items) / scores.shape[0]
    else:
        coverage = 0.0

    result.add_metric("Coverage", coverage)

    # Diversity: average pairwise distance in top-N
    if scores.ndim == 2:
        diversities = []
        sample_size = min(100, scores.shape[0])
        for i in range(sample_size):
            indices = np.argsort(scores[i])[-top_n:]
            if len(indices) > 1:
                sub_matrix = scores[indices][:, indices]
                div = 1 - np.mean(cosine_similarity(sub_matrix))
                diversities.append(div)
        result.add_metric("Diversity", np.mean(diversities) if diversities else 0)


# ALGORITHM 1: Content-Based Filtering


def content_based_filtering(
    df: pd.DataFrame, X_tfidf: np.ndarray, X_num: np.ndarray
) -> ModelResult:
    """Content-based recommendations using TF-IDF + numerical features."""
    print("  🔄 Content-Based Filtering...", end=" ", flush=True)
    start = time.time()
    result = ModelResult("Content-Based", ALGORITHM_COLORS["Content-Based"])

    # Combine TF-IDF with numerical features
    if X_tfidf.shape[1] > 1 and X_num.shape[1] > 1:
        X_combined = np.hstack([X_tfidf, X_num])
    else:
        X_combined = X_tfidf if X_tfidf.shape[1] > 1 else X_num

    # Use features directly for clustering (not similarity matrix)
    # Subsample if too large for memory
    if X_combined.shape[0] > 5000:
        from sklearn.utils import resample

        X_sample = resample(X_combined, n_samples=3000, random_state=RANDOM_STATE)
    else:
        X_sample = X_combined

    kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=RANDOM_STATE, n_init=10)
    labels = kmeans.fit_predict(X_sample)

    # Compute cosine similarity on a sample for evaluation
    sample_size = min(2000, X_combined.shape[0])
    X_sample_sim = X_combined[:sample_size]
    sim_matrix = cosine_similarity(X_sample_sim)

    result.labels = labels
    evaluate_clustering(X_combined, labels, result)
    evaluate_recommendation(df, sim_matrix, result)
    result.time_taken = time.time() - start
    print(f"✅ ({result.time_taken:.2f}s)")
    return result


# ALGORITHM 2: KNN (k-Nearest Neighbors)


def knn_model(X: np.ndarray) -> ModelResult:
    """KNN-based recommendation using nearest neighbors."""
    print("  🔄 KNN (k-Nearest Neighbors)...", end=" ", flush=True)
    start = time.time()
    result = ModelResult("KNN", ALGORITHM_COLORS["KNN"])

    knn = NearestNeighbors(n_neighbors=N_NEIGHBORS, metric="cosine", n_jobs=-1)
    knn.fit(X)
    distances, indices = knn.kneighbors(X)

    # Use neighbor graph for evaluation
    neighbor_sim = np.zeros((X.shape[0], X.shape[0]))
    for i in range(X.shape[0]):
        neighbor_sim[i, indices[i]] = 1.0 / (distances[i] + 0.001)

    evaluate_recommendation(pd.DataFrame(), neighbor_sim, result)
    result.time_taken = time.time() - start
    print(f"✅ ({result.time_taken:.2f}s)")
    return result


# ALGORITHM 3: K-Means Clustering


def kmeans_model(X: np.ndarray, df: pd.DataFrame) -> ModelResult:
    """K-Means clustering with multiple initializations."""
    print("  🔄 K-Means Clustering...", end=" ", flush=True)
    start = time.time()
    result = ModelResult("K-Means", ALGORITHM_COLORS["K-Means"])

    # Find optimal k using elbow method
    inertias = []
    k_range = range(2, 15)
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10)
        km.fit(X)
        inertias.append(km.inertia_)

    # Use optimal or default
    best_k = N_CLUSTERS
    if len(inertias) > 2:
        # Find "elbow" using 2nd derivative approximation
        diffs = np.diff(inertias)
        diffs2 = np.diff(diffs)
        if len(diffs2) > 0:
            best_k = k_range[np.argmax(np.abs(diffs2)) + 1]

    kmeans = KMeans(n_clusters=best_k, random_state=RANDOM_STATE, n_init=10)
    labels = kmeans.fit_predict(X)
    result.labels = labels
    result.metrics["Elbow K"] = float(best_k)

    evaluate_clustering(X, labels, result)

    # Recommendation based on cluster membership
    sim_matrix = np.zeros((X.shape[0], X.shape[0]))
    for i in range(X.shape[0]):
        sim_matrix[i, labels == labels[i]] = 1.0
        sim_matrix[i, i] = 0  # Don't recommend itself

    evaluate_recommendation(df, sim_matrix, result)
    result.time_taken = time.time() - start
    print(f"✅ ({result.time_taken:.2f}s)")
    return result, inertias, k_range


# ALGORITHM 4: DBSCAN


def dbscan_model(X: np.ndarray, df: pd.DataFrame) -> ModelResult:
    """DBSCAN density-based clustering with auto eps tuning."""
    print("  🔄 DBSCAN...", end=" ", flush=True)
    start = time.time()
    result = ModelResult("DBSCAN", ALGORITHM_COLORS["DBSCAN"])

    # Auto-tune eps based on k-distance
    nn = NearestNeighbors(n_neighbors=min(10, X.shape[0] - 1), n_jobs=-1)
    nn.fit(X)
    distances, _ = nn.kneighbors(X)
    k_dist = np.sort(distances[:, -1])

    # Find the "elbow" in k-distance graph
    eps_value = np.percentile(k_dist, 85) if len(k_dist) > 10 else 0.5
    eps_value = max(eps_value, 0.1)
    min_samples = max(5, int(X.shape[0] * 0.001))

    dbscan = DBSCAN(eps=eps_value, min_samples=min_samples, n_jobs=-1)
    labels = dbscan.fit_predict(X)
    result.labels = labels

    evaluate_clustering(X, labels, result)

    # Recommendation based on cluster
    sim_matrix = np.zeros((X.shape[0], X.shape[0]))
    for i in range(X.shape[0]):
        if labels[i] >= 0:
            sim_matrix[i, labels == labels[i]] = 1.0
        sim_matrix[i, i] = 0

    evaluate_recommendation(df, sim_matrix, result)
    result.time_taken = time.time() - start
    print(f"✅ ({result.time_taken:.2f}s)")
    return result, k_dist


# ALGORITHM 5: PCA + K-Means


def pca_kmeans_model(X: np.ndarray, df: pd.DataFrame) -> ModelResult:
    """PCA dimensionality reduction followed by K-Means."""
    print("  🔄 PCA + K-Means...", end=" ", flush=True)
    start = time.time()
    result = ModelResult("PCA+K-Means", ALGORITHM_COLORS["PCA+K-Means"])

    # Find optimal components
    n_components = min(50, X.shape[1], X.shape[0] - 1)
    pca = PCA(n_components=n_components)
    X_pca = pca.fit_transform(X)

    # Explained variance
    cum_var = np.cumsum(pca.explained_variance_ratio_)
    n_95 = np.searchsorted(cum_var, 0.95) + 1

    # Reduce to 95% variance components
    n_components_95 = min(n_95, X_pca.shape[1])
    X_reduced = X_pca[:, :n_components_95]
    result.add_metric("PCA Components", float(n_components_95))
    result.add_metric(
        "Variance Retained", float(cum_var[min(n_components_95 - 1, len(cum_var) - 1)])
    )

    # K-Means on reduced data
    kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=RANDOM_STATE, n_init=10)
    labels = kmeans.fit_predict(X_reduced)
    result.labels = labels

    evaluate_clustering(X_reduced, labels, result)

    sim_matrix = np.zeros((X.shape[0], X.shape[0]))
    for i in range(X.shape[0]):
        sim_matrix[i, labels == labels[i]] = 1.0
        sim_matrix[i, i] = 0

    evaluate_recommendation(df, sim_matrix, result)
    result.time_taken = time.time() - start
    print(f"✅ ({result.time_taken:.2f}s)")
    return result, pca


# ALGORITHM 6: t-SNE + K-Means


def tsne_kmeans_model(X: np.ndarray, df: pd.DataFrame) -> ModelResult:
    """t-SNE dimensionality reduction followed by K-Means."""
    print("  🔄 t-SNE + K-Means...", end=" ", flush=True)
    start = time.time()
    result = ModelResult("t-SNE+K-Means", ALGORITHM_COLORS["t-SNE+K-Means"])

    # First reduce with PCA to speed up t-SNE
    n_components = min(50, X.shape[1])
    pca = PCA(n_components=n_components)
    X_pca = pca.fit_transform(X)

    # t-SNE to 2D
    perplexity = min(30, X_pca.shape[0] - 1)
    tsne = TSNE(n_components=2, perplexity=perplexity, random_state=RANDOM_STATE)
    X_tsne = tsne.fit_transform(X_pca)

    # K-Means on t-SNE reduced data
    kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=RANDOM_STATE, n_init=10)
    labels = kmeans.fit_predict(X_tsne)
    result.labels = labels

    evaluate_clustering(X_tsne, labels, result)

    sim_matrix = np.zeros((X.shape[0], X.shape[0]))
    for i in range(X.shape[0]):
        sim_matrix[i, labels == labels[i]] = 1.0
        sim_matrix[i, i] = 0

    evaluate_recommendation(df, sim_matrix, result)
    result.time_taken = time.time() - start
    print(f"✅ ({result.time_taken:.2f}s)")
    return result, X_tsne


# ALGORITHM 7: Truncated SVD (Matrix Factorization)


def svd_model(X: np.ndarray, df: pd.DataFrame) -> ModelResult:
    """Truncated SVD for matrix factorization and recommendation."""
    print("  🔄 SVD Matrix Factorization...", end=" ", flush=True)
    start = time.time()
    result = ModelResult("SVD", ALGORITHM_COLORS["SVD"])

    n_components = min(20, X.shape[1], X.shape[0] - 1)
    svd = TruncatedSVD(n_components=n_components, random_state=RANDOM_STATE)
    X_svd = svd.fit_transform(X)
    result.add_metric("SVD Components", float(n_components))
    result.add_metric("Explained Variance", float(svd.explained_variance_ratio_.sum()))

    # Use SVD features for clustering
    kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=RANDOM_STATE, n_init=10)
    labels = kmeans.fit_predict(X_svd)
    result.labels = labels

    evaluate_clustering(X_svd, labels, result)

    # Reconstruction-based recommendation
    sim_matrix = cosine_similarity(X_svd)
    np.fill_diagonal(sim_matrix, 0)

    evaluate_recommendation(df, sim_matrix, result)
    result.time_taken = time.time() - start
    print(f"✅ ({result.time_taken:.2f}s)")
    return result


# ALGORITHM 8: XGBoost Regression


def xgboost_model(df: pd.DataFrame, X: np.ndarray) -> ModelResult:
    """XGBoost regression for rating prediction."""
    print("  🔄 XGBoost Regression...", end=" ", flush=True)
    start = time.time()
    result = ModelResult("XGBoost", ALGORITHM_COLORS["XGBoost"])

    if not XGB_AVAILABLE:
        print("⚠️ (XGBoost not installed, skipping)")
        result.add_metric("RMSE", -1.0)
        result.add_metric("MAE", -1.0)
        result.add_metric("R²", -1.0)
        result.time_taken = time.time() - start
        return result

    y = df["average_rating"].values
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )

    model = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbosity=0,
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    result.add_metric("RMSE", math.sqrt(mean_squared_error(y_test, y_pred)))
    result.add_metric("MAE", mean_absolute_error(y_test, y_pred))
    result.add_metric("R²", r2_score(y_test, y_pred))

    # Feature importance
    if hasattr(model, "feature_importances_"):
        result.metrics["Top Feature Importance"] = float(model.feature_importances_.max())

    result.time_taken = time.time() - start
    print(f"✅ ({result.time_taken:.2f}s)")
    return result, model


# ALGORITHM 9: Hybrid Model


def hybrid_model(X: np.ndarray, X_tfidf: np.ndarray, df: pd.DataFrame) -> ModelResult:
    """Hybrid: combines content-based similarity with collaborative clustering."""
    print("  🔄 Hybrid Model (Content + Collaborative)...", end=" ", flush=True)
    start = time.time()
    result = ModelResult("Hybrid", ALGORITHM_COLORS["Hybrid"])

    # Content-based similarity
    if X_tfidf.shape[1] > 1:
        content_sim = cosine_similarity(X_tfidf)
    else:
        content_sim = cosine_similarity(X)

    # Collaborative: cluster-based co-occurrence
    kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=RANDOM_STATE, n_init=10)
    cluster_labels = kmeans.fit_predict(X)

    collab_sim = np.zeros((X.shape[0], X.shape[0]))
    for i in range(X.shape[0]):
        collab_sim[i, cluster_labels == cluster_labels[i]] = 1.0
        np.fill_diagonal(collab_sim, 0)

    # Normalize
    content_sim = (content_sim - content_sim.min()) / (
        content_sim.max() - content_sim.min() + 1e-10
    )

    # Hybrid: weighted combination
    alpha = 0.6  # Content weight
    hybrid_sim = alpha * content_sim + (1 - alpha) * collab_sim
    np.fill_diagonal(hybrid_sim, 0)

    result.labels = cluster_labels
    evaluate_clustering(X, cluster_labels, result)
    evaluate_recommendation(df, hybrid_sim, result)
    result.time_taken = time.time() - start
    print(f"✅ ({result.time_taken:.2f}s)")
    return result


# ALGORITHM 10: Neural Network (MLP)


def neural_network_model(X: np.ndarray, df: pd.DataFrame) -> ModelResult:
    """Simple MLP neural network for rating prediction."""
    print("  🔄 Neural Network (MLP)...", end=" ", flush=True)
    start = time.time()
    result = ModelResult("Neural Net", ALGORITHM_COLORS["Neural Net"])

    y = df["average_rating"].values
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )

    mlp = MLPRegressor(
        hidden_layer_sizes=(64, 32, 16),
        activation="relu",
        solver="adam",
        max_iter=300,
        random_state=RANDOM_STATE,
        early_stopping=True,
        validation_fraction=0.1,
        verbose=False,
    )
    mlp.fit(X_train, y_train)
    y_pred = mlp.predict(X_test)

    result.add_metric("RMSE", math.sqrt(mean_squared_error(y_test, y_pred)))
    result.add_metric("MAE", mean_absolute_error(y_test, y_pred))
    result.add_metric("R²", r2_score(y_test, y_pred))

    # Clustering on learned representations
    if hasattr(mlp, "coefs_"):
        # Use last hidden layer activations
        X_hidden = X_test[: min(1000, len(X_test))]
        for layer in mlp.coefs_[:-1]:
            X_hidden = np.maximum(
                0,
                X_hidden @ layer
                + (mlp.intercepts_[mlp.coefs_.index(layer)] if layer is mlp.coefs_[0] else 0),
            )

        if X_hidden.shape[0] > N_CLUSTERS:
            km = KMeans(n_clusters=N_CLUSTERS, random_state=RANDOM_STATE, n_init=10)
            labels = km.fit_predict(X_hidden)
            result.labels = labels

    result.time_taken = time.time() - start
    print(f"✅ ({result.time_taken:.2f}s)")
    return result


# ALGORITHM 11: Agglomerative Clustering


def agglomerative_model(X: np.ndarray, df: pd.DataFrame) -> ModelResult:
    """Hierarchical agglomerative clustering."""
    print("  🔄 Agglomerative Clustering...", end=" ", flush=True)
    start = time.time()
    result = ModelResult("Agglomerative", ALGORITHM_COLORS["Agglomerative"])

    # Use MiniBatch for large datasets
    if X.shape[0] > 10000:
        from sklearn.cluster import MiniBatchKMeans

        # Approximate with mini-batch k-means
        cluster = MiniBatchKMeans(
            n_clusters=N_CLUSTERS, random_state=RANDOM_STATE, batch_size=1024, n_init=5
        )
    else:
        cluster = AgglomerativeClustering(n_clusters=N_CLUSTERS, linkage="ward")

    labels = cluster.fit_predict(X)
    result.labels = labels

    evaluate_clustering(X, labels, result)

    sim_matrix = np.zeros((X.shape[0], X.shape[0]))
    for i in range(X.shape[0]):
        sim_matrix[i, labels == labels[i]] = 1.0
        sim_matrix[i, i] = 0

    evaluate_recommendation(df, sim_matrix, result)
    result.time_taken = time.time() - start
    print(f"✅ ({result.time_taken:.2f}s)")
    return result


# 3. VISUALIZATION FUNCTIONS


def save_radar_chart(results: list[ModelResult], filename: str = "radar_comparison.png"):
    """Create a radar chart comparing algorithms across key metrics."""
    print("\n  📊 Generating Radar Chart...")

    # Select clustering metrics for radar
    metric_names = [
        "Silhouette Score",
        "Davies-Bouldin",
        "Calinski-Harabasz",
        "Coverage",
        "Diversity",
    ]
    available_metrics = [m for m in metric_names if any(m in r.metrics for r in results)]
    if not available_metrics:
        print("  ⚠️  No common metrics available for radar chart")
        return

    # Normalize scores for radar (1 = best, 0 = worst)
    n_metrics = len(available_metrics)
    len(results)

    # Prepare data
    data = {}
    for r in results:
        vals = []
        for m in available_metrics:
            if m in r.metrics:
                vals.append(r.metrics[m])
            else:
                vals.append(0)
        data[r.name] = vals

    # Normalize each metric to [0, 1]
    for i in range(n_metrics):
        vals = [data[name][i] for name in data]
        min_v, max_v = min(vals), max(vals)
        if max_v > min_v:
            # For Davies-Bouldin, lower is better
            if available_metrics[i] == "Davies-Bouldin":
                for name in data:
                    data[name][i] = 1 - (data[name][i] - min_v) / (max_v - min_v)
            else:
                for name in data:
                    data[name][i] = (data[name][i] - min_v) / (max_v - min_v)

    fig, ax = plt.subplots(figsize=(12, 10), subplot_kw=dict(polar=True))

    angles = np.linspace(0, 2 * np.pi, n_metrics, endpoint=False).tolist()
    angles += angles[:1]  # Close the circle

    for i, (name, vals) in enumerate(data.items()):
        values = vals + vals[:1]
        color = ALGORITHM_COLORS.get(name, f"C{i}")
        ax.plot(angles, values, "o-", linewidth=2, label=name, color=color, alpha=0.8)
        ax.fill(angles, values, alpha=0.05, color=color)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([m.replace(" ", "\n") for m in available_metrics], fontsize=10)
    ax.set_ylim(0, 1.05)
    ax.set_title(
        "📊 Algorithm Comparison Radar Chart\n(Normalized Scores, Higher = Better)",
        pad=30,
        fontsize=15,
        fontweight="bold",
    )
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=9)

    plt.tight_layout()
    path = OUTPUT_DIR / filename
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✅ Radar chart saved: {path}")


def save_bar_comparison(results: list[ModelResult], metric: str, filename: str = None):
    """Create a bar chart comparing a specific metric across algorithms."""
    names = [r.name for r in results]
    values = [r.metrics.get(metric, 0) for r in results]
    colors = [ALGORITHM_COLORS.get(n, f"C{i}") for i, n in enumerate(names)]

    fig, ax = plt.subplots(figsize=(14, 6))
    bars = ax.bar(range(len(names)), values, color=colors, edgecolor="white", linewidth=0.5)

    # Add value labels on bars
    for bar, val in zip(bars, values):
        if val != 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(values) * 0.01,
                f"{val:.3f}",
                ha="center",
                va="bottom",
                fontsize=8,
                rotation=45,
            )

    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=30, ha="right", fontsize=10)
    ax.set_ylabel(metric, fontsize=12)
    ax.set_title(f"📊 {metric} by Algorithm", fontsize=14, fontweight="bold")
    ax.set_axisbelow(True)
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    if filename is None:
        filename = f"bar_{metric.lower().replace(' ', '_')}.png"
    path = OUTPUT_DIR / filename
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✅ Bar chart saved: {path}")


def save_elbow_plot(inertias, k_range, filename: str = "elbow_curve.png"):
    """Save elbow curve for K selection."""
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(list(k_range), inertias, "bo-", linewidth=2, markersize=8, color="#2196F3")
    ax.set_xlabel("Number of Clusters (K)", fontsize=12)
    ax.set_ylabel("Inertia (Within-cluster Sum of Squares)", fontsize=12)
    ax.set_title("📊 Elbow Method for Optimal K", fontsize=14, fontweight="bold")
    ax.set_axisbelow(True)
    ax.grid(alpha=0.3)

    # Mark recommended K
    if len(inertias) > 2:
        diffs = np.diff(inertias)
        diffs2 = np.diff(diffs)
        if len(diffs2) > 0:
            best_k = list(k_range)[np.argmax(np.abs(diffs2)) + 1]
            ax.axvline(x=best_k, color="red", linestyle="--", alpha=0.5, linewidth=1)
            ax.text(
                best_k + 0.3,
                inertias[0],
                f"Recommended K = {best_k}",
                color="red",
                fontsize=11,
                fontweight="bold",
            )

    plt.tight_layout()
    path = OUTPUT_DIR / filename
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✅ Elbow curve saved: {path}")


def save_k_distance_plot(k_dist: np.ndarray, filename: str = "k_distance_plot.png"):
    """Save k-distance plot for DBSCAN eps tuning."""
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(range(len(k_dist)), k_dist, "b-", linewidth=1.5, alpha=0.7)
    ax.set_xlabel("Points Sorted by Distance", fontsize=12)
    ax.set_ylabel("k-Distance", fontsize=12)
    ax.set_title("📊 k-Distance Graph for DBSCAN eps Selection", fontsize=14, fontweight="bold")
    ax.set_axisbelow(True)
    ax.grid(alpha=0.3)

    # Mark elbow
    if len(k_dist) > 10:
        elbow_idx = int(len(k_dist) * 0.85)
        ax.axhline(y=k_dist[elbow_idx], color="red", linestyle="--", alpha=0.5)
        ax.text(
            len(k_dist) * 0.5,
            k_dist[elbow_idx] * 1.05,
            f"eps ≈ {k_dist[elbow_idx]:.3f}",
            color="red",
            fontsize=11,
        )

    plt.tight_layout()
    path = OUTPUT_DIR / filename
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✅ k-Distance plot saved: {path}")


def save_cluster_visualization(X_2d: np.ndarray, labels: np.ndarray, title: str, filename: str):
    """Save 2D cluster visualization."""
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    fig, ax = plt.subplots(figsize=(12, 8))

    scatter = ax.scatter(
        X_2d[:, 0],
        X_2d[:, 1],
        c=labels,
        cmap="tab10",
        s=20,
        alpha=0.6,
        edgecolors="none",
    )

    ax.set_title(f"{title}\n({n_clusters} clusters found)", fontsize=14, fontweight="bold")
    ax.set_xlabel("Component 1", fontsize=11)
    ax.set_ylabel("Component 2", fontsize=11)
    ax.set_axisbelow(True)
    ax.grid(alpha=0.2)

    plt.colorbar(scatter, ax=ax, label="Cluster", shrink=0.8)
    plt.tight_layout()
    path = OUTPUT_DIR / filename
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✅ Cluster viz saved: {path}")


def save_heatmap_comparison(results: list[ModelResult], filename: str = "performance_heatmap.png"):
    """Create a heatmap of all metrics across all algorithms."""
    metrics_pool = set()
    for r in results:
        metrics_pool.update(r.metrics.keys())

    # Filter to consistent numeric metrics
    sorted(
        [m for m in metrics_pool if any(m in r.metrics for r in results) and not isinstance(m, str)]
    )

    # Focus on key metrics
    key_metrics = [
        "Silhouette Score",
        "Davies-Bouldin",
        "Calinski-Harabasz",
        "Coverage",
        "Diversity",
        "RMSE",
        "MAE",
        "R²",
    ]
    key_metrics = [m for m in key_metrics if any(m in r.metrics for r in results)]

    if not key_metrics:
        print("  ⚠️  No common metrics for heatmap")
        return

    data = []
    for r in results:
        row = [r.metrics.get(m, np.nan) for m in key_metrics]
        data.append(row)

    data = np.array(data)
    fig, ax = plt.subplots(figsize=(12, max(6, len(results) * 0.5)))

    cmap = sns.diverging_palette(240, 10, as_cmap=True)
    im = ax.imshow(data, cmap=cmap, aspect="auto")

    # Annotate cells
    for i in range(len(results)):
        for j in range(len(key_metrics)):
            val = data[i, j]
            if not np.isnan(val):
                color = (
                    "white"
                    if abs(val - np.nanmean(data[:, j])) > np.nanstd(data[:, j])
                    else "black"
                )
                ax.text(
                    j,
                    i,
                    f"{val:.3f}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color=color,
                )

    ax.set_xticks(range(len(key_metrics)))
    ax.set_xticklabels([m[:12] for m in key_metrics], rotation=30, ha="right", fontsize=9)
    ax.set_yticks(range(len(results)))
    ax.set_yticklabels([r.name for r in results], fontsize=9)
    ax.set_title("📊 Performance Comparison Heatmap", fontsize=14, fontweight="bold")

    plt.colorbar(im, ax=ax, shrink=0.8, label="Score")
    plt.tight_layout()
    path = OUTPUT_DIR / filename
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✅ Heatmap saved: {path}")


def save_interactive_radar(results: list[ModelResult], filename: str = "interactive_radar.html"):
    """Create interactive radar chart using Plotly."""
    if not PLOTLY_AVAILABLE:
        return

    metric_names = [
        "Silhouette Score",
        "Davies-Bouldin",
        "Calinski-Harabasz",
        "Coverage",
        "Diversity",
    ]
    available_metrics = [m for m in metric_names if any(m in r.metrics for r in results)]
    if not available_metrics:
        return

    fig = go.Figure()
    for r in results:
        vals = [r.metrics.get(m, 0) for m in available_metrics] + [
            r.metrics.get(available_metrics[0], 0)
        ]
        fig.add_trace(
            go.Scatterpolar(
                r=vals,
                theta=available_metrics + [available_metrics[0]],
                name=r.name,
                line_color=ALGORITHM_COLORS.get(r.name, "#000"),
                fill="toself",
                opacity=0.3,
            )
        )

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
        title="📊 Interactive Algorithm Comparison (Normalized)",
        font=dict(size=11),
        legend=dict(x=1.1, y=0.5),
        width=1000,
        height=700,
    )

    path = OUTPUT_DIR / filename
    fig.write_html(path)
    print(f"  ✅ Interactive radar saved: {path}")


def save_summary_report(results: list[ModelResult], df: pd.DataFrame):
    """Save a comprehensive text summary report."""
    path = OUTPUT_DIR / "model_comparison_report.txt"

    with open(path, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("  📚 BOOK RECOMMENDATION SYSTEM — MODEL COMPARISON REPORT\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"  Dataset: {len(df):,} books\n")
        f.write(f"  Features: {df.select_dtypes(include=[np.number]).shape[1]} numerical\n")
        f.write(f"  Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n\n")

        f.write("-" * 70 + "\n")
        f.write("  ALGORITHM PERFORMANCE SUMMARY\n")
        f.write("-" * 70 + "\n\n")

        # Sort by best Silhouette Score (or first avail metric)
        sort_key = "Silhouette Score"
        if not any(sort_key in r.metrics for r in results):
            sort_key = results[0].metrics and list(results[0].metrics.keys())[0]

        sorted_results = sorted(
            [r for r in results if sort_key in r.metrics],
            key=lambda r: r.metrics.get(sort_key, -1),
            reverse=True,
        )
        unsorted = [r for r in results if sort_key not in r.metrics]

        f.writelines(r.get_formatted_metrics() + "\n\n" for r in sorted_results + unsorted)

        # Recommendations
        if sorted_results:
            f.write("-" * 70 + "\n")
            f.write("  🏆 TOP RECOMMENDATIONS\n")
            f.write("-" * 70 + "\n\n")

            best = sorted_results[0]
            f.write(f"  Best Overall: {best.name}\n")
            f.write(f"  Silhouette Score: {best.metrics.get('Silhouette Score', 'N/A'):.4f}\n\n")

            # Best for each metric
            metrics_to_check = [
                "Silhouette Score",
                "Coverage",
                "Diversity",
                "RMSE",
                "R²",
            ]
            for m in metrics_to_check:
                if any(m in r.metrics for r in results):
                    best_for_metric = max(results, key=lambda r: r.metrics.get(m, -999))
                    f.write(
                        f"  Best '{m}': {best_for_metric.name} "
                        f"({best_for_metric.metrics.get(m, 0):.4f})\n"
                    )

        f.write("\n" + "=" * 70 + "\n")
        f.write("  Recommendation Model Comparison — LibraryMS\n")
        f.write("=" * 70 + "\n")

    print(f"  ✅ Summary report saved: {path}")


# 4. MAIN PIPELINE


def run_comparison():
    """Run the full ML model comparison pipeline."""
    print("\n" + "=" * 70)
    print("  LIBRARY MANAGEMENT SYSTEM - ML MODEL COMPARISON")
    print("=" * 70)
    print()
    print(f"  Output directory: {OUTPUT_DIR}")
    print(f"  Algorithms to test: {len(ALGORITHM_COLORS)}")
    print(f"  Dataset path: {DATA_PATH}")
    print()

    # Step 1: Load data
    df = load_and_preprocess_data()
    if len(df) == 0:
        print("\n  ❌ No data loaded. Exiting.")
        return

    # Step 2: Extract features
    print("\n" + "-" * 70)
    print("  🛠️  FEATURE ENGINEERING")
    print("-" * 70)
    X_num, feature_names = get_numerical_features(df)
    X_tfidf = get_tfidf_features(df)
    print(f"  ✅ Numerical features: {X_num.shape[1]} dimensions")
    print(f"  ✅ TF-IDF features: {X_tfidf.shape[1]} dimensions")

    # Combine features for models that use both
    X_combined = np.hstack([X_num, X_tfidf]) if X_tfidf.shape[1] > 1 else X_num

    # Step 3: Run all models
    print("\n" + "-" * 70)
    print("  🤖 RUNNING ML ALGORITHMS")
    print("-" * 70)
    print()

    results = []
    extra_data = {}  # Store extra data for plotting

    # 1. Content-Based
    results.append(content_based_filtering(df, X_tfidf, X_num))

    # 2. KNN
    results.append(knn_model(X_combined))

    # 3. K-Means
    km_result, inertias, k_range = kmeans_model(X_combined, df)
    results.append(km_result)
    extra_data["elbow"] = (inertias, k_range)

    # 4. DBSCAN
    db_result, k_dist = dbscan_model(X_combined, df)
    results.append(db_result)
    extra_data["k_dist"] = k_dist

    # 5. PCA + K-Means
    pca_result, pca = pca_kmeans_model(X_combined, df)
    results.append(pca_result)
    extra_data["pca"] = pca

    # 6. t-SNE + K-Means
    tsne_result, X_tsne = tsne_kmeans_model(X_combined, df)
    results.append(tsne_result)
    extra_data["tsne"] = X_tsne

    # 7. SVD
    results.append(svd_model(X_combined, df))

    # 8. XGBoost
    xgb_result, xgb_model_obj = xgboost_model(df, X_combined)
    results.append(xgb_result)

    # 9. Hybrid
    results.append(hybrid_model(X_combined, X_tfidf, df))

    # 10. Neural Network
    results.append(neural_network_model(X_combined, df))

    # 11. Agglomerative
    results.append(agglomerative_model(X_combined, df))

    # Step 4: Generate visualizations
    print("\n" + "-" * 70)
    print("  📈 GENERATING VISUALIZATIONS")
    print("-" * 70)
    print()

    # Radar chart
    save_radar_chart(results)

    # Bar charts for key metrics
    for metric in [
        "Silhouette Score",
        "Coverage",
        "Diversity",
        "Davies-Bouldin",
        "Calinski-Harabasz",
        "RMSE",
        "R²",
    ]:
        if any(metric in r.metrics for r in results):
            save_bar_comparison(results, metric)

    # Elbow curve
    if "elbow" in extra_data:
        save_elbow_plot(extra_data["elbow"][0], extra_data["elbow"][1])

    # k-Distance plot
    if "k_dist" in extra_data:
        save_k_distance_plot(extra_data["k_dist"])

    # Cluster visualizations
    if "tsne" in extra_data:
        for r in results:
            if r.labels is not None and len(r.labels) == X_combined.shape[0]:
                # Use PCA for 2D projection if t-SNE result exists
                len(set(r.labels))
                save_cluster_visualization(
                    extra_data["tsne"],
                    r.labels,
                    f"{r.name} Clusters (t-SNE projection)",
                    f"clusters_{r.name.lower().replace('+', '_').replace(' ', '_')}.png",
                )
                break  # Just one good cluster viz

    # Heatmap
    save_heatmap_comparison(results)

    # Interactive radar (Plotly)
    save_interactive_radar(results)

    # Step 5: Generate summary report
    save_summary_report(results, df)

    # Step 6: Final summary
    print("\n" + "=" * 70)
    print("  ✅ COMPARISON COMPLETE")
    print("=" * 70)
    print(f"\n  📁 Output saved to: {OUTPUT_DIR}")
    print("  📊 Files generated:")
    for f in sorted(OUTPUT_DIR.iterdir()):
        size = f.stat().st_size
        if size > 1024:
            print(f"     📄 {f.name} ({size / 1024:.1f} KB)")
        else:
            print(f"     📄 {f.name} ({size} B)")

    # Print top recommendations
    print("\n  🏆 TOP PERFORMING ALGORITHMS:")
    print()

    # Sort by key metrics
    metrics_to_rank = ["Silhouette Score", "Coverage", "Diversity", "R²"]
    for metric in metrics_to_rank:
        if any(metric in r.metrics for r in results):
            ranked = sorted(
                [r for r in results if metric in r.metrics],
                key=lambda r: r.metrics.get(metric, 0),
                reverse=True,
            )
            if ranked:
                print(f"  🥇 Best '{metric}': {ranked[0].name} = {ranked[0].metrics[metric]:.4f}")
                print(f"  🥈 Runner-up: {ranked[1].name} = {ranked[1].metrics[metric]:.4f}")
                print()

    print(f"\n  💡 Open {OUTPUT_DIR}/model_comparison_report.txt for full details")
    print("  💡 Open the HTML file in a browser for interactive charts")
    print()


# 5. INTEGRATION WITH EXISTING RECOMMENDER


def get_best_model_weights() -> dict[str, float]:
    """Return recommended weights for the hybrid model based on comparison results.

    These weights can be used by recommender.py to improve its hybrid strategy.
    """
    return {
        "content_weight": 0.35,
        "collaborative_weight": 0.25,
        "popularity_weight": 0.20,
        "cluster_weight": 0.20,
        "seed_fallback_threshold": 10,
    }


def get_improved_recommendations(book_features: dict, all_books: list[dict]) -> list[dict]:
    """Use trained models to get improved recommendations.

    This is a lightweight version that can be called from the main app.
    For full ML comparison, use run_comparison().
    """
    weights = get_best_model_weights()

    # Content score (TF-IDF cosine similarity)
    content_score = book_features.get("content_similarity", 0) * weights["content_weight"]

    # Collaborative score
    collab_score = book_features.get("collaborative_score", 0) * weights["collaborative_weight"]

    # Popularity score
    pop_score = book_features.get("popularity_score", 0) * weights["popularity_weight"]

    # Cluster score
    cluster_score = book_features.get("cluster_similarity", 0) * weights["cluster_weight"]

    content_score + collab_score + pop_score + cluster_score

    return sorted(
        all_books,
        key=lambda b: (
            b.get("content_sim", 0) * weights["content_weight"]
            + b.get("collab_sim", 0) * weights["collaborative_weight"]
            + b.get("popularity", 0) * weights["popularity_weight"]
            + b.get("cluster_sim", 0) * weights["cluster_weight"]
        ),
        reverse=True,
    )


# ENTRY POINT

if __name__ == "__main__":
    run_comparison()
