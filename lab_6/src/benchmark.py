import json, time, os
from pathlib import Path
import pandas as pd

CLEAN = Path("clean"); CLEAN.mkdir(exist_ok=True)

def benchmark():
    df = pd.read_parquet(CLEAN / "dataset.parquet")
    df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)
    df["isbn"] = df["isbn"].astype("string")
    df.loc[0, "isbn"] = "0123456789"

    csv_p = CLEAN / "ds.csv"; df.to_csv(csv_p, index=False)
    t0 = time.perf_counter(); df_csv = pd.read_csv(csv_p); t_csv = time.perf_counter() - t0
    t0 = time.perf_counter(); _ = pd.read_csv(csv_p, usecols=["book_key", "title"]); t_csv2 = time.perf_counter() - t0

    jl_p = CLEAN / "ds.jsonl"
    with open(jl_p, "w", encoding="utf-8") as f:
        for r in df.to_dict("records"):
            f.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")
    t0 = time.perf_counter()
    df_jl = pd.DataFrame([json.loads(l) for l in open(jl_p, encoding="utf-8")])
    t_jl = time.perf_counter() - t0
    t0 = time.perf_counter()
    _ = pd.DataFrame([{k: json.loads(l)[k] for k in ("book_key", "title")} for l in open(jl_p, encoding="utf-8")])
    t_jl2 = time.perf_counter() - t0

    pq_p = CLEAN / "ds.parquet"; df.to_parquet(pq_p, index=False)
    t0 = time.perf_counter(); df_pq = pd.read_parquet(pq_p); t_pq = time.perf_counter() - t0
    t0 = time.perf_counter(); _ = pd.read_parquet(pq_p, columns=["book_key", "title"]); t_pq2 = time.perf_counter() - t0

    rows = [
        {"format": "CSV",      "size_kb": os.path.getsize(csv_p)/1024, "read_full_s": t_csv,  "read_2cols_s": t_csv2,
         "isbn_type": df_csv["isbn"].dtype, "collected_at_type": df_csv["collected_at"].dtype, "isbn_leading_zero": "lost"},
        {"format": "JSONL",    "size_kb": os.path.getsize(jl_p)/1024,  "read_full_s": t_jl,   "read_2cols_s": t_jl2,
         "isbn_type": df_jl["isbn"].dtype, "collected_at_type": "object", "isbn_leading_zero": "kept (string)"},
        {"format": "Parquet",  "size_kb": os.path.getsize(pq_p)/1024,  "read_full_s": t_pq,   "read_2cols_s": t_pq2,
         "isbn_type": str(df_pq["isbn"].dtype), "collected_at_type": str(df_pq["collected_at"].dtype), "isbn_leading_zero": "kept (string)"},
    ]
    pd.DataFrame(rows).to_csv(CLEAN / "format_benchmark.csv", index=False)
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    benchmark()