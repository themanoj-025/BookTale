"""Model result, evaluation, content-based filtering."""

from __future__ import annotations
from app.services.recommendations.ml.Model.ml_pkg.data_loading import N_CLUSTERS, RANDOM_STATE, TOP_N_RECS
from app.services.recommendations.ml.Model.ml_pkg.models import ALGORITHM_COLORS
from sklearn.cluster import KMeans
from sklearn.metrics import calinski_harabasz_score
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.metrics import davies_bouldin_score
import numpy as np
import pandas as pd
from sklearn.metrics import silhouette_score
import time
import logging

logger = logging.getLogger(__name__)


class ModelResult:
    """Stores evaluation results for a single model."""

    def __init__(self, name: str, color: str) -> None:
        self.name = name
        self.color = color
        self.metrics = {}
        self.predictions = None
        self.labels = None
        self.time_taken = 0.0

    def add_metric(self, name: str, value: float) -> None:
        self.metrics[name] = value

    def get_formatted_metrics(self) -> str:
        lines = [f"  📊 {self.name}:"]
        for k, v in sorted(self.metrics.items()):
            lines.append(f"     {k:30s} = {v:.4f}")
        lines.append(f"     {'Time':30s} = {self.time_taken:.3f}s")
        return "\n".join(lines)


def evaluate_clustering(X: np.ndarray, labels: np.ndarray, result: ModelResult) -> None:
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
        except (ValueError, TypeError):
            result.add_metric("Silhouette Score", -1.0)

        try:
            db = davies_bouldin_score(X, labels)
            result.add_metric("Davies-Bouldin", db)
        except (ValueError, TypeError):
            result.add_metric("Davies-Bouldin", -1.0)

        try:
            ch = calinski_harabasz_score(X, labels)
            result.add_metric("Calinski-Harabasz", ch)
        except (ValueError, TypeError):
            result.add_metric("Calinski-Harabasz", -1.0)


def evaluate_recommendation(
    df: pd.DataFrame, scores: np.ndarray, result: ModelResult, top_n: int = TOP_N_RECS
) -> dict:
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
    logger.info("  🔄 Content-Based Filtering...")
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
    logger.info(f"✅ ({result.time_taken:.2f}s)")
    return result


# ALGORITHM 2: KNN (k-Nearest Neighbors)


