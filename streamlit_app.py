import os
import json
import time
import pandas as pd
import streamlit as st
import plotly.express as px

# Import scraping, analysis and email modules
from phase1_data_collection import scraper
from phase2_analysis_and_report import analyzer, email_service

# Page Config
st.set_page_config(
    page_title="Spotify Growth - User Review Insights",
    page_icon="🟢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Spotify Dark Green Theme
st.markdown("""
<style>
    /* Hide header decorations */
    header {visibility: hidden;}
    
    /* Main App Background and text style overrides */
    .stApp {
        background-color: #121212 !important;
        color: #FFFFFF !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    
    /* Sidebar Overrides */
    [data-testid="stSidebar"] {
        background-color: #000000 !important;
        border-right: 1px solid #282828 !important;
    }
    
    /* Sidebar element text colors */
    [data-testid="stSidebar"] * {
        color: #FFFFFF !important;
    }
    
    /* Card panel container */
    .card-panel {
        background-color: #181818;
        border: 1px solid #282828;
        border-radius: 8px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.25);
    }
    
    /* Metric Card Styling */
    [data-testid="metric-container"] {
        background-color: #181818 !important;
        border: 1px solid #282828 !important;
        padding: 16px 20px !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15) !important;
        transition: transform 0.25s ease, background-color 0.25s ease;
    }
    [data-testid="metric-container"]:hover {
        transform: translateY(-4px);
        background-color: #242424 !important;
        border-color: #383838 !important;
    }
    
    /* Metric Labels */
    [data-testid="metric-container"] label {
        color: #B3B3B3 !important;
        font-size: 11px !important;
        text-transform: uppercase !important;
        letter-spacing: 0.8px !important;
        font-weight: 700 !important;
    }
    
    /* Metric Values */
    [data-testid="metric-container"] div[data-testid="stMetricValue"] {
        font-size: 28px !important;
        font-weight: 800 !important;
        color: #FFFFFF !important;
        letter-spacing: -0.5px !important;
    }

    /* Spotify Green primary buttons */
    div.stButton > button {
        background-color: #1DB954 !important;
        color: #000000 !important;
        font-weight: 700 !important;
        border-radius: 20px !important;
        border: none !important;
        padding: 8px 24px !important;
        transition: all 0.2s ease !important;
    }
    div.stButton > button:hover {
        background-color: #1ed760 !important;
        transform: scale(1.02) !important;
        color: #000000 !important;
    }
    div.stButton > button:active {
        transform: scale(0.98) !important;
    }
    
    /* Selectboxes and inputs background override */
    div[data-baseweb="select"] > div, 
    div[data-baseweb="input"] input, 
    div[data-baseweb="textarea"] textarea {
        background-color: #282828 !important;
        border-color: #3e3e3e !important;
        color: #FFFFFF !important;
    }
    
    /* Text Input focus border */
    div[data-baseweb="input"]:focus-within {
        border-color: #1DB954 !important;
    }
    
    /* Chat history scrollbar adjustment */
    .stChatMessage {
        background-color: rgba(255, 255, 255, 0.03) !important;
        border: 1px solid #282828 !important;
        border-radius: 8px !important;
        padding: 12px 16px !important;
        margin-bottom: 12px !important;
    }
    
    /* Link styling */
    a {
        color: #1DB954 !important;
        text-decoration: none !important;
    }
    a:hover {
        text-decoration: underline !important;
    }
</style>
""", unsafe_allow_html=True)

# Helper functions for config management
def load_config() -> dict:
    # 1. Load config.json as base configuration if it exists
    config_data = {}
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                saved = json.load(f)
                config_data = {k: v.strip() if isinstance(v, str) else v for k, v in saved.items()}
        except Exception as e:
            print(f"[Streamlit] Error loading configuration: {str(e)}")

    # 2. Allow environment variables (Streamlit Secrets) to overwrite base values
    keys = ["groq_api_key", "groq_model", "smtp_host", "smtp_port", "smtp_username", "smtp_password", "smtp_sender_email"]
    defaults = {
        "groq_api_key": "",
        "groq_model": "llama-3.3-70b-versatile",
        "smtp_host": "",
        "smtp_port": "587",
        "smtp_username": "",
        "smtp_password": "",
        "smtp_sender_email": ""
    }
    
    for k in keys:
        # Check both uppercase (Streamlit Secrets standard) and lowercase
        env_val = os.environ.get(k.upper()) or os.environ.get(k)
        if env_val:
            config_data[k] = env_val.strip()
        elif k not in config_data:
            config_data[k] = defaults[k]
            
    return config_data

def save_config(config: dict):
    try:
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"[Streamlit] Error saving configuration: {str(e)}")

# Helper functions for database management
def load_db() -> list:
    DB_FILE = os.environ.get("REVIEWS_DB_PATH", "reviews_db.json")
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Streamlit] Error loading database: {str(e)}")
    mock_data = scraper.load_mock_data()
    if mock_data:
        save_db(mock_data)
        return mock_data
    return []

def save_db(data: list):
    DB_FILE = os.environ.get("REVIEWS_DB_PATH", "reviews_db.json")
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Streamlit] Error saving database: {str(e)}")

# Calculate Stats
def get_stats(db: list) -> dict:
    total = len(db)
    analyzed = [r for r in db if r.get("analysis_status") == "analyzed"]
    analyzed_count = len(analyzed)
    pending_count = sum(1 for r in db if r.get("analysis_status") == "pending")
    
    sentiments = {"Positive": 0, "Neutral": 0, "Negative": 0}
    categories = {}
    pain_points = {}
    discovery_issues_count = 0
    
    for r in analyzed:
        analysis = r.get("analysis") or {}
        sent = analysis.get("sentiment", "Neutral")
        sentiments[sent] = sentiments.get(sent, 0) + 1
        
        cat = analysis.get("category", "Other")
        categories[cat] = categories.get(cat, 0) + 1
        
        pain = analysis.get("pain_point", "N/A")
        if pain and pain != "N/A" and pain != "Error performing analysis":
            pain_points[pain] = pain_points.get(pain, 0) + 1
            
        if analysis.get("discovery_issue") is True:
            discovery_issues_count += 1
            
    sorted_pain_points = sorted(pain_points.items(), key=lambda x: x[1], reverse=True)[:5]
    top_pain_points = [{"pain_point": k, "count": v} for k, v in sorted_pain_points]
    
    play_store_ratings = [r["rating"] for r in db if r["source"] == "play_store" and r.get("rating") is not None]
    avg_rating = round(sum(play_store_ratings) / len(play_store_ratings), 2) if play_store_ratings else None
    
    discovery_ratio = round((discovery_issues_count / analyzed_count) * 100, 1) if analyzed_count > 0 else 0.0
    
    return {
        "total_count": total,
        "analyzed_count": analyzed_count,
        "pending_count": pending_count,
        "average_rating": avg_rating,
        "discovery_issues_count": discovery_issues_count,
        "discovery_ratio": discovery_ratio,
        "sentiments": sentiments,
        "categories": categories,
        "top_pain_points": top_pain_points
    }

# Dynamic Scraper Callback
def make_scraper_callback(progress_bar, status_text, limit):
    def callback(current, total):
        pct = min(1.0, current / limit)
        progress_bar.progress(pct)
        status_text.text(f"Downloaded {current} / {limit} entries...")
    return callback

# Load Config & DB
config = load_config()
db = load_db()

# Initialize Session State
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        {
            "role": "assistant",
            "content": "Hello! I am your Spotify Growth Assistant. I can synthesize insights from your reviews database. Select a research question on the left or type your custom query below."
        }
    ]

if "cached_report_html" not in st.session_state:
    if os.path.exists("cached_report.html"):
        try:
            with open("cached_report.html", "r", encoding="utf-8") as f:
                st.session_state.cached_report_html = f.read()
        except Exception:
            st.session_state.cached_report_html = ""
    else:
        st.session_state.cached_report_html = ""

# Sidebar Branding
st.sidebar.markdown(
    """
    <div style="display: flex; align-items: center; gap: 12px; padding: 10px 0; margin-bottom: 20px;">
        <span style="font-size: 24px;">🟢</span>
        <span style="font-size: 20px; font-weight: 800; color: #FFFFFF; letter-spacing: -0.5px;">Spotify Insights</span>
    </div>
    """,
    unsafe_allow_html=True
)

tab = st.sidebar.radio(
    "Navigation",
    options=["Dashboard", "Review Explorer", "AI Product Assistant", "Growth Reports", "Settings & Ingestion"],
    label_visibility="collapsed"
)

# Groq Config status in sidebar footer
config_status = "Configured" if config.get("groq_api_key") else "Not Configured"
dot_color = "#1DB954" if config.get("groq_api_key") else "#e91429"
st.sidebar.markdown("---")
st.sidebar.markdown(
    f"""
    <div style="display: flex; align-items: center; gap: 8px; font-size: 12px; color: #B3B3B3; font-weight: 500; margin-top: 10px;">
        <span style="width: 8px; height: 8px; border-radius: 50%; background-color: {dot_color}; display: inline-block; box-shadow: 0 0 8px {dot_color};"></span>
        <span>Groq {config_status}</span>
    </div>
    """,
    unsafe_allow_html=True
)

# Header Row
top_col1, top_col2 = st.columns([4, 1])
with top_col1:
    st.title(f"Growth {tab}" if tab == "Dashboard" else tab)
with top_col2:
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 12px; justify-content: flex-end; margin-top: 15px;">
            <span style="font-size: 13px; color: #B3B3B3; font-weight: 500;">Growth Product Team</span>
            <div style="width: 32px; height: 32px; border-radius: 50%; background-color: #282828; display: flex; align-items: center; justify-content: center; color: #B3B3B3; font-size: 14px;">👤</div>
        </div>
        """,
        unsafe_allow_html=True
    )
st.markdown("---")

# Main Content Routing
if tab == "Dashboard":
    stats = get_stats(db)
    
    # Metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Ingested Feedback", stats["total_count"])
    m2.metric("AI Analyzed Reviews", stats["analyzed_count"])
    m3.metric("Discovery Frustration Ratio", f"{stats['discovery_ratio']}%")
    m4.metric("Avg Play Store Rating", stats["average_rating"] if stats["average_rating"] is not None else "N/A")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Charts
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="card-panel">', unsafe_allow_html=True)
        st.subheader("Sentiment Distribution")
        sent_dict = stats["sentiments"]
        
        if stats["analyzed_count"] > 0:
            sent_df = pd.DataFrame({
                "Sentiment": list(sent_dict.keys()),
                "Count": list(sent_dict.values())
            })
            
            fig_sent = px.pie(
                sent_df,
                names="Sentiment",
                values="Count",
                hole=0.5,
                color="Sentiment",
                color_discrete_map={
                    "Positive": "#2ebd59",
                    "Neutral": "#a0a0a0",
                    "Negative": "#e91429"
                }
            )
            fig_sent.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color='#FFFFFF',
                margin=dict(t=20, b=20, l=10, r=10),
                legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5)
            )
            st.plotly_chart(fig_sent, use_container_width=True)
        else:
            st.info("No analyzed reviews. Seed mock data or scrape to populate sentiment metrics.")
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="card-panel">', unsafe_allow_html=True)
        st.subheader("Common Feedback Categories")
        cat_dict = stats["categories"]
        
        # Filter categories with 0 values
        active_cats = {k: v for k, v in cat_dict.items() if v > 0}
        
        if active_cats:
            cat_df = pd.DataFrame({
                "Category": list(active_cats.keys()),
                "Count": list(active_cats.values())
            }).sort_values(by="Count", ascending=True)
            
            fig_cat = px.bar(
                cat_df,
                x="Count",
                y="Category",
                orientation="h",
                color_discrete_sequence=["#1DB954"]
            )
            fig_cat.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color='#FFFFFF',
                margin=dict(t=20, b=20, l=10, r=10),
                xaxis=dict(gridcolor='#282828', showgrid=True),
                yaxis=dict(gridcolor='#282828')
            )
            st.plotly_chart(fig_cat, use_container_width=True)
        else:
            st.info("No categorized reviews. Seed mock data or analyze pending reviews to populate charts.")
        st.markdown('</div>', unsafe_allow_html=True)

    # Pain Points Panel
    st.markdown('<div class="card-panel">', unsafe_allow_html=True)
    st.subheader("Recurring User Pain Points (LLM Tagged)")
    if stats["top_pain_points"]:
        pain_html = ""
        for item in stats["top_pain_points"]:
            pain_html += f"""
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background-color: rgba(255,255,255,0.02); border-radius: 6px; border-left: 4px solid #1DB954; border: 1px solid #282828; margin-bottom: 12px;">
                <span style="font-size: 14px; font-weight: 600; color: #FFFFFF;">{item['pain_point']}</span>
                <span style="font-size: 12px; font-weight: 700; color: #1DB954; background-color: rgba(29, 185, 84, 0.1); padding: 4px 8px; border-radius: 12px;">{item['count']} occurrences</span>
            </div>
            """
        st.markdown(pain_html, unsafe_allow_html=True)
    else:
        st.info("No pain points tagged. Classify pending reviews under 'Review Explorer' to extract pain points.")
    st.markdown('</div>', unsafe_allow_html=True)

elif tab == "Review Explorer":
    st.markdown('<div class="card-panel">', unsafe_allow_html=True)
    st.subheader("Filter Controls")
    
    # Filters Layout
    f_col1, f_col2, f_col3, f_col4 = st.columns(4)
    with f_col1:
        source_filter = st.selectbox("Platform Source", options=["All Platforms", "Google Play Store", "Reddit Discussions", "Spotify Forums"])
    with f_col2:
        sentiment_filter = st.selectbox("Sentiment", options=["All Sentiments", "Positive", "Neutral", "Negative"])
    with f_col3:
        category_filter = st.selectbox("Theme/Category", options=[
            "All Categories",
            "Algorithm Frustration",
            "Playlist Management",
            "UI/UX",
            "Repeat Listening",
            "Music Discovery",
            "Other"
        ])
    with f_col4:
        discovery_filter = st.selectbox("Discovery Issue?", options=["All Reviews", "Discovery Issues Only", "Non-Discovery Reviews"])

    search_filter = st.text_input("Search Text", placeholder="Type keyword to filter review contents...")

    # Filter actions row
    act_col1, act_col2, act_col3 = st.columns([1, 1, 2])
    with act_col1:
        reset_clicked = st.button("Reset Filters", use_container_width=True)
    with act_col2:
        refresh_clicked = st.button("Refresh Reviews", use_container_width=True)
    with act_col3:
        pending_count = len([r for r in db if r.get("analysis_status", "pending") == "pending"])
        analyze_pending_clicked = st.button(f"Analyze Pending ({pending_count})", use_container_width=True)

    # Progress Area inside Filter Panel
    progress_placeholder = st.empty()
    st.markdown('</div>', unsafe_allow_html=True)

    # Reset trigger logic
    if reset_clicked:
        st.rerun()
    if refresh_clicked:
        st.rerun()

    # Trigger LLM Analysis in Streamlit Loop
    if analyze_pending_clicked:
        if not config.get("groq_api_key"):
            st.error("Groq API Key is not configured in settings. Classifications cannot be performed.")
        else:
            pending = [r for r in db if r.get("analysis_status", "pending") == "pending"]
            if not pending:
                st.info("No pending reviews left to classify.")
            else:
                with progress_placeholder.container():
                    st.write("### AI Bulk Analysis Progress")
                    progress_bar = st.progress(0.0)
                    status_text = st.empty()
                    total_pending = len(pending)
                    
                    for idx, r in enumerate(pending):
                        status_text.text(f"Classifying review {idx + 1} of {total_pending} via Groq...")
                        
                        # Call analyzer module
                        analysis = analyzer.analyze_review(
                            api_key=config["groq_api_key"],
                            model_id=config["groq_model"],
                            review_text=r["content"],
                            source=r["source"],
                            rating=r.get("rating")
                        )
                        
                        r["analysis"] = analysis
                        r["analysis_status"] = "analyzed" if "error" not in analysis else "failed"
                        
                        # Save database progressively
                        save_db(db)
                        
                        # Update progress bar
                        progress_bar.progress((idx + 1) / total_pending)
                        
                        # Mitigate API rate limits
                        time.sleep(0.25)
                        
                    st.success(f"Successfully classified all {total_pending} pending reviews!")
                    time.sleep(0.5)
                    st.rerun()

    # Apply Filter Options
    filtered_reviews = db
    if source_filter != "All Platforms":
        source_map = {
            "Google Play Store": "play_store",
            "Reddit Discussions": "reddit",
            "Spotify Forums": "spotify_forum"
        }
        filtered_reviews = [r for r in filtered_reviews if r["source"] == source_map[source_filter]]

    if sentiment_filter != "All Sentiments":
        filtered_reviews = [r for r in filtered_reviews if (r.get("analysis") or {}).get("sentiment") == sentiment_filter]

    if category_filter != "All Categories":
        filtered_reviews = [r for r in filtered_reviews if (r.get("analysis") or {}).get("category") == category_filter]

    if discovery_filter != "All Reviews":
        disc_val = (discovery_filter == "Discovery Issues Only")
        filtered_reviews = [r for r in filtered_reviews if (r.get("analysis") or {}).get("discovery_issue") is disc_val]

    if search_filter:
        s_val = search_filter.lower()
        filtered_reviews = [r for r in filtered_reviews if s_val in r["content"].lower()]

    st.write(f"### Ingested Reviews Feed ({len(filtered_reviews)} matching)")

    # Pagination
    reviews_per_page = 20
    if "explorer_page" not in st.session_state:
        st.session_state.explorer_page = 0

    total_pages = max(1, (len(filtered_reviews) + reviews_per_page - 1) // reviews_per_page)
    st.session_state.explorer_page = min(st.session_state.explorer_page, total_pages - 1)

    page_reviews = filtered_reviews[st.session_state.explorer_page * reviews_per_page : (st.session_state.explorer_page + 1) * reviews_per_page]

    # Page Controls Row
    col_prev, col_page_num, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("Previous Page", disabled=(st.session_state.explorer_page == 0), key="btn_prev_page"):
            st.session_state.explorer_page -= 1
            st.rerun()
    with col_page_num:
        st.markdown(f"<p style='text-align: center; margin-top: 10px;'>Page {st.session_state.explorer_page + 1} of {total_pages}</p>", unsafe_allow_html=True)
    with col_next:
        if st.button("Next Page", disabled=(st.session_state.explorer_page >= total_pages - 1), key="btn_next_page"):
            st.session_state.explorer_page += 1
            st.rerun()

    # Render Review Cards inside Expanders
    for r in page_reviews:
        source_name = r["source"].upper()
        rating_str = f" ⭐ {r['rating']}/5" if r.get("rating") else ""
        
        analysis = r.get("analysis") or {}
        sentiment = analysis.get("sentiment", "PENDING")
        category = analysis.get("category", "")
        disc_issue = " ⚠️ Discovery Issue" if analysis.get("discovery_issue") else ""
        
        # Color Coding source tags and sentiment tags
        sentiment_badge = f"[{sentiment}]"
        
        # Header Label containing crucial metadata
        header_text = f"[{source_name}{rating_str}] {sentiment_badge} {category}{disc_issue} - \"{r['content'][:60]}...\""
        
        with st.expander(header_text):
            exp_col1, exp_col2 = st.columns(2)
            with exp_col1:
                st.markdown("**Original Review Feedback**")
                st.markdown(f"*{r['content']}*")
                st.markdown(f"<p style='color: #727272; font-size: 11px; margin-top: 12px;'>Author: {r.get('author', 'Anonymous')} | Date: {r.get('timestamp', 'N/A')}</p>", unsafe_allow_html=True)
                st.markdown(f"<a href='{r.get('url', '#')}' target='_blank'>Link to Original Post</a>", unsafe_allow_html=True)
            with exp_col2:
                st.markdown("**AI Insights Classification**")
                status = r.get("analysis_status", "pending")
                if status == "analyzed":
                    st.markdown(f"- **Sentiment**: {sentiment}")
                    st.markdown(f"- **Theme/Category**: {category}")
                    st.markdown(f"- **Executive Summary**: {analysis.get('summary', 'N/A')}")
                    st.markdown(f"- **Primary Pain Point**: {analysis.get('pain_point', 'N/A')}")
                    st.markdown(f"- **Discovery Struggle**: {'Yes' if analysis.get('discovery_issue') else 'No'}")
                    st.markdown(f"- **Analyzed At**: {analysis.get('analyzed_at', 'N/A')}")
                    st.markdown(f"<p style='color: #727272; font-size: 11px;'>Model Used: {analysis.get('model_used', 'N/A')}</p>", unsafe_allow_html=True)
                elif status == "failed":
                    st.error(f"Analysis failed: {analysis.get('error', 'Unknown Error')}")
                else:
                    st.info("Analysis pending. Use 'Analyze Pending' button at the top to classify.")

elif tab == "AI Product Assistant":
    questions_map = {
        "q1": "Why do users struggle to discover new music?",
        "q2": "What are the most common frustrations with Spotify's recommendation system?",
        "q3": "What listening goals or behaviors are users trying to achieve?",
        "q4": "Why do users repeatedly listen to the same playlists, artists, or songs?",
        "q5": "Which user segments face different music discovery challenges?",
        "q6": "What unmet needs consistently emerge across user feedback?",
        "q7": "What product improvement opportunities can be identified from the collected data?"
    }
    
    col1, col2 = st.columns([2, 3])
    
    with col1:
        st.subheader("Research Focus Questions")
        st.write("Select a target query below. Groq LLM will read your reviews database and synthesize a structured response.")
        
        for qid, qtext in questions_map.items():
            if st.button(f"{qid.upper()}: {qtext}", key=f"btn_qa_{qid}", use_container_width=True):
                if not config.get("groq_api_key"):
                    st.error("Groq API Key is not configured. Please add it in Settings & Ingestion.")
                else:
                    with st.spinner("Synthesizing answer from review corpus..."):
                        answer = analyzer.synthesize_key_questions(
                            api_key=config["groq_api_key"],
                            model_id=config["groq_model"],
                            reviews=db,
                            question_id=qid
                        )
                        st.session_state.chat_history.append({"role": "user", "content": qtext})
                        st.session_state.chat_history.append({"role": "assistant", "content": answer})
                        st.rerun()

    with col2:
        st.subheader("AI Synthesis Terminal")
        
        # Chat container scroll wrapper
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                
        user_query = st.chat_input("Ask custom synthesis questions (e.g. 'What do Play Store users think of the UI?')...")
        if user_query:
            if not config.get("groq_api_key"):
                st.error("Groq API Key is not configured.")
            else:
                st.session_state.chat_history.append({"role": "user", "content": user_query})
                with st.spinner("Synthesizing custom answer..."):
                    answer = analyzer.synthesize_key_questions(
                        api_key=config["groq_api_key"],
                        model_id=config["groq_model"],
                        reviews=db,
                        question_id=user_query
                    )
                    st.session_state.chat_history.append({"role": "assistant", "content": answer})
                st.rerun()

elif tab == "Growth Reports":
    col1, col2 = st.columns([2, 3])
    
    with col1:
        st.subheader("Report Generation Console")
        st.write("Compile an AI-powered Executive One-Page Report analyzing behaviors and opportunities.")
        
        if st.button("Generate One-Page Summary Report", use_container_width=True):
            if not config.get("groq_api_key"):
                st.error("Groq API Key is not configured.")
            else:
                with st.spinner("Compiling insights and generating report html..."):
                    try:
                        html_report = analyzer.generate_one_page_summary(
                            api_key=config["groq_api_key"],
                            model_id=config["groq_model"],
                            reviews=db
                        )
                        # Cache locally
                        with open("cached_report.html", "w", encoding="utf-8") as f:
                            f.write(html_report)
                        st.session_state.cached_report_html = html_report
                        st.success("Report generated and cached successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to generate report: {str(e)}")
                        
        st.markdown("---")
        
        # Email sharing block
        st.subheader("Email Dispatcher")
        st.write("Send the generated report directly to stakeholders.")
        
        recipient_email = st.text_input("Recipient Email(s)", placeholder="team@spotify.com (comma separated)")
        subject_input = st.text_input("Subject", value="Spotify Growth Insights Report")
        note_input = st.text_area("Personalized Message", value="Hey team, here is the fresh reviews summary showing recommendations pain points. Let me know your thoughts.", height=100)
        
        # Dispatch button
        has_cached = bool(st.session_state.cached_report_html)
        send_clicked = st.button("Send Report via Email", disabled=not has_cached, use_container_width=True)
        
        if send_clicked:
            smtp_config = {
                "host": config["smtp_host"],
                "port": config["smtp_port"],
                "username": config["smtp_username"],
                "password": config["smtp_password"],
                "sender_email": config["smtp_sender_email"]
            }
            with st.spinner("Dispatching email..."):
                try:
                    result = email_service.send_html_email(
                        smtp_config=smtp_config,
                        recipient_email=recipient_email,
                        subject=subject_input,
                        html_content=st.session_state.cached_report_html,
                        personalized_note=note_input
                    )
                    if result.get("success"):
                        if result.get("simulation"):
                            st.info(f"📧 **Simulation Mode Active**: SMTP credentials are not fully configured. Email was saved locally to: `{result.get('log_file')}`.")
                        else:
                            st.success(f"📧 Email sent successfully to {', '.join(result.get('recipients'))}!")
                    else:
                        st.error("Failed to send email.")
                except Exception as e:
                    st.error(f"Email delivery failed: {str(e)}")

    with col2:
        st.subheader("One-Pager Summary Preview")
        
        if st.session_state.cached_report_html:
            # HTML Preview container
            st.components.v1.html(st.session_state.cached_report_html, height=600, scrolling=True)
            
            # Raw HTML view
            st.markdown("---")
            with st.expander("Show Raw HTML Source"):
                st.code(st.session_state.cached_report_html, language="html")
        else:
            st.info("No report generated yet. Click 'Generate One-Page Summary Report' in the console to compile insights.")

elif tab == "Settings & Ingestion":
    col_api, col_smtp = st.columns(2)
    with col_api:
        st.markdown('<div class="card-panel">', unsafe_allow_html=True)
        st.subheader("Groq API Settings")
        
        masked_key = ""
        if config.get("groq_api_key"):
            k = config["groq_api_key"]
            masked_key = k[:6] + "..." + k[-4:] if len(k) > 10 else "Configured"
            
        api_key_input = st.text_input("Groq API Key", value=config.get("groq_api_key", ""), type="password", help=f"Currently: {masked_key}" if masked_key else "Not set")
        
        model_selection = st.selectbox("LLM Model", options=[
            "llama-3.3-70b-versatile",
            "llama-3.1-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768"
        ], index=["llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"].index(config.get("groq_model", "llama-3.3-70b-versatile")))
        
        if st.button("Save API Configuration", use_container_width=True, key="btn_save_groq"):
            config["groq_api_key"] = api_key_input.strip()
            config["groq_model"] = model_selection.strip()
            save_config(config)
            st.success("Groq API settings saved!")
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with col_smtp:
        st.markdown('<div class="card-panel">', unsafe_allow_html=True)
        st.subheader("SMTP Email Settings")
        
        smtp_host_input = st.text_input("SMTP Host", value=config.get("smtp_host", ""))
        smtp_port_input = st.text_input("SMTP Port", value=config.get("smtp_port", "587"))
        smtp_user_input = st.text_input("SMTP Username", value=config.get("smtp_username", ""))
        smtp_pass_input = st.text_input("SMTP Password", value=config.get("smtp_password", ""), type="password")
        smtp_sender_input = st.text_input("Sender Email Address", value=config.get("smtp_sender_email", ""))
        
        if st.button("Save SMTP Configuration", use_container_width=True, key="btn_save_smtp"):
            config["smtp_host"] = smtp_host_input.strip()
            config["smtp_port"] = smtp_port_input.strip()
            config["smtp_username"] = smtp_user_input.strip()
            config["smtp_password"] = smtp_pass_input.strip()
            config["smtp_sender_email"] = smtp_sender_input.strip()
            save_config(config)
            st.success("SMTP settings saved!")
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    col_scraper, col_db = st.columns(2)
    with col_scraper:
        st.markdown('<div class="card-panel">', unsafe_allow_html=True)
        st.subheader("Live Review Ingestion")
        
        scrape_source_input = st.selectbox("Ingestion Platform", options=[
            ("play_store", "Google Play Store Reviews (No Auth)"),
            ("reddit", "Reddit Discussions (Search API-less)"),
            ("spotify_forum", "Spotify Forums (BeautifulSoup Scrape)")
        ], format_func=lambda x: x[1])
        
        scrape_limit_input = st.selectbox("Ingestion Limit (Record Count)", options=[10, 20, 50, 100, 500, 1000, 2500, 5000], index=1)
        scrape_query_input = st.text_input("Search Keywords (Reddit & Forum)", value="music discovery")
        
        trigger_scrape = st.button("Trigger Data Ingestion", use_container_width=True)
        
        if trigger_scrape:
            progress_bar = st.progress(0.0)
            status_text = st.empty()
            callback = make_scraper_callback(progress_bar, status_text, scrape_limit_input)
            
            try:
                with st.spinner("Executing review collection loops..."):
                    new_reviews = []
                    source_id = scrape_source_input[0]
                    if source_id == "play_store":
                        new_reviews = scraper.scrape_play_store(limit=scrape_limit_input, progress_callback=callback)
                    elif source_id == "reddit":
                        new_reviews = scraper.scrape_reddit(query=scrape_query_input, limit=scrape_limit_input, progress_callback=callback)
                    elif source_id == "spotify_forum":
                        new_reviews = scraper.scrape_spotify_community(query=scrape_query_input, limit=scrape_limit_input, progress_callback=callback)
                    
                    if new_reviews:
                        # Ingest into database
                        existing_ids = {r["id"] for r in db}
                        added_count = 0
                        for r in new_reviews:
                            if r["id"] not in existing_ids:
                                db.insert(0, r)
                                existing_ids.add(r["id"])
                                added_count += 1
                        
                        if added_count > 0:
                            save_db(db)
                        
                        st.success(f"Ingestion completed. Crawled {len(new_reviews)} reviews. Added {added_count} new unique records.")
                        time.sleep(1.0)
                        st.rerun()
                    else:
                        st.warning("Finished. No reviews were returned by the scraper.")
            except Exception as e:
                st.error(f"Ingestion failed: {str(e)}")
        st.markdown('</div>', unsafe_allow_html=True)

    with col_db:
        st.markdown('<div class="card-panel">', unsafe_allow_html=True)
        st.subheader("Database Operations")
        st.write("Reset and populate the database with realistic sample reviews across Google Play, Reddit and Spotify Community Forums.")
        
        if st.button("Seed/Reset Mock Reviews Database", use_container_width=True, key="btn_reset_mock"):
            mock_reviews = scraper.load_mock_data()
            if mock_reviews:
                save_db(mock_reviews)
                st.success(f"Reviews database reset and seeded with {len(mock_reviews)} mock reviews!")
                time.sleep(1.0)
                st.rerun()
            else:
                st.error("Mock data file could not be read.")
        st.markdown('</div>', unsafe_allow_html=True)
