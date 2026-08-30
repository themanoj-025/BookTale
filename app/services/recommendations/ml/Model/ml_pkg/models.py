"""ML model implementations."""

from __future__ import annotations
from app.services.recommendations.ml.Model.ml_pkg.data_loading import N_CLUSTERS, N_NEIGHBORS, RANDOM_STATE, TEST_SIZE, XGB_AVAILABLE
from app.services.recommendations.ml.Model.ml_pkg.models import ALGORITHM_COLORS
from sklearn.cluster import AgglomerativeClustering
from sklearn.cluster import DBSCAN
from sklearn.cluster import KMeans
from sklearn.neural_network import MLPRegressor
from app.services.recommendations.ml.Model.ml_pkg.models import ModelResult
from sklearn.neighbors import NearestNeighbors
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.decomposition import TruncatedSVD
from sklearn.metrics.pairwise import cosine_similarity
from app.services.recommendations.ml.Model.ml_pkg.models import evaluate_clustering
from app.services.recommendations.ml.Model.ml_pkg.models import evaluate_recommendation
import math
from sklearn.metrics import mean_absolute_error
from sklearn.metrics import mean_squared_error
import numpy as np
import pandas as pd
from sklearn.metrics import r2_score
import time
from sklearn.model_selection import train_test_split
import xgboost as xgb
import logging

logger = logging.getLogger(__name__)


def knn_model(X: np.ndarray) -> ModelResult:
    """KNN-based recommendation using nearest neighbors."""
    logger.info("  🔄 KNN (k-Nearest Neighbors)...")
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
    logger.info(f"✅ ({result.time_taken:.2f}s)")
    return result


# ALGORITHM 3: K-Means Clustering


def kmeans_model(X: np.ndarray, df: pd.DataFrame) -> ModelResult:
    """K-Means clustering with multiple initializations."""
    logger.info("  🔄 K-Means Clustering...")
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
    logger.info(f"✅ ({result.time_taken:.2f}s)")
    return result, inertias, k_range


# ALGORITHM 4: DBSCAN


def dbscan_model(X: np.ndarray, df: pd.DataFrame) -> ModelResult:
    """DBSCAN density-based clustering with auto eps tuning."""
    logger.info("  🔄 DBSCAN...")
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
    logger.info(f"✅ ({result.time_taken:.2f}s)")
    return result, k_dist


# ALGORITHM 5: PCA + K-Means


def pca_kmeans_model(X: np.ndarray, df: pd.DataFrame) -> ModelResult:
    """PCA dimensionality reduction followed by K-Means."""
    logger.info("  🔄 PCA + K-Means...")
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
    logger.info(f"✅ ({result.time_taken:.2f}s)")
    return result, pca


# ALGORITHM 6: t-SNE + K-Means


def tsne_kmeans_model(X: np.ndarray, df: pd.DataFrame) -> ModelResult:
    """t-SNE dimensionality reduction followed by K-Means."""
    logger.info("  🔄 t-SNE + K-Means...")
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
    logger.info(f"✅ ({result.time_taken:.2f}s)")
    return result, X_tsne


# ALGORITHM 7: Truncated SVD (Matrix Factorization)


def svd_model(X: np.ndarray, df: pd.DataFrame) -> ModelResult:
    """Truncated SVD for matrix factorization and recommendation."""
    logger.info("  🔄 SVD Matrix Factorization...")
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
    logger.info(f"✅ ({result.time_taken:.2f}s)")
    return result


# ALGORITHM 8: XGBoost Regression


def xgboost_model(df: pd.DataFrame, X: np.ndarray) -> ModelResult:
    """XGBoost regression for rating prediction."""
    logger.info("  🔄 XGBoost Regression...")
    start = time.time()
    result = ModelResult("XGBoost", ALGORITHM_COLORS["XGBoost"])

    if not XGB_AVAILABLE:
        logger.info("⚠️ (XGBoost not installed, skipping)")
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
    logger.info(f"✅ ({result.time_taken:.2f}s)")
    return result, model


# ALGORITHM 9: Hybrid Model


def hybrid_model(X: np.ndarray, X_tfidf: np.ndarray, df: pd.DataFrame) -> ModelResult:
    """Hybrid: combines content-based similarity with collaborative clustering."""
    logger.info("  🔄 Hybrid Model (Content + Collaborative)...")
    start = time.time()
    result = ModelResult("Hybrid", ALGORITHM_COLORS["Hybrid"])

    # Content-based similarity
    content_sim = cosine_similarity(X_tfidf) if X_tfidf.shape[1] > 1 else cosine_similarity(X)

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
    logger.info(f"✅ ({result.time_taken:.2f}s)")
    return result


# ALGORITHM 10: Neural Network (MLP)


def neural_network_model(X: np.ndarray, df: pd.DataFrame) -> ModelResult:
    """Simple MLP neural network for rating prediction."""
    logger.info("  🔄 Neural Network (MLP)...")
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
    logger.info(f"✅ ({result.time_taken:.2f}s)")
    return result


# ALGORITHM 11: Agglomerative Clustering


def agglomerative_model(X: np.ndarray, df: pd.DataFrame) -> ModelResult:
    """Hierarchical agglomerative clustering."""
    logger.info("  🔄 Agglomerative Clustering...")
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
    logger.info(f"✅ ({result.time_taken:.2f}s)")
    return result


# 3. VISUALIZATION FUNCTIONS


