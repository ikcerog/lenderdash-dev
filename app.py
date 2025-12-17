import streamlit as st
import pandas as pd
import plotly.express as px
import feedparser
from datetime import datetime

# Page Configuration
st.set_page_config(page_title="Mortgage Industry Live Dashboard", layout="wide")

st.title("🏦 Mortgage Industry Live Dashboard")
st.markdown("Real-time rates and industry news powered by FRED and RSS.")

# --- DATA FETCHING (Zero API Key Required) ---
@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_mortgage_data():
    # FRED CSV URLs (Direct export, no API key needed for basic series)
    urls = {
        "30Y Fixed": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=MORTGAGE30US",
        "15Y Fixed": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=MORTGAGE15US",
        "10Y Treasury": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
    }
    
    dfs = []
    for name, url in urls.items():
        df = pd.read_csv(url)
        df['DATE'] = pd.to_datetime(df['DATE'])
        df = df.rename(columns={df.columns[1]: name})
        # Clean non-numeric FRED placeholders (.)
        df[name] = pd.to_numeric(df[name], errors='coerce')
        dfs.append(df.set_index('DATE'))
    
    combined = pd.concat(dfs, axis=1).ffill().dropna()
    return combined

# --- NEWS FETCHING ---
def get_rss_news(feed_url):
    feed = feedparser.parse(feed_url)
    return feed.entries[:5]  # Top 5 stories

# --- UI LAYOUT ---
data = get_mortgage_data()
latest_rates = data.iloc[-1]
prev_rates = data.iloc[-2]

# Row 1: Key Metrics
col1, col2, col3 = st.columns(3)
with col1:
    delta = round(latest_rates['30Y Fixed'] - prev_rates['30Y Fixed'], 2)
    st.metric("30Y Fixed Average", f"{latest_rates['30Y Fixed']}%", f"{delta}%")
with col2:
    delta_15 = round(latest_rates['15Y Fixed'] - prev_rates['15Y Fixed'], 2)
    st.metric("15Y Fixed Average", f"{latest_rates['15Y Fixed']}%", f"{delta_15}%")
with col3:
    delta_10y = round(latest_rates['10Y Treasury'] - prev_rates['10Y Treasury'], 2)
    st.metric("10Y Treasury Yield", f"{latest_rates['10Y Treasury']}%", f"{delta_10y}%")

# Row 2: Charts
st.subheader("Historical Trends")
fig = px.line(data, x=data.index, y=data.columns, 
              title="Mortgage Rates vs 10Y Yield",
              labels={"value": "Rate (%)", "DATE": "Year"},
              color_discrete_sequence=["#1f77b4", "#ff7f0e", "#2ca02c"])
st.plotly_chart(fig, use_container_width=True)

# Row 3: Industry News (RSS)
st.divider()
n_col1, n_col2 = st.columns(2)

with n_col1:
    st.subheader("📰 Mortgage News Daily")
    mnd_news = get_rss_news("http://www.mortgagenewsdaily.com/rss/news")
    for entry in mnd_news:
        st.markdown(f"**[{entry.title}]({entry.link})**")
        st.caption(f"Published: {entry.published[:16]}")

with n_col2:
    st.subheader("🏠 HousingWire Latest")
    hw_news = get_rss_news("https://www.housingwire.com/feed/")
    for entry in hw_news:
        st.markdown(f"**[{entry.title}]({entry.link})**")
        st.caption(f"Published: {entry.published[:16]}")

st.sidebar.info("Data source: St. Louis Fed (FRED). Update frequency: Weekly/Daily. This dashboard is for informational purposes.")
