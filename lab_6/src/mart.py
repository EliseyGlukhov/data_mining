from datetime import datetime, timezone
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from quality import metrics, should_load_mart

CLEAN = Path("clean/dataset.parquet")
MART = Path("mart"); VIEWS = MART / "views"; FIGS = MART / "figures"
VIEWS.mkdir(parents=True, exist_ok=True); FIGS.mkdir(parents=True, exist_ok=True)


def build(prev_count: int | None = None) -> None:
    m = metrics(prev_count)
    if not should_load_mart(m):
        raise SystemExit("Mart build aborted due to red metric")

    df = pd.read_parquet(CLEAN)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")

    v1 = (df.dropna(subset=["category", "price"])
            .groupby("category", as_index=False)
            .agg(avg_price=("price", "mean"), n_books=("book_key", "count"))
            .sort_values("avg_price", ascending=False))
    v1.to_parquet(VIEWS / "avg_price_by_category.parquet", index=False)

    v2 = df.dropna(subset=["rating"]).sort_values(["rating", "title"], ascending=[False, True]).head(10)
    v2[["book_key", "title", "rating", "category"]].to_parquet(VIEWS / "top_rated_books.parquet", index=False)

    df["decade"] = (pd.to_numeric(df["publish_year"], errors="coerce") // 10 * 10)
    v3 = df.dropna(subset=["decade"]).groupby("decade", as_index=False).agg(n=("book_key","count"))
    v3.to_parquet(VIEWS / "books_by_decade.parquet", index=False)

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    part = MART / "snapshots" / f"dt={day}"; part.mkdir(parents=True, exist_ok=True)
    df.to_parquet(part / "snapshot.parquet", index=False)

    v1.sort_values("avg_price").plot(kind="barh", x="category", y="avg_price", legend=False)
    plt.title("Средняя цена по категориям"); plt.tight_layout()
    plt.savefig(FIGS / "price_distribution.png", dpi=120); plt.close()

    v3.sort_values("decade").plot(kind="bar", x="decade", y="n", legend=False)
    plt.title("Книги по десятилетиям"); plt.tight_layout()
    plt.savefig(FIGS / "rating_dynamics.png", dpi=120); plt.close()
    print("mart built")


if __name__ == "__main__":
    build()