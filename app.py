import streamlit as st
import pandas as pd
import plotly.express as px
import feedparser
import requests
import io
import re
import urllib.parse
from datetime import datetime

# --- CONFIG & STYLING ---
st.set_page_config(page_title="Mortgage & Media Intelligence", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stMetric { background-color: #1e1e1e; padding: 10px; border-radius: 5px; border: 1px solid #333; }
    .stExpander { border: 1px solid #444 !important; }
    /* Ensure the app doesn't crash on long titles */
    .stExpander p { word-break: break-all; }
    </style>
""", unsafe_allow_html=True)

st.title("🏦 Mortgage & Media Command Center")

# --- GLOBAL SEARCH ---
st.sidebar.title("🔍 Intel Search")
search_query = st.sidebar.text_input("Filter across all feeds:", placeholder="e.g. 'Fed', 'Rates', 'Inventory'").lower()

# --- FRED DATA ENGINE ---
@st.cache_data(ttl=3600)
def get_mortgage_data():
    headers = {"User-Agent": "Mozilla/5.0"}
    urls = {
        "30Y Fixed": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=MORTGAGE30US",
        "15Y Fixed": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=MORTGAGE15US",
        "10Y Treasury": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
    }
    dfs = []
    for name, url in urls.items():
        try:
            r = requests.get(url, headers=headers)
            df = pd.read_csv(io.StringIO(r.text))
            date_col, val_col = df.columns[0], df.columns[1]
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.rename(columns={date_col: 'DATE', val_col: name})
            df[name] = pd.to_numeric(df[name], errors='coerce')
            dfs.append(df.set_index('DATE'))
        except: continue
    return pd.concat(dfs, axis=1).ffill().dropna() if dfs else pd.DataFrame()

# --- CONTENT ENGINES ---
def fetch_and_filter(url, query, limit=8):
    try:
        # User-agent helps prevent some RSS feeds from blocking the request
        feed = feedparser.parse(url, agent='Mozilla/5.0')
        entries = []
        if not feed.entries:
            return []
        for entry in feed.entries:
            title = entry.get('title', '')
            summary = entry.get('summary', '')
            if query in title.lower() or query in summary.lower():
                entries.append(entry)
        return entries[:limit]
    except Exception as e:
        return []

def parse_guest(title):
    patterns = [r"^(?:#\d+[:\s]+)?([^|:—-]+)", r"with\s+([^|:—-]+)", r"ft\.\s+([^|:—-]+)"]
    for p in patterns:
        match = re.search(p, title)
        if match:
            clean = match.group(1).strip()
            return clean if len(clean) > 3 else title[:30]
    return title[:40]

def get_gnews_rss(name, source):
    # This remains the most stable 'hack' for non-RSS publications
    query = f'inauthor:"{name}" source:"{source}"'
    return f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}"

# --- UPDATED SOURCE LISTS ---
PODCASTS = {
    "Diary of a CEO": "https://rss.art19.com/the-diary-of-a-ceo-with-steven-bartlett",
    "Lex Fridman": "https://lexfridman.com/feed/podcast/",
    "Tim Ferriss": "https://rss.art19.com/tim-ferriss-show",
    "All-In": "http://allinchamathjason.libsyn.com/rss",
    "Acquired": "https://feeds.transistor.fm/acquired",
    "Pioneers of AI": "https://feeds.art19.com/pioneers-of-ai",
    "Lenny's Podcast": "https://www.lennysnewsletter.com/feed",
    "TBPN (Tech Brothers)": "https://feeds.transistor.fm/technology-brother",
    "How Leaders Lead": "https://feeds.megaphone.fm/how-leaders-lead",
    "Leadership Next": "https://feeds.megaphone.fm/fortuneleadershipnext"
}

JOURNALISTS = {
    "Nick Timiraos (WSJ)": get_gnews_rss("Nick Timiraos", "The Wall Street Journal"),
    "Gina Heeb (WSJ)": get_gnews_rss("Gina Heeb", "The Wall Street Journal"),
    "Ben Eisen (WSJ)": get_gnews_rss("Ben Eisen", "The Wall Street Journal"),
    "Nicole Friedman (WSJ)": get_gnews_rss("Nicole Friedman", "The Wall Street Journal"),
    "AnnaMaria Andriotis (WSJ)": get_gnews_rss("AnnaMaria Andriotis", "The Wall Street Journal"),
    "Veronica Dagher (WSJ)": get_gnews_rss("Veronica Dagher", "The Wall Street Journal"),
    "Telis Demos (WSJ)": get_gnews_rss("Telis Demos", "The Wall Street Journal"),
    "Nick Manes (Crain's)": "https://www.crainsdetroit.com/author/nick-manes/feed",
    "Sarah Wolak (HW)": "https://www.housingwire.com/author/sarahwolak/feed",
    "Shaina Mishkin (Barron's)": get_gnews_rss("Shaina Mishkin", "Barron's")
}

# --- DASHBOARD RENDER ---
data = get_mortgage_data()
if not data.empty:
    m1, m2, m3 = st.columns(3)
    curr, prev = data.iloc[-1], data.iloc[-2]
    m1.metric("30Y Fixed", f"{curr['30Y Fixed']}%", f"{round(curr['30Y Fixed']-prev['30Y Fixed'], 3)}%")
    m2.metric("15Y Fixed", f"{curr['15Y Fixed']}%", f"{round(curr['15Y Fixed']-prev['15Y Fixed'], 3)}%")
    m3.metric("10Y Treasury", f"{curr['10Y Treasury']}%", f"{round(curr['10Y Treasury']-prev['10Y Treasury'], 3)}%")
    st.plotly_chart(px.line(data, y=data.columns, template="plotly_dark", height=300), use_container_width=True)

st.divider()

tabs = st.tabs(["🎙️ Podcast Guest Tracker", "🖋️ Journalist Feed", "🏢 Competitors", "🗞️ Industry News"])

with tabs[0]:
    st.info("Tracking recent guests and episode intelligence across target shows.")
    cols = st.columns(2)
    # We loop through all podcasts; if one fails, the loop continues to the next
    for idx, (name, rss) in enumerate(PODCASTS.items()):
        col = cols[idx % 2]
        with col.expander(f"🎧 {name}", expanded=True if search_query else False):
            try:
                eps = fetch_and_filter(rss, search_query)
                if not eps:
                    st.write("No episodes found or feed unavailable.")
                for e in eps:
                    # Logic Fix: Use .get() to prevent AttributeError
                    link = e.get('link', '#')
                    title = e.get('title', 'Untitled Episode')
                    guest = parse_guest(title)
                    st.markdown(f"👤 **{guest}** — [Link]({link})")
                    st.caption(f"{e.get('published', '')[:16]}")
            except:
                st.error(f"Error loading {name}")

with tabs[1]:
    st.info("Direct and Search-Aggregated feeds for elite financial reporters.")
    cols = st.columns(2)
    for idx, (name, rss) in enumerate(JOURNALISTS.items()):
        with cols[idx % 2].expander(f"🖋️ {name}"):
            try:
                articles = fetch_and_filter(rss, search_query)
                if not articles: st.write("No matches found.")
                for a in articles:
                    link = a.get('link', '#')
                    st.markdown(f"📄 **[{a.get('title', 'Article')}]({link})**")
                    st.caption(f"{a.get('published', '')[:16]}")
            except:
                st.error(f"Error loading {name}")

with tabs[2]:
    comps = {
        "Rocket Mortgage (HW)": "https://www.housingwire.com/tag/rocket-mortgage/feed/",
        "Rocket Co (Press)": "https://www.rocketcompanies.com/feed/?post_type=press_release",
        "UWM (Updates)": "https://feed.businesswire.com/rss/home/company/United+Wholesale+Mortgage%2C+LLC/w6euAGJXjezVpz22AaGCsA=="
    }
    for label, url in comps.items():
        st.subheader(label)
        items = fetch_and_filter(url, search_query, limit=4)
        for item in items:
            st.markdown(f"🔹 **[{item.get('title', 'News')}]({item.get('link', '#')})**")

with tabs[3]:
    industry = {
        "National Mortgage News": "https://www.nationalmortgagenews.com/feed?rss=true",
        "Mortgage News Daily": "http://www.mortgagenewsdaily.com/rss/news"
    }
    for label, url in industry.items():
        st.subheader(label)
        items = fetch_and_filter(url, search_query, limit=4)
        for item in items:
            st.markdown(f"🗞️ **[{item.get('title', 'Article')}]({item.get('link', '#')})**")

st.sidebar.markdown(f"--- \n**Last Sync:** {datetime.now().strftime('%H:%M:%S')}")
