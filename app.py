import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Oil Price Dashboard",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .metric-card {
    background: #1a1a2e;
    border: 1px solid #2d2d44;
    border-radius: 12px;
    padding: 20px 24px;
    text-align: center;
  }
  .metric-label { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 1px; }
  .metric-value { font-size: 32px; font-weight: 700; color: #fff; margin: 4px 0; }
  .metric-delta-up   { font-size: 13px; color: #22c55e; }
  .metric-delta-down { font-size: 13px; color: #ef4444; }
  [data-testid="stAppViewContainer"] { background-color: #0f0f1a; }
  section[data-testid="stSidebar"] { background-color: #13131f; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🛢️ Oil Dashboard")
    st.markdown("---")

    api_key = st.text_input(
        "EIA API Key",
        type="password",
        placeholder="Paste your key here",
        help="Free at eia.gov/opendata/register.php"
    )

    days = st.selectbox(
        "Time Range",
        [30, 60, 90, 180, 365, 730],
        index=2,
        format_func=lambda d: {
            30: "1 Month", 60: "2 Months", 90: "3 Months",
            180: "6 Months", 365: "1 Year", 730: "2 Years"
        }[d]
    )

    show_ma = st.checkbox("Show Moving Averages", value=True)
    show_vol = st.checkbox("Show Volatility Band", value=False)

    st.markdown("---")
    st.caption("Data: U.S. Energy Information Administration (EIA)")
    st.caption("Prices in USD per barrel")

# ── Data fetching ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_eia(api_key: str, series: str, label: str, days: int) -> pd.DataFrame:
    start = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    url = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
    params = {
        "api_key": api_key,
        "frequency": "daily",
        "data[]": "value",
        "facets[series][]": series,
        "start": start,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 500,
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    rows = r.json()["response"]["data"]
    df = pd.DataFrame(rows)[["period", "value"]].rename(columns={"period": "date", "value": label})
    df["date"] = pd.to_datetime(df["date"])
    df[label] = pd.to_numeric(df[label], errors="coerce")
    return df.dropna().sort_values("date").reset_index(drop=True)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_inventory(api_key: str, days: int) -> pd.DataFrame:
    """Weekly crude oil inventory levels (thousand barrels)"""
    start = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    url = "https://api.eia.gov/v2/petroleum/stoc/wstk/data/"
    params = {
        "api_key": api_key,
        "frequency": "weekly",
        "data[]": "value",
        "facets[series][]": "WCRSTUS1",
        "start": start,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 200,
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    rows = r.json()["response"]["data"]
    df = pd.DataFrame(rows)[["period", "value"]].rename(columns={"period": "date", "value": "inventory"})
    df["date"] = pd.to_datetime(df["date"])
    df["inventory"] = pd.to_numeric(df["inventory"], errors="coerce")
    return df.dropna().sort_values("date").reset_index(drop=True)

# ── Main ──────────────────────────────────────────────────────────────────────
if not api_key:
    st.markdown("## 🛢️ Oil Price Research Dashboard")
    st.info("👈 Enter your free EIA API key in the sidebar to get started.  \nGet one at **eia.gov/opendata/register.php** — takes 30 seconds.")
    st.stop()

# Load data
with st.spinner("Fetching data from EIA..."):
    try:
        wti   = fetch_eia(api_key, "RWTC",  "WTI",   days)
        brent = fetch_eia(api_key, "RBRTE", "Brent", days)
        df = wti.merge(brent, on="date", how="inner")
        df["Spread"] = df["Brent"] - df["WTI"]
        df["WTI_MA20"]   = df["WTI"].rolling(20).mean()
        df["Brent_MA20"] = df["Brent"].rolling(20).mean()
        df["WTI_vol"]    = df["WTI"].rolling(20).std()

        inv = fetch_inventory(api_key, days)
    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
        st.caption("Check your API key or try again shortly.")
        st.stop()

# ── Metrics row ───────────────────────────────────────────────────────────────
latest = df.iloc[-1]
prev   = df.iloc[-2] if len(df) > 1 else latest

wti_delta   = latest["WTI"]   - prev["WTI"]
brent_delta = latest["Brent"] - prev["Brent"]
spread_delta = latest["Spread"] - prev["Spread"]

wti_chg_pct   = (wti_delta   / prev["WTI"])   * 100
brent_chg_pct = (brent_delta / prev["Brent"]) * 100

wti_ytd_start = df[df["date"] >= df["date"].iloc[0]]["WTI"].iloc[0]
brent_ytd_start = df[df["date"] >= df["date"].iloc[0]]["Brent"].iloc[0]
wti_ytd   = ((latest["WTI"]   - wti_ytd_start)   / wti_ytd_start)   * 100
brent_ytd = ((latest["Brent"] - brent_ytd_start) / brent_ytd_start) * 100

st.markdown(f"## 🛢️ Oil Price Dashboard &nbsp; <small style='color:#888;font-size:14px'>Updated {latest['date'].strftime('%b %d, %Y')}</small>", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)

def metric(col, label, value, delta, pct, period_chg):
    arrow = "▲" if delta >= 0 else "▼"
    color = "metric-delta-up" if delta >= 0 else "metric-delta-down"
    col.markdown(f"""
    <div class="metric-card">
      <div class="metric-label">{label}</div>
      <div class="metric-value">${value:.2f}</div>
      <div class="{color}">{arrow} ${abs(delta):.2f} ({abs(pct):.1f}%) day</div>
      <div class="{color}" style="font-size:11px;margin-top:2px">Period: {period_chg:+.1f}%</div>
    </div>
    """, unsafe_allow_html=True)

metric(c1, "WTI Crude", latest["WTI"], wti_delta, wti_chg_pct, wti_ytd)
metric(c2, "Brent Crude", latest["Brent"], brent_delta, brent_chg_pct, brent_ytd)

spread_color = "metric-delta-up" if latest["Spread"] >= 0 else "metric-delta-down"
c3.markdown(f"""
<div class="metric-card">
  <div class="metric-label">Brent–WTI Spread</div>
  <div class="metric-value">${latest['Spread']:.2f}</div>
  <div class="{spread_color}">{'▲' if spread_delta >= 0 else '▼'} ${abs(spread_delta):.2f} day change</div>
  <div style="font-size:11px;color:#888;margin-top:2px">Higher = tighter global supply</div>
</div>
""", unsafe_allow_html=True)

if not inv.empty:
    inv_latest = inv.iloc[-1]
    inv_prev   = inv.iloc[-2] if len(inv) > 1 else inv_latest
    inv_chg    = inv_latest["inventory"] - inv_prev["inventory"]
    inv_color  = "metric-delta-down" if inv_chg > 0 else "metric-delta-up"  # build = bearish
    c4.markdown(f"""
    <div class="metric-card">
      <div class="metric-label">US Crude Inventories</div>
      <div class="metric-value">{inv_latest['inventory']:,.0f}K</div>
      <div class="{inv_color}">{'▲' if inv_chg > 0 else '▼'} {abs(inv_chg):,.0f}K bbl weekly</div>
      <div style="font-size:11px;color:#888;margin-top:2px">Build = bearish · Draw = bullish</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Price chart ───────────────────────────────────────────────────────────────
fig_price = go.Figure()

fig_price.add_trace(go.Scatter(
    x=df["date"], y=df["WTI"], name="WTI",
    line=dict(color="#f59e0b", width=2),
    hovertemplate="WTI: $%{y:.2f}<extra></extra>"
))
fig_price.add_trace(go.Scatter(
    x=df["date"], y=df["Brent"], name="Brent",
    line=dict(color="#60a5fa", width=2),
    hovertemplate="Brent: $%{y:.2f}<extra></extra>"
))

if show_ma:
    fig_price.add_trace(go.Scatter(
        x=df["date"], y=df["WTI_MA20"], name="WTI 20-day MA",
        line=dict(color="#f59e0b", width=1, dash="dot"), opacity=0.6
    ))
    fig_price.add_trace(go.Scatter(
        x=df["date"], y=df["Brent_MA20"], name="Brent 20-day MA",
        line=dict(color="#60a5fa", width=1, dash="dot"), opacity=0.6
    ))

if show_vol:
    fig_price.add_trace(go.Scatter(
        x=pd.concat([df["date"], df["date"][::-1]]),
        y=pd.concat([df["WTI"] + df["WTI_vol"], (df["WTI"] - df["WTI_vol"])[::-1]]),
        fill="toself", fillcolor="rgba(245,158,11,0.08)",
        line=dict(color="rgba(255,255,255,0)"),
        name="WTI Volatility Band", showlegend=True
    ))

fig_price.update_layout(
    title="WTI vs Brent Spot Prices (USD/bbl)",
    template="plotly_dark",
    paper_bgcolor="#1a1a2e",
    plot_bgcolor="#13131f",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(l=0, r=0, t=50, b=0),
    height=380,
)
fig_price.update_xaxes(gridcolor="#2d2d44", showspikes=True)
fig_price.update_yaxes(gridcolor="#2d2d44", tickprefix="$")

st.plotly_chart(fig_price, use_container_width=True)

# ── Spread + Inventory ────────────────────────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    fig_spread = go.Figure()
    fig_spread.add_trace(go.Scatter(
        x=df["date"], y=df["Spread"],
        fill="tozeroy",
        fillcolor="rgba(139,92,246,0.15)",
        line=dict(color="#8b5cf6", width=2),
        name="Spread",
        hovertemplate="Spread: $%{y:.2f}<extra></extra>"
    ))
    fig_spread.add_hline(y=0, line_color="#555", line_dash="dash")
    fig_spread.update_layout(
        title="Brent–WTI Spread (USD/bbl)",
        template="plotly_dark",
        paper_bgcolor="#1a1a2e",
        plot_bgcolor="#13131f",
        height=280,
        margin=dict(l=0, r=0, t=50, b=0),
        showlegend=False,
    )
    fig_spread.update_xaxes(gridcolor="#2d2d44")
    fig_spread.update_yaxes(gridcolor="#2d2d44", tickprefix="$")
    st.plotly_chart(fig_spread, use_container_width=True)

with col_right:
    if not inv.empty:
        inv["color"] = inv["inventory"].diff().apply(lambda x: "#ef4444" if x > 0 else "#22c55e")
        fig_inv = go.Figure()
        fig_inv.add_trace(go.Bar(
            x=inv["date"], y=inv["inventory"],
            marker_color=inv["color"].tolist(),
            name="Inventory",
            hovertemplate="Inventory: %{y:,.0f}K bbl<extra></extra>"
        ))
        fig_inv.update_layout(
            title="US Crude Inventories (thousand bbl) — Red=Build, Green=Draw",
            template="plotly_dark",
            paper_bgcolor="#1a1a2e",
            plot_bgcolor="#13131f",
            height=280,
            margin=dict(l=0, r=0, t=50, b=0),
            showlegend=False,
        )
        fig_inv.update_xaxes(gridcolor="#2d2d44")
        fig_inv.update_yaxes(gridcolor="#2d2d44")
        st.plotly_chart(fig_inv, use_container_width=True)

# ── Returns distribution ──────────────────────────────────────────────────────
st.markdown("### Returns & Volatility Analysis")
col_a, col_b = st.columns(2)

df["WTI_ret"]   = df["WTI"].pct_change() * 100
df["Brent_ret"] = df["Brent"].pct_change() * 100

with col_a:
    fig_dist = go.Figure()
    fig_dist.add_trace(go.Histogram(
        x=df["WTI_ret"].dropna(), name="WTI Daily Returns",
        marker_color="#f59e0b", opacity=0.7, nbinsx=40
    ))
    fig_dist.add_trace(go.Histogram(
        x=df["Brent_ret"].dropna(), name="Brent Daily Returns",
        marker_color="#60a5fa", opacity=0.7, nbinsx=40
    ))
    fig_dist.update_layout(
        title="Daily Returns Distribution (%)",
        barmode="overlay",
        template="plotly_dark",
        paper_bgcolor="#1a1a2e",
        plot_bgcolor="#13131f",
        height=280,
        margin=dict(l=0, r=0, t=50, b=0),
        legend=dict(orientation="h", y=1.1),
    )
    fig_dist.update_xaxes(gridcolor="#2d2d44", ticksuffix="%")
    fig_dist.update_yaxes(gridcolor="#2d2d44")
    st.plotly_chart(fig_dist, use_container_width=True)

with col_b:
    df["WTI_roll_vol"]   = df["WTI_ret"].rolling(20).std()
    df["Brent_roll_vol"] = df["Brent_ret"].rolling(20).std()

    fig_vol = go.Figure()
    fig_vol.add_trace(go.Scatter(
        x=df["date"], y=df["WTI_roll_vol"],
        name="WTI 20-day Vol", line=dict(color="#f59e0b", width=2)
    ))
    fig_vol.add_trace(go.Scatter(
        x=df["date"], y=df["Brent_roll_vol"],
        name="Brent 20-day Vol", line=dict(color="#60a5fa", width=2)
    ))
    fig_vol.update_layout(
        title="Rolling 20-day Volatility (%)",
        template="plotly_dark",
        paper_bgcolor="#1a1a2e",
        plot_bgcolor="#13131f",
        height=280,
        margin=dict(l=0, r=0, t=50, b=0),
        legend=dict(orientation="h", y=1.1),
    )
    fig_vol.update_xaxes(gridcolor="#2d2d44")
    fig_vol.update_yaxes(gridcolor="#2d2d44", ticksuffix="%")
    st.plotly_chart(fig_vol, use_container_width=True)

# ── Raw data table ────────────────────────────────────────────────────────────
with st.expander("📋 Raw Data"):
    display_df = df[["date","WTI","Brent","Spread","WTI_ret","Brent_ret"]].copy()
    display_df.columns = ["Date","WTI ($/bbl)","Brent ($/bbl)","Spread ($/bbl)","WTI Return %","Brent Return %"]
    display_df = display_df.sort_values("Date", ascending=False).head(100)
    st.dataframe(display_df.style.format({
        "WTI ($/bbl)": "${:.2f}",
        "Brent ($/bbl)": "${:.2f}",
        "Spread ($/bbl)": "${:.2f}",
        "WTI Return %": "{:.2f}%",
        "Brent Return %": "{:.2f}%",
    }), use_container_width=True)
