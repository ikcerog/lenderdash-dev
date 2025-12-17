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

# Memory limit: ~500MB max per page load - limit data retention
MAX_ENTRIES_PER_FEED = 10
MAX_FRED_DAYS = 365  # Limit FRED data to 1 year for efficiency

st.markdown("""
    <style>
    .stMetric { background-color: #1e1e1e; padding: 10px; border-radius: 5px; border: 1px solid #333; }
    .stExpander { border: 1px solid #444 !important; }
    .stExpander p { word-break: break-all; }
    .episode-summary { font-size: 0.85em; color: #aaa; margin-top: 4px; margin-bottom: 8px; }
    </style>
""", unsafe_allow_html=True)

st.title("🏦 Mortgage & Media Command Center")

# --- GLOBAL SEARCH ---
st.sidebar.title("🔍 Intel Search")
search_query = st.sidebar.text_input("Filter across all feeds:", placeholder="e.g. 'Fed', 'Rates', 'Inventory'").lower()

# --- FRED DATA ENGINE (Optimized: limit to MAX_FRED_DAYS for <500MB) ---
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
            r = requests.get(url, headers=headers, timeout=10)
            df = pd.read_csv(io.StringIO(r.text))
            date_col, val_col = df.columns[0], df.columns[1]
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.rename(columns={date_col: 'DATE', val_col: name})
            df[name] = pd.to_numeric(df[name], errors='coerce')
            dfs.append(df.set_index('DATE'))
        except: continue
    if not dfs:
        return pd.DataFrame()
    combined = pd.concat(dfs, axis=1).ffill().dropna()
    # Limit to last MAX_FRED_DAYS for memory efficiency
    return combined.tail(MAX_FRED_DAYS)

# --- CONTENT ENGINES (Cached for efficiency) ---
@st.cache_data(ttl=900)  # Cache RSS feeds for 15 minutes
def fetch_rss_feed(url):
    """Fetch and cache RSS feed to minimize network calls."""
    try:
        # Enhanced User-Agent to avoid blocking
        feed = feedparser.parse(
            url,
            agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        if feed.entries:
            # Limit entries stored in cache for memory efficiency
            return feed.entries[:MAX_ENTRIES_PER_FEED]
        return []
    except Exception:
        return []

def fetch_and_filter(url, query, limit=8):
    """Fetch RSS feed (cached) and filter by query."""
    try:
        entries = fetch_rss_feed(url)
        if not entries:
            return []
        if not query:
            return entries[:limit]
        filtered = []
        for entry in entries:
            title = entry.get('title', '').lower()
            summary = entry.get('summary', '').lower()
            if query in title or query in summary:
                filtered.append(entry)
        return filtered[:limit]
    except Exception:
        return []

def parse_guest(title):
    """
    Extract guest name from podcast episode title.
    Enhanced patterns for Diary of a CEO and other common formats.
    """
    # Clean common prefixes
    title = re.sub(r'^(E\d+[:\s]+|Ep\.?\s*\d+[:\s]+|Episode\s*\d+[:\s]+)', '', title, flags=re.IGNORECASE)

    patterns = [
        # "Guest Name: Topic" or "Guest Name - Topic"
        r'^([A-Z][a-zA-Z\s\.]+(?:\s+[A-Z][a-zA-Z]+)*)\s*[:\-–—|]',
        # "#123: Guest Name - Topic" or "E123: Guest Name"
        r'^(?:#?\d+[:\s]+)?([A-Z][a-zA-Z\s\.]+(?:\s+[A-Z][a-zA-Z]+)*)\s*[:\-–—|]',
        # "with Guest Name" pattern
        r'[Ww]ith\s+([A-Z][a-zA-Z\s\.]+)',
        # "ft. Guest Name" or "featuring Guest Name"
        r'(?:[Ff]t\.?|[Ff]eaturing)\s+([A-Z][a-zA-Z\s\.]+)',
        # "Interview: Guest Name" or "Conversation with Guest Name"
        r'(?:[Ii]nterview|[Cc]onversation)[:\s]+(?:with\s+)?([A-Z][a-zA-Z\s\.]+)',
        # Fallback: first proper noun sequence before punctuation
        r'^([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})',
    ]

    for p in patterns:
        match = re.search(p, title)
        if match:
            guest = match.group(1).strip()
            # Clean trailing words like "on", "about", "discusses"
            guest = re.sub(r'\s+(on|about|discusses|talks|shares|reveals|explains)\s*$', '', guest, flags=re.IGNORECASE)
            if 3 < len(guest) < 50:
                return guest

    # Last resort: return truncated title
    return title[:45] + '...' if len(title) > 45 else title

def get_summary(entry, max_length=150):
    """Extract and clean episode summary."""
    summary = entry.get('summary', '') or entry.get('description', '')
    if not summary:
        return None
    # Remove HTML tags
    summary = re.sub(r'<[^>]+>', '', summary)
    # Remove excessive whitespace
    summary = ' '.join(summary.split())
    if len(summary) > max_length:
        summary = summary[:max_length].rsplit(' ', 1)[0] + '...'
    return summary if summary else None

def get_gnews_rss(name, source):
    # This remains the most stable 'hack' for non-RSS publications
    query = f'inauthor:"{name}" source:"{source}"'
    return f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}"

# --- UPDATED SOURCE LISTS ---
# Multiple fallback URLs for Diary of a CEO for reliability
DOAC_FEEDS = [
    "https://feeds.megaphone.fm/thedairyofaceo",
    "https://feeds.megaphone.fm/the-diary-of-a-ceo",
    "https://rss.art19.com/the-diary-of-a-ceo-with-steven-bartlett",
]

PODCASTS = {
    "Diary of a CEO": DOAC_FEEDS,  # Multiple fallback URLs
    "Lex Fridman": "https://lexfridman.com/feed/podcast/",
    "Tim Ferriss": "https://rss.art19.com/tim-ferriss-show",
    "All-In": "https://feeds.megaphone.fm/all-in-with-chamath-jason-sacks-friedberg",
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

def fetch_podcast_with_fallback(rss_urls, query):
    """Try multiple RSS URLs for podcasts with fallback support."""
    if isinstance(rss_urls, str):
        return fetch_and_filter(rss_urls, query)
    # Try each URL until one works
    for url in rss_urls:
        eps = fetch_and_filter(url, query)
        if eps:
            return eps
    return []

with tabs[0]:
    st.info("Tracking recent guests and episode intelligence across target shows.")
    cols = st.columns(2)
    for idx, (name, rss) in enumerate(PODCASTS.items()):
        col = cols[idx % 2]
        with col.expander(f"🎧 {name}", expanded=True if search_query else False):
            try:
                eps = fetch_podcast_with_fallback(rss, search_query)
                if not eps:
                    st.write("No episodes found or feed unavailable.")
                for e in eps:
                    link = e.get('link', '#')
                    title = e.get('title', 'Untitled Episode')
                    guest = parse_guest(title)
                    st.markdown(f"👤 **{guest}** — [Link]({link})")
                    # Add summary if available
                    summary = get_summary(e)
                    if summary:
                        st.markdown(f'<div class="episode-summary">{summary}</div>', unsafe_allow_html=True)
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
