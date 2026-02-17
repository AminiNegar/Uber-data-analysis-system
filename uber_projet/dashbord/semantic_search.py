import chromadb
from chromadb.utils import embedding_functions
import psycopg2
import os
import hashlib

os.environ["HF_HUB_TIMEOUT"] = "60"


conn = psycopg2.connect(
    dbname="UberDB",
    user="postgres",
    password="4043614002",
    host="localhost",
    port="5432"
)
cur = conn.cursor()


client = chromadb.Client()

embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

try:
    client.delete_collection("cancellation_reasons")
except:
    pass

collection = client.get_or_create_collection(
    name="cancellation_reasons",
    embedding_function=embedding_function
)


def index_data_dedup_reason():
    cur.execute("""
        SELECT unified_cancellation_reason, COUNT(*) AS cnt, MIN(booking_id) AS sample_booking
        FROM gold.dataset
        WHERE unified_cancellation_reason IS NOT NULL
          AND LENGTH(TRIM(unified_cancellation_reason)) > 0
        GROUP BY unified_cancellation_reason
    """)
    rows = cur.fetchall()

    documents, ids, metas = [], [], []

    for reason, cnt, sample_trip in rows:
        r = str(reason).strip()
        rid = hashlib.md5(r.lower().encode("utf-8")).hexdigest()  # id ثابت برای هر reason

        documents.append(r)
        ids.append(rid)
        metas.append({
            "count": int(cnt),
            "sample_booking_id": int(sample_trip) if sample_trip is not None else None
        })

    batch_size = 2000
    for i in range(0, len(ids), batch_size):
        collection.add(
            documents=documents[i:i + batch_size],
            ids=ids[i:i + batch_size],
            metadatas=metas[i:i + batch_size]
        )
        print(f"Indexed {min(i + batch_size, len(ids))} / {len(ids)}")

def semantic_search_with_scores(query_text, top_k=5):
    res = collection.query(query_texts=[query_text], n_results=top_k)

    docs = res["documents"][0]
    dists = res.get("distances", [[]])[0]
    metas = res.get("metadatas", [[]])[0]

    out = []
    for i in range(len(docs)):
        dist = dists[i] if i < len(dists) else None
        sim = (1 - dist) if dist is not None else None  
        out.append({
            "rank": i + 1,
            "distance": dist,
            "sim_est": sim,
            "reason": docs[i],
            "count": (metas[i] or {}).get("count"),
            "sample_booking_id": (metas[i] or {}).get("sample_booking_id"),
        })
    return out

def fetch_examples_for_reason(reason_text, limit=5):
    cur.execute("""
        SELECT *
        FROM gold.dataset
        WHERE unified_cancellation_reason = %s
        LIMIT %s
    """, (reason_text, limit))
    return cur.fetchall()


if __name__ == "__main__":
    print("Indexing data (dedup by reason)...")
    index_data_dedup_reason()
    print("Indexing completed ✅")

    while True:
        query = input("\nEnter search text (or type exit): ").strip()

        if query.lower() == "exit":
            break

        matches = semantic_search_with_scores(query, top_k=5)

        print("\nTop 5 Similar Results (with scores):")
        for m in matches:
            dist_str = f"{m['distance']:.4f}" if m["distance"] is not None else "NA"
            sim_str = f"{m['sim_est']:.4f}" if m["sim_est"] is not None else "NA"
            print(
                f"#{m['rank']} | distance={dist_str} | sim≈{sim_str} | "
                f"count={m.get('count')} | sample_booking_id={m.get('sample_booking_id')} | "
                f"reason={m['reason']}"
            )

        print("\nExamples from DB for each matched reason:")
        for m in matches:
            reason_text = m["reason"]
            examples = fetch_examples_for_reason(reason_text, limit=3)
            print(f"\n--- Reason (rank {m['rank']}): {reason_text}")
            for r in examples:
                print(r)
