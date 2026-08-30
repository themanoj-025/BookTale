"""Chart and visualization functions."""

from __future__ import annotations
from app.services.recommendations.ml.Model.ml_pkg.models import ALGORITHM_COLORS
from app.services.recommendations.ml.Model.ml_pkg.models import ModelResult
from app.services.recommendations.ml.Model.ml_pkg.models import OUTPUT_DIR
from app.services.recommendations.ml.Model.ml_pkg.models import PLOTLY_AVAILABLE
import plotly.graph_objects as go
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import logging

logger = logging.getLogger(__name__)


def save_radar_chart(results: list[ModelResult], filename: str = "radar_comparison.png") -> None:
    """Create a radar chart comparing algorithms across key metrics."""
    logger.info("\n  📊 Generating Radar Chart...")

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
        logger.info("  ⚠️  No common metrics available for radar chart")
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
        vals = [row[i] for row in data.values()]
        min_v, max_v = min(vals), max(vals)
        if max_v > min_v:
            # For Davies-Bouldin, lower is better
            if available_metrics[i] == "Davies-Bouldin":
                for row in data.values():
                    row[i] = 1 - (row[i] - min_v) / (max_v - min_v)
            else:
                for row in data.values():
                    row[i] = (row[i] - min_v) / (max_v - min_v)

    _fig, ax = plt.subplots(figsize=(12, 10), subplot_kw={"polar": True})

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
    logger.info(f"  ✅ Radar chart saved: {path}")


def save_bar_comparison(results: list[ModelResult], metric: str, filename: str | None = None) -> None:
    """Create a bar chart comparing a specific metric across algorithms."""
    names = [r.name for r in results]
    values = [r.metrics.get(metric, 0) for r in results]
    colors = [ALGORITHM_COLORS.get(n, f"C{i}") for i, n in enumerate(names)]

    _fig, ax = plt.subplots(figsize=(14, 6))
    bars = ax.bar(range(len(names)), values, color=colors, edgecolor="white", linewidth=0.5)

    # Add value labels on bars
    for bar, val in zip(bars, values, strict=False):
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
    logger.info(f"  ✅ Bar chart saved: {path}")


def save_elbow_plot(inertias, k_range, filename: str = "elbow_curve.png") -> None:
    """Save elbow curve for K selection."""
    _fig, ax = plt.subplots(figsize=(10, 6))
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
    logger.info(f"  ✅ Elbow curve saved: {path}")


def save_k_distance_plot(k_dist: np.ndarray, filename: str = "k_distance_plot.png") -> None:
    """Save k-distance plot for DBSCAN eps tuning."""
    _fig, ax = plt.subplots(figsize=(10, 6))
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
    logger.info(f"  ✅ k-Distance plot saved: {path}")


def save_cluster_visualization(X_2d: np.ndarray, labels: np.ndarray, title: str, filename: str) -> None:
    """Save 2D cluster visualization."""
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    _fig, ax = plt.subplots(figsize=(12, 8))

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
    logger.info(f"  ✅ Cluster viz saved: {path}")


def save_heatmap_comparison(results: list[ModelResult], filename: str = "performance_heatmap.png") -> None:
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
        logger.info("  ⚠️  No common metrics for heatmap")
        return

    data = []
    for r in results:
        row = [r.metrics.get(m, np.nan) for m in key_metrics]
        data.append(row)

    data = np.array(data)
    _fig, ax = plt.subplots(figsize=(12, max(6, len(results) * 0.5)))

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
    logger.info(f"  ✅ Heatmap saved: {path}")


def save_interactive_radar(results: list[ModelResult], filename: str = "interactive_radar.html") -> None:
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
                theta=[*available_metrics, available_metrics[0]],
                name=r.name,
                line_color=ALGORITHM_COLORS.get(r.name, "#000"),
                fill="toself",
                opacity=0.3,
            )
        )

    fig.update_layout(
        polar={"radialaxis": {"visible": True, "range": [0, 1]}},
        title="📊 Interactive Algorithm Comparison (Normalized)",
        font={"size": 11},
        legend={"x": 1.1, "y": 0.5},
        width=1000,
        height=700,
    )

    path = OUTPUT_DIR / filename
    fig.write_html(path)
    logger.info(f"  ✅ Interactive radar saved: {path}")


def save_summary_report(results: list[ModelResult], df: pd.DataFrame) -> None:
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
            sort_key = results[0].metrics and next(iter(results[0].metrics.keys()))

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

    logger.info(f"  ✅ Summary report saved: {path}")


# 4. MAIN PIPELINE


