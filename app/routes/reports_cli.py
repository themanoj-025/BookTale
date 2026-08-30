"""
reports_cli.py - Reports, Analytics, and CSV Export CLI.
"""

import csv
import os
from datetime import datetime

from app.config.settings import Config
from app.core.utils import (
    header,
    menu,
    pause,
    print_success,
)
from app.services.books.library import Library
import logging

logger = logging.getLogger(__name__)



def reports_menu(lib: Library) -> None:
    while True:
        choice = menu(
            "📊 REPORTS & ANALYTICS",
            [
                "Most Issued Books",
                "Active Users",
                "Issued Today / This Month",
                "Fine Collection Report",
                "Category-wise Book Count",
                "Back",
            ],
        )
        if choice == "1":
            data = lib.report_most_issued()
            header("📚 Most Issued Books")
            for i, r in enumerate(data, 1):
                logger.info(f"  {i:2}. [{r['id']}] {r['title']} — {r['author']} " f"| Issued {r['count']}×")
        elif choice == "2":
            data = lib.report_active_users()
            header("🏆 Most Active Users")
            for i, r in enumerate(data, 1):
                logger.info(f"  {i:2}. [{r['user_id']}] {r['name']} — {r['total_issues']} issues")
        elif choice == "3":
            header("📅 Issue Counts")
            logger.info(f"  Today         : {lib.report_issued_today()} books")
            logger.info(f"  This Month    : {lib.report_issued_this_month()} books")
        elif choice == "4":
            r = lib.report_fine_collection()
            header("💰 Fine Collection Report")
            logger.info(f"  Total Fines   : ₹{r['total']:.2f}")
            logger.info(f"  Collected     : ₹{r['collected']:.2f}")
            logger.info(f"  Pending       : ₹{r['pending']:.2f}")
            logger.info(f"  Transactions  : {r['count']}")
        elif choice == "5":
            data = lib.report_category_count()
            header("🗂  Category-wise Book Count")
            for cat, cnt in data.items():
                logger.info(f"  {cat:<20} : {cnt} book(s)")
        elif choice == "6":
            break
        pause()


def export_reports_menu(lib: Library) -> None:
    """Export various reports to CSV."""
    header("📤 EXPORT REPORTS TO CSV")
    logger.info("  1. Export Most Issued Books")
    logger.info("  2. Export All Books Inventory")
    logger.info("  3. Export Active Users")
    logger.info("  4. Export All Transactions")
    choice = input("  Choice: ").strip()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(Config.DATA_DIR, exist_ok=True)

    if choice == "1":
        data = lib.report_most_issued(50)
        path = os.path.join(Config.DATA_DIR, f"most_issued_{timestamp}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id", "title", "author", "count"])
            w.writeheader()
            w.writerows(data)
        print_success(f"Exported to: {path}")
    elif choice == "2":
        books = [b for b in lib.storage.load_books().values() if not b.is_deleted]
        path = os.path.join(Config.DATA_DIR, f"inventory_{timestamp}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "book_id",
                    "title",
                    "author",
                    "isbn",
                    "category",
                    "total_copies",
                    "available_copies",
                    "issue_count",
                ],
            )
            w.writeheader()
            for b in books:
                w.writerow(b.to_dict())
        print_success(f"Exported to: {path}")
    elif choice == "3":
        data = lib.report_active_users(50)
        path = os.path.join(Config.DATA_DIR, f"active_users_{timestamp}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["user_id", "name", "total_issues"])
            w.writeheader()
            w.writerows(data)
        print_success(f"Exported to: {path}")
    elif choice == "4":
        txns = lib.storage.load_transactions()
        path = os.path.join(Config.DATA_DIR, f"transactions_{timestamp}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "txn_id",
                    "type",
                    "user_id",
                    "book_id",
                    "issue_date",
                    "due_date",
                    "return_date",
                    "fine",
                ],
            )
            w.writeheader()
            w.writerows(txns)
        print_success(f"Exported to: {path}")
    pause()
