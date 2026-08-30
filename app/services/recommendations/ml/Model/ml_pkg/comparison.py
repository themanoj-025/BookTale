"""Comparison runner and weight extraction."""

from __future__ import annotations
from app.services.recommendations.ml.Model.ml_pkg.models import ALGORITHM_COLORS
from app.services.recommendations.ml.Model.ml_pkg.models import DATA_PATH
from app.services.recommendations.ml.Model.ml_pkg.models import OUTPUT_DIR
from app.services.recommendations.ml.Model.ml_pkg.models import agglomerative_model
from app.services.recommendations.ml.Model.ml_pkg.models import content_based_filtering
from app.services.recommendations.ml.Model.ml_pkg.models import dbscan_model
from app.services.recommendations.ml.Model.ml_pkg.models import get_numerical_features
from app.services.recommendations.ml.Model.ml_pkg.models import get_tfidf_features
from app.services.recommendations.ml.Model.ml_pkg.models import hybrid_model
from app.services.recommendations.ml.Model.ml_pkg.models import kmeans_model
from app.services.recommendations.ml.Model.ml_pkg.models import knn_model
from app.services.recommendations.ml.Model.ml_pkg.models import load_and_preprocess_data
from app.services.recommendations.ml.Model.ml_pkg.models import neural_network_model
import numpy as np
from app.services.recommendations.ml.Model.ml_pkg.models import pca_kmeans_model
from app.services.recommendations.ml.Model.ml_pkg.visualization import save_bar_comparison
from app.services.recommendations.ml.Model.ml_pkg.visualization import save_cluster_visualization
from app.services.recommendations.ml.Model.ml_pkg.visualization import save_elbow_plot
from app.services.recommendations.ml.Model.ml_pkg.visualization import save_heatmap_comparison
from app.services.recommendations.ml.Model.ml_pkg.visualization import save_interactive_radar
from app.services.recommendations.ml.Model.ml_pkg.visualization import save_k_distance_plot
from app.services.recommendations.ml.Model.ml_pkg.visualization import save_radar_chart
from app.services.recommendations.ml.Model.ml_pkg.visualization import save_summary_report
from app.services.recommendations.ml.Model.ml_pkg.models import svd_model
from app.services.recommendations.ml.Model.ml_pkg.models import tsne_kmeans_model
from app.services.recommendations.ml.Model.ml_pkg.models import xgboost_model
import logging

logger = logging.getLogger(__name__)


def run_comparison() -> dict:
    """Run the full ML model comparison pipeline."""
    logger.info("\n" + "=" * 70)
    logger.info("  LIBRARY MANAGEMENT SYSTEM - ML MODEL COMPARISON")
    logger.info("=" * 70)
    print()
    logger.info(f"  Output directory: {OUTPUT_DIR}")
    logger.info(f"  Algorithms to test: {len(ALGORITHM_COLORS)}")
    logger.info(f"  Dataset path: {DATA_PATH}")
    print()

    # Step 1: Load data
    df = load_and_preprocess_data()
    if len(df) == 0:
        logger.info("\n  ❌ No data loaded. Exiting.")
        return

    # Step 2: Extract features
    logger.info("\n" + "-" * 70)
    logger.info("  🛠️  FEATURE ENGINEERING")
    logger.info("-" * 70)
    X_num, _feature_names = get_numerical_features(df)
    X_tfidf = get_tfidf_features(df)
    logger.info(f"  ✅ Numerical features: {X_num.shape[1]} dimensions")
    logger.info(f"  ✅ TF-IDF features: {X_tfidf.shape[1]} dimensions")

    # Combine features for models that use both
    X_combined = np.hstack([X_num, X_tfidf]) if X_tfidf.shape[1] > 1 else X_num

    # Step 3: Run all models
    logger.info("\n" + "-" * 70)
    logger.info("  🤖 RUNNING ML ALGORITHMS")
    logger.info("-" * 70)
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
    xgb_result, _xgb_model_obj = xgboost_model(df, X_combined)
    results.append(xgb_result)

    # 9. Hybrid
    results.append(hybrid_model(X_combined, X_tfidf, df))

    # 10. Neural Network
    results.append(neural_network_model(X_combined, df))

    # 11. Agglomerative
    results.append(agglomerative_model(X_combined, df))

    # Step 4: Generate visualizations
    logger.info("\n" + "-" * 70)
    logger.info("  📈 GENERATING VISUALIZATIONS")
    logger.info("-" * 70)
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
    logger.info("\n" + "=" * 70)
    logger.info("  ✅ COMPARISON COMPLETE")
    logger.info("=" * 70)
    logger.info(f"\n  📁 Output saved to: {OUTPUT_DIR}")
    logger.info("  📊 Files generated:")
    for f in sorted(OUTPUT_DIR.iterdir()):
        size = f.stat().st_size
        if size > 1024:
            logger.info(f"     📄 {f.name} ({size / 1024:.1f} KB)")
        else:
            logger.info(f"     📄 {f.name} ({size} B)")

    # Print top recommendations
    logger.info("\n  🏆 TOP PERFORMING ALGORITHMS:")
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
                logger.info(f"  🥇 Best '{metric}': {ranked[0].name} = {ranked[0].metrics[metric]:.4f}")
                logger.info(f"  🥈 Runner-up: {ranked[1].name} = {ranked[1].metrics[metric]:.4f}")
                print()

    logger.info(f"\n  💡 Open {OUTPUT_DIR}/model_comparison_report.txt for full details")
    logger.info("  💡 Open the HTML file in a browser for interactive charts")
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
