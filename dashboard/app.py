"""NEPSE AI Trading Dashboard — Streamlit entry point.

This module is intentionally thin: it owns global page config, shared styling,
authentication, the sidebar navigation menu, and routing. Each page's rendering
logic lives in its own module under ``views/`` and is imported below. Shared
helpers, formatters, and cached API wrappers live in ``common.py``.
"""

import datetime as dt

import requests
import streamlit as st
from common import API_BASE, require_backend_or_safe_mode
from streamlit_option_menu import option_menu
from views import (
    alerts,
    analytics,
    backtesting,
    data_sources,
    explainability,
    factor_analysis,
    features,
    live_signals,
    market_overview,
    ml_models,
    mlops,
    paper_trading,
    signals,
    strategies,
    system_status,
)

# ============================================================================
# PAGE CONFIG & STYLING
# ============================================================================

st.set_page_config(
    page_title="NEPSE AI Trading Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for professional fintech aesthetic
st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    :root {
        --primary: #081D33;
        --secondary: #1E293B;
        --accent: #0EA5E9;
        --success: #10B981;
        --warning: #F59E0B;
        --danger: #EF4444;
        --info: #6366F1;
        --text-primary: #F8FAFC;
        --text-secondary: #CBD5E1;
        --border: #334155;
    }



    .main {
        background: linear-gradient(135deg, #081D33 0%, #1E293B 100%);
        color: var(--text-primary);
    }

    .hero {
        background:
            radial-gradient(circle at top right, rgba(14, 165, 233, 0.18), transparent 30%),
            linear-gradient(135deg, rgba(15, 23, 42, 0.92), rgba(30, 41, 59, 0.72));
        border: 1px solid rgba(14, 165, 233, 0.18);
        border-radius: 20px;
        padding: 1.25rem 1.5rem;
        margin: 0 0 1rem 0;
        box-shadow: 0 18px 50px rgba(2, 6, 23, 0.35);
    }

    .hero h1 {
        font-size: 2rem;
        margin: 0;
        line-height: 1.1;
    }

    .hero p {
        margin: 0.35rem 0 0;
        color: var(--text-secondary);
    }

    .section-label {
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-size: 0.72rem;
        margin-bottom: 0.25rem;
    }

    .stMetric {
        background: rgba(30, 41, 59, 0.6);
        padding: 1.5rem;
        border-radius: 12px;
        border: 1px solid rgba(100, 116, 139, 0.2);
        backdrop-filter: blur(10px);
    }

    .stMetric label {
        font-size: 0.875rem;
        color: var(--text-secondary);
        font-weight: 500;
        letter-spacing: 0.5px;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 1rem;
        border-bottom: 1px solid rgba(100, 116, 139, 0.2);
    }

    .stTabs [aria-selected="true"] {
        border-bottom: 2px solid var(--accent);
    }

    [data-testid="stVerticalBlock"] > [style*="flex-direction: column"] > [data-testid="stVerticalBlock"] {
        background: rgba(30, 41, 59, 0.4);
        border: 1px solid rgba(100, 116, 139, 0.15);
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }

    .stDataFrame {
        font-size: 0.875rem;
    }

    .stDataFrame tbody tr {
        border-bottom: 1px solid rgba(100, 116, 139, 0.1);
    }

    .stat-card {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.8), rgba(30, 41, 59, 0.6));
        border: 1px solid rgba(14, 165, 233, 0.2);
        border-radius: 12px;
        padding: 1.5rem;
        backdrop-filter: blur(20px);
    }

    .profit {
        color: var(--success);
    }

    .loss {
        color: var(--danger);
    }

    /* Typography scale (§2.2) — Inter, tightened headings */
    html, body, [class*="css"], .stMarkdown, .stButton, input, textarea, select {
        font-family: 'Inter', sans-serif;
    }
    h1 { font-size: 2rem; line-height: 1.2; letter-spacing: -0.5px; font-weight: 600; }
    h2 { font-size: 1.5rem; line-height: 1.2; letter-spacing: -0.5px; font-weight: 600; }
    h3 { font-size: 1.25rem; line-height: 1.2; font-weight: 600; }

    /* Buttons (§2.4) — primary filled accent, secondary outlined */
    .stButton > button {
        background: var(--accent);
        color: var(--primary);
        border: none;
        border-radius: 8px;
        font-weight: 600;
        transition: opacity 0.15s ease;
    }
    .stButton > button:hover { opacity: 0.9; color: var(--primary); }
    .stButton > button[kind="secondary"] {
        background: transparent;
        color: var(--accent);
        border: 1px solid var(--accent);
    }

    /* Input fields (§2.4) — translucent slate, accent focus ring */
    .stTextInput input, .stNumberInput input, .stDateInput input,
    .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div {
        background: rgba(30, 41, 59, 0.6);
        border: 1px solid rgba(100, 116, 139, 0.2);
        border-radius: 8px;
    }
    .stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {
        border-color: var(--accent);
        box-shadow: 0 0 0 2px var(--accent);
    }

    /* Tables (§2.4) — header fill, zebra rows, accent hover */
    .stDataFrame thead tr th { background: var(--secondary); color: var(--text-primary); }
    .stDataFrame tbody tr:nth-child(even) { background: rgba(100, 116, 139, 0.1); }
    .stDataFrame tbody tr:hover { background: rgba(14, 165, 233, 0.1); }

    /* Tabs (§2.4) — inactive secondary text, active accent */
    .stTabs [data-baseweb="tab"] { color: var(--text-secondary); }
    .stTabs [aria-selected="true"] { color: var(--accent); }

    /* Alerts/toasts (§2.4) — rounded, accent left rule */
    [data-testid="stAlert"] { border-radius: 8px; border-left: 4px solid var(--accent); }

    /* Loading (§2.4) — accent spinner */
    .stSpinner > div { border-top-color: var(--accent) !important; }

    /* Responsive (§3.4) — stack columns on narrow viewports */
    @media (max-width: 640px) {
        [data-testid="stHorizontalBlock"] { flex-direction: column; }
        .hero h1 { font-size: 1.5rem; }
    }
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================================
# SESSION / AUTH
# ============================================================================

# Initialize auth token in session state
if "auth_token" not in st.session_state:
    st.session_state.auth_token = st.secrets.get("AUTH_TOKEN", "")


# ============================================================================
# NAVIGATION & ROUTING
# ============================================================================

# Sidebar label -> page render function. Order here drives the menu order.
PAGES = {
    "📊 Market Overview": market_overview.page_market_overview,
    "🎯 Strategies": strategies.page_strategies,
    "🧪 Backtesting": backtesting.page_backtesting,
    "📈 Signals": signals.page_signals,
    "📡 Live Signals": live_signals.page_live_signals,
    "📝 Paper Trading": paper_trading.page_paper_trading,
    "🧮 Factor Analysis": factor_analysis.page_factor_analysis,
    "🔧 Features": features.page_features,
    "🗄️ Data Sources": data_sources.page_data_sources,
    "🔔 Alerts": alerts.page_alerts,
    "🖥️ System Status": system_status.page_system_status,
    "🤖 ML Models": ml_models.page_ml_models,
    "📉 Analytics": analytics.page_analytics,
    "⚙️ MLOps": mlops.page_mlops,
    "🔍 Explainability": explainability.page_explainability,
}

# Bootstrap icons matching each page above (one per entry).
PAGE_ICONS = [
    "graph-up",
    "bullseye",
    "flask",
    "bar-chart",
    "broadcast",
    "journal-text",
    "diagram-3",
    "gear",
    "hdd-network",
    "bell",
    "display",
    "robot",
    "graph-down",
    "sliders",
    "search",
]


def main():
    """Main application entry point."""

    # Startup backend check (Phase 6 validation hardening)
    if not require_backend_or_safe_mode():
        st.warning("🛡️ Safe Mode: read-only UI. Backend is required for interactive data.")
        st.stop()

    # Login for authenticated endpoints
    if not st.session_state.auth_token:
        with st.sidebar:
            st.caption("🔐 Authentication")
            email = st.text_input("Email", value="test@example.com", key="auth_email")
            password = st.text_input("Password", type="password", key="auth_pass")
            if st.button("Login", key="auth_login"):
                try:
                    res = requests.post(
                        f"{API_BASE}/auth/login",
                        json={"email": email, "password": password},
                        timeout=10,
                    )
                    if res.status_code == 200:
                        st.session_state.auth_token = res.json().get("access_token", "")
                        st.success("Logged in!")
                    else:
                        st.error("Login failed")
                except Exception as e:
                    st.error(f"Error: {e}")

    # Navigation menu
    with st.sidebar:
        # ponytail: text header over a hot-linked stock photo — no external dep,
        # works offline. Swap in st.image(local_path) if a real logo asset lands.
        st.markdown("## 📈 NEPSE AI")
        st.caption("AI Trading System")
        st.divider()

        # Search filter (§3.1): narrow the flat 15-page menu by label substring.
        query = st.text_input("Search pages", key="nav_search", placeholder="🔍 Filter pages…")
        labels, icons = list(PAGES.keys()), PAGE_ICONS
        if query:
            filtered = [
                (lbl, ic)
                for lbl, ic in zip(labels, PAGE_ICONS, strict=True)
                if query.lower() in lbl.lower()
            ]
            labels, icons = [f[0] for f in filtered], [f[1] for f in filtered]

        if labels:
            page = option_menu(
                "Navigation",
                labels,
                icons=icons,
                menu_icon="list",
                default_index=0,
            )
        else:
            st.caption("No pages match your search.")
            page = None
    # Route to the selected page
    render = PAGES.get(page) if page is not None else None
    if render is not None:
        render()

    # Footer
    st.divider()
    st.caption(f"NEPSE AI Trading System • {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
