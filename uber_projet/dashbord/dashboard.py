import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

import chromadb
from chromadb.utils import embedding_functions
import psycopg2
import hashlib

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

st.set_page_config(page_title="Uber Smart Dashboard", page_icon="🚖", layout="wide")

st.markdown("""
    <style>
    .main {font-family: 'Tahoma', sans-serif;}
    h1, h2, h3 {text-align: center;}
    .stChatInput {position: fixed; bottom: 30px;}
    </style>
    """, unsafe_allow_html=True)

DB_CONNECTION = "postgresql://postgres:4043614002@localhost:5432/UberDB"

GOLD_SCHEMA = """
Table: gold.dataset
Columns:
- trip_id (integer)
- booking_id (text)
- date (date)
- time (time without time zone)
- vehicle_type (text): values are 'Auto', 'Car', 'Bike'
- booking_status (text): values are 'Completed', 'Cancelled by Driver', 'Cancelled by Customer', 'Incomplete'
- unified_cancellation_reason (text): unified cancellation reason
- customer_rating (numeric): 0 to 5
- booking_value (numeric): The cost of the trip
- payment_method (text): 'Cash', 'Wallet', 'UPI', 'Credit Card'
- day_name (text): 'Monday', 'Tuesday', etc.
- hour (numeric): 0 to 23
"""

# Vector Search (Chroma) Config
CHROMA_COLLECTION_NAME = "cancellation_reasons"
EMBED_MODEL = "all-MiniLM-L6-v2"
MIN_SIM = 0.40  

@st.cache_resource
def get_pg_cursor():
    conn = psycopg2.connect(
        dbname="UberDB",
        user="postgres",
        password="4043614002",
        host="localhost",
        port="5432"
    )
    return conn, conn.cursor()

@st.cache_resource
def get_chroma_collection():
    client = chromadb.Client()
    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)

    col = client.get_or_create_collection(
        name=CHROMA_COLLECTION_NAME,
        embedding_function=emb_fn
    )
    return client, col

def reset_chroma_collection():
    client, _ = get_chroma_collection()
    try:
        client.delete_collection(CHROMA_COLLECTION_NAME)
    except:
        pass
    st.cache_resource.clear()

def build_reason_index_dedup():
    _, cur = get_pg_cursor()

    cur.execute("""
        SELECT unified_cancellation_reason, COUNT(*) AS cnt, MIN(trip_id) AS sample_trip
        FROM gold.dataset
        WHERE unified_cancellation_reason IS NOT NULL
          AND LENGTH(TRIM(unified_cancellation_reason)) > 0
        GROUP BY unified_cancellation_reason
    """)
    rows = cur.fetchall()

    documents, ids, metas = [], [], []
    for reason, cnt, sample_trip in rows:
        r = str(reason).strip()
        rid = hashlib.md5(r.lower().encode("utf-8")).hexdigest()
        documents.append(r)
        ids.append(rid)
        metas.append({
            "count": int(cnt),
            "sample_trip_id": int(sample_trip) if sample_trip is not None else None
        })

    reset_chroma_collection()
    _, collection = get_chroma_collection()

    batch_size = 2000
    for i in range(0, len(ids), batch_size):
        collection.add(
            documents=documents[i:i+batch_size],
            ids=ids[i:i+batch_size],
            metadatas=metas[i:i+batch_size],
        )
    return len(ids)

def normalize_query(q: str) -> str:
    q = q.strip().lower()
    q = q.replace("not find", "not found")
    q = q.replace("cant", "can't")
    return q

def semantic_search_reasons(query_text: str, top_k=5):
    query_text = normalize_query(query_text)
    _, collection = get_chroma_collection()

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
            "sim": sim,
            "reason": docs[i],
            "count": (metas[i] or {}).get("count"),
            "sample_trip_id": (metas[i] or {}).get("sample_trip_id"),
        })

    out = [m for m in out if (m["sim"] is not None and m["sim"] >= MIN_SIM)]
    return out

def fetch_examples_for_reason(reason_text: str, limit=5):
    conn, cur = get_pg_cursor()
    cur.execute("""
        SELECT *
        FROM gold.dataset
        WHERE unified_cancellation_reason = %s
        LIMIT %s
    """, (reason_text, limit))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    return pd.DataFrame(rows, columns=cols)

def label_quality(sim: float):
    if sim is None:
        return "Unknown"
    if sim >= 0.60:
        return "High"
    if sim >= 0.45:
        return "Medium"
    return "Low"


# Groq Text-to-SQL
def get_ai_response(user_question):
    if not GROQ_API_KEY:
        return "ERROR: Please set GROQ_API_KEY in .env file", False

    llm = ChatGroq(temperature=0, model_name="llama-3.3-70b-versatile", api_key=GROQ_API_KEY)

    system_prompt = f"""
    You are a Postgres SQL expert. Given an input question, create a syntactically correct Postgres SQL query to run.

    Here is the schema of the table you must query:
    {GOLD_SCHEMA}

    Rules:
    1. Return ONLY the SQL code. No markdown, no explanation, no '```sql'.
    2. Only use SELECT statements. Never use DELETE, DROP, INSERT, or UPDATE.
    3. If the user asks about something unrelated to the data return exactly: "NOT_RELATED"
    4. Always limit the query to a maximum of 10 rows unless specified otherwise.
    5. CRITICAL: When filtering text columns (like vehicle_type), use ILIKE for case-insensitivity (e.g. vehicle_type ILIKE 'Car').
    6. Ensure aggregation functions (AVG, SUM) are applied to numeric columns.
    7. CRITICAL: When sorting by numeric columns (like booking_value) to find top/highest records, ALWAYS exclude NULLs (add WHERE booking_value IS NOT NULL).
    """

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{question}"),
    ])

    chain = prompt | llm
    try:
        response = chain.invoke({"question": user_question})
        return response.content.strip(), True
    except Exception as e:
        return str(e), False
import re
def validate_and_fix_sql(sql_query):
    sql_upper = sql_query.upper()

    forbidden = ["DROP", "DELETE", "INSERT", "UPDATE", "TRUNCATE", "ALTER"]
    for word in forbidden:
        if word in sql_upper:
            return None, "Security Alert: Malicious command detected in SQL."

    if "NOT_RELATED" in sql_upper:
        return None, "I am a Data Assistant. Please ask questions about Uber trips."

    if not sql_upper.startswith("SELECT"):
        return None, "Invalid Query: Only SELECT queries are allowed."
    
    is_select_star = re.search(r"\bSELECT\s+\*\s+FROM\b", sql_upper) is not None
    has_limit = re.search(r"\bLIMIT\b", sql_upper) is not None
    if is_select_star and not has_limit:
        return None, "Security Alert: SELECT * without LIMIT is not allowed."
    if "LIMIT" not in sql_upper and "AVG" not in sql_upper and "COUNT" not in sql_upper and "SUM" not in sql_upper:
        sql_query += " LIMIT 20"
    
    return sql_query, "OK"

# Data loading / filters

@st.cache_data(ttl=60)
def load_data():
    try:
        engine = create_engine(DB_CONNECTION)
        query = "SELECT * FROM gold.dataset"
        df = pd.read_sql(query, engine)
        df['booking_value'] = pd.to_numeric(df['booking_value'], errors='coerce').fillna(0)
        df['customer_rating'] = pd.to_numeric(df['customer_rating'], errors='coerce')
        df['date'] = pd.to_datetime(df['date'])
        return df
    except Exception as e:
        st.error(f"Database Error: {e}")
        return pd.DataFrame()

def run_custom_query(sql):
    try:
        engine = create_engine(DB_CONNECTION)
        with engine.connect() as conn:
            result = pd.read_sql(text(sql), conn)
        return result, None
    except Exception as e:
        return None, str(e)


# Sidebar navigation

st.sidebar.title("Navigation")
page = st.sidebar.radio(
    "Go to",
    ["General KPIs", "Visual Charts", "AI Assistant (Text-to-SQL)", "Semantic Search (Cancellations)"]
)

st.sidebar.markdown("---")
st.sidebar.title("Filter Options")

if st.sidebar.button('Refresh Data'):
    st.cache_data.clear()
    st.rerun()

df = load_data()

if not df.empty:
    min_date = df['date'].min()
    max_date = df['date'].max()

    date_range = st.sidebar.date_input(
        "Select Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

    vehicle_options = df['vehicle_type'].unique()
    selected_vehicles = st.sidebar.multiselect(
        "Select Vehicle Type",
        options=vehicle_options,
        default=vehicle_options
    )

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        mask = (
            (df['date'].dt.date >= start_date) &
            (df['date'].dt.date <= end_date) &
            (df['vehicle_type'].isin(selected_vehicles))
        )
        filtered_df = df[mask]
    else:
        filtered_df = df[df['vehicle_type'].isin(selected_vehicles)]

    # Pages
    if page == "General KPIs":
        st.title("📊 General Key Performance Indicators")
        st.markdown("---")

        total_bookings = len(filtered_df)
        successful_bookings = len(filtered_df[filtered_df['booking_status'] == 'Completed'])
        total_revenue = filtered_df['booking_value'].sum()
        success_rate = (successful_bookings / total_bookings) * 100 if total_bookings > 0 else 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Bookings", f"{total_bookings:,}")
        k2.metric("Successful Trips", f"{successful_bookings:,}")
        k3.metric("Total Revenue", f"${total_revenue:,.0f}")
        k4.metric("Success Rate", f"{success_rate:.1f}%")

        st.markdown("---")
        with st.expander("View Filtered Raw Data"):
            st.dataframe(filtered_df.head(100))

    elif page == "Visual Charts":
        st.title("📈 Analytical Charts")
        st.markdown("---")

        tab_dist, tab_vehicle, tab_time = st.tabs(["General Distributions", "Vehicle Analysis", "Time Analysis"])

        with tab_dist:
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Payment Methods")
                payment_counts = filtered_df['payment_method'].value_counts().reset_index()
                payment_counts.columns = ['Payment Method', 'Count']
                fig_pie = px.pie(
                    payment_counts,
                    values='Count',
                    names='Payment Method',
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                st.plotly_chart(fig_pie, use_container_width=True)

            with col2:
                st.subheader("Cancellation Reasons")
                cancelled_df = filtered_df[filtered_df['booking_status'].str.contains('Cancelled', case=False, na=False)]
                if not cancelled_df.empty:
                    cancel_counts = cancelled_df['booking_status'].value_counts().reset_index()
                    cancel_counts.columns = ['Reason', 'Count']
                    fig_cancel = px.pie(
                        cancel_counts,
                        values='Count',
                        names='Reason',
                        hole=0.4,
                        color_discrete_sequence=px.colors.qualitative.Set3
                    )
                    st.plotly_chart(fig_cancel, use_container_width=True)
                else:
                    st.info("No cancelled trips in the selected range.")

        with tab_vehicle:
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Total Trips by Vehicle")
                vehicle_counts = filtered_df['vehicle_type'].value_counts().reset_index()
                vehicle_counts.columns = ['Vehicle Type', 'Count']
                fig_bar = px.bar(
                    vehicle_counts,
                    x='Vehicle Type',
                    y='Count',
                    color='Vehicle Type',
                    text='Count',
                    title="Number of Trips"
                )
                st.plotly_chart(fig_bar, use_container_width=True)

            with col2:
                st.subheader("Average Rating by Vehicle")
                rating_avg = filtered_df.groupby('vehicle_type')['customer_rating'].mean().reset_index()
                rating_avg.columns = ['Vehicle Type', 'Avg Rating']
                fig_rating = px.bar(
                    rating_avg,
                    x='Vehicle Type',
                    y='Avg Rating',
                    color='Vehicle Type',
                    text_auto='.1f',
                    title="Average Customer Rating (0-5)",
                    color_discrete_sequence=px.colors.qualitative.Vivid
                )
                fig_rating.update_yaxes(range=[0, 5.5])
                st.plotly_chart(fig_rating, use_container_width=True)

        with tab_time:
            subtab1, subtab2 = st.tabs(["Rush Hour", "Weekly Trends"])

            with subtab1:
                if 'hour' in filtered_df.columns and not filtered_df['hour'].isnull().all():
                    hourly_counts = filtered_df.groupby('hour').size().reset_index(name='Count')
                    fig_line_hour = px.line(
                        hourly_counts,
                        x='hour',
                        y='Count',
                        markers=True,
                        title="Peak Hours Analysis"
                    )
                    st.plotly_chart(fig_line_hour, use_container_width=True)
                else:
                    st.warning("Hour data not available.")

            with subtab2:
                if 'day_name' in filtered_df.columns and not filtered_df['day_name'].isnull().all():
                    days_order = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
                    filtered_df['day_name'] = pd.Categorical(filtered_df['day_name'], categories=days_order, ordered=True)
                    daily_counts = filtered_df.groupby('day_name').size().reset_index(name='Count')
                    fig_line_day = px.line(
                        daily_counts,
                        x='day_name',
                        y='Count',
                        markers=True,
                        title="Weekly Traffic Trends"
                    )
                    st.plotly_chart(fig_line_day, use_container_width=True)
                else:
                    st.warning("Day name data not available.")

    elif page == "AI Assistant (Text-to-SQL)":
        st.title("🤖 Uber AI Assistant")
        st.markdown("Ask questions in **English** about the data, and the AI will generate and run the SQL for you.")
        st.markdown("---")

        user_query = st.text_input("💬 Ask your question here:", placeholder="e.g., Delete all trips")

        if user_query:
            forbidden_input = ["DROP", "DELETE", "UPDATE", "INSERT", "TRUNCATE", "ALTER"]
            if any(word in user_query.upper() for word in forbidden_input):
                st.error("Security Alert: Malicious command detected.")
            else:
                with st.spinner("Thinking & Generating SQL..."):
                    raw_sql, success = get_ai_response(user_query)

                    if success:
                        final_sql, msg = validate_and_fix_sql(raw_sql)

                        if final_sql:
                            st.code(final_sql, language="sql")

                            result_df, err = run_custom_query(final_sql)

                            if err:
                                st.error(f"SQL Execution Error: {err}")
                            elif result_df is not None and not result_df.empty:
                                if result_df.iloc[0, 0] is None:
                                    st.warning("Result is NULL. Try adding more data.")
                                else:
                                    st.success("Query executed successfully!")
                                    st.dataframe(result_df)
                            else:
                                st.warning("Query executed but returned no results.")
                        else:
                            st.error(msg)
                    else:
                        st.error(f"AI Error: {raw_sql}")

    elif page == "Semantic Search (Cancellations)":
        st.title("🔎 Semantic Search - Cancellation Reasons")
        st.markdown("---")

        colA, colB, colC = st.columns([1.2, 1.2, 2])

        with colA:
            if st.button("🧱 Build/Update Vector Index"):
                with st.spinner("Building Chroma index (dedup by reason)..."):
                    n = build_reason_index_dedup()
                st.success(f"Indexed {n} unique reasons ")

        with colB:
            if st.button("🗑️ Reset Index"):
                reset_chroma_collection()
                st.success("Index cleared. Build again ")

        with colC:
            st.info(f"Quality threshold: sim ≥ {MIN_SIM} (tune MIN_SIM in code)")

        query_text = st.text_input(
            "✍️ Type cancellation reason text:",
            placeholder="e.g., driver not found / driver didn't arrive"
        )

        top_k = st.slider("Top-K", 1, 10, 5)
        examples_k = st.slider("Examples per reason", 1, 10, 3)

        if st.button("🔍 Search"):
            if not query_text.strip():
                st.warning("Please enter a search text.")
            else:
                with st.spinner("Searching..."):
                    matches = semantic_search_reasons(query_text, top_k=top_k)

                if not matches:
                    st.warning("No strong matches found. Try a clearer query.")
                else:
                    df_matches = pd.DataFrame([{
                        "rank": m["rank"],
                        "reason": m["reason"],
                        "sim": round(m["sim"], 4) if m["sim"] is not None else None,
                        "distance": round(m["distance"], 4) if m["distance"] is not None else None,
                        "quality": label_quality(m["sim"]),
                        "count": m["count"],
                        "sample_trip_id": m["sample_trip_id"],
                    } for m in matches])

                    st.subheader("Top Matches")
                    st.dataframe(df_matches, use_container_width=True)

                    st.subheader("Examples from Database")
                    for m in matches:
                        with st.expander(f"#{m['rank']} | {label_quality(m['sim'])} | sim={m['sim']:.3f} | {m['reason']}"):
                            ex_df = fetch_examples_for_reason(m["reason"], limit=examples_k)
                            if ex_df.empty:
                                st.info("No examples found.")
                            else:
                                st.dataframe(ex_df, use_container_width=True)

else:
    st.warning("No data found in DB.")
