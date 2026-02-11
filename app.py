import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import feedparser
import requests
import io
import re
import urllib.parse
from datetime import datetime, timedelta
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.utils import parsedate_to_datetime

# --- CONFIG & STYLING ---
st.set_page_config(page_title="Strategic Trends, Analytics & Real-estate Knowledge", layout="wide", initial_sidebar_state="expanded")

# Memory limit: ~500MB max per page load - aggressive data retention limits
MAX_ENTRIES_PER_FEED = 8  # Reduced from 10 to save memory
MAX_FRED_DAYS = 180  # Limit FRED data to 6 months for memory efficiency (reduced from 365)
MAX_CHART_DISPLAY_DAYS = 90  # Only display last 90 days on chart for better performance

# --- SESSION STATE INITIALIZATION ---
# Theme persistence (uses query params for cross-page-load persistence)
if 'theme' not in st.session_state:
    st.session_state.theme = st.query_params.get('theme', 'dark')

# Chart line visibility toggles
if 'show_30y' not in st.session_state:
    st.session_state.show_30y = True
if 'show_15y' not in st.session_state:
    st.session_state.show_15y = True
if 'show_10y' not in st.session_state:
    st.session_state.show_10y = True
if 'show_rkt' not in st.session_state:
    st.session_state.show_rkt = True

# Expand/collapse state for sections
if 'expand_journalists' not in st.session_state:
    st.session_state.expand_journalists = False
if 'expand_podcasts' not in st.session_state:
    st.session_state.expand_podcasts = False
if 'show_trends' not in st.session_state:
    st.session_state.show_trends = False

# Loading states for feeds
if 'journalists_loading' not in st.session_state:
    st.session_state.journalists_loading = False
if 'feeds_loaded' not in st.session_state:
    st.session_state.feeds_loaded = False

# --- THEME DEFINITIONS ---
THEMES = {
    'light': {
        'bg': '#ffffff',
        'text': '#333333',
        'card_bg': '#f0f0f0',
        'border': '#cccccc',
        'summary': '#555555',
        'plotly': 'plotly_white',
        'link': '#0066cc'
    },
    'dark': {
        'bg': '#0e1117',
        'text': '#fafafa',
        'card_bg': '#1e1e1e',
        'border': '#333333',
        'summary': '#aaaaaa',
        'plotly': 'plotly_dark',
        'link': '#58a6ff'
    },
    'midnight': {
        'bg': '#0a0a12',
        'text': '#e0e0ff',
        'card_bg': '#12121f',
        'border': '#252540',
        'summary': '#8888aa',
        'plotly': 'plotly_dark',
        'link': '#8ab4f8'
    }
}

theme = THEMES[st.session_state.theme]

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Saira:ital,wght@0,100..900;1,100..900&display=swap');
    * {{ font-family: 'Saira', sans-serif !important; }}
    *[data-testid="stIconMaterial"] {{ font-family: "Material Symbols Rounded" !important; }}
    .stApp {{ background-color: {theme['bg']}; color: {theme['text']}; }}
    .stMarkdown {{ color: {theme['text']}; }}
    .stMarkdown a {{ color: {theme['link']} !important; }}
    h1, h2, h3, h4, h5, h6 {{ color: {theme['text']} !important; }}
    .stMetric {{ background-color: {theme['card_bg']}; padding: 10px; border-radius: 5px; border: 1px solid {theme['border']}; cursor: pointer; transition: opacity 0.2s; }}
    .stMetric:hover {{ opacity: 0.8; }}
    .metric-hidden {{ opacity: 0.4; }}
    .stExpander {{ border: 1px solid {theme['border']} !important; }}
    .stExpander p {{ word-break: break-all; }}
    .episode-summary {{ font-size: 0.85em; color: {theme['summary']}; margin-top: 4px; margin-bottom: 8px; }}
    /* Loading indicator - prominent pulsing animation */
    .stSpinner > div {{ border-color: #4CAF50 transparent transparent transparent !important; }}
    .loading-banner {{
        background: linear-gradient(90deg, #1a1a2e, #16213e, #1a1a2e);
        background-size: 200% 100%;
        animation: shimmer 1.5s infinite;
        padding: 12px 20px;
        border-radius: 8px;
        border: 1px solid #4CAF50;
        margin-bottom: 16px;
        text-align: center;
    }}
    @keyframes shimmer {{
        0% {{ background-position: -200% 0; }}
        100% {{ background-position: 200% 0; }}
    }}
    .trend-badge {{
        display: inline-block;
        background-color: {theme['card_bg']};
        border: 1px solid {theme['border']};
        border-radius: 12px;
        padding: 4px 10px;
        margin: 4px;
        font-size: 0.85em;
    }}
    .trending {{ border-color: #FF6B6B; background-color: rgba(255, 107, 107, 0.1); }}
    .emerging {{ border-color: #4ECDC4; background-color: rgba(78, 205, 196, 0.1); }}
    </style>
""", unsafe_allow_html=True)

# --- SIDEBAR: Theme Toggle ---
st.sidebar.title("⚙️ Settings")
def update_theme():
    """Callback to update theme without explicit rerun."""
    st.session_state.theme = st.session_state.theme_selector
    st.query_params['theme'] = st.session_state.theme_selector

theme_choice = st.sidebar.radio(
    "Theme",
    options=['light', 'dark', 'midnight'],
    index=['light', 'dark', 'midnight'].index(st.session_state.theme),
    horizontal=True,
    key='theme_selector',
    on_change=update_theme
)

st.sidebar.markdown("---")

st.title("🏦 *S.T.A.R.K.*")
st.caption("Strategic Trends, Analytics & Real-estate Knowledge")

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

@st.cache_data(ttl=86400)  # Cache for 24 hours (historical data rarely changes)
def get_rkt_historical_from_sheet():
    """
    Fetch historical RKT stock prices from Google Sheet.
    To use: Share your Google Sheet as 'Anyone with link can view', then replace the URL below
    with: https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}

    Expected CSV format:
    Date,Close
    2024-01-01,15.23
    2024-01-02,15.45
    ...
    """
    # Google Sheet CSV export URL (published sheet format)
    SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRbhaj5pOJbUNEpOEp-xaNi9vn8UyKNBndxMClDsKLmMDu7jCOXEz5GZEofCt2kH6RA9I84YW4EG8Td/pub?output=csv"

    if not SHEET_URL:
        return pd.DataFrame()

    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(SHEET_URL, headers=headers, timeout=10)
        df = pd.read_csv(io.StringIO(r.text))

        # Assume first column is date, second column is close price
        date_col = df.columns[0]
        close_col = df.columns[1]

        # Parse dates and convert to datetime
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        df = df.rename(columns={date_col: 'DATE', close_col: 'RKT'})
        df['RKT'] = pd.to_numeric(df['RKT'], errors='coerce')

        # Remove rows with invalid dates or prices
        df = df.dropna(subset=['DATE', 'RKT'])

        # Set datetime index
        df = df.set_index('DATE').sort_index()

        # Verify index is DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        return df[['RKT']]
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=3600)  # Cache live data for 1 hour
def get_rkt_stock_data():
    """
    Fetch RKT stock price from Alpha Vantage API and merge with historical Google Sheet data.
    Historical data provides the base, API provides recent updates (up to 25/day, throttled to ~1/hour).
    """
    # Get free API key at: https://www.alphavantage.co/support/#api-key
    API_KEY = "demo"  # Replace with your free Alpha Vantage API key
    headers = {"User-Agent": "Mozilla/5.0"}

    # Fetch historical data from Google Sheet
    historical_df = get_rkt_historical_from_sheet()

    # Fetch recent live data from API
    live_df = pd.DataFrame()
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=RKT&apikey={API_KEY}&datatype=csv"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if "Error" not in r.text and "Invalid" not in r.text:
            live_df = pd.read_csv(io.StringIO(r.text))
            live_df['timestamp'] = pd.to_datetime(live_df['timestamp'])
            live_df = live_df.set_index('timestamp').sort_index()
            live_df = live_df[['close']].rename(columns={'close': 'RKT'})
            live_df['RKT'] = pd.to_numeric(live_df['RKT'], errors='coerce')
    except:
        pass

    # Merge historical and live data
    if not historical_df.empty and not live_df.empty:
        # Ensure both dataframes have datetime indices before merging
        if not isinstance(historical_df.index, pd.DatetimeIndex):
            historical_df.index = pd.to_datetime(historical_df.index)
        if not isinstance(live_df.index, pd.DatetimeIndex):
            live_df.index = pd.to_datetime(live_df.index)

        # Combine: historical data + live data (live overwrites historical for overlapping dates)
        combined = pd.concat([historical_df, live_df])
        combined = combined[~combined.index.duplicated(keep='last')]  # Keep latest for duplicates
        combined = combined.sort_index().tail(MAX_FRED_DAYS)
        return combined
    elif not historical_df.empty:
        return historical_df.sort_index().tail(MAX_FRED_DAYS)
    elif not live_df.empty:
        return live_df.sort_index().tail(MAX_FRED_DAYS)
    else:
        return pd.DataFrame()

# --- CONTENT ENGINES (Cached for efficiency) ---
@st.cache_data(ttl=600, max_entries=128)  # 10-min cache; slim dicts only to stay well under 512MB
def fetch_rss_feed(url):
    """Fetch and cache RSS feed. Stores only the 4 fields we use — not heavy feedparser objects."""
    try:
        feed = feedparser.parse(
            url,
            agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        if feed.entries:
            return [
                {
                    'title':     e.get('title', ''),
                    'link':      e.get('link', '#'),
                    'published': e.get('published', ''),
                    'summary':   (e.get('summary', '') or e.get('description', ''))[:300],
                }
                for e in feed.entries[:MAX_ENTRIES_PER_FEED]
            ]
        return []
    except Exception:
        return []

def fetch_and_filter(url, query, limit=8):
    """Fetch RSS feed (cached) and filter by query. Memory-optimized. Sorted chronologically (newest first)."""
    try:
        entries = fetch_rss_feed(url)
        if not entries:
            return []

        def parse_date(date_str):
            if not date_str:
                return datetime.min
            try:
                return parsedate_to_datetime(date_str)
            except:
                try:
                    return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                except:
                    return datetime.min

        # If no query, return first N items sorted by date (newest first)
        if not query:
            result = []
            for entry in entries:
                result.append({
                    'title': entry.get('title', ''),
                    'link': entry.get('link', '#'),
                    'published': entry.get('published', ''),
                    'summary': entry.get('summary', ''),
                    '_date': parse_date(entry.get('published', ''))
                })
            # Sort by date (newest first)
            result.sort(key=lambda x: x['_date'], reverse=True)
            # Remove internal _date field and limit results
            for item in result:
                del item['_date']
            return result[:limit]

        # Memory optimization: only keep essential fields, filter and sort
        filtered = []
        for entry in entries:
            title = entry.get('title', '').lower()
            summary = entry.get('summary', '').lower()
            if query in title or query in summary:
                # Only keep fields we actually use
                filtered.append({
                    'title': entry.get('title', ''),
                    'link': entry.get('link', '#'),
                    'published': entry.get('published', ''),
                    'summary': entry.get('summary', ''),
                    '_date': parse_date(entry.get('published', ''))
                })

        # Sort by date (newest first)
        filtered.sort(key=lambda x: x['_date'], reverse=True)
        # Remove internal _date field and limit results
        for item in filtered:
            del item['_date']
        return filtered[:limit]
    except Exception:
        return []

def fetch_feeds_concurrently(feed_dict, query, limit=8, max_workers=8):
    """Fetch multiple RSS feeds in parallel using a thread pool."""
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_label = {
            executor.submit(fetch_and_filter, url, query, limit): label
            for label, url in feed_dict.items()
        }
        for future in as_completed(future_to_label):
            label = future_to_label[future]
            try:
                results[label] = future.result()
            except Exception:
                results[label] = []
    return results

def fetch_podcast_with_fallback(rss_urls, query):
    if isinstance(rss_urls, str):
        return fetch_and_filter(rss_urls, query)
    for url in rss_urls:
        eps = fetch_and_filter(url, query)
        if eps:
            return eps
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

def extract_keywords(text):
    """Extract meaningful keywords from text (titles, summaries)."""
    # Remove common stop words
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'is', 'are', 'was', 'were', 'will', 'has', 'have', 'had', 'this', 'that', 'these', 'those', 'from', 'by', 'as', 'it', 'its', 'their', 'what', 'which', 'who', 'how', 'why', 'when'}
    
    # Clean and tokenize
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    words = text.split()
    
    # Filter keywords
    keywords = [w for w in words if len(w) > 3 and w not in stop_words]
    return keywords

def analyze_podcast_trends(podcast_data):
    """Analyze podcast episodes to find trending guests and topics."""
    guest_counter = Counter()
    topic_counter = Counter()
    guest_shows = {}  # Track which shows each guest appears on
    
    for show_name, episodes in podcast_data.items():
        for ep in episodes:
            title = ep.get('title', '')
            guest = parse_guest(title)
            
            # Count guest appearances
            if guest and len(guest) > 3:
                guest_counter[guest] += 1
                if guest not in guest_shows:
                    guest_shows[guest] = []
                if show_name not in guest_shows[guest]:
                    guest_shows[guest].append(show_name)
            
            # Extract and count topics
            keywords = extract_keywords(title)
            for kw in keywords:
                topic_counter[kw] += 1
    
    # Find guests on multiple shows (trending)
    trending_guests = [(guest, shows) for guest, shows in guest_shows.items() if len(shows) >= 2]
    trending_guests.sort(key=lambda x: len(x[1]), reverse=True)
    
    # Find most common topics
    popular_topics = topic_counter.most_common(10)
    
    return trending_guests[:5], popular_topics

def analyze_emerging_topics(news_data):
    """Find emerging topics that appear infrequently (opportunities to be first)."""
    topic_counter = Counter()
    topic_sources = {}
    
    for source_name, articles in news_data.items():
        for article in articles:
            title = article.get('title', '')
            keywords = extract_keywords(title)
            
            for kw in keywords:
                topic_counter[kw] += 1
                if kw not in topic_sources:
                    topic_sources[kw] = []
                if source_name not in topic_sources[kw]:
                    topic_sources[kw].append(source_name)
    
    # Find topics mentioned only 1-2 times (emerging/unique)
    emerging = [(topic, count, topic_sources[topic]) for topic, count in topic_counter.items() if 1 <= count <= 2]
    emerging.sort(key=lambda x: x[1])
    
    return emerging[:10]

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

def get_gnews_rss(name, domain=None):
    """
    Build Google News RSS URL for journalist articles.
    Uses site: operator with domain for more targeted results.
    """
    if domain:
        query = f'"{name}" site:{domain}.com'
    else:
        query = f'"{name}"'
    return f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"

# --- UPDATED SOURCE LISTS ---
PODCASTS = {
    "Diary of a CEO": "https://www.youtube.com/feeds/videos.xml?channel_id=UCnjgxChqYYnyoqO4k_Q1d6Q",
    "Lex Fridman": "https://lexfridman.com/feed/podcast/",
    "Tim Ferriss": "https://rss.art19.com/tim-ferriss-show",
    "All-In": "https://www.youtube.com/feeds/videos.xml?channel_id=UCESLZhusAkFfsNsApnjF_Cg",
    "Acquired": "https://feeds.transistor.fm/acquired",
    "Pioneers of AI": "https://www.youtube.com/feeds/videos.xml?channel_id=UCsZwYD6b7hse6O9SIclwYEA",
    "Lenny's Podcast": "https://www.lennysnewsletter.com/feed",
    "TBPN (Tech Brothers)": "https://feeds.transistor.fm/technology-brother",
    "How Leaders Lead": "https://www.youtube.com/feeds/videos.xml?channel_id=UCa4HLorpafz21UwJem_OnGg",
    "Leadership Next": "https://feeds.megaphone.fm/fortuneleadershipnext"
}

JOURNALISTS = {
    "Nick Timiraos (WSJ)": get_gnews_rss("Nick Timiraos", "wsj"),
    "Gina Heeb (WSJ)": get_gnews_rss("Gina Heeb", "wsj"),
    "Ben Eisen (WSJ)": get_gnews_rss("Ben Eisen", "wsj"),
    "Nicole Friedman (WSJ)": get_gnews_rss("Nicole Friedman", "wsj"),
    "AnnaMaria Andriotis (WSJ)": get_gnews_rss("AnnaMaria Andriotis", "wsj"),
    "Veronica Dagher (WSJ)": get_gnews_rss("Veronica Dagher", "wsj"),
    "Telis Demos (WSJ)": get_gnews_rss("Telis Demos", "wsj"),
    "Nick Manes (Crain's)": "https://www.crainsdetroit.com/author/nick-manes/feed",
    "Sarah Wolak (HW)": "https://www.housingwire.com/author/sarahwolak/feed",
    "Shaina Mishkin (Barron's)": get_gnews_rss("Shaina Mishkin", "barrons")
}

INDUSTRY_FEEDS = {
    "National Mortgage News": "https://www.nationalmortgagenews.com/feed?rss=true",
    "Mortgage News Daily": "http://www.mortgagenewsdaily.com/rss/news"
}

COMPETITOR_FEEDS = {
    "Rocket Mortgage (HW)": "https://www.housingwire.com/tag/rocket-mortgage/feed/",
    "Rocket Co (Press)": "https://www.rocketcompanies.com/feed/?post_type=press_release",
    "UWM (Updates) [SEC Feed]": "https://data.sec.gov/rss?cik=0001783398&type=3,4,5&exclude=true&count=40",
    "UWM Releases (Scraped from Y!)": "https://ikcerog.github.io/scrapethis/rss.xml"
}

# Expand/Collapse callbacks
def expand_journalists():
    st.session_state.expand_journalists = True

def collapse_journalists():
    st.session_state.expand_journalists = False

def expand_podcasts():
    st.session_state.expand_podcasts = True

def collapse_podcasts():
    st.session_state.expand_podcasts = False

def toggle_trends():
    st.session_state.show_trends = not st.session_state.show_trends

# --- DASHBOARD RENDER ---
data = get_mortgage_data()
rkt_data = get_rkt_stock_data()

# Toggle callbacks
def toggle_30y():
    st.session_state.show_30y = not st.session_state.show_30y

def toggle_15y():
    st.session_state.show_15y = not st.session_state.show_15y

def toggle_10y():
    st.session_state.show_10y = not st.session_state.show_10y

def toggle_rkt():
    st.session_state.show_rkt = not st.session_state.show_rkt

if not data.empty and len(data) >= 2:
    curr, prev = data.iloc[-1], data.iloc[-2]

    # Metrics row with toggle buttons - click to show/hide on chart
    st.caption("💡 Click metrics below to show/hide lines on chart")
    m1, m2, m3, m4 = st.columns(4)

    with m1:
        label_30y = "30Y Fixed" + (" ✓" if st.session_state.show_30y else " ○")
        if '30Y Fixed' in data.columns:
            st.button(
                f"**{label_30y}**\n\n{curr['30Y Fixed']}% ({round(curr['30Y Fixed']-prev['30Y Fixed'], 3):+}%)",
                key="btn_30y",
                use_container_width=True,
                on_click=toggle_30y
            )
        else:
            st.button(f"**{label_30y}**\n\nN/A", key="btn_30y", use_container_width=True, disabled=True)

    with m2:
        label_15y = "15Y Fixed" + (" ✓" if st.session_state.show_15y else " ○")
        if '15Y Fixed' in data.columns:
            st.button(
                f"**{label_15y}**\n\n{curr['15Y Fixed']}% ({round(curr['15Y Fixed']-prev['15Y Fixed'], 3):+}%)",
                key="btn_15y",
                use_container_width=True,
                on_click=toggle_15y
            )
        else:
            st.button(f"**{label_15y}**\n\nN/A", key="btn_15y", use_container_width=True, disabled=True)

    with m3:
        label_10y = "10Y Treasury" + (" ✓" if st.session_state.show_10y else " ○")
        if '10Y Treasury' in data.columns:
            st.button(
                f"**{label_10y}**\n\n{curr['10Y Treasury']}% ({round(curr['10Y Treasury']-prev['10Y Treasury'], 3):+}%)",
                key="btn_10y",
                use_container_width=True,
                on_click=toggle_10y
            )
        else:
            st.button(f"**{label_10y}**\n\nN/A", key="btn_10y", use_container_width=True, disabled=True)

    with m4:
        label_rkt = "RKT" + (" ✓" if st.session_state.show_rkt else " ○")
        if not rkt_data.empty and len(rkt_data) >= 2:
            rkt_curr, rkt_prev = rkt_data.iloc[-1]['RKT'], rkt_data.iloc[-2]['RKT']
            st.button(
                f"**{label_rkt}**\n\n${rkt_curr:.2f} ({rkt_curr - rkt_prev:+.2f})",
                key="btn_rkt",
                use_container_width=True,
                on_click=toggle_rkt
            )
        else:
            st.button(f"**{label_rkt}**\n\nN/A", key="btn_rkt", use_container_width=True, disabled=True)

    # Dual-axis chart: Rates (left) + RKT Stock (right)
    chart_data = data.tail(MAX_CHART_DISPLAY_DAYS)
    chart_rkt_data = rkt_data.tail(MAX_CHART_DISPLAY_DAYS) if not rkt_data.empty else rkt_data

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    colors = {'30Y Fixed': '#636EFA', '15Y Fixed': '#EF553B', '10Y Treasury': '#00CC96'}
    visibility_map = {'30Y Fixed': st.session_state.show_30y, '15Y Fixed': st.session_state.show_15y, '10Y Treasury': st.session_state.show_10y}

    for col in chart_data.columns:
        if visibility_map.get(col, True):
            fig.add_trace(
                go.Scatter(x=chart_data.index, y=chart_data[col], name=col, line=dict(color=colors.get(col))),
                secondary_y=False
            )

    if not chart_rkt_data.empty and st.session_state.show_rkt:
        fig.add_trace(
            go.Scatter(x=chart_rkt_data.index, y=chart_rkt_data['RKT'], name='RKT', line=dict(color='#FFA15A', width=2)),
            secondary_y=True
        )

    fig.update_layout(
        template=theme['plotly'],
        height=280,
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        showlegend=True,
        hovermode='x unified'
    )
    fig.update_yaxes(title_text="Rate (%)", secondary_y=False)
    fig.update_yaxes(title_text="RKT ($)", secondary_y=True)

    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

# --- SEARCH BAR ---
search_query = st.text_input("🔍 Filter across all feeds:", placeholder="e.g. 'Fed', 'Rates', 'Inventory'", key="main_search").lower()

st.divider()

# Collect data for trend analysis
podcast_data = {}
news_data = {}

# Pre-load Industry News and Competitors (for Insights) - fetched concurrently
with st.spinner("🔄 Loading feeds for insights..."):
    all_news_feeds = {**INDUSTRY_FEEDS, **COMPETITOR_FEEDS}
    news_data.update(fetch_feeds_concurrently(all_news_feeds, search_query, limit=4))

st.session_state.feeds_loaded = True

@st.fragment
def _journalist_tab(search_q):
    alert_placeholder = st.empty()
    alert_placeholder.info("🔄 Loading journalist feeds...")

    hdr_col1, hdr_col2 = st.columns([6, 2])
    with hdr_col1:
        st.info("Direct and Search-Aggregated feeds for elite financial reporters.")
    with hdr_col2:
        components.html("""<style>
  .xpbtn{background:transparent;border:1px solid rgba(255,255,255,.25);border-radius:4px;
         color:rgba(255,255,255,.85);cursor:pointer;font-size:13px;padding:4px 10px;
         margin:2px;white-space:nowrap}
  .xpbtn:hover{background:rgba(255,255,255,.1)}
</style>
<button class="xpbtn" onclick="window.parent.document.querySelectorAll('details').forEach(d=>d.open=true)">📂 Expand All</button>
<button class="xpbtn" onclick="window.parent.document.querySelectorAll('details').forEach(d=>d.open=false)">📁 Collapse</button>
""", height=40)

    cols = st.columns(2)
    loaded_count = 0
    total_count = len(JOURNALISTS)
    journalist_results = fetch_feeds_concurrently(JOURNALISTS, search_q)

    for idx, (name, rss) in enumerate(JOURNALISTS.items()):
        with cols[idx % 2].expander(f"📰 {name}"):
            try:
                articles = journalist_results.get(name, [])
                loaded_count += 1
                if not articles: st.write("No matches found.")
                for a in articles:
                    link = a.get('link', '#')
                    st.markdown(f"📄 **[{a.get('title', 'Article')}]({link})**")
                    st.caption(f"{a.get('published', '')[:16]}")
            except:
                st.error(f"Error loading {name}")
                loaded_count += 1

    alert_placeholder.success(f"✅ Loaded {loaded_count}/{total_count} journalist feeds.")

@st.fragment
def _podcast_tab(search_q):
    hdr_col1, hdr_col2 = st.columns([6, 2])
    with hdr_col1:
        st.info("⚡ Podcast feeds load on-demand. Click a show to fetch episodes.")
    with hdr_col2:
        components.html("""<style>
  .xpbtn{background:transparent;border:1px solid rgba(255,255,255,.25);border-radius:4px;
         color:rgba(255,255,255,.85);cursor:pointer;font-size:13px;padding:4px 10px;
         margin:2px;white-space:nowrap}
  .xpbtn:hover{background:rgba(255,255,255,.1)}
</style>
<button class="xpbtn" onclick="window.parent.document.querySelectorAll('details').forEach(d=>d.open=true)">📂 Expand All</button>
<button class="xpbtn" onclick="window.parent.document.querySelectorAll('details').forEach(d=>d.open=false)">📁 Collapse</button>
""", height=40)

    with st.spinner("⟳ Fetching podcast feeds..."):
        pod_data = {}
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_name = {
                executor.submit(fetch_podcast_with_fallback, rss, search_q): name
                for name, rss in PODCASTS.items()
            }
            for future in as_completed(future_to_name):
                pod_data[future_to_name[future]] = future.result() or []
    st.session_state['podcast_data'] = pod_data

    cols = st.columns(2)
    for idx, (name, rss) in enumerate(PODCASTS.items()):
        col = cols[idx % 2]
        with col.expander(f"🎧 {name}"):
            try:
                eps = pod_data.get(name, [])
                if not eps:
                    st.write("No episodes found or feed unavailable.")
                for e in eps:
                    link = e.get('link', '#')
                    title = e.get('title', 'Untitled Episode')
                    guest = parse_guest(title)
                    st.markdown(f"🎤 **{guest}** — [Link]({link})")
                    summary = get_summary(e)
                    if summary:
                        st.markdown(f'<div class="episode-summary">{summary}</div>', unsafe_allow_html=True)
                    st.caption(f"{e.get('published', '')[:16]}")
            except:
                st.error(f"Error loading {name}")

tabs = st.tabs(["🗞️ Industry News", "🏢 Competitors", "🖋️ Journalist Feed", "🎙️ Podcasts"])

# --- TAB 0: Industry News ---
with tabs[0]:
    for label, url in INDUSTRY_FEEDS.items():
        st.subheader(label)
        items = news_data.get(label, [])
        for item in items:
            st.markdown(f"🔹 **[{item.get('title', 'Article')}]({item.get('link', '#')})**")

# --- TAB 1: Competitors ---
with tabs[1]:
    for label, url in COMPETITOR_FEEDS.items():
        st.subheader(label)
        items = news_data.get(label, [])
        for item in items:
            st.markdown(f"🔹 **[{item.get('title', 'News')}]({item.get('link', '#')})**")

# --- TAB 2: Journalist Feed ---
with tabs[2]:
    _journalist_tab(search_query)

# --- TAB 3: Podcasts ---
with tabs[3]:
    _podcast_tab(search_query)

podcast_data = st.session_state.get('podcast_data', {})

# --- TRENDS & INSIGHTS BUTTON (placed here, below tabs) ---
col_trends, col_spacer = st.columns([2, 6])
with col_trends:
    trends_label = "🔥 Hide Insights" if st.session_state.show_trends else "🔥 Show Trends & Insights"
    st.button(trends_label, key="toggle_trends_btn", use_container_width=True, on_click=toggle_trends)

# --- TRENDS & INSIGHTS SECTION ---
if st.session_state.show_trends and (podcast_data or news_data):
    st.divider()
    st.markdown("## 🔥 Trends & Emerging Opportunities")
    
    trend_col1, trend_col2 = st.columns(2)
    
    with trend_col1:
        if podcast_data:
            st.markdown("### 🎙️ **Trending in Podcasts**")
            trending_guests, popular_topics = analyze_podcast_trends(podcast_data)
            
            if trending_guests:
                st.markdown("**🌟 Guests on Multiple Shows:**")
                for guest, shows in trending_guests:
                    shows_str = ", ".join(shows)
                    st.markdown(f'<div class="trend-badge trending">👤 {guest} <small>({len(shows)} shows)</small></div>', unsafe_allow_html=True)
                    st.caption(f"   Featured on: {shows_str}")
            
            if popular_topics:
                st.markdown("**📊 Hot Topics:**")
                for topic, count in popular_topics[:5]:
                    st.markdown(f'<div class="trend-badge trending">🔥 {topic} <small>({count} mentions)</small></div>', unsafe_allow_html=True)
    
    with trend_col2:
        if news_data:
            st.markdown("### 💎 **Emerging Opportunities**")
            emerging_topics = analyze_emerging_topics(news_data)
            
            if emerging_topics:
                st.markdown("**🌱 Unique/Rare Topics** *(be first!)*")
                for topic, count, sources in emerging_topics[:8]:
                    sources_str = ", ".join(sources[:2])
                    st.markdown(f'<div class="trend-badge emerging">💡 {topic} <small>({count}x)</small></div>', unsafe_allow_html=True)
                    st.caption(f"   Source: {sources_str}")
            else:
                st.write("*Load more feeds to discover emerging topics*")

st.sidebar.markdown(f"--- \n**Last Sync:** {datetime.now().strftime('%H:%M:%S')}")
