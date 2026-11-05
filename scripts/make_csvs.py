"""Turn bookleaf_sample_data.json into CSVs for Bubble's App Data uploader.

Royalty status follows the assignment's rule, evaluated on the run date:
  Paid    - nothing pending
  Overdue - pending, and the last payout is more than 90 days old,
            or nothing was ever paid on a book published more than 90 days ago
  Pending - pending, but still inside that window
Books still in production get no royalty status.

Usage: python3 scripts/make_csvs.py [YYYY-MM-DD]   (defaults to today)
"""
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE.parent / "data"
TODAY = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
CUTOFF = TODAY - timedelta(days=90)


def d(s):
    return date.fromisoformat(s) if s else None


def bubble_date(x):
    # Bubble's CSV importer reads MM/DD/YYYY unambiguously.
    return x.strftime("%m/%d/%Y") if x else ""


def royalty_status(b):
    if not b["status"].startswith("Published"):
        return ""
    if b["royalty_pending"] == 0:
        return "Paid"
    last, published = d(b["last_royalty_payout_date"]), d(b["publication_date"])
    if (last and last < CUTOFF) or (not last and published and published < CUTOFF):
        return "Overdue"
    return "Pending"


def main():
    authors = json.loads((HERE / "bookleaf_sample_data.json").read_text())["authors"]
    OUT.mkdir(exist_ok=True)
    author_rows, book_rows, payout_rows = [], [], []

    for a in authors:
        statuses = []
        for b in a["books"]:
            status = royalty_status(b)
            statuses.append(status)
            published = b["status"].startswith("Published")
            book_rows.append({
                "book_code": b["book_id"],
                "author_code": a["author_id"],  # resolved to the Author link at import time
                "title": b["title"],
                "isbn": b["isbn"],
                "genre": b["genre"],
                "status": b["status"],
                "is_published": "yes" if published else "no",
                "production_stage": "" if published else b["status"].replace("In Production - ", ""),
                "publication_date": bubble_date(d(b["publication_date"])),
                "mrp": b["mrp"] if b["mrp"] is not None else "",
                "royalty_per_copy": b["author_royalty_per_copy"] if b["author_royalty_per_copy"] is not None else "",
                "copies_sold": b["total_copies_sold"],
                "royalty_earned": b["total_royalty_earned"],
                "royalty_paid": b["royalty_paid"],
                "royalty_pending": b["royalty_pending"],
                "last_payout_date": bubble_date(d(b["last_royalty_payout_date"])),
                "print_partner": b["print_partner"] or "",
                "available_on": ", ".join(b["available_on"]),
                "royalty_status": status,
            })
            # The dataset only carries the cumulative amount paid and the latest payout date,
            # so each paid book gets one payout record representing everything paid to date.
            if b["royalty_paid"] > 0 and b["last_royalty_payout_date"]:
                payout_rows.append({
                    "book_code": b["book_id"],
                    "author_code": a["author_id"],
                    "amount": b["royalty_paid"],
                    "paid_on": bubble_date(d(b["last_royalty_payout_date"])),
                    "note": "Cumulative royalties paid to date (latest payout)",
                })

        payout_status = "Overdue" if "Overdue" in statuses else "Pending" if "Pending" in statuses else "Paid"
        author_rows.append({
            "author_code": a["author_id"],
            "name": a["name"],
            "email": a["email"].lower(),
            "phone": a["phone"],
            "city": a["city"],
            "joined_date": bubble_date(d(a["joined_date"])),
            "total_books": len(a["books"]),
            "total_earned": sum(b["total_royalty_earned"] for b in a["books"]),
            "total_paid": sum(b["royalty_paid"] for b in a["books"]),
            "total_pending": sum(b["royalty_pending"] for b in a["books"]),
            "payout_status": payout_status,
        })

    for name, rows in [("authors", author_rows), ("books", book_rows), ("payouts", payout_rows)]:
        with open(OUT / f"{name}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"{name}.csv: {len(rows)} rows")
    print(f"Statuses evaluated as of {TODAY} (90-day cutoff {CUTOFF})")
    for r in author_rows:
        print(f"  {r['author_code']} {r['name']:<18} {r['city']:<11} pending {r['total_pending']:>6}  {r['payout_status']}")


if __name__ == "__main__":
    main()
