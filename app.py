# -*- coding: utf-8 -*-
"""
ניהול אובליגו ומחשבון פריטת צ'קים
Streamlit Web App — Mobile-first + Supabase
"""

import os
from datetime import date, datetime, timedelta
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
import streamlit as st
import streamlit_authenticator as stauth

st.set_page_config(
    page_title="ניהול צ'קים | פריטה",
    page_icon="💸",
    layout="centered",
    initial_sidebar_state="collapsed",
)

STATUSES = ["ממתין למזומן", "להפקדה", "בפריטה"]
STATUS_COLORS = {
    "ממתין למזומן": "#FF9F1C",
    "להפקדה": "#39FF14",
    "בפריטה": "#FF2D95",
}


# ─────────────────────────────────────────────
# DB — Supabase/Postgres
# ─────────────────────────────────────────────
def get_db_url():
    url = st.secrets.get("DATABASE_URL", os.environ.get("DATABASE_URL", ""))
    if not url:
        st.error("❌ חסר DATABASE_URL ב-secrets.")
        st.stop()
    return url


@contextmanager
def get_conn():
    url = get_db_url()
    try:
        conn = psycopg.connect(url, row_factory=dict_row)
    except Exception as e:
        st.error(f"❌ שגיאת חיבור: {e}")
        st.stop()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                name     TEXT NOT NULL,
                password TEXT NOT NULL,
                email    TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id       SERIAL PRIMARY KEY,
                name     TEXT NOT NULL,
                username TEXT NOT NULL DEFAULT 'admin',
                UNIQUE(name, username)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS checks (
                id        SERIAL PRIMARY KEY,
                client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                amount    REAL NOT NULL,
                due_date  DATE NOT NULL,
                status    TEXT NOT NULL,
                remind_on DATE
            )
        """)


def current_user():
    return st.session_state.get("current_user", "admin")


def add_client(name):
    name = name.strip()
    if not name:
        return None
    u = current_user()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO clients (name, username) VALUES (%s, %s) ON CONFLICT (name, username) DO NOTHING",
            (name, u)
        )
        cur.execute("SELECT id FROM clients WHERE name=%s AND username=%s", (name, u))
        row = cur.fetchone()
        return row["id"] if row else None


def get_clients():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name FROM clients WHERE username=%s ORDER BY name",
            (current_user(),)
        )
        return cur.fetchall()


def add_check(client_id, amount, due_date, status, remind_on):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO checks (client_id,amount,due_date,status,remind_on) VALUES (%s,%s,%s,%s,%s)",
            (client_id, amount, due_date, status, remind_on),
        )


def get_checks(client_id=None):
    u = current_user()
    q = """SELECT ch.*, cl.name AS client_name
           FROM checks ch JOIN clients cl ON cl.id=ch.client_id
           WHERE cl.username=%s"""
    params = [u]
    if client_id is not None:
        q += " AND ch.client_id=%s"
        params.append(client_id)
    q += " ORDER BY ch.due_date"
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(q, params)
        return cur.fetchall()


def update_status(check_id, status):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE checks SET status=%s WHERE id=%s", (status, check_id))


def delete_check(check_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM checks WHERE id=%s", (check_id,))


def get_totals():
    u = current_user()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COALESCE(SUM(ch.amount),0) AS total, COUNT(ch.id) AS cnt
            FROM checks ch JOIN clients cl ON cl.id=ch.client_id
            WHERE cl.username=%s
        """, (u,))
        row = cur.fetchone()
        return row["total"], row["cnt"]


def get_client_obligo():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT cl.id, cl.name,
                   COALESCE(SUM(ch.amount),0) AS obligo,
                   COUNT(ch.id) AS cnt
            FROM clients cl
            LEFT JOIN checks ch ON ch.client_id=cl.id
            WHERE cl.username=%s
            GROUP BY cl.id ORDER BY obligo DESC
        """, (current_user(),))
        return cur.fetchall()


def get_upcoming_checks(days_ahead=2):
    u = current_user()
    results = {}
    today = date.today()
    with get_conn() as conn:
        cur = conn.cursor()
        for i in range(days_ahead + 1):
            d = today + timedelta(days=i)
            cur.execute("""
                SELECT ch.id, ch.amount, ch.due_date, ch.status, cl.name AS client_name
                FROM checks ch JOIN clients cl ON cl.id=ch.client_id
                WHERE cl.username=%s AND ch.due_date=%s
                ORDER BY cl.name
            """, (u, d))
            rows = cur.fetchall()
            if rows:
                results[d] = [dict(r) for r in rows]
    return results


def add_checks_batch(client_id, amounts, due_dates, status):
    with get_conn() as conn:
        cur = conn.cursor()
        for amt, dd in zip(amounts, due_dates):
            cur.execute(
                "INSERT INTO checks (client_id,amount,due_date,status,remind_on) VALUES (%s,%s,%s,%s,NULL)",
                (client_id, float(amt), dd, status)
            )


def do_login(username, password):
    username = username.strip()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
    if not user:
        return False, "שם משתמש לא קיים"
    if stauth.Hasher().check_pw(password, user["password"]):
        st.session_state["authentication_status"] = True
        st.session_state["username"] = user["username"]
        st.session_state["name"] = user["name"]
        return True, ""
    return False, "סיסמה שגויה"


def get_cashflow_forecast():
    u = current_user()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT DATE_TRUNC('month', ch.due_date) AS month,
                   SUM(ch.amount) AS total, COUNT(ch.id) AS cnt
            FROM checks ch JOIN clients cl ON cl.id=ch.client_id
            WHERE cl.username=%s AND ch.due_date >= CURRENT_DATE
            GROUP BY 1 ORDER BY 1
        """, (u,))
        return cur.fetchall()


def get_status_breakdown():
    u = current_user()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ch.status, SUM(ch.amount) AS total, COUNT(ch.id) AS cnt
            FROM checks ch JOIN clients cl ON cl.id=ch.client_id
            WHERE cl.username=%s GROUP BY ch.status
        """, (u,))
        return cur.fetchall()



def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Comfortaa:wght@700&family=Inter:wght@400;500;600;700;800;900&display=swap');

    html, body, [class*="css"] { direction: rtl; }

    .stApp {
        background: #041424;
        background-image: linear-gradient(135deg, #041424 0%, #0b243a 50%, #041424 100%);
        font-family: 'Inter', sans-serif;
        color: #dec599;
        min-height: 100vh;
    }
    #MainMenu, header, footer { visibility: hidden; }
    .block-container {
        padding-top: 0 !important;
        padding-bottom: 6rem;
        max-width: 480px;
    }

    /* ─── לוגו ─── */
    .logo-title {
        font-family: 'Comfortaa', sans-serif;
        font-weight: 700;
        font-size: 3rem;
        letter-spacing: -1px;
        background: linear-gradient(135deg, #e59a65 0%, #f0c090 40%, #b06a3b 70%, #e59a65 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        filter: drop-shadow(0px 3px 6px rgba(0,0,0,0.7));
        display: block;
        text-align: center;
        line-height: 1;
        margin-bottom: 4px;
    }

    /* ─── KPI ─── */
    .kpi {
        background: rgba(30, 35, 42, 0.85);
        border: 1px solid rgba(229, 154, 101, 0.25);
        border-radius: 28px;
        padding: 28px 24px 22px;
        margin-bottom: 6px;
        text-align: center;
        box-shadow: 0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(229,154,101,0.15);
    }
    .kpi-label {
        font-size: 11px; font-weight: 700; letter-spacing: 2px;
        color: #e59a65; text-transform: uppercase; margin-bottom: 8px;
    }
    .kpi-value {
        font-family: 'Inter', sans-serif;
        font-size: 3rem; font-weight: 900; line-height: 1;
        background: linear-gradient(135deg, #f0c090 0%, #e59a65 50%, #dec599 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        display: block; letter-spacing: -2px; direction: ltr;
    }
    .kpi-sub { font-size: 13px; color: #8c6a45; margin-top: 10px; font-weight: 500; }

    /* ─── glass card ─── */
    .glass {
        background: rgba(30, 35, 42, 0.7);
        border: 1px solid rgba(229,154,101,0.15);
        border-radius: 24px;
        padding: 20px 22px;
        margin-bottom: 5px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    }

    /* ─── pill ─── */
    .pill {
        display: inline-block; padding: 2px 10px; border-radius: 999px;
        font-size: 11px; font-weight: 700; margin-inline-start: 6px;
    }

    /* ─── section titles ─── */
    .section-title {
        font-size: 22px; font-weight: 900; letter-spacing: -0.5px;
        color: #e59a65; margin: 20px 0 5px; text-align: right;
    }
    .section-title-right {
        font-size: 22px; font-weight: 900; letter-spacing: -0.5px;
        color: #e59a65; margin: 10px 0 5px; text-align: right;
    }
    .neon-bar {
        height: 2px; width: 36px; border-radius: 3px;
        background: linear-gradient(90deg, #e59a65, #b06a3b);
        margin: 0 auto 16px;
    }
    .neon-bar-right {
        height: 2px; width: 36px; border-radius: 3px;
        background: linear-gradient(90deg, #e59a65, #b06a3b);
        margin: 0 0 16px auto;
    }

    /* ─── client card ─── */
    .client-card {
        display: flex; justify-content: space-between; align-items: center;
        background: rgba(30,35,42,0.85);
        border: 1px solid rgba(229,154,101,0.2);
        border-radius: 22px; padding: 16px 18px; margin-bottom: 5px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    }
    .client-name { font-weight: 800; font-size: 1rem; color: #dec599; }
    .client-obligo {
        font-weight: 900; font-size: 1.15rem;
        background: linear-gradient(135deg, #e59a65, #dec599);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        direction: ltr; letter-spacing: -0.5px;
    }

    /* ─── calc output ─── */
    .calc-out { border-radius: 24px; padding: 20px 22px; margin-top: 5px; text-align: center; }
    .calc-out.fee {
        background: rgba(140,42,80,0.25);
        border: 1px solid rgba(255,45,149,0.2);
    }
    .calc-out.net {
        background: rgba(42,122,74,0.25);
        border: 1px solid rgba(57,255,20,0.2);
        margin-top: 5px;
    }
    .calc-out .lbl {
        font-size: 11px; font-weight: 700; letter-spacing: 1.5px;
        text-transform: uppercase; color: #8c6a45; margin-bottom: 6px;
    }
    .calc-out .big {
        font-family: 'Inter', sans-serif; font-size: 2.6rem;
        font-weight: 900; direction: ltr; line-height: 1.1;
        letter-spacing: -1.5px; color: #dec599;
    }

    /* ─── reminder card ─── */
    .reminder-card {
        background: rgba(139,106,0,0.2);
        border: 1px solid rgba(229,154,101,0.25);
        border-radius: 22px; padding: 16px 18px; margin-bottom: 6px;
    }
    .reminder-title {
        font-size: 11px; font-weight: 700; letter-spacing: 1.5px;
        text-transform: uppercase; color: #e59a65; margin-bottom: 8px;
    }
    .reminder-row {
        display: flex; justify-content: space-between; align-items: center;
        padding: 5px 0; border-bottom: 1px solid rgba(229,154,101,0.1);
    }
    .reminder-row:last-child { border-bottom: none; }

    /* ─── buttons general ─── */
    .stButton > button {
        border-radius: 16px !important;
        border: 1px solid rgba(229,154,101,0.2) !important;
        background: rgba(30,35,42,0.9) !important;
        color: #dec599 !important;
        font-weight: 700 !important;
        font-family: 'Inter', sans-serif !important;
        transition: all .15s ease !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3) !important;
    }
    .stButton > button:hover {
        border-color: rgba(229,154,101,0.5) !important;
        box-shadow: 0 4px 20px rgba(229,154,101,0.15) !important;
    }

    /* home nav buttons */
    .home-nav-btn .stButton > button {
        border-radius: 24px !important;
        font-size: 1.15rem !important;
        font-weight: 900 !important;
        min-height: 90px !important;
        height: auto !important;
        padding: 26px 24px !important;
        letter-spacing: -0.3px !important;
    }
    .home-nav-green .stButton > button {
        background: linear-gradient(180deg, #1a3a2a 0%, #0f2318 100%) !important;
        border-color: rgba(57,255,20,0.2) !important;
        color: #6ddf8a !important;
    }
    .home-nav-pink .stButton > button {
        background: linear-gradient(180deg, #2a1a3a 0%, #180f23 100%) !important;
        border-color: rgba(229,154,101,0.3) !important;
        color: #c4a0e0 !important;
    }
    .home-nav-blue .stButton > button {
        background: linear-gradient(180deg, #1a2a3a 0%, #0f1823 100%) !important;
        border-color: rgba(100,160,229,0.3) !important;
        color: #90bfdf !important;
    }

    /* add check buttons */
    .btn-single .stButton > button {
        border-radius: 50px !important;
        background: linear-gradient(135deg, #e59a65 0%, #b06a3b 100%) !important;
        color: #fff !important;
        font-size: 0.92rem !important;
        font-weight: 800 !important;
        padding: 13px 0 !important;
        border: none !important;
        box-shadow: 0 4px 16px rgba(176,106,59,0.4) !important;
    }
    .btn-batch .stButton > button {
        border-radius: 50px !important;
        background: rgba(30,35,42,0.9) !important;
        color: #e59a65 !important;
        font-size: 0.92rem !important;
        font-weight: 800 !important;
        padding: 13px 0 !important;
        border: 1px solid rgba(229,154,101,0.4) !important;
    }

    /* small buttons */
    .btn-sm .stButton > button {
        padding: 3px 8px !important;
        font-size: 0.75rem !important;
        border-radius: 8px !important;
        min-height: 0 !important;
        height: auto !important;
        font-weight: 700 !important;
    }

    /* back button */
    .back-btn { position: fixed !important; bottom: 28px !important; left: 20px !important; z-index: 9999 !important; }
    .back-btn .stButton > button {
        border-radius: 50px !important;
        background: linear-gradient(135deg, #e59a65 0%, #b06a3b 100%) !important;
        color: #fff !important;
        font-size: 0.82rem !important;
        font-weight: 800 !important;
        padding: 10px 22px !important;
        height: auto !important;
        min-height: 0 !important;
        border: none !important;
        box-shadow: 0 4px 20px rgba(176,106,59,0.5) !important;
    }

    /* inputs */
    .stTextInput input, .stNumberInput input, .stDateInput input,
    [data-baseweb="input"] input, [data-baseweb="base-input"] input {
        color: #dec599 !important;
        background-color: rgba(30,35,42,0.9) !important;
        -webkit-text-fill-color: #dec599 !important;
        caret-color: #e59a65 !important;
        border-radius: 14px !important;
        border: 1px solid rgba(229,154,101,0.2) !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        direction: rtl !important;
        text-align: right !important;
    }
    .stTextInput div[data-baseweb="input"], .stNumberInput div[data-baseweb="input"],
    .stDateInput div[data-baseweb="input"], div[data-baseweb="select"] > div {
        background-color: rgba(30,35,42,0.9) !important;
        border: 1px solid rgba(229,154,101,0.2) !important;
        border-radius: 14px !important;
    }
    div[data-baseweb="select"] div { color: #dec599 !important; font-weight: 600 !important; }
    input::placeholder { color: #5a4030 !important; opacity: 1 !important; }

    div[data-testid="stNumberInput"]:has(input[aria-label*="סכום"]) input {
        font-size: 1.8rem !important; font-weight: 900 !important;
        text-align: center !important; letter-spacing: -1px !important; height: 64px !important;
    }

    label {
        color: #8c6a45 !important; font-weight: 700 !important;
        font-size: 11px !important; letter-spacing: 0.8px !important;
        text-transform: uppercase !important; text-align: right !important; display: block !important;
    }

    /* radio */
    div[data-testid="stRadio"] > div { gap: 8px !important; justify-content: center !important; }
    div[data-testid="stRadio"] label {
        background: rgba(30,35,42,0.9) !important;
        border: 1px solid rgba(229,154,101,0.2) !important;
        border-radius: 14px !important; padding: 10px 28px !important;
        font-size: 0.95rem !important; font-weight: 800 !important;
        color: #dec599 !important; cursor: pointer;
        text-transform: none !important; letter-spacing: 0 !important;
    }
    div[data-testid="stRadio"] label:hover { border-color: rgba(229,154,101,0.5) !important; }
    div[data-testid="stRadio"] input[type="radio"] { display: none !important; }
    div[data-testid="stRadio"] div[data-baseweb="radio"] > div:first-child { display: none !important; }

    /* tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 5px; justify-content: center; background: transparent !important; }
    .stTabs [data-baseweb="tab"] {
        background: rgba(30,35,42,0.9) !important;
        border: 1px solid rgba(229,154,101,0.15) !important;
        border-radius: 14px !important; padding: 10px 22px !important;
        font-size: 0.9rem !important; font-weight: 700 !important;
        color: #8c6a45 !important; min-width: 120px; text-align: center;
    }
    .stTabs [data-baseweb="tab"] p, .stTabs [data-baseweb="tab"] span,
    .stTabs [data-baseweb="tab"] div { color: #8c6a45 !important; }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #e59a65 0%, #b06a3b 100%) !important;
        border-color: transparent !important;
    }
    .stTabs [aria-selected="true"] p, .stTabs [aria-selected="true"] span,
    .stTabs [aria-selected="true"] div { color: #fff !important; }

    /* expander */
    .streamlit-expanderHeader {
        background: rgba(30,35,42,0.9) !important;
        border-radius: 14px !important; font-weight: 700 !important;
        color: #dec599 !important; border: 1px solid rgba(229,154,101,0.15) !important;
    }
    .streamlit-expanderContent {
        background: rgba(20,25,32,0.8) !important; border: none !important;
    }

    /* checkbox */
    .stCheckbox label {
        color: #dec599 !important; font-weight: 700 !important;
        font-size: 0.9rem !important; text-transform: none !important; letter-spacing: 0 !important;
    }

    /* select dropdown */
    ul[role="listbox"], div[data-baseweb="popover"] {
        background-color: #0b1a2a !important;
        border: 1px solid rgba(229,154,101,0.2) !important;
        border-radius: 16px !important;
    }
    ul[role="listbox"] li { color: #dec599 !important; font-weight: 600 !important; }

    /* data editor */
    .stDataFrame, [data-testid="stDataEditor"] {
        border-radius: 16px !important; overflow: hidden !important; border: none !important;
    }

    /* dashboard cards */
    .forecast-card {
        background: rgba(30,35,42,0.85);
        border: 1px solid rgba(229,154,101,0.15);
        border-radius: 22px; padding: 16px 18px; margin-bottom: 5px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    }
    .forecast-month { font-size: 11px; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; color: #8c6a45; margin-bottom: 4px; }
    .forecast-amount { font-size: 1.4rem; font-weight: 900; color: #dec599; direction: ltr; }
    .forecast-bar-bg { background: rgba(255,255,255,0.06); border-radius: 99px; height: 5px; margin-top: 8px; }
    .forecast-bar-fill { background: linear-gradient(90deg, #e59a65, #b06a3b); border-radius: 99px; height: 5px; }
    </style>
    """, unsafe_allow_html=True)

    st.components.v1.html("""
    <script>
    function attachSelectAll() {
        var inputs = window.parent.document.querySelectorAll('input[type="number"]');
        inputs.forEach(function(inp) {
            if (inp._sa) return;
            inp._sa = true;
            inp.addEventListener('focus', function() {
                var s = this; setTimeout(function(){ s.select(); }, 50);
            });
        });
    }
    attachSelectAll();
    setInterval(attachSelectAll, 600);
    </script>
    """, height=0)


def fmt_ils(x):
    return f"₪{x:,.0f}"

def calc_fee(amount, due_date, rate_val, rate_basis):
    """חישוב עמלת פריטה"""
    days = max((due_date - date.today()).days + 1, 0)
    if rate_basis == "חודשית":
        fee = float(amount) * (rate_val / 100.0) * (days / 30.0)
    else:
        fee = float(amount) * (rate_val / 100.0) * (days / 365.0)
    return fee, days


def fmt_date(d):
    """ממיר תאריך לפורמט עברי DD.MM.YYYY"""
    if not d:
        return ""
    try:
        if isinstance(d, str):
            d = datetime.fromisoformat(d).date()
        return d.strftime("%d.%m.%Y")
    except Exception:
        return str(d)



# ─────────────────────────────────────────────
# מסך התחברות / הרשמה
# ─────────────────────────────────────────────
def get_upcoming_checks(days_ahead=2):
    u = current_user()
    results = {}
    today = date.today()
    with get_conn() as conn:
        cur = conn.cursor()
        for i in range(days_ahead + 1):
            d = today + timedelta(days=i)
            cur.execute("""
                SELECT ch.id, ch.amount, ch.due_date, ch.status, cl.name AS client_name
                FROM checks ch JOIN clients cl ON cl.id=ch.client_id
                WHERE cl.username=%s AND ch.due_date=%s
                ORDER BY cl.name
            """, (u, d))
            rows = cur.fetchall()
            if rows:
                results[d] = [dict(r) for r in rows]
    return results


def add_checks_batch(client_id, amounts, due_dates, status):
    with get_conn() as conn:
        cur = conn.cursor()
        for amt, dd in zip(amounts, due_dates):
            cur.execute(
                "INSERT INTO checks (client_id,amount,due_date,status,remind_on) VALUES (%s,%s,%s,%s,NULL)",
                (client_id, float(amt), dd, status)
            )


def do_login(username, password):
    username = username.strip()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
    if not user:
        return False, "שם משתמש לא קיים"
    if stauth.Hasher().check_pw(password, user["password"]):
        st.session_state["authentication_status"] = True
        st.session_state["username"] = user["username"]
        st.session_state["name"] = user["name"]
        return True, ""
    return False, "סיסמה שגויה"


def render_auth_screen():
    st.markdown(
        "<div style='height:40px'></div>"
        "<p style='text-align:center;font-size:12px;font-weight:700;letter-spacing:3px;"
        "color:#8c6a45;text-transform:uppercase;margin-bottom:4px;letter-spacing:3px;'>CHECK MANAGEMENT</p>"
        "<h1><span class='logo-title'>CHECKFLOW</span></h1>"
        "<p style='text-align:center;color:rgba(255,255,255,0.7);font-size:0.9rem;"
        "font-weight:500;margin-bottom:28px;'>ניהול צ׳קים ופריטה</p>",
        unsafe_allow_html=True,
    )

    tab_login, tab_register = st.tabs(["🔑  כניסה", "📝  הרשמה"])

    with tab_login:
        with st.form("login_form", clear_on_submit=False):
            l_user = st.text_input("שם משתמש", key="l_user")
            l_pass = st.text_input("סיסמה", type="password", key="l_pass")
            login_btn = st.form_submit_button("כניסה →", use_container_width=True)
        if login_btn:
            ok, msg = do_login(l_user, l_pass)
            if ok:
                st.rerun()
            else:
                st.error(msg)

    with tab_register:
        st.markdown("#### צור חשבון חדש")
        with st.form("reg_form", clear_on_submit=True):
            r_user  = st.text_input("שם משתמש (אנגלית)", key="r_user")
            r_name  = st.text_input("שם מלא", key="r_name")
            r_email = st.text_input("אימייל", key="r_email")
            r_pass  = st.text_input("סיסמה (6+ תווים)", type="password", key="r_pass")
            r_pass2 = st.text_input("אימות סיסמה", type="password", key="r_pass2")
            submitted = st.form_submit_button("הרשמה ✅", use_container_width=True)

        if submitted:
            r_user = r_user.strip(); r_name = r_name.strip(); r_email = r_email.strip()
            if not all([r_user, r_name, r_email, r_pass]):
                st.error("יש למלא את כל השדות.")
            elif len(r_pass) < 6:
                st.error("הסיסמה חייבת להכיל לפחות 6 תווים.")
            elif r_pass != r_pass2:
                st.error("הסיסמאות אינן תואמות.")
            else:
                with get_conn() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT 1 FROM users WHERE username=%s", (r_user,))
                    exists = cur.fetchone()
                if exists:
                    st.error("שם המשתמש כבר קיים.")
                else:
                    hashed = stauth.Hasher().hash(r_pass)
                    with get_conn() as conn:
                        cur = conn.cursor()
                        cur.execute(
                            "INSERT INTO users (username,name,password,email) VALUES (%s,%s,%s,%s)",
                            (r_user, r_name, hashed, r_email)
                        )
                    st.success("נרשמת בהצלחה! עבור ללשונית 'כניסה' והתחבר. 🎉")


# ─────────────────────────────────────────────
# מסך ראשי
# ─────────────────────────────────────────────
def render_home_screen():
    # בדיקת query param לתמיכה בכפתור חזור
    qp = st.query_params.get("s", None)
    if qp in ("calc", "mgmt", "dash"):
        st.session_state.screen = qp
        st.rerun()

    st.markdown(
        "<div style='height:40px'></div>"
        "<p style='text-align:center;font-size:12px;font-weight:700;letter-spacing:3px;"
        "color:#8c6a45;text-transform:uppercase;margin-bottom:4px;letter-spacing:3px;'>CHECK MANAGEMENT</p>"
        "<h1><span class='logo-title'>CHECKFLOW</span></h1>"
        "<p style='text-align:center;color:#8A8A93;font-size:0.9rem;margin-bottom:28px;"
        "font-weight:500;'>ניהול צ׳קים ופריטה</p>",
        unsafe_allow_html=True,
    )

    render_kpi()

    st.markdown('<div class="home-nav-btn home-nav-green">', unsafe_allow_html=True)
    if st.button("🧮  מחשבון פריטה", key="go_calc", use_container_width=True):
        st.session_state.screen = "calc"
        st.rerun()
    st.markdown('</div><div style="height:14px"></div>', unsafe_allow_html=True)

    st.markdown('<div class="home-nav-btn home-nav-pink">', unsafe_allow_html=True)
    if st.button("📋  ניהול צ׳קים", key="go_mgmt", use_container_width=True):
        st.session_state.screen = "mgmt"
        st.rerun()
    st.markdown('</div><div style="height:14px"></div>', unsafe_allow_html=True)

    st.markdown('<div class="home-nav-btn" style="background:#C4CEFF;">', unsafe_allow_html=True)
    st.markdown('<style>.home-nav-dash .stButton > button { background: #C4CEFF !important; }</style>', unsafe_allow_html=True)
    if st.button("📊  דשבורד תזרים", key="go_dash", use_container_width=True):
        st.session_state.screen = "dash"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────
# כפתור חזרה
# ─────────────────────────────────────────────
def render_back_button():
    st.markdown('<div class="back-btn">', unsafe_allow_html=True)
    if st.button("← ראשי", key="back_home"):
        st.session_state.screen = "home"
        st.query_params.clear()
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────
# KPI
# ─────────────────────────────────────────────
def render_kpi():
    total, cnt = get_totals()
    st.markdown(f"""
    <div class="kpi">
        <div class="kpi-label">סך הצ'קים שביד כרגע</div>
        <div class="kpi-value">{fmt_ils(total)}</div>
        <div class="kpi-sub">{cnt} צ'קים פיזיים בארנק 💸</div>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# הוספת צ'ק
# ─────────────────────────────────────────────
def render_upcoming_reminder():
    upcoming = get_upcoming_checks(days_ahead=2)
    if not upcoming:
        return  # אין פירעונות — לא מציג כלום

    day_labels = {
        date.today():                     "היום",
        date.today() + timedelta(days=1): "מחר",
        date.today() + timedelta(days=2): "מחרתיים",
    }

    total_checks = sum(len(v) for v in upcoming.values())
    total_amount = sum(ch["amount"] for v in upcoming.values() for ch in v)

    header = (
        "<div class='reminder-card'>"
        "<div class='reminder-title'>⏰ פירעונות קרובים</div>"
        "<div style='display:flex;justify-content:space-between;'>"
        f"<span style='font-weight:800;font-size:1rem;color:#000;'>{total_checks} צ'קים</span>"
        f"<span style='font-weight:900;font-size:1rem;color:#000;'>{fmt_ils(total_amount)}</span>"
        "</div></div>"
    )
    st.markdown(header, unsafe_allow_html=True)

    expanded = st.session_state.get("reminder_open", False)
    btn_label = "📋 פרטים מלאים" if not expanded else "✖ סגור"
    if st.button(btn_label, key="toggle_reminder"):
        st.session_state.reminder_open = not expanded
        st.rerun()

    if not st.session_state.get("reminder_open", False):
        return

    for d, checks in sorted(upcoming.items()):
        label   = day_labels.get(d, d.strftime("%d.%m"))
        day_sum = sum(ch["amount"] for ch in checks)
        bg_map  = {
            date.today():                     "#D6F5E0",
            date.today() + timedelta(days=1): "#E8E4FF",
            date.today() + timedelta(days=2): "#FFF3C8",
        }
        bg = bg_map.get(d, "#F0F0F5")
        date_str   = d.strftime("%d.%m.%Y")
        total_str  = fmt_ils(day_sum)
        header_day = (
            f"<div style='background:{bg};border-radius:18px;"
            f"padding:14px 16px;margin-bottom:6px;'>"
            f"<div style='font-size:11px;font-weight:700;letter-spacing:1.2px;"
            f"text-transform:uppercase;color:#555;margin-bottom:8px;'>"
            f"{label} — {date_str} | {total_str}</div>"
        )
        rows_html = ""
        for ch in checks:
            rows_html += (
                "<div class='reminder-row'>"
                f"<span style='font-weight:700;color:#000;'>{ch['client_name']}</span>"
                f"<span style='font-weight:900;color:#000;'>{fmt_ils(ch['amount'])}</span>"
                "</div>"
            )
        st.markdown(header_day + rows_html + "</div>", unsafe_allow_html=True)


def render_add_check_form():
    clients = get_clients()
    names   = [c["name"] for c in clients]

    # ── שני כפתורים ──
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="btn-single">', unsafe_allow_html=True)
        if st.button("➕ צ'ק בודד", key="open_single", use_container_width=True):
            st.session_state.add_mode = "single" if st.session_state.get("add_mode") != "single" else None
        st.markdown('</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="btn-batch">', unsafe_allow_html=True)
        if st.button("📦 מקבץ צ'קים", key="open_batch", use_container_width=True):
            st.session_state.add_mode = "batch" if st.session_state.get("add_mode") != "batch" else None
        st.markdown('</div>', unsafe_allow_html=True)

    # הצגת סיכום אחרי שמירת מקבץ
    if "batch_summary" in st.session_state and st.session_state.batch_summary:
        bs = st.session_state.batch_summary
        st.markdown(
            f"<div style='background:#D6F5E0;border-radius:22px;padding:18px 20px;margin-bottom:10px;'>"
            f"<div style='font-size:11px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;"
            f"color:#2A7A4A;margin-bottom:10px;'>✅ {bs['count']} צ\'קים נשמרו | ריבית {bs['rate_val']:.2f}% {bs['rate_basis']}</div>",
            unsafe_allow_html=True
        )
        import pandas as pd
        df_sum = pd.DataFrame(bs["rows"])
        st.dataframe(df_sum, use_container_width=True, hide_index=True)
        fee_str = fmt_ils(bs["total_fee"])
        net_str = fmt_ils(bs["total_net"])
        st.markdown(
            "<div style='display:flex;justify-content:space-between;"
            "padding:10px 4px 4px;font-weight:800;font-size:1rem;color:#000;'>"
            f"<span>סהכ עמלות: {fee_str}</span>"
            f"<span>סהכ נטו: {net_str}</span>"
            "</div></div>",
            unsafe_allow_html=True
        )
        if st.button("✖ סגור סיכום", key="close_summary"):
            st.session_state.batch_summary = None
            st.rerun()

    mode = st.session_state.get("add_mode")
    if not mode:
        return

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── בחירת לקוח משותפת ──
    sel = st.selectbox("לקוח", ["— חדש —"] + names, key="add_client_sel")
    if sel == "— חדש —":
        new_name = st.text_input("שם לקוח חדש", key="new_client_name",
                                  placeholder="הזן שם לקוח...")
    else:
        new_name = None

    # ════════════════════
    # מסלול א׳ — צ'ק בודד
    # ════════════════════
    if mode == "single":
        amount = st.number_input("סכום הצ'ק (₪)", min_value=0.0, step=100.0,
                                 format="%.0f", key="add_amount")
        c1, c2 = st.columns(2)
        with c1:
            due = st.date_input("תאריך פירעון",
                                value=date.today() + timedelta(days=30),
                                min_value=date.today(), key="add_due")
        with c2:
            use_remind = st.checkbox("הוסף תזכורת", value=False, key="add_use_remind")
        remind = None
        if use_remind:
            remind = st.date_input("תאריך תזכורת",
                                   value=date.today() + timedelta(days=30),
                                   min_value=date.today(), key="add_remind")
        status = st.selectbox("סטטוס", STATUSES, key="add_status")

        # ── ריבית ──
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        ra, rb = st.columns(2)
        with ra:
            single_rate = st.number_input("ריבית (%)", min_value=0.0, max_value=100.0,
                                          value=float(st.session_state.get("fixed_rate", 12.0)),
                                          step=0.1, format="%.2f", key="single_rate")
        with rb:
            single_basis = st.radio("בסיס", ["חודשית", "שנתית"],
                                    index=["חודשית","שנתית"].index(
                                        st.session_state.get("rate_basis","שנתית")),
                                    key="single_basis", horizontal=True)
        # שמירה בsession לשימוש במחשבון
        st.session_state.fixed_rate = single_rate
        st.session_state.rate_basis = single_basis

        # ── תצוגה חיה ──
        if amount > 0:
            fee, days = calc_fee(amount, due, single_rate, single_basis)
            net = amount - fee
            st.markdown(
                f"<div style='background:#FFF3C8;border-radius:18px;padding:14px 16px;"
                f"margin:8px 0;display:flex;justify-content:space-between;'>"
                f"<div style='text-align:center;'>"
                f"<div style='font-size:11px;font-weight:700;color:#8A6A00;'>{days} ימים</div>"
                f"<div style='font-weight:900;font-size:1rem;color:#000;'>{fmt_ils(fee)}</div>"
                f"<div style='font-size:11px;color:#8A6A00;'>עמלה</div></div>"
                f"<div style='text-align:center;'>"
                f"<div style='font-size:11px;font-weight:700;color:#2A7A4A;'>נטו מזומן</div>"
                f"<div style='font-weight:900;font-size:1.2rem;color:#000;'>{fmt_ils(net)}</div>"
                f"<div style='font-size:11px;color:#2A7A4A;'>מתקבל</div></div>"
                f"</div>",
                unsafe_allow_html=True
            )

        if st.button("💾 שמירת צ'ק", use_container_width=True, key="save_single"):
            cid = add_client(new_name or "") if sel == "— חדש —" else                   next((c["id"] for c in clients if c["name"] == sel), None)
            if not cid:
                st.error("נא לבחור או להזין שם לקוח.")
            elif amount <= 0:
                st.error("נא להזין סכום גדול מאפס.")
            else:
                add_check(cid, amount, due, status, remind)
                st.session_state.add_mode = None
                st.rerun()

    # ════════════════════
    # מסלול ב׳ — מקבץ
    # ════════════════════
    elif mode == "batch":
        import pandas as pd

        amount_base = st.number_input("סכום לכל צ'ק (₪)", min_value=0.0, step=100.0,
                                      format="%.0f", key="batch_amount")
        b1, b2, b3 = st.columns(3)
        with b1:
            first_date = st.date_input("תאריך ראשון",
                                       value=date.today() + timedelta(days=30),
                                       min_value=date.today(), key="batch_first")
        with b2:
            count = st.number_input("מספר צ'קים", min_value=2, max_value=36,
                                    value=4, step=1, key="batch_count", format="%d")
        with b3:
            gap = st.number_input("קפיצה (ימים)", min_value=1, max_value=90,
                                  value=30, step=1, key="batch_gap", format="%d")
        status = st.selectbox("סטטוס", STATUSES, key="batch_status")

        # ── ריבית ──
        ba, bb = st.columns(2)
        with ba:
            batch_rate = st.number_input("ריבית (%)", min_value=0.0, max_value=100.0,
                                         value=float(st.session_state.get("fixed_rate", 12.0)),
                                         step=0.1, format="%.2f", key="batch_rate")
        with bb:
            batch_basis = st.radio("בסיס", ["חודשית", "שנתית"],
                                   index=["חודשית","שנתית"].index(
                                       st.session_state.get("rate_basis","שנתית")),
                                   key="batch_basis", horizontal=True)
        st.session_state.fixed_rate = batch_rate
        st.session_state.rate_basis = batch_basis

        # בניית הטבלה
        if st.button("🔄 צור טבלת עריכה", use_container_width=True, key="gen_table"):
            rows = []
            for i in range(int(count)):
                d = first_date + timedelta(days=int(gap) * i)
                rows.append({
                    "#": i+1,
                    "סכום (₪)": float(amount_base),
                    "תאריך": d.isoformat(),
                })
            # סדר עמודות RTL: # ימין, סכום אמצע, תאריך שמאל
            st.session_state.batch_df = pd.DataFrame(rows)[["#", "סכום (₪)", "תאריך"]]

        if "batch_df" in st.session_state and st.session_state.batch_df is not None:
            st.markdown("**ערוך לפי הצורך — לחץ על תא לשינוי:**")
            # RTL wrapper
            st.markdown("<div style='direction:rtl;'>", unsafe_allow_html=True)
            edited = st.data_editor(
                st.session_state.batch_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "#": st.column_config.NumberColumn(disabled=True, width="small"),
                    "סכום (₪)": st.column_config.NumberColumn(min_value=0, format="%.0f"),
                    "תאריך": st.column_config.TextColumn(),
                },
                key="batch_editor"
            )
            st.markdown("</div>", unsafe_allow_html=True)

            # כוונון עדין — כפתורי +/- קומפקטיים
            st.markdown(
                "<div style='font-size:11px;font-weight:700;letter-spacing:1px;"
                "text-transform:uppercase;color:#8A8A93;"
                "margin:10px 0 4px;text-align:right;letter-spacing:1px;'>כוונון תאריך</div>",
                unsafe_allow_html=True
            )
            for idx, row in edited.iterrows():
                date_val = str(row["תאריך"])
                row_html = (
                    f"<div style='display:flex;align-items:center;justify-content:space-between;"
                    f"background:rgba(255,255,255,0.10);border-radius:12px;"
                    f"padding:6px 10px;margin-bottom:4px;direction:rtl;'>"
                    f"<span style='font-size:12px;font-weight:800;color:#fff;min-width:24px;'>"
                    f"#{int(row['#'])}</span>"
                    f"<span style='font-size:13px;font-weight:700;color:#fff;flex:1;text-align:center;'>"
                    f"{date_val}</span>"
                    f"</div>"
                )
                st.markdown(row_html, unsafe_allow_html=True)
                ca, cb = st.columns([1, 1])
                with ca:
                    if st.button(f"− יום", key=f"dm_{idx}", use_container_width=True):
                        try:
                            d = datetime.fromisoformat(date_val).date()
                        except Exception:
                            d = date.today()
                        edited.at[idx, "תאריך"] = (d - timedelta(days=1)).isoformat()
                        st.session_state.batch_df = edited
                        st.rerun()
                with cb:
                    if st.button(f"+ יום", key=f"dp_{idx}", use_container_width=True):
                        try:
                            d = datetime.fromisoformat(date_val).date()
                        except Exception:
                            d = date.today()
                        edited.at[idx, "תאריך"] = (d + timedelta(days=1)).isoformat()
                        st.session_state.batch_df = edited
                        st.rerun()

            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            if st.button("💾 שמור את כל הצ'קים", use_container_width=True, key="save_batch"):
                cid = add_client(new_name or "") if sel == "— חדש —" else                       next((c["id"] for c in clients if c["name"] == sel), None)
                if not cid:
                    st.error("נא לבחור או להזין שם לקוח.")
                else:
                    amounts   = edited["סכום (₪)"].tolist()
                    due_dates = [datetime.fromisoformat(str(d)).date() for d in edited["תאריך"].tolist()]
                    add_checks_batch(cid, amounts, due_dates, status)
                    saved = len(amounts)

                    # ── סיכום עמלות לפי ריבית קבועה ──
                    rate_val   = st.session_state.get("fixed_rate", 12.0)
                    rate_basis = st.session_state.get("rate_basis", "שנתית")
                    today = date.today()
                    summary_rows = []
                    total_fee = 0.0
                    total_net = 0.0
                    for amt, dd in zip(amounts, due_dates):
                        days = max((dd - today).days + 1, 0)
                        if rate_basis == "חודשית":
                            fee = float(amt) * (rate_val / 100.0) * (days / 30.0)
                        else:
                            fee = float(amt) * (rate_val / 100.0) * (days / 365.0)
                        net = float(amt) - fee
                        total_fee += fee
                        total_net += net
                        summary_rows.append({
                            "תאריך": fmt_date(dd),
                            "סכום": fmt_ils(amt),
                            "עמלה": fmt_ils(fee),
                            "נטו": fmt_ils(net),
                        })

                    st.session_state.batch_summary = {
                        "rows": summary_rows,
                        "total_fee": total_fee,
                        "total_net": total_net,
                        "count": saved,
                        "rate_val": rate_val,
                        "rate_basis": rate_basis,
                    }
                    st.session_state.add_mode = None
                    st.session_state.batch_df = None
                    st.rerun()

# ─────────────────────────────────────────────
# רשימת לקוחות
# ─────────────────────────────────────────────
# פלטת צבעי פסטל ללקוחות
CLIENT_PALETTE = [
    ("#E8E4FF", "#5A5AA3"),
    ("#D6F5E0", "#2A7A4A"),
    ("#FFD6E8", "#8A2A50"),
    ("#E8F5A3", "#5A6800"),
    ("#FFF3C8", "#8A6A00"),
    ("#C8E8FF", "#1A5A8A"),
    ("#FFE8D6", "#8A3A00"),
]

def render_clients():
    st.markdown('<div class="section-title">הלקוחות שלי</div>', unsafe_allow_html=True)
    st.markdown('<div class="neon-bar"></div>', unsafe_allow_html=True)

    rows = [r for r in get_client_obligo() if r["cnt"] > 0]
    if not rows:
        st.markdown('<div class="glass">אין עדיין צ\'קים ⬆️</div>', unsafe_allow_html=True)
        return

    for i, r in enumerate(rows):
        bg, txt = CLIENT_PALETTE[i % len(CLIENT_PALETTE)]
        st.markdown(f"""
        <div class="client-card" style="background:{bg};">
            <div>
                <div class="client-name">{r['name']}</div>
                <div style="font-size:.82rem;color:{txt};font-weight:600;">{r['cnt']} צ'קים</div>
            </div>
            <div class="client-obligo">{fmt_ils(r['obligo'])}</div>
        </div>""", unsafe_allow_html=True)

        with st.expander("צפייה בצ'קים"):
            for ch in get_checks(r["id"]):
                color = STATUS_COLORS.get(ch["status"], "#888")
                remind_str = f" | תזכורת: {ch['remind_on']}" if ch["remind_on"] else ""
                cc1, cc2 = st.columns([3, 2])
                with cc1:
                    st.markdown(f"""
                    <div style="padding:6px 0;">
                        <span style="font-family:'Orbitron';font-weight:700;direction:ltr;">
                            {fmt_ils(ch['amount'])}</span><br>
                        <span style="font-size:.8rem;color:rgba(255,255,255,0.75);">
                            פירעון: {fmt_date(ch['due_date'])}{remind_str}</span>
                        <span class="pill" style="background:{color}22;color:{color};
                            border:1px solid {color}66;">{ch['status']}</span>
                    </div>""", unsafe_allow_html=True)
                with cc2:
                    new_st = st.selectbox("סטטוס", STATUSES,
                                          index=STATUSES.index(ch["status"]),
                                          key=f"st_{ch['id']}", label_visibility="collapsed")
                    st.markdown('<div class="btn-sm">', unsafe_allow_html=True)
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("✓", key=f"upd_{ch['id']}", use_container_width=True):
                            update_status(ch["id"], new_st)
                            st.rerun()
                    with b2:
                        if st.button("🗑", key=f"del_{ch['id']}", use_container_width=True):
                            delete_check(ch["id"])
                            st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────
# מחשבון פריטה
# ─────────────────────────────────────────────
def render_calculator():
    st.markdown('<div class="section-title-right">מחשבון פריטה (ניכיון)</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="neon-bar-right"></div>', unsafe_allow_html=True)

    if "fixed_rate"    not in st.session_state: st.session_state.fixed_rate    = 12.0
    if "rate_basis"    not in st.session_state: st.session_state.rate_basis    = "שנתית"
    if "rate_edit_open" not in st.session_state: st.session_state.rate_edit_open = False

    checks  = get_checks()
    options = ["— הזנה ידנית —"] + [
        f"{c['client_name']} | {fmt_ils(c['amount'])} | {c['due_date']}" for c in checks
    ]
    pick = st.selectbox("בחר צ'ק קיים (או הזנה ידנית)", options, key="calc_pick")

    default_amount = 10000.0
    default_due    = date.today() + timedelta(days=30)
    if pick != "— הזנה ידנית —":
        idx = options.index(pick) - 1
        ch  = checks[idx]
        default_amount = float(ch["amount"])
        try:    default_due = datetime.fromisoformat(ch["due_date"]).date()
        except: default_due = date.today() + timedelta(days=30)

    # כשמשנים צ'ק — מאפסים את המפתח כדי לאלץ עדכון הסכום
    if st.session_state.get("_last_pick") != pick:
        st.session_state.calc_due    = default_due
        st.session_state.calc_amount = default_amount
        st.session_state._last_pick  = pick

    amount = st.number_input("סכום הצ'ק (₪)", min_value=0.0, step=100.0,
                             value=st.session_state.get("calc_amount", default_amount),
                             format="%.0f", key="calc_amount")

    due_date = st.date_input("תאריך פירעון הצ'ק", key="calc_due",
                             min_value=date.today(),
                             help="החישוב מתחיל ממחר וכולל את יום הפירעון")

    days = max((due_date - date.today()).days + 1, 0)
    st.markdown(
        f"<div style='background:#D6F5E0;border-radius:22px;padding:16px;text-align:center;margin:6px 0 10px;'>"
        f"<span style='font-size:11px;font-weight:700;letter-spacing:1.2px;color:#5A6800;"
        f"text-transform:uppercase;display:block;margin-bottom:2px;'>ימי זיכוי</span>"
        f"<span style='font-family:Inter,sans-serif;font-size:2.4rem;font-weight:900;"
        f"color:#000;letter-spacing:-1.5px;'>{days}</span>"
        f"<span style='font-size:0.9rem;font-weight:600;color:#2A7A4A;'> ימים</span></div>",
        unsafe_allow_html=True)

    st.markdown("<div style='text-align:center;font-size:11px;font-weight:700;"
                "letter-spacing:1.5px;color:#8A8A93;text-transform:uppercase;"
                "margin-bottom:8px;'>סוג הריבית</div>", unsafe_allow_html=True)
    basis = st.radio("סוג הריבית", ["חודשית", "שנתית"],
                     index=["חודשית", "שנתית"].index(st.session_state.rate_basis),
                     horizontal=True, key="basis_radio", label_visibility="collapsed")
    st.session_state.rate_basis = basis

    rate_val = st.session_state.fixed_rate
    r1, r2 = st.columns([2, 1])
    with r1:
        st.markdown(
            f"<div style='background:#EBEBEB;border-radius:18px;padding:14px 16px;text-align:center;margin-bottom:0;'>"
            f"<span style='font-size:11px;font-weight:700;letter-spacing:1.2px;color:#8A8A93;"
            f"text-transform:uppercase;display:block;margin-bottom:4px;'>ריבית קבועה ({basis})</span>"
            f"<span style='font-family:Inter,sans-serif;font-size:2rem;font-weight:900;"
            f"color:#000;letter-spacing:-1px;'>{rate_val:.2f}%</span>"
            f"</div>", unsafe_allow_html=True)
    with r2:
        st.write(""); st.write("")
        if st.button("✏️ שינוי ריבית", use_container_width=True, key="edit_rate"):
            st.session_state.rate_edit_open = not st.session_state.rate_edit_open

    if st.session_state.rate_edit_open:
        new_rate = st.number_input("הזן ריבית (%)", min_value=0.0, max_value=100.0,
                                   value=float(rate_val), step=0.1, format="%.2f",
                                   key="rate_input_manual")
        if st.button("💾 שמירת הריבית", use_container_width=True, key="save_rate"):
            st.session_state.fixed_rate    = new_rate
            st.session_state.rate_edit_open = False
            st.rerun()

    fee = amount * (rate_val/100.0) * (days/30.0 if basis == "חודשית" else days/365.0)
    net = amount - fee

    if days <= 0:
        st.markdown("<div style='background:#FFD6E8;border-radius:16px;padding:12px;"
                    "text-align:center;font-size:13px;font-weight:700;color:#8A2A50;"
                    "margin:8px 0;'>⚠️ תאריך הפירעון עבר — אין ימי זיכוי.</div>",
                    unsafe_allow_html=True)

    st.markdown(f"""
    <div class="calc-out fee"><div class="lbl">סך העמלה שיורדת</div>
        <div class="big">{fmt_ils(fee)}</div></div>
    <div class="calc-out net"><div class="lbl">נטו מזומן שמתקבל</div>
        <div class="big">{fmt_ils(net)}</div></div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# דשבורד תזרים
# ─────────────────────────────────────────────
def render_dashboard():
    st.markdown('<div class="section-title">📊 דשבורד תזרים</div>', unsafe_allow_html=True)
    st.markdown('<div class="neon-bar"></div>', unsafe_allow_html=True)

    status_rows = get_status_breakdown()
    if status_rows:
        status_bg = {"ממתין למזומן": "#FFF3C8", "להפקדה": "#D6F5E0", "בפריטה": "#FFD6E8"}
        for r in status_rows:
            bg = status_bg.get(r["status"], "#EBEBEB")
            color = STATUS_COLORS.get(r["status"], "#000")
            st.markdown(f"""
            <div style="background:{bg};border-radius:20px;padding:14px 18px;margin-bottom:5px;
                        display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <span style="font-weight:800;font-size:0.95rem;color:#000;">{r['status']}</span>
                    <span style="font-size:11px;color:#8A8A93;font-weight:700;margin-right:8px;
                                 letter-spacing:0.5px;">{r['cnt']} צ'קים</span>
                </div>
                <span style="font-weight:900;font-size:1.1rem;color:#000;direction:ltr;">{fmt_ils(r['total'])}</span>
            </div>""", unsafe_allow_html=True)

    forecast = get_cashflow_forecast()
    if not forecast:
        st.markdown('<div class="glass" style="text-align:center;color:#8A8A93;">אין צ\'קים עתידיים 📭</div>', unsafe_allow_html=True)
        return

    max_amount = max(r["total"] for r in forecast) or 1
    st.markdown("<div style='font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#8A8A93;margin:16px 0 8px;'>פירעונות לפי חודש</div>", unsafe_allow_html=True)

    month_he = {"January":"ינואר","February":"פברואר","March":"מרץ","April":"אפריל",
                "May":"מאי","June":"יוני","July":"יולי","August":"אוגוסט",
                "September":"ספטמבר","October":"אוקטובר","November":"נובמבר","December":"דצמבר"}

    for r in forecast:
        month_dt = r["month"]
        if hasattr(month_dt, "strftime"):
            month_label = month_dt.strftime("%B %Y")
            for en, he in month_he.items():
                month_label = month_label.replace(en, he)
        else:
            month_label = str(month_dt)[:7]
        pct = int((r["total"] / max_amount) * 100)
        st.markdown(f"""
        <div style="background:#FFFFFF;border-radius:24px;padding:18px 20px;margin-bottom:5px;">
            <div style="font-size:11px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;
                        color:#8A8A93;margin-bottom:6px;">{month_label} · {r['cnt']} צ'קים</div>
            <div style="font-family:'Inter',sans-serif;font-size:1.5rem;font-weight:900;
                        color:#000;direction:ltr;letter-spacing:-0.5px;">{fmt_ils(r['total'])}</div>
            <div style="background:#EBEBEB;border-radius:99px;height:5px;margin-top:10px;">
                <div style="background:#000;border-radius:99px;height:5px;width:{pct}%;"></div>
            </div>
        </div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    init_db()
    inject_css()

    if "current_user" not in st.session_state:
        st.session_state.current_user = "admin"

    screen = st.session_state.get("screen", "home")
    st.components.v1.html(f"""
    <script>
    (function(){{
        var s = "{screen}";
        var cur = new URLSearchParams(window.location.search).get("s");
        if(cur !== s) window.history.pushState({{screen:s}},"","?s="+s);
    }})();
    </script>""", height=0)

    if "screen" not in st.session_state:
        st.session_state.screen = "home"

    if screen == "home":
        render_home_screen()
    elif screen == "calc":
        render_back_button()
        render_calculator()
    elif screen == "mgmt":
        render_back_button()
        render_kpi()
        render_upcoming_reminder()
        render_add_check_form()
        render_clients()
    elif screen == "dash":
        render_back_button()
        render_dashboard()


if __name__ == "__main__":
    main()
