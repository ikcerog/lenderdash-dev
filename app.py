import streamlit as st
import pandas as pd
import plotly.express as px
import feedparser
import requests
import io
import re
from datetime import datetime

# --- CONFIG & STYLING ---
st.set_page_config(page_title="Mortgage & Leadership Intel", layout="wide", initial_sidebar_state="expanded")

# Fixed: changed unsafe_allow_stdio to unsafe_allow_html
st.markdown("""
    <style>
    .stMetric { background-color: #1e1e1e; padding: 10px; border-radius: 5px; border: 1px solid #333; }
    .stExpander { border: 1px solid #444 !important; }
    </style>
""", unsafe_allow_html=True)

st.title("🏦 Mortgage & Leadership Command Center")

# --- GLOBAL SEARCH ---
st.sidebar.title("🔍 Search Intelligence")
search_query = st.sidebar.text_input("Filter all news & podcasts:", placeholder="e.g. 'Rocket', 'AI', 'Jamie Dimon'").lower()

# --- FRED DATA ENGINE (Mortgage Rates) ---
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

# --- CONTENT ENGINE ---
def fetch_and_filter(url, query, limit=10):
    try:
        feed = feedparser.parse(url)
        entries = []
        for entry in feed.entries:
            title = entry.get('title', '')
            summary = entry.get('summary', '')
            if query in title.lower() or query in summary.lower():
                entries.append(entry)
        return entries[:limit]
    except: return []

def parse_guest(title):
    patterns = [
        r"^(?:#\d+[:\s]+)?([^|:—-]+)", # Before separators
        r"with\s+([^|:—-]+)",          # After 'with'
        r"ft\.\s+([^|:—-]+)"           # After 'ft.'
    ]
    for p in patterns:
        match = re.search(p, title)
        if match:
            clean = match.group(1).strip()
            return clean if len(clean) > 3 else title[:30]
    return title[:40]

# --- SOURCES ---
PODCASTS = {
    "Diary of a CEO": "https://rss2.flightcast.com/xmsftuzjjykcmqwolaqn6mdn",
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

# --- DASHBOARD LAYOUT ---
data = get_mortgage_data()
if not data.empty:
    m1, m2, m3 = st.columns(3)
    curr, prev = data.iloc[-1], data.iloc[-2]
    m1.metric("30Y Fixed", f"{curr['30Y Fixed']}%", f"{round(curr['30Y Fixed']-prev['30Y Fixed'], 3)}%")
    m2.metric("15Y Fixed", f"{curr['15Y Fixed']}%", f"{round(curr['15Y Fixed']-prev['15Y Fixed'], 3)}%")
    m3.metric("10Y Treasury", f"{curr['10Y Treasury']}%", f"{round(curr['10Y Treasury']-prev['10Y Treasury'], 3)}%")
    st.plotly_chart(px.line(data, y=data.columns, template="plotly_dark", height=350), use_container_width=True)

st.divider()

t1, t2, t3 = st.tabs(["🎙️ Podcast Guest Tracker", "🏢 Competitors (Rocket/UWM)", "📰 Industry News"])

with t1:
    st.info("Varun's Pursuit List: Tracking the last 10 guests across elite shows.")
    p_cols = st.columns(2)
    for idx, (name, rss) in enumerate(PODCASTS.items()):
        col = p_cols[idx % 2]
        with col.expander(f"🎧 {name}", expanded=True if search_query else False):
            episodes = fetch_and_filter(rss, search_query)
            if not episodes: st.write("No matches found.")
            for ep in episodes:
                guest = parse_guest(ep.title)
                st.markdown(f"👤 **{guest}** — [Link]({ep.link})")
                st.caption(f"{ep.get('published', '')[:16]} | {ep.title[:60]}...")

with t2:
    comp_feeds = {
        "Rocket Mortgage (HW)": "https://www.housingwire.com/tag/rocket-mortgage/feed/",
        "Rocket Companies (Press)": "https://www.rocketcompanies.com/feed/?post_type=press_release",
        "UWM (BusinessWire)": "https://feed.businesswire.com/rss/home/company/United+Wholesale+Mortgage%2C+LLC/w6euAGJXjezVpz22AaGCsA=="
    }
    for label, url in comp_feeds.items():
        st.subheader(label)
        for item in fetch_and_filter(url, search_query, limit=5):
            st.markdown(f"🔹 **[{item.title}]({item.link})**")

with t3:
    industry = {
        "National Mortgage News": "https://www.nationalmortgagenews.com/feed?rss=true",
        "Mortgage News Daily": "http://www.mortgagenewsdaily.com/rss/news"
    }
    for label, url in industry.items():
        st.subheader(label)
        for item in fetch_and_filter(url, search_query, limit=5):
            st.markdown(f"🗞️ **[{item.title}]({item.link})**")
            st.caption(item.get('published', ''))

st.sidebar.markdown(f"--- \n**System Status:** 🟢 Online \n**Last Sync:** {datetime.now().strftime('%H:%M:%S')}")
