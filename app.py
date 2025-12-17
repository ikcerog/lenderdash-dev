import streamlit as st
import pandas as pd
import plotly.express as px
import feedparser
import requests
import io
from datetime import datetime

# Page Configuration
st.set_page_config(page_title="Mortgage Intel Dashboard", layout="wide", initial_sidebar_state="collapsed")

st.title("🏦 Mortgage Industry Intelligence")
st.markdown(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# --- DATA FETCHING (FRED with User-Agent Fix) ---
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
        except Exception as e:
            st.error(f"Error loading {name}: {e}")
    
    return pd.concat(dfs, axis=1).ffill().dropna()

# --- NEWS FETCHING ENGINE ---
def render_feed(title, url, limit=5):
    with st.expander(f"📖 {title}", expanded=True):
        feed = feedparser.parse(url)
        if not feed.entries:
            st.write("No recent updates found.")
        for entry in feed.entries[:limit]:
            # Clean up timestamp
            ts = entry.get('published', 'No Date')
            st.markdown(f"**[{entry.title}]({entry.link})**")
            st.caption(f"{ts} | {title}")

# --- MAIN UI ---
data = get_mortgage_data()
if not data.empty:
    latest = data.iloc[-1]
    prev = data.iloc[-2]

    # Metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("30Y Fixed", f"{latest['30Y Fixed']}%", f"{round(latest['30Y Fixed']-prev['30Y Fixed'], 3)}%")
    m2.metric("15Y Fixed", f"{latest['15Y Fixed']}%", f"{round(latest['15Y Fixed']-prev['15Y Fixed'], 3)}%")
    m3.metric("10Y Treasury", f"{latest['10Y Treasury']}%", f"{round(latest['10Y Treasury']-prev['10Y Treasury'], 3)}%")

    # Chart
    fig = px.line(data, y=data.columns, title="Rate Trends", template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- THE RSS ENGINE (Organized by Strategy) ---
st.subheader("🎯 Market & Competitor Intelligence")
tab1, tab2, tab3, tab4 = st.tabs(["Key Reporters", "The Big Two (Rocket/UWM)", "Industry News", "Podcasts"])

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        render_feed("Connie Kim (HW)", "https://www.housingwire.com/author/Connie-Kim/feed/")
        render_feed("Flavia Furlan Nunes (HW)", "https://www.housingwire.com/author/Flavia-Furlan-Nunes/feed/")
    with col2:
        render_feed("James Kleimann (HW)", "https://www.housingwire.com/author/James-Kleimann/feed/")

with tab2:
    col1, col2 = st.columns(2)
    with col1:
        st.info("Rocket Mortgage Focus")
        render_feed("Rocket (HW Tag)", "https://www.housingwire.com/tag/rocket-mortgage/feed/")
        render_feed("Rocket Co. Press", "https://www.rocketcompanies.com/feed/?post_type=press_release")
    with col2:
        st.info("UWM Focus")
        render_feed("UWM (BusinessWire)", "https://feed.businesswire.com/rss/home/company/United+Wholesale+Mortgage%2C+LLC/w6euAGJXjezVpz22AaGCsA==?_gl=1*16nikhv*_gcl_au*MzE3OTYyNzg4LjE3MjQ3NjUwMjM.*_ga*MTI5NTUzNDI3OS4xNzI0NzY1MDIz*_ga_ZQWF70T3FK*MTcyNjA2NzQyNC4zLjEuMTcyNjA2NzQzOS40NS4wLjA.")

with tab3:
    render_feed("National Mortgage News", "https://www.nationalmortgagenews.com/feed?rss=true")
    render_feed("Mortgage News Daily", "http://www.mortgagenewsdaily.com/rss/news")

with tab4:
    st.write("🎧 **Latest Audio Briefings**")
    render_feed("NBC News Podcast", "https://podcastfeeds.nbcnews.com/HL4TzgYCw")

st.sidebar.markdown("""
### 🛠️ Dashboard Tools
- **Data Source:** FRED & RSS
- **Refresh:** Hourly
- **Status:** 🟢 Live
""")
