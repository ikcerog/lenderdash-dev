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
    </style>
""", unsafe_allow_html=True)

st.title("🏦 Mortgage & Media Command Center")

# --- GLOBAL SEARCH ---
st.sidebar.title("🔍 Intel Search")
search_query = st.sidebar.text_input("Filter across all feeds:", placeholder="e.g. 'Fed', 'Inventory', 'Altman'").lower()

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
    patterns = [r"^(?:#\d+[:\s]+)?([^|:—-]+)", r"with\s+([^|:—-]+)", r"ft\.\s+([^|:—-]+)"]
    for p in patterns:
        match = re.search(p, title)
        if match:
            clean = match.group(1).strip()
            return clean if len(clean) > 3 else title[:30]
    return title[:40]

def get_gnews_rss(name, source):
    # Pro-tip hack for WSJ/Barron's authors
    query = f'inauthor:"{name}" source:"{source}"'
    return f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}"

# --- SOURCE DIRECTORIES ---
PODCASTS = {
    "Diary of a CEO": "https://rss2.flightcast.com/xmsftuzjjykcmqwolaqn6mdn",
    "Lex Fridman": "https://lexfridman.com/feed/podcast/",
    "Tim Ferriss": "https://rss.art19.com/tim-ferriss-show",
    "All-In": "http://allinchamathjason.libsyn.com/rss",
    "Acquired": "https://feeds.transistor.fm/acquired",
    "Pioneers of AI": "https://feeds.art19.com/pioneers-of-ai",
    "Lenny's Podcast": "https://www.lennysnewsletter.com/feed",
    "TBPN": "https://feeds.transistor.fm/technology-brother",
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
    "Robyn Friedman (WSJ)": get_gnews_rss("Robyn Friedman", "The Wall Street Journal"),
    "Tara Siegel Bernard (NYT)": "https://www.nytimes.com/svc/collections/v1/publish/www.nytimes.com/by/tara-siegel-bernard/rss.xml",
    "Nick Manes (Crain's)": "https://www.crainsdetroit.com/author/nick-manes/feed",
    "Sarah Wolak (HW)": "https://www.housingwire.com/author/sarahwolak/feed",
    "Matt Carter (Inman)": "https://www.inman.com/author/mattcarter/feed",
    "Shaina Mishkin (Barron's)": get_gnews_rss("Shaina Mishkin", "Barron's"),
    "Aarthi Swaminathan (MW)": "https://www.marketwatch.com/author/aarthi-swaminathan/feed"
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

tabs = st.tabs(["🎙️ Podcast Guest Tracker", "✍️ Elite Journalist Feed", "🏢 Competitors", "📰 Industry News"])

with tabs[0]:
    st.info("Varun's Pursuit: Tracking latest guests and episode topics.")
    cols = st.columns(2)
    for idx, (name, rss) in enumerate(PODCASTS.items()):
        with cols[idx % 2].expander(f"🎧 {name}", expanded=True if search_query else False):
            eps = fetch_and_filter(rss, search_query)
            for e in eps:
                st.markdown(f"👤 **{parse_guest(e.title)}** — [Link]({e.link})")
                st.caption(f"{e.get('published', '')[:16]}")

with tabs[1]:
    st.info("Direct and 'Hacked' feeds for key financial & real estate journalists.")
    cols = st.columns(2)
    for idx, (name, rss) in enumerate(JOURNALISTS.items()):
        with cols[idx % 2].expander(f"🖋️ {name}"):
            articles = fetch_and_filter(rss, search_query)
            if not articles: st.write("No recent articles found.")
            for a in articles:
                st.markdown(f"📄 **[{a.title}]({a.link})**")
                st.caption(f"{a.get('published', '')[:16]}")

with tabs[2]:
    comps = {
        "Rocket Mortgage (HW)": "https://www.housingwire.com/tag/rocket-mortgage/feed/",
        "Rocket Co (Press)": "https://www.rocketcompanies.com/feed/?post_type=press_release",
        "UWM (Updates)": "https://feed.businesswire.com/rss/home/company/United+Wholesale+Mortgage%2C+LLC/w6euAGJXjezVpz22AaGCsA=="
    }
    for label, url in comps.items():
        st.subheader(label)
        for item in fetch_and_filter(url, search_query, limit=4):
            st.markdown(f"🔹 **[{item.title}]({item.link})**")

with tabs[3]:
    industry = {
        "National Mortgage News": "https://www.nationalmortgagenews.com/feed?rss=true",
        "Mortgage News Daily": "http://www.mortgagenewsdaily.com/rss/news"
    }
    for label, url in industry.items():
        st.subheader(label)
        for item in fetch_and_filter(url, search_query, limit=4):
            st.markdown(f"🗞️ **[{item.title}]({item.link})**")

st.sidebar.markdown(f"--- \n**Last Sync:** {datetime.now().strftime('%H:%M:%S')}")
