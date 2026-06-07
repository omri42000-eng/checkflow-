# -*- coding: utf-8 -*-
"""CheckFlow — Supabase + Dark Copper Design v3"""

import os
from datetime import date, datetime, timedelta
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
import streamlit as st
import streamlit_authenticator as stauth

st.set_page_config(
    page_title="CheckFlow | פריטה",
    page_icon="💸",
    layout="centered",
    initial_sidebar_state="collapsed",
)

STATUSES = ["ממתין למזומן", "להפקדה", "בפריטה"]
STATUS_COLORS = {"ממתין למזומן": "#FF9F1C", "להפקדה": "#39FF14", "בפריטה": "#FF2D95"}

# ─── DB ───
def get_db_url():
    url = st.secrets.get("DATABASE_URL", os.environ.get("DATABASE_URL", ""))
    if not url:
        st.error("❌ חסר DATABASE_URL"); st.stop()
    return url

@st.cache_resource(show_spinner=False)
def _get_persistent_conn():
    """One DB connection shared across all reruns - this is what makes it fast."""
    conn = psycopg.connect(get_db_url(), row_factory=dict_row, autocommit=True)
    return conn

@contextmanager
def get_conn():
    try:
        conn = _get_persistent_conn()
        # Check if connection is alive, reconnect if dead
        if conn.closed:
            _get_persistent_conn.clear()
            conn = _get_persistent_conn()
    except Exception as e:
        st.error(f"❌ שגיאת חיבור: {e}"); st.stop()
    try:
        yield conn
    except Exception:
        try: conn.rollback()
        except: pass
        # If connection broke, clear cache so next call reconnects
        try: _get_persistent_conn.clear()
        except: pass
        raise

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, name TEXT NOT NULL,
            password TEXT NOT NULL, email TEXT NOT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY, name TEXT NOT NULL,
            username TEXT NOT NULL DEFAULT 'admin',
            rate REAL DEFAULT 12.0,
            rate_basis TEXT DEFAULT 'שנתית',
            UNIQUE(name, username))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS checks (
            id SERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
            amount REAL NOT NULL, due_date DATE NOT NULL,
            status TEXT NOT NULL, remind_on DATE)""")
        # Add rate columns if missing (migration)
        cur.execute("""ALTER TABLE clients ADD COLUMN IF NOT EXISTS rate REAL DEFAULT 12.0""")
        cur.execute("""ALTER TABLE clients ADD COLUMN IF NOT EXISTS rate_basis TEXT DEFAULT 'שנתית'""")

def current_user():
    return st.session_state.get("current_user", "admin")

# ─── cached data fetchers ───
@st.cache_data(ttl=30)
def cached_totals(user):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT COALESCE(SUM(ch.amount),0) AS total, COUNT(ch.id) AS cnt
            FROM checks ch JOIN clients cl ON cl.id=ch.client_id WHERE cl.username=%s""", (user,))
        row = cur.fetchone()
        return float(row["total"]), int(row["cnt"])

@st.cache_data(ttl=30)
def cached_checks(user, client_id=None):
    q = """SELECT ch.*, cl.name AS client_name FROM checks ch
           JOIN clients cl ON cl.id=ch.client_id WHERE cl.username=%s"""
    params = [user]
    if client_id:
        q += " AND ch.client_id=%s"; params.append(client_id)
    q += " ORDER BY ch.due_date"
    with get_conn() as conn:
        cur = conn.cursor(); cur.execute(q, params)
        return cur.fetchall()

@st.cache_data(ttl=30)
def cached_clients(user):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, rate, rate_basis FROM clients WHERE username=%s ORDER BY name", (user,))
        return cur.fetchall()

@st.cache_data(ttl=30)
def cached_obligo(user):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT cl.id, cl.name, COALESCE(SUM(ch.amount),0) AS obligo, COUNT(ch.id) AS cnt
            FROM clients cl LEFT JOIN checks ch ON ch.client_id=cl.id
            WHERE cl.username=%s GROUP BY cl.id ORDER BY obligo DESC""", (user,))
        return cur.fetchall()

@st.cache_data(ttl=30)
def cached_upcoming(user):
    results = {}
    today = date.today()
    with get_conn() as conn:
        cur = conn.cursor()
        for i in range(3):
            d = today + timedelta(days=i)
            cur.execute("""SELECT ch.id, ch.amount, ch.due_date, ch.status, cl.name AS client_name
                FROM checks ch JOIN clients cl ON cl.id=ch.client_id
                WHERE cl.username=%s AND ch.due_date=%s ORDER BY cl.name""", (user, d))
            rows = cur.fetchall()
            if rows:
                results[d.isoformat()] = [dict(r) for r in rows]
    return results

@st.cache_data(ttl=30)
def cached_forecast(user):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT DATE_TRUNC('month', ch.due_date) AS month,
            SUM(ch.amount) AS total, COUNT(ch.id) AS cnt
            FROM checks ch JOIN clients cl ON cl.id=ch.client_id
            WHERE cl.username=%s AND ch.due_date >= CURRENT_DATE
            GROUP BY 1 ORDER BY 1""", (user,))
        return cur.fetchall()

@st.cache_data(ttl=30)
def cached_status_breakdown(user):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT ch.status, SUM(ch.amount) AS total, COUNT(ch.id) AS cnt
            FROM checks ch JOIN clients cl ON cl.id=ch.client_id
            WHERE cl.username=%s GROUP BY ch.status""", (user,))
        return cur.fetchall()

@st.cache_data(ttl=30)
def cached_month_checks(user, month_str):
    """Returns all checks for a given month (YYYY-MM format)."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT ch.amount, ch.due_date, ch.status, cl.name AS client_name
            FROM checks ch JOIN clients cl ON cl.id=ch.client_id
            WHERE cl.username=%s AND TO_CHAR(ch.due_date, 'YYYY-MM') = %s
            ORDER BY ch.due_date""", (user, month_str))
        return cur.fetchall()

def invalidate_cache():
    cached_totals.clear(); cached_checks.clear(); cached_clients.clear()
    cached_obligo.clear(); cached_upcoming.clear(); cached_forecast.clear()
    cached_status_breakdown.clear(); cached_month_checks.clear()

# ─── write functions ───
def add_client(name, rate=12.0, rate_basis="שנתית"):
    name = name.strip()
    if not name: return None
    u = current_user()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO clients (name,username,rate,rate_basis) VALUES (%s,%s,%s,%s) ON CONFLICT (name,username) DO NOTHING",
                    (name, u, rate, rate_basis))
        cur.execute("SELECT id FROM clients WHERE name=%s AND username=%s", (name, u))
        row = cur.fetchone()
        return row["id"] if row else None

def update_client_rate(client_id, rate, rate_basis):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE clients SET rate=%s, rate_basis=%s WHERE id=%s", (rate, rate_basis, client_id))

def add_check(client_id, amount, due_date, status, remind_on):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO checks (client_id,amount,due_date,status,remind_on) VALUES (%s,%s,%s,%s,%s)",
                    (client_id, amount, due_date, status, remind_on))

def update_status(check_id, status):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE checks SET status=%s WHERE id=%s", (status, check_id))

def delete_check(check_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM checks WHERE id=%s", (check_id,))

def add_checks_batch(client_id, amounts, due_dates, status):
    with get_conn() as conn:
        cur = conn.cursor()
        for amt, dd in zip(amounts, due_dates):
            cur.execute("INSERT INTO checks (client_id,amount,due_date,status,remind_on) VALUES (%s,%s,%s,%s,NULL)",
                        (client_id, float(amt), dd, status))

def do_login(username, password):
    username = username.strip()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
    if not user: return False, "שם משתמש לא קיים"
    if stauth.Hasher().check_pw(password, user["password"]):
        st.session_state["authentication_status"] = True
        st.session_state["username"] = user["username"]
        st.session_state["name"] = user["name"]
        return True, ""
    return False, "סיסמה שגויה"

# ─── helpers ───
def fmt_ils(x): return f"₪{x:,.0f}"
def fmt_date(d):
    if not d: return ""
    try:
        if isinstance(d, str): d = datetime.fromisoformat(d).date()
        return d.strftime("%d.%m.%Y")
    except: return str(d)

def calc_fee(amount, due_date, rate_val, rate_basis):
    days = max((due_date - date.today()).days + 1, 0)
    fee = float(amount) * (rate_val/100.0) * (days/30.0 if rate_basis=="חודשית" else days/365.0)
    return fee, days


# ─── CSS ───
def inject_css():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Comfortaa:wght@700&family=Inter:wght@400;500;600;700;800;900&display=swap');
html,body,[class*="css"]{direction:rtl}
.stApp{background:#0d2240;background-image:linear-gradient(135deg,#0d2240 0%,#163652 50%,#0d2240 100%);font-family:'Inter',sans-serif;color:#dec599;min-height:100vh}
#MainMenu,header,footer{visibility:hidden}
.block-container{padding-top:0!important;padding-bottom:6rem;max-width:480px}
.logo-title{font-family:'Comfortaa',sans-serif;font-weight:700;font-size:2.6rem;white-space:nowrap;background:linear-gradient(135deg,#e59a65 0%,#f0c090 40%,#b06a3b 70%,#e59a65 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;filter:drop-shadow(0px 3px 6px rgba(0,0,0,.7));display:block;text-align:center;line-height:1;margin-bottom:2px}
.kpi{background:rgba(44,52,64,.88);border:1px solid rgba(229,154,101,.25);border-radius:24px;padding:18px 20px 14px;margin-bottom:6px;text-align:center;box-shadow:0 8px 32px rgba(0,0,0,.4),inset 0 1px 0 rgba(229,154,101,.15)}
.kpi-label{font-size:10px;font-weight:700;letter-spacing:2px;color:#e59a65;text-transform:uppercase;margin-bottom:4px}
.kpi-value{font-family:'Inter',sans-serif;font-size:2.4rem;font-weight:900;line-height:1;background:linear-gradient(135deg,#f0c090 0%,#e59a65 50%,#dec599 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;display:block;letter-spacing:-2px;direction:ltr}
.kpi-sub{font-size:12px;color:#a07850;margin-top:6px;font-weight:500}
.glass{background:rgba(44,52,64,.75);border:1px solid rgba(229,154,101,.15);border-radius:22px;padding:18px 20px;margin-bottom:5px;box-shadow:0 4px 16px rgba(0,0,0,.3)}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:11px;font-weight:700;margin-inline-start:6px}
.section-title{font-size:20px;font-weight:900;letter-spacing:-.5px;color:#e59a65;margin:16px 0 4px;text-align:right}
.section-title-right{font-size:20px;font-weight:900;letter-spacing:-.5px;color:#e59a65;margin:8px 0 4px;text-align:right}
.neon-bar{height:2px;width:36px;border-radius:3px;background:linear-gradient(90deg,#e59a65,#b06a3b);margin:0 auto 14px}
.neon-bar-right{height:2px;width:36px;border-radius:3px;background:linear-gradient(90deg,#e59a65,#b06a3b);margin:0 0 14px auto}
.client-card{display:flex;justify-content:space-between;align-items:center;background:rgba(44,52,64,.88);border:1px solid rgba(229,154,101,.2);border-radius:20px;padding:14px 16px;margin-bottom:5px;box-shadow:0 4px 16px rgba(0,0,0,.3)}
.client-name{font-weight:800;font-size:.95rem;color:#dec599}
.client-obligo{font-weight:900;font-size:1.1rem;background:linear-gradient(135deg,#e59a65,#dec599);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;direction:ltr;letter-spacing:-.5px}
.calc-out{border-radius:22px;padding:18px 20px;margin-top:5px;text-align:center}
.calc-out.fee{background:rgba(140,42,80,.28);border:1px solid rgba(255,45,149,.25)}
.calc-out.net{background:rgba(42,122,74,.28);border:1px solid rgba(57,255,20,.25);margin-top:5px}
.calc-out .lbl{font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#a07850;margin-bottom:6px}
.calc-out .big{font-family:'Inter',sans-serif;font-size:2.4rem;font-weight:900;direction:ltr;line-height:1.1;letter-spacing:-1.5px;color:#dec599}
.reminder-card{background:rgba(139,106,0,.22);border:1px solid rgba(229,154,101,.25);border-radius:20px;padding:14px 16px;margin-bottom:6px}
.reminder-title{font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#e59a65;margin-bottom:8px}
.reminder-row{display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid rgba(229,154,101,.1)}
.reminder-row:last-child{border-bottom:none}
.deposit-alert{background:rgba(57,255,20,.08);border:1px solid rgba(57,255,20,.3);border-radius:18px;padding:12px 16px;margin-bottom:8px}
/* carousel wrap (legacy) */
.carousel-wrap{display:flex;gap:12px;overflow-x:auto;padding:8px 2px 12px;scrollbar-width:none;-ms-overflow-style:none}
.carousel-wrap::-webkit-scrollbar{display:none}
/* ─── Home nav card buttons ─── */
.nav-calc .stButton>button,.nav-mgmt .stButton>button,.nav-dash .stButton>button{
    border-radius:18px!important;height:72px!important;width:100%!important;
    padding:0 22px!important;font-size:.9rem!important;font-weight:900!important;
    white-space:nowrap!important;letter-spacing:-.2px!important;
    transition:all .25s cubic-bezier(.34,1.56,.64,1)!important;
    box-shadow:0 8px 24px rgba(0,0,0,.4)!important;
    display:flex!important;align-items:center!important;justify-content:center!important;
    border:none!important;
}
.nav-calc .stButton>button{
    background:linear-gradient(135deg,#1a4a2a 0%,#0a2a15 100%)!important;
    color:#6dff8a!important;
    box-shadow:0 8px 24px rgba(57,255,20,.18),inset 0 1px 0 rgba(255,255,255,.1)!important;
    border-right:4px solid #39FF14!important;
}
.nav-mgmt .stButton>button{
    background:linear-gradient(135deg,#5a3218 0%,#3a1e08 100%)!important;
    color:#ffc699!important;
    box-shadow:0 8px 24px rgba(229,154,101,.25),inset 0 1px 0 rgba(255,255,255,.12)!important;
    border-right:4px solid #e59a65!important;
    transform:scale(1.04) translateY(-3px)!important;
}
.nav-dash .stButton>button{
    background:linear-gradient(135deg,#1a2a4a 0%,#0a1525 100%)!important;
    color:#90c0ff!important;
    box-shadow:0 8px 24px rgba(100,160,229,.18),inset 0 1px 0 rgba(255,255,255,.08)!important;
    border-right:4px solid #4090e0!important;
}
.nav-calc .stButton>button:hover{background:linear-gradient(135deg,#205a34 0%,#103a1e 100%)!important;transform:translateY(-3px) scale(1.03)!important;box-shadow:0 14px 32px rgba(57,255,20,.35)!important}
.nav-mgmt .stButton>button:hover{background:linear-gradient(135deg,#6a4020 0%,#4a2a10 100%)!important;transform:scale(1.07) translateY(-6px)!important;box-shadow:0 14px 36px rgba(229,154,101,.45)!important}
.nav-dash .stButton>button:hover{background:linear-gradient(135deg,#203256 0%,#101e3a 100%)!important;transform:translateY(-3px) scale(1.03)!important;box-shadow:0 14px 32px rgba(100,160,229,.35)!important}
/* general buttons */
.stButton>button{border-radius:14px!important;border:1px solid rgba(229,154,101,.22)!important;background:rgba(44,52,64,.9)!important;color:#dec599!important;font-weight:700!important;font-family:'Inter',sans-serif!important;transition:all .12s ease!important;box-shadow:0 3px 10px rgba(0,0,0,.3)!important}
.stButton>button:hover{border-color:rgba(229,154,101,.5)!important}
.btn-single .stButton>button{border-radius:50px!important;background:linear-gradient(135deg,#e59a65 0%,#b06a3b 100%)!important;color:#fff!important;font-size:.92rem!important;font-weight:800!important;padding:13px 0!important;border:none!important;box-shadow:0 4px 16px rgba(176,106,59,.4)!important}
.btn-batch .stButton>button{border-radius:50px!important;background:rgba(44,52,64,.9)!important;color:#e59a65!important;font-size:.92rem!important;font-weight:800!important;padding:13px 0!important;border:1px solid rgba(229,154,101,.4)!important}
.btn-sm .stButton>button{padding:3px 8px!important;font-size:.75rem!important;border-radius:8px!important;min-height:0!important;height:auto!important;font-weight:700!important}
.back-btn{position:fixed!important;bottom:28px!important;left:20px!important;z-index:9999!important}
.back-btn .stButton>button{border-radius:50px!important;background:linear-gradient(135deg,#e59a65 0%,#b06a3b 100%)!important;color:#fff!important;font-size:.82rem!important;font-weight:800!important;padding:10px 22px!important;height:auto!important;min-height:0!important;border:none!important;box-shadow:0 4px 20px rgba(176,106,59,.5)!important}
/* inputs */
.stTextInput input,.stNumberInput input,.stDateInput input,[data-baseweb="input"] input,[data-baseweb="base-input"] input{color:#dec599!important;background-color:rgba(44,52,64,.9)!important;-webkit-text-fill-color:#dec599!important;caret-color:#e59a65!important;border-radius:12px!important;border:1px solid rgba(229,154,101,.22)!important;font-weight:600!important;font-size:.95rem!important;direction:rtl!important;text-align:right!important}
.stTextInput div[data-baseweb="input"],.stNumberInput div[data-baseweb="input"],.stDateInput div[data-baseweb="input"],div[data-baseweb="select"]>div{background-color:rgba(44,52,64,.9)!important;border:1px solid rgba(229,154,101,.22)!important;border-radius:12px!important}
div[data-baseweb="select"] div{color:#dec599!important;font-weight:600!important}
input::placeholder{color:#7a5a40!important;opacity:1!important}
div[data-testid="stNumberInput"]:has(input[aria-label*="סכום"]) input{font-size:1.8rem!important;font-weight:900!important;text-align:center!important;letter-spacing:-1px!important;height:64px!important}
label{color:#a07850!important;font-weight:700!important;font-size:10px!important;letter-spacing:.8px!important;text-transform:uppercase!important;text-align:right!important;display:block!important}
/* radio basis buttons */
div[data-testid="stRadio"]>div{gap:8px!important;justify-content:center!important}
div[data-testid="stRadio"] label{background:rgba(44,52,64,.9)!important;border:1px solid rgba(229,154,101,.22)!important;border-radius:12px!important;padding:9px 22px!important;font-size:.9rem!important;font-weight:800!important;color:#dec599!important;cursor:pointer;text-transform:none!important;letter-spacing:0!important}
div[data-testid="stRadio"] label:hover{border-color:rgba(229,154,101,.5)!important}
div[data-testid="stRadio"] input[type="radio"]{display:none!important}
div[data-testid="stRadio"] div[data-baseweb="radio"]>div:first-child{display:none!important}
/* tabs */
.stTabs [data-baseweb="tab-list"]{gap:5px;justify-content:center;background:transparent!important}
.stTabs [data-baseweb="tab"]{background:rgba(44,52,64,.9)!important;border:1px solid rgba(229,154,101,.15)!important;border-radius:12px!important;padding:9px 20px!important;font-size:.88rem!important;font-weight:700!important;color:#a07850!important;min-width:110px;text-align:center}
.stTabs [data-baseweb="tab"] p,.stTabs [data-baseweb="tab"] span,.stTabs [data-baseweb="tab"] div{color:#a07850!important}
.stTabs [aria-selected="true"]{background:linear-gradient(135deg,#e59a65 0%,#b06a3b 100%)!important;border-color:transparent!important}
.stTabs [aria-selected="true"] p,.stTabs [aria-selected="true"] span,.stTabs [aria-selected="true"] div{color:#fff!important}
/* expander */
.streamlit-expanderHeader{background:rgba(44,52,64,.9)!important;border-radius:12px!important;font-weight:700!important;color:#dec599!important;border:1px solid rgba(229,154,101,.15)!important}
.streamlit-expanderContent{background:rgba(30,38,48,.85)!important;border:none!important}
.stCheckbox label{color:#dec599!important;font-weight:700!important;font-size:.88rem!important;text-transform:none!important;letter-spacing:0!important}
ul[role="listbox"],div[data-baseweb="popover"]{background-color:#142438!important;border:1px solid rgba(229,154,101,.2)!important;border-radius:14px!important}
ul[role="listbox"] li{color:#dec599!important;font-weight:600!important}
.stDataFrame,[data-testid="stDataEditor"]{border-radius:14px!important;overflow:hidden!important;border:none!important}
/* center inline buttons */
div[data-testid="stHorizontalBlock"] div[data-testid="column"] .stButton {
    display: flex; justify-content: center;
}
div[data-testid="stHorizontalBlock"] div[data-testid="column"] .stButton>button:not([style*="width:100"]) {
    min-width: 80px;
}
/* dashboard */
.dash-day-card{background:rgba(44,52,64,.88);border:1px solid rgba(229,154,101,.2);border-radius:20px;padding:14px 16px;margin-bottom:6px;cursor:pointer;transition:border-color .15s}
.dash-day-card:hover{border-color:rgba(229,154,101,.5)}
.dash-month-card{background:rgba(44,52,64,.88);border:1px solid rgba(229,154,101,.15);border-radius:20px;padding:14px 16px;margin-bottom:5px;cursor:pointer;transition:all .15s ease}
.dash-month-card:hover{border-color:rgba(229,154,101,.4)}
.dash-bar-bg{background:rgba(255,255,255,.08);border-radius:99px;height:5px;margin-top:8px}
.dash-bar-fill{background:linear-gradient(90deg,#e59a65,#b06a3b);border-radius:99px;height:5px}
/* batch table row edit */
.batch-row{background:rgba(44,52,64,.88);border:1px solid rgba(229,154,101,.15);border-radius:14px;padding:12px 14px;margin-bottom:5px}
/* ══ HOME NAV PREMIUM CARDS (Prompt 2: Flat-Volumetric Badge) ══ */
.hnc{display:flex;direction:ltr!important;height:90px;border-radius:26px;overflow:hidden;box-shadow:0 16px 44px rgba(0,0,0,.6);margin-bottom:4px;cursor:pointer;transition:transform .2s,box-shadow .2s}
.hnc-badge{width:37%;display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden;flex-shrink:0}
.hnc-badge::before{content:'';position:absolute;top:-22px;right:-22px;width:72px;height:72px;border-radius:50%;background:rgba(255,255,255,.18)}
.hnc-badge::after{content:'';position:absolute;bottom:-16px;left:-16px;width:54px;height:54px;border-radius:50%;background:rgba(0,0,0,.18)}
.hnc-icon{font-size:2.4rem;position:relative;z-index:2;filter:drop-shadow(4px 4px 0px rgba(0,0,0,.35))}
.hnc-body{flex:1;display:flex;flex-direction:column;justify-content:center;padding:0 20px;direction:rtl!important}
.hnc-title{font-size:1.02rem;font-weight:900;color:#fff;letter-spacing:-.4px;line-height:1.1}
.hnc-rule{height:2px;border-radius:2px;width:30px;margin:6px 0}
.hnc-desc{font-size:.71rem;color:rgba(255,255,255,.5);font-weight:500;letter-spacing:.2px}
/* transparent click overlay */
.hnc-over{margin-top:-102px;height:102px;position:relative;z-index:50;margin-bottom:22px}
.hnc-over .stButton{height:100%!important}
.hnc-over .stButton>button{background:transparent!important;color:transparent!important;border:none!important;box-shadow:none!important;width:100%!important;height:102px!important;cursor:pointer!important;border-radius:26px!important;position:relative;outline:none!important;font-size:1px!important}
.hnc-over .stButton>button::after{content:'';position:absolute;inset:0;border-radius:26px;background:rgba(255,255,255,0);transition:background .2s}
.hnc-over .stButton>button:hover::after{background:rgba(255,255,255,.07)}
/* ══ DASHBOARD GLASSMORPHISM TIMELINE (Prompt 1: Dark Glass + Timeline) ══ */
.db-hdr{display:flex;justify-content:space-between;align-items:center;padding:10px 4px 20px;direction:rtl}
.db-hdr-left .db-hdr-lbl{font-size:.62rem;font-weight:700;letter-spacing:2.5px;color:#9BA1A6;text-transform:uppercase}
.db-hdr-left .db-hdr-date{font-size:1.25rem;font-weight:900;color:#fff}
.db-hdr-cap{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.14);border-radius:20px;padding:6px 18px;font-size:.78rem;font-weight:700;color:#dec599}
.glass-section{background:rgba(36,42,52,.68);backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);border:1px solid rgba(255,255,255,.08);border-radius:28px;padding:18px 20px;margin-bottom:12px}
.gs-label{font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#9BA1A6;margin-bottom:14px}
.dep-alert-tl{background:#fff;border-radius:14px;padding:11px 15px;margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;direction:rtl;box-shadow:0 4px 14px rgba(0,0,0,.3)}
.tl-day{margin-bottom:14px}
.tl-day-hdr{display:flex;align-items:center;gap:8px;margin-bottom:9px;direction:rtl}
.tl-dot{width:12px;height:12px;border-radius:50%;flex-shrink:0}
.tl-day-lbl{font-weight:800;font-size:.9rem;color:#fff}
.tl-day-date{font-size:.74rem;color:#9BA1A6;flex:1}
.tl-day-total{font-weight:900;color:#e59a65;direction:ltr;font-size:.95rem}
.tl-rows-wrap{display:flex;gap:12px;padding-right:18px}
.tl-vert-line{width:2px;flex-shrink:0;border-radius:2px;min-height:44px}
.tl-items{flex:1;display:flex;flex-direction:column;gap:7px}
.tl-white-card{background:#fff;border-radius:16px;padding:11px 15px;display:flex;justify-content:space-between;align-items:center;box-shadow:0 6px 16px rgba(0,0,0,.28);direction:rtl}
.tl-wc-left{flex:1}
.tl-wc-client{font-weight:700;font-size:.88rem;color:#111;margin-bottom:2px}
.tl-wc-status{font-size:.68rem;font-weight:600}
.tl-wc-right{display:flex;align-items:center;gap:8px;direction:ltr}
.tl-wc-amount{font-weight:900;font-size:.95rem;color:#1a4a2a;direction:ltr}
.tl-wc-chevron{font-size:1.3rem;color:#bbb;font-weight:300}
.tl-dep-badge{background:#1a4a2a;color:#39FF14;font-size:.6rem;font-weight:800;border-radius:5px;padding:1px 7px;margin-right:6px;vertical-align:middle}
.status-row{border:1px solid;border-radius:16px;padding:12px 15px;margin-bottom:7px;display:flex;justify-content:space-between;align-items:center;direction:rtl}
.status-amnt{font-weight:900;font-size:.9rem;direction:ltr;padding:4px 12px;border-radius:10px}
.month-card{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);border-radius:16px;padding:13px 15px;margin-bottom:6px;transition:border-color .15s}
.month-card:hover{border-color:rgba(229,154,101,.3)}
.mc-hdr{display:flex;justify-content:space-between;align-items:center;direction:rtl}
.mc-label{font-size:.9rem;font-weight:700;color:#fff}
.mc-count{font-size:.7rem;color:#9BA1A6;margin-top:2px}
.mc-amount{font-weight:900;font-size:1.05rem;color:#e59a65;direction:ltr}
.month-bar-bg{background:rgba(255,255,255,.07);border-radius:99px;height:4px;margin-top:9px}
.month-bar-fill{background:linear-gradient(90deg,#e59a65,#b06a3b);border-radius:99px;height:4px}
</style>""", unsafe_allow_html=True)

    st.components.v1.html("""<script>
function attachSelectAll(){
    var inputs=window.parent.document.querySelectorAll('input[type="number"]');
    inputs.forEach(function(inp){if(inp._sa)return;inp._sa=true;
    inp.addEventListener('focus',function(){var s=this;setTimeout(function(){s.select();},50);});});
}
attachSelectAll();setInterval(attachSelectAll,600);
</script>""", height=0)


# ─── Auth ───
def render_auth_screen():
    st.markdown(
        "<div style='height:30px'></div>"
        "<p style='text-align:center;font-size:11px;font-weight:700;letter-spacing:3px;"
        "color:#8c6a45;text-transform:uppercase;margin-bottom:4px;'>CHECK MANAGEMENT</p>"
        "<h1><span class='logo-title'>CHECKFLOW</span></h1>",
        unsafe_allow_html=True)
    tab_login, tab_register = st.tabs(["🔑  כניסה", "📝  הרשמה"])
    with tab_login:
        with st.form("login_form", clear_on_submit=False):
            l_user = st.text_input("שם משתמש", key="l_user")
            l_pass = st.text_input("סיסמה", type="password", key="l_pass")
            login_btn = st.form_submit_button("כניסה →", use_container_width=True)
        if login_btn:
            ok, msg = do_login(l_user, l_pass)
            if ok: st.rerun()
            else: st.error(msg)
    with tab_register:
        st.markdown("#### צור חשבון חדש")
        with st.form("reg_form", clear_on_submit=True):
            r_user = st.text_input("שם משתמש (אנגלית)", key="r_user")
            r_name = st.text_input("שם מלא", key="r_name")
            r_email = st.text_input("אימייל", key="r_email")
            r_pass = st.text_input("סיסמה (6+ תווים)", type="password", key="r_pass")
            r_pass2 = st.text_input("אימות סיסמה", type="password", key="r_pass2")
            submitted = st.form_submit_button("הרשמה ✅", use_container_width=True)
        if submitted:
            r_user=r_user.strip(); r_name=r_name.strip(); r_email=r_email.strip()
            if not all([r_user,r_name,r_email,r_pass]): st.error("יש למלא את כל השדות.")
            elif len(r_pass)<6: st.error("הסיסמה חייבת להכיל לפחות 6 תווים.")
            elif r_pass!=r_pass2: st.error("הסיסמאות אינן תואמות.")
            else:
                with get_conn() as conn:
                    cur=conn.cursor(); cur.execute("SELECT 1 FROM users WHERE username=%s",(r_user,)); exists=cur.fetchone()
                if exists: st.error("שם המשתמש כבר קיים.")
                else:
                    hashed=stauth.Hasher().hash(r_pass)
                    with get_conn() as conn:
                        cur=conn.cursor()
                        cur.execute("INSERT INTO users (username,name,password,email) VALUES (%s,%s,%s,%s)",(r_user,r_name,hashed,r_email))
                    st.success("נרשמת בהצלחה! 🎉")

# ─── Back button ───
def render_back_button():
    st.markdown('<div class="back-btn">', unsafe_allow_html=True)
    if st.button("← ראשי", key="back_home"):
        st.session_state.screen = "home"; st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# ─── KPI ───
def render_kpi():
    total, cnt = cached_totals(current_user())
    st.markdown(f"""<div class="kpi">
        <div class="kpi-label">אובליגו כולל</div>
        <div class="kpi-value">{fmt_ils(total)}</div>
        <div class="kpi-sub">{cnt} צ'קים בארנק 💸</div>
    </div>""", unsafe_allow_html=True)

# ─── Home ───
def render_home_screen():
    # Title (main page)
    st.markdown(
        "<div style='height:28px'></div>"
        "<p style='text-align:center;font-size:10px;font-weight:700;letter-spacing:4px;"
        "color:#a07850;text-transform:uppercase;margin-bottom:3px;'>CHECK MANAGEMENT SYSTEM</p>"
        "<h1><span class='logo-title'>CHECKFLOW</span></h1>",
        unsafe_allow_html=True)

    # ── Cards inside iframe — onclick works here (no CSP restriction inside iframe) ──
    st.components.v1.html("""
<!DOCTYPE html>
<html>
<head>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@700;800;900&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d2240;font-family:'Inter',sans-serif;padding:12px 0 8px;}
.hnc{display:flex;direction:ltr;height:90px;border-radius:26px;overflow:hidden;
    box-shadow:0 16px 44px rgba(0,0,0,.6);margin-bottom:18px;cursor:pointer;
    transition:transform .2s,box-shadow .2s;}
.hnc:hover{filter:brightness(1.08);}
.hnc-badge{width:37%;display:flex;align-items:center;justify-content:center;
    position:relative;overflow:hidden;flex-shrink:0;}
.hnc-badge::before{content:'';position:absolute;top:-22px;right:-22px;
    width:72px;height:72px;border-radius:50%;background:rgba(255,255,255,.18)}
.hnc-badge::after{content:'';position:absolute;bottom:-16px;left:-16px;
    width:54px;height:54px;border-radius:50%;background:rgba(0,0,0,.18)}
.hnc-icon{font-size:2.4rem;position:relative;z-index:2;filter:drop-shadow(4px 4px 0px rgba(0,0,0,.35))}
.hnc-body{flex:1;display:flex;flex-direction:column;justify-content:center;
    padding:0 20px;direction:rtl;}
.hnc-title{font-size:1.02rem;font-weight:900;color:#fff;letter-spacing:-.4px;line-height:1.1}
.hnc-rule{height:2px;border-radius:2px;width:30px;margin:6px 0}
.hnc-desc{font-size:.71rem;color:rgba(255,255,255,.5);font-weight:500;letter-spacing:.2px}
.hnc-mgmt{transform:scale(1.04) translateY(-4px);transform-origin:center;
    box-shadow:0 20px 52px rgba(0,0,0,.65)!important;}
</style>
</head>
<body>

<div class="hnc" onclick="nav('calc')">
  <div class="hnc-badge" style="background:linear-gradient(160deg,#2bf06e 0%,#0c7c2a 100%)">
    <span class="hnc-icon">💸</span>
  </div>
  <div class="hnc-body" style="background:linear-gradient(135deg,#1a4a2a 0%,#0a2814 100%)">
    <div class="hnc-title">מחשבון פריטה</div>
    <div class="hnc-rule" style="background:#39FF14"></div>
    <div class="hnc-desc">חישוב עמלות פריטה מהיר ומדויק</div>
  </div>
</div>

<div class="hnc hnc-mgmt" onclick="nav('mgmt')">
  <div class="hnc-badge" style="background:linear-gradient(160deg,#ffc080 0%,#a85818 100%)">
    <span class="hnc-icon">💳</span>
  </div>
  <div class="hnc-body" style="background:linear-gradient(135deg,#4a2808 0%,#281404 100%)">
    <div class="hnc-title">ניהול צ׳קים</div>
    <div class="hnc-rule" style="background:#e59a65"></div>
    <div class="hnc-desc">לקוחות · סטטוסים · מעקב מלא</div>
  </div>
</div>

<div class="hnc" onclick="nav('dash')">
  <div class="hnc-badge" style="background:linear-gradient(160deg,#70c0ff 0%,#1040a0 100%)">
    <span class="hnc-icon">📈</span>
  </div>
  <div class="hnc-body" style="background:linear-gradient(135deg,#1a2a4a 0%,#0a1428 100%)">
    <div class="hnc-title">דשבורד תזרים</div>
    <div class="hnc-rule" style="background:#4090e0"></div>
    <div class="hnc-desc">תחזית חודשית · פירעונות</div>
  </div>
</div>

<script>
function nav(key) {
    var btns = window.parent.document.querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
        if (btns[i].textContent.trim() === key) {
            btns[i].click();
            return;
        }
    }
}
</script>
</body>
</html>
""", height=335)

    # Hidden nav buttons in main page — found and clicked by iframe JS above
    st.markdown("""<style>
.nav-hidden .stButton>button{position:fixed!important;top:-9999px!important;
    left:-9999px!important;width:1px!important;height:1px!important;opacity:0!important}
</style>""", unsafe_allow_html=True)
    st.markdown('<div class="nav-hidden">', unsafe_allow_html=True)
    if st.button("calc", key="go_calc"): st.session_state.screen = "calc"; st.rerun()
    if st.button("mgmt", key="go_mgmt"): st.session_state.screen = "mgmt"; st.rerun()
    if st.button("dash", key="go_dash"): st.session_state.screen = "dash"; st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    render_kpi()


# ─── Dashboard ───
def render_dashboard():
    render_back_button()
    u = current_user()
    today = date.today()

    # Header (capsule selector style from Prompt 1)
    st.markdown(
        f"<div class='db-hdr'>"
        f"<div class='db-hdr-left'>"
        f"<div class='db-hdr-lbl'>CHECKFLOW DASHBOARD</div>"
        f"<div class='db-hdr-date'>{today.strftime('%d.%m.%Y')}</div>"
        f"</div>"
        f"<div class='db-hdr-cap'>תזרים מזומנים</div>"
        f"</div>", unsafe_allow_html=True)

    # ══ GLASS SECTION 1: Timeline ─ upcoming 48 hrs ══
    upcoming_raw = cached_upcoming(u)
    DAY_LABELS = {today.isoformat(): "היום", (today+timedelta(days=1)).isoformat(): "מחר",
                  (today+timedelta(days=2)).isoformat(): "מחרתיים"}
    DAY_DOTS   = {today.isoformat(): "#FF3B30", (today+timedelta(days=1)).isoformat(): "#FFCC00",
                  (today+timedelta(days=2)).isoformat(): "#FF9500"}

    if upcoming_raw:
        to_deposit = [ch for v in upcoming_raw.values() for ch in v if ch["status"] == "להפקדה"]
        html = '<div class="glass-section"><div class="gs-label">⏰  פירעונות 48 השעות הקרובות</div>'

        if to_deposit:
            dep_total = sum(ch["amount"] for ch in to_deposit)
            dep_names = "، ".join(dict.fromkeys(ch["client_name"] for ch in to_deposit))
            html += (f"<div class='dep-alert-tl'>"
                     f"<span style='font-size:.8rem;font-weight:800;color:#1a4a2a;'>🏦 {len(to_deposit)} צ׳קים להפקדה | {dep_names}</span>"
                     f"<span style='font-weight:900;font-size:1rem;color:#0a4020;direction:ltr;'>{fmt_ils(dep_total)}</span>"
                     f"</div>")

        for d_str, checks in sorted(upcoming_raw.items()):
            lbl   = DAY_LABELS.get(d_str, d_str)
            dot_c = DAY_DOTS.get(d_str, "#e59a65")
            day_t = sum(ch["amount"] for ch in checks)
            date_label = d_str[5:].replace("-",".")

            html += (f"<div class='tl-day'>"
                     f"<div class='tl-day-hdr'>"
                     f"<div class='tl-dot' style='background:{dot_c};box-shadow:0 0 8px {dot_c}99;'></div>"
                     f"<span class='tl-day-lbl'>{lbl}</span>"
                     f"<span class='tl-day-date'>{date_label}</span>"
                     f"<span class='tl-day-total'>{fmt_ils(day_t)}</span>"
                     f"</div>"
                     f"<div class='tl-rows-wrap'>"
                     f"<div class='tl-vert-line' style='background:linear-gradient(to bottom,{dot_c}55,transparent);'></div>"
                     f"<div class='tl-items'>")

            for ch in checks:
                s_color = STATUS_COLORS.get(ch["status"], "#888")
                dep_badge = "<span class='tl-dep-badge'>להפקדה</span>" if ch["status"] == "להפקדה" else ""
                html += (f"<div class='tl-white-card'>"
                         f"<div class='tl-wc-left'>"
                         f"<div class='tl-wc-client'>{dep_badge}{ch['client_name']}</div>"
                         f"<div class='tl-wc-status' style='color:{s_color};'>{ch['status']}</div>"
                         f"</div>"
                         f"<div class='tl-wc-right'>"
                         f"<span class='tl-wc-amount'>{fmt_ils(ch['amount'])}</span>"
                         f"<span class='tl-wc-chevron'>›</span>"
                         f"</div></div>")

            html += "</div></div></div>"   # tl-items · tl-rows-wrap · tl-day

        html += "</div>"   # glass-section
        st.markdown(html, unsafe_allow_html=True)

    else:
        st.markdown(
            "<div class='glass-section'><div class='gs-label'>⏰  פירעונות 48 שעות</div>"
            "<div style='color:#9BA1A6;font-size:.85rem;text-align:center;padding:12px 0;'>אין פירעונות קרובים ✓</div>"
            "</div>", unsafe_allow_html=True)

    # ══ GLASS SECTION 2: Status breakdown ══
    status_rows = cached_status_breakdown(u)
    if status_rows:
        status_bg  = {"ממתין למזומן":"rgba(255,159,28,.1)","להפקדה":"rgba(57,255,20,.08)","בפריטה":"rgba(255,45,149,.1)"}
        html = "<div class='glass-section'><div class='gs-label'>פירוט לפי סטטוס</div>"
        for r in status_rows:
            bg    = status_bg.get(r["status"], "rgba(255,255,255,.04)")
            color = STATUS_COLORS.get(r["status"], "#dec599")
            html += (f"<div class='status-row' style='background:{bg};border-color:{color}33;'>"
                     f"<div>"
                     f"<div style='font-weight:800;font-size:.9rem;color:#fff;'>{r['status']}</div>"
                     f"<div style='font-size:.72rem;color:#9BA1A6;margin-top:2px;'>{r['cnt']} צ׳קים</div>"
                     f"</div>"
                     f"<div class='status-amnt' style='background:{color}18;border:1.5px solid {color}55;color:{color};'>"
                     f"{fmt_ils(r['total'])}</div>"
                     f"</div>")
        html += "</div>"
        st.markdown(html, unsafe_allow_html=True)

    # ══ GLASS SECTION 3: Monthly forecast ══
    forecast = cached_forecast(u)
    if forecast:
        max_amount = max(r["total"] for r in forecast) or 1
        month_he = {"January":"ינואר","February":"פברואר","March":"מרץ","April":"אפריל",
                    "May":"מאי","June":"יוני","July":"יולי","August":"אוגוסט",
                    "September":"ספטמבר","October":"אוקטובר","November":"נובמבר","December":"דצמבר"}

        st.markdown("<div class='glass-section'><div class='gs-label'>תחזית חודשית — לחץ לפירוט</div>",
                    unsafe_allow_html=True)

        for r in forecast:
            m         = r["month"]
            label     = m.strftime("%B %Y") if hasattr(m,"strftime") else str(m)[:7]
            month_str = m.strftime("%Y-%m") if hasattr(m,"strftime") else str(m)[:7]
            for en,he in month_he.items(): label = label.replace(en,he)
            pct     = int((r["total"] / max_amount) * 100)
            key_m   = f"month_expand_{month_str}"
            exp_m   = st.session_state.get(key_m, False)

            mc1, mc2 = st.columns([5, 1])
            with mc1:
                st.markdown(
                    f"<div class='month-card'>"
                    f"<div class='mc-hdr'>"
                    f"<div><div class='mc-label'>{label}</div><div class='mc-count'>{r['cnt']} צ׳קים</div></div>"
                    f"<div class='mc-amount'>{fmt_ils(r['total'])}</div>"
                    f"</div>"
                    f"<div class='month-bar-bg'><div class='month-bar-fill' style='width:{pct}%;'></div></div>"
                    f"</div>", unsafe_allow_html=True)
            with mc2:
                st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
                if st.button("▼" if not exp_m else "▲", key=f"btn_{key_m}", use_container_width=True):
                    st.session_state[key_m] = not exp_m; st.rerun()

            if exp_m:
                month_checks = cached_month_checks(u, month_str)
                if month_checks:
                    rows_html = ""
                    for ch in month_checks:
                        color = STATUS_COLORS.get(ch["status"], "#888")
                        rows_html += (
                            f"<div style='display:flex;justify-content:space-between;align-items:center;"
                            f"padding:8px 13px;background:rgba(255,255,255,.04);border-radius:10px;"
                            f"margin-bottom:3px;direction:rtl;'>"
                            f"<span style='font-weight:700;color:#fff;font-size:.84rem;flex:1;'>{ch['client_name']}</span>"
                            f"<span style='font-size:.75rem;color:#9BA1A6;margin:0 10px;'>{fmt_date(ch['due_date'])}</span>"
                            f"<span style='font-size:.7rem;font-weight:700;color:{color};margin-left:8px;'>{ch['status']}</span>"
                            f"<span style='font-weight:900;color:#e59a65;direction:ltr;margin-right:6px;'>{fmt_ils(ch['amount'])}</span>"
                            f"</div>")
                    st.markdown(rows_html, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)


# ─── Calculator ───
def render_calculator():
    render_back_button()
    st.markdown('<div class="section-title-right">🧮 מחשבון פריטה</div>', unsafe_allow_html=True)
    st.markdown('<div class="neon-bar-right"></div>', unsafe_allow_html=True)

    if "fixed_rate" not in st.session_state: st.session_state.fixed_rate = 12.0
    if "rate_basis" not in st.session_state: st.session_state.rate_basis = "שנתית"
    if "rate_edit_open" not in st.session_state: st.session_state.rate_edit_open = False

    checks = cached_checks(current_user())
    options = ["— הזנה ידנית —"] + [f"{c['client_name']} | {fmt_ils(c['amount'])} | {fmt_date(c['due_date'])}" for c in checks]
    pick = st.selectbox("בחר צ'ק קיים", options, key="calc_pick")

    default_amount = 10000.0
    default_due = date.today() + timedelta(days=30)
    if pick != "— הזנה ידנית —":
        idx = options.index(pick)-1
        ch = checks[idx]
        default_amount = float(ch["amount"])
        try:
            default_due = ch["due_date"] if isinstance(ch["due_date"],date) else datetime.fromisoformat(str(ch["due_date"])).date()
        except: pass

    if st.session_state.get("_last_pick") != pick:
        st.session_state.calc_due = default_due
        st.session_state.calc_amount = default_amount
        st.session_state._last_pick = pick

    amount = st.number_input("סכום הצ'ק (₪)", min_value=0.0, step=100.0,
                             value=st.session_state.get("calc_amount", default_amount),
                             format="%.0f", key="calc_amount")
    due_date = st.date_input("תאריך פירעון", key="calc_due", min_value=date.today(),
                             help="החישוב כולל את יום הפירעון")

    days = max((due_date-date.today()).days+1, 0)
    st.markdown(
        f"<div style='background:rgba(229,154,101,.12);border:1px solid rgba(229,154,101,.2);border-radius:18px;padding:14px;text-align:center;margin:6px 0 10px;'>"
        f"<span style='font-size:10px;font-weight:700;letter-spacing:1.2px;color:#8c6a45;text-transform:uppercase;display:block;margin-bottom:2px;'>ימי זיכוי</span>"
        f"<span style='font-size:2.2rem;font-weight:900;color:#e59a65;letter-spacing:-1.5px;'>{days}</span>"
        f"<span style='font-size:.9rem;font-weight:600;color:#8c6a45;'> ימים</span></div>",
        unsafe_allow_html=True)

    # Basis buttons — no label
    basis = st.radio("", ["ריבית חודשית", "ריבית שנתית"],
                     index=0 if st.session_state.rate_basis=="חודשית" else 1,
                     horizontal=True, key="basis_radio", label_visibility="collapsed")
    st.session_state.rate_basis = "חודשית" if basis=="שכר טרחה חודשי" else "שנתית"

    rate_val = st.session_state.fixed_rate
    r1, r2 = st.columns([2,1])
    with r1:
        st.markdown(
            f"<div style='background:rgba(30,35,42,.85);border:1px solid rgba(229,154,101,.2);border-radius:16px;padding:14px;text-align:center;'>"
            f"<span style='font-size:10px;font-weight:700;letter-spacing:1.2px;color:#8c6a45;text-transform:uppercase;display:block;margin-bottom:4px;'>אחוז שכ\"ט</span>"
            f"<span style='font-size:1.8rem;font-weight:900;color:#e59a65;letter-spacing:-1px;'>{rate_val:.2f}%</span>"
            f"</div>", unsafe_allow_html=True)
    with r2:
        if st.button("✏️ שינוי", use_container_width=True, key="edit_rate"):
            st.session_state.rate_edit_open = not st.session_state.rate_edit_open
    if st.session_state.rate_edit_open:
        new_rate = st.number_input("אחוז שכ\"ט (%)", min_value=0.0, max_value=100.0,
                                   value=float(rate_val), step=0.1, format="%.2f", key="rate_input_manual")
        if st.button("💾 שמור", use_container_width=True, key="save_rate"):
            st.session_state.fixed_rate = new_rate; st.session_state.rate_edit_open = False; st.rerun()

    fee = amount*(rate_val/100.0)*(days/30.0 if st.session_state.rate_basis=="חודשית" else days/365.0)
    net = amount-fee

    if days<=0:
        st.markdown("<div style='background:rgba(255,45,149,.15);border:1px solid rgba(255,45,149,.3);border-radius:14px;padding:10px;text-align:center;font-size:13px;font-weight:700;color:#ff6bba;margin:8px 0;'>⚠️ תאריך הפירעון עבר</div>", unsafe_allow_html=True)

    st.markdown(f"""<div class="calc-out fee"><div class="lbl">עמלה שיורדת</div><div class="big">{fmt_ils(fee)}</div></div>
    <div class="calc-out net"><div class="lbl">נטו מזומן שמתקבל</div><div class="big">{fmt_ils(net)}</div></div>""", unsafe_allow_html=True)


# ─── Management screen ───
CLIENT_PALETTE = [
    ("#E8E4FF","#5A5AA3"),("#D6F5E0","#2A7A4A"),("#FFD6E8","#8A2A50"),
    ("#E8F5A3","#5A6800"),("#FFF3C8","#8A6A00"),("#C8E8FF","#1A5A8A"),("#FFE8D6","#8A3A00"),
]

def render_upcoming_reminder():
    u = current_user()
    upcoming_raw = cached_upcoming(u)
    if not upcoming_raw: return
    today = date.today()
    day_labels = {today.isoformat():"היום",(today+timedelta(days=1)).isoformat():"מחר",(today+timedelta(days=2)).isoformat():"מחרתיים"}
    total_checks = sum(len(v) for v in upcoming_raw.values())
    total_amount = sum(ch["amount"] for v in upcoming_raw.values() for ch in v)
    st.markdown(
        f"<div class='reminder-card'>"
        f"<div class='reminder-title'>⏰ פירעונות קרובים</div>"
        f"<div style='display:flex;justify-content:space-between;'>"
        f"<span style='font-weight:800;font-size:1rem;color:#dec599;'>{total_checks} צ'קים</span>"
        f"<span style='font-weight:900;font-size:1rem;color:#e59a65;'>{fmt_ils(total_amount)}</span>"
        f"</div></div>", unsafe_allow_html=True)
    expanded = st.session_state.get("reminder_open", False)
    if st.button("📋 פרטים" if not expanded else "✖ סגור", key="toggle_reminder"):
        st.session_state.reminder_open = not expanded; st.rerun()
    if not st.session_state.get("reminder_open", False): return
    for d_str, checks in sorted(upcoming_raw.items()):
        label = day_labels.get(d_str, d_str)
        day_sum = sum(ch["amount"] for ch in checks)
        rows_html = "".join(
            f"<div class='reminder-row'><span style='font-weight:700;color:#dec599;'>{ch['client_name']}</span>"
            f"<span style='font-weight:900;color:#e59a65;'>{fmt_ils(ch['amount'])}</span></div>"
            for ch in checks)
        st.markdown(
            f"<div style='background:rgba(30,35,42,.85);border:1px solid rgba(229,154,101,.15);border-radius:16px;padding:12px 14px;margin-bottom:5px;'>"
            f"<div style='font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8c6a45;margin-bottom:8px;'>"
            f"{label} | {fmt_ils(day_sum)}</div>{rows_html}</div>", unsafe_allow_html=True)


def render_add_check_form():
    u = current_user()
    clients = cached_clients(u)
    names = [c["name"] for c in clients]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="btn-single">', unsafe_allow_html=True)
        if st.button("➕ צ'ק בודד", key="open_single", use_container_width=True):
            st.session_state.add_mode = "single" if st.session_state.get("add_mode")!="single" else None
        st.markdown('</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="btn-batch">', unsafe_allow_html=True)
        if st.button("📦 מקבץ צ'קים", key="open_batch", use_container_width=True):
            st.session_state.add_mode = "batch" if st.session_state.get("add_mode")!="batch" else None
        st.markdown('</div>', unsafe_allow_html=True)

    if "batch_summary" in st.session_state and st.session_state.batch_summary:
        import pandas as pd
        bs = st.session_state.batch_summary
        st.markdown(
            f"<div style='background:rgba(42,122,74,.2);border:1px solid rgba(57,255,20,.2);border-radius:20px;padding:16px 18px;margin-bottom:10px;'>"
            f"<div style='font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#6ddf8a;margin-bottom:10px;'>✅ {bs['count']} צ'קים נשמרו | שכ\"ט {bs['rate_val']:.2f}% {bs['rate_basis']}</div>",
            unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(bs["rows"]), use_container_width=True, hide_index=True)
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;padding:10px 4px 4px;font-weight:800;font-size:1rem;color:#dec599;'>"
            f"<span>סה\"כ עמלות: {fmt_ils(bs['total_fee'])}</span><span>סה\"כ נטו: {fmt_ils(bs['total_net'])}</span></div></div>",
            unsafe_allow_html=True)
        if st.button("✖ סגור", key="close_summary"):
            st.session_state.batch_summary = None; st.rerun()

    mode = st.session_state.get("add_mode")
    if not mode: return
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    sel = st.selectbox("לקוח", ["— חדש —"]+names, key="add_client_sel")
    new_name = None
    if sel == "— חדש —":
        new_name = st.text_input("שם לקוח חדש", key="new_client_name", placeholder="הזן שם לקוח...")

    # Get client rate if existing
    client_rate = 12.0
    client_basis = "שנתית"
    if sel != "— חדש —":
        cl = next((c for c in clients if c["name"]==sel), None)
        if cl:
            client_rate = float(cl["rate"] or 12.0)
            client_basis = cl["rate_basis"] or "שנתית"

    if mode == "single":
        amount = st.number_input("סכום הצ'ק (₪)", min_value=0.0, step=100.0, format="%.0f", key="add_amount")
        c1, c2 = st.columns(2)
        with c1:
            due = st.date_input("תאריך פירעון", value=date.today()+timedelta(days=30), min_value=date.today(), key="add_due")
        with c2:
            use_remind = st.checkbox("תזכורת", value=False, key="add_use_remind")
        remind = st.date_input("תאריך תזכורת", value=date.today()+timedelta(days=30), min_value=date.today(), key="add_remind") if use_remind else None
        status = st.selectbox("סטטוס", STATUSES, key="add_status")

        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        ra, rb = st.columns(2)
        with ra:
            single_rate = st.number_input("אחוז שכ\"ט (%)", min_value=0.0, max_value=100.0,
                                          value=client_rate, step=0.1, format="%.2f", key="single_rate")
        with rb:
            single_basis_lbl = st.radio("", ["שכר טרחה חודשי","שכר טרחה שנתי"],
                                    index=["חודשית","שנתית"].index(client_basis),
                                    key="single_basis", horizontal=True, label_visibility="collapsed")
        single_basis = "חודשית" if single_basis_lbl=="שכר טרחה חודשי" else "שנתית"
        st.session_state.fixed_rate = single_rate
        st.session_state.rate_basis = single_basis

        if amount > 0:
            fee, days = calc_fee(amount, due, single_rate, single_basis)
            net = amount-fee
            st.markdown(
                f"<div style='background:rgba(229,154,101,.1);border:1px solid rgba(229,154,101,.2);border-radius:16px;padding:12px 14px;margin:8px 0;display:flex;justify-content:space-between;'>"
                f"<div style='text-align:center;'><div style='font-size:10px;font-weight:700;color:#8c6a45;'>{days} ימים</div>"
                f"<div style='font-weight:900;font-size:1rem;color:#e59a65;'>{fmt_ils(fee)}</div>"
                f"<div style='font-size:10px;color:#8c6a45;'>עמלה</div></div>"
                f"<div style='text-align:center;'><div style='font-size:10px;font-weight:700;color:#6ddf8a;'>נטו מזומן</div>"
                f"<div style='font-weight:900;font-size:1.1rem;color:#dec599;'>{fmt_ils(net)}</div>"
                f"<div style='font-size:10px;color:#6ddf8a;'>מתקבל</div></div></div>",
                unsafe_allow_html=True)

        if st.button("💾 שמירת צ'ק", use_container_width=True, key="save_single"):
            cid = add_client(new_name or "", single_rate, single_basis) if sel=="— חדש —" else next((c["id"] for c in clients if c["name"]==sel), None)
            if not cid: st.error("נא לבחור או להזין שם לקוח.")
            elif amount<=0: st.error("נא להזין סכום גדול מאפס.")
            else:
                if sel != "— חדש —": update_client_rate(cid, single_rate, single_basis)
                add_check(cid, amount, due, status, remind)
                invalidate_cache(); st.session_state.add_mode=None; st.rerun()

    elif mode == "batch":
        import pandas as pd
        amount_base = st.number_input("סכום לכל צ'ק (₪)", min_value=0.0, step=100.0, format="%.0f", key="batch_amount")
        b1, b2, b3 = st.columns(3)
        with b1: first_date = st.date_input("תאריך ראשון", value=date.today()+timedelta(days=30), min_value=date.today(), key="batch_first")
        with b2: count = st.number_input("מספר צ'קים", min_value=2, max_value=36, value=4, step=1, key="batch_count", format="%d")
        with b3: gap = st.number_input("קפיצה (ימים)", min_value=1, max_value=90, value=30, step=1, key="batch_gap", format="%d")
        status = st.selectbox("סטטוס", STATUSES, key="batch_status")

        ba, bb = st.columns(2)
        with ba:
            batch_rate = st.number_input("אחוז שכ\"ט (%)", min_value=0.0, max_value=100.0,
                                         value=client_rate, step=0.1, format="%.2f", key="batch_rate")
        with bb:
            batch_basis_lbl = st.radio("", ["שכר טרחה חודשי","שכר טרחה שנתי"],
                                   index=["חודשית","שנתית"].index(client_basis),
                                   key="batch_basis", horizontal=True, label_visibility="collapsed")
        batch_basis = "חודשית" if batch_basis_lbl=="שכר טרחה חודשי" else "שנתית"
        st.session_state.fixed_rate = batch_rate
        st.session_state.rate_basis = batch_basis

        if st.button("🔄 צור טבלה", use_container_width=True, key="gen_table"):
            rows = [{"#":i+1,"סכום (₪)":float(amount_base),"תאריך":(first_date+timedelta(days=int(gap)*i)).isoformat()} for i in range(int(count))]
            st.session_state.batch_df = pd.DataFrame(rows)[["#","סכום (₪)","תאריך"]]
            st.session_state.batch_edit_idx = None

        if "batch_df" in st.session_state and st.session_state.batch_df is not None:
            df = st.session_state.batch_df
            edit_idx = st.session_state.get("batch_edit_idx", None)

            for idx, row in df.iterrows():
                date_val = str(row["תאריך"])
                amt_val = float(row["סכום (₪)"])
                fee_v, _ = calc_fee(amt_val, datetime.fromisoformat(date_val).date(), batch_rate, batch_basis)
                net_v = amt_val - fee_v
                is_editing = (edit_idx == idx)

                row_html = (
                    f"<div class='batch-row' style='{'border-color:rgba(229,154,101,.5);' if is_editing else ''}'>"
                    f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                    f"<span style='font-size:11px;font-weight:800;color:#e59a65;'>#{int(row['#'])}</span>"
                    f"<span style='font-weight:700;color:#dec599;font-size:.95rem;'>{fmt_ils(amt_val)}</span>"
                    f"<span style='font-size:12px;color:#8c6a45;'>{date_val}</span>"
                    f"<span style='font-size:11px;color:#5a4030;'>עמלה: {fmt_ils(fee_v)}</span>"
                    f"</div></div>"
                )
                st.markdown(row_html, unsafe_allow_html=True)

                if st.button("✏️ ערוך" if not is_editing else "✖ סגור", key=f"edit_row_{idx}", use_container_width=False):
                    st.session_state.batch_edit_idx = idx if not is_editing else None
                    st.rerun()

                if is_editing:
                    ea, eb = st.columns(2)
                    with ea:
                        new_amt = st.number_input("סכום", min_value=0.0, value=amt_val, step=100.0, format="%.0f", key=f"amt_{idx}")
                    with eb:
                        new_date = st.date_input("תאריך", value=datetime.fromisoformat(date_val).date(), key=f"dt_{idx}")
                    if st.button("✅ עדכן שורה", key=f"upd_row_{idx}", use_container_width=True):
                        df.at[idx,"סכום (₪)"] = float(new_amt)
                        df.at[idx,"תאריך"] = new_date.isoformat()
                        st.session_state.batch_df = df
                        st.session_state.batch_edit_idx = None
                        st.rerun()

            # Total summary
            total_fee = sum(calc_fee(float(r["סכום (₪)"]), datetime.fromisoformat(str(r["תאריך"])).date(), batch_rate, batch_basis)[0] for _, r in df.iterrows())
            total_amt = df["סכום (₪)"].sum()
            st.markdown(
                f"<div style='background:rgba(229,154,101,.08);border:1px solid rgba(229,154,101,.2);border-radius:14px;padding:12px 14px;margin:8px 0;display:flex;justify-content:space-between;'>"
                f"<span style='font-weight:700;color:#8c6a45;font-size:12px;'>סה\"כ עמלות: {fmt_ils(total_fee)}</span>"
                f"<span style='font-weight:700;color:#6ddf8a;font-size:12px;'>נטו: {fmt_ils(total_amt-total_fee)}</span></div>",
                unsafe_allow_html=True)

            if st.button("💾 שמור את כל הצ'קים", use_container_width=True, key="save_batch"):
                cid = add_client(new_name or "", batch_rate, batch_basis) if sel=="— חדש —" else next((c["id"] for c in clients if c["name"]==sel), None)
                if not cid: st.error("נא לבחור או להזין שם לקוח.")
                else:
                    if sel != "— חדש —": update_client_rate(cid, batch_rate, batch_basis)
                    amounts = df["סכום (₪)"].tolist()
                    due_dates = [datetime.fromisoformat(str(d)).date() for d in df["תאריך"].tolist()]
                    add_checks_batch(cid, amounts, due_dates, status)
                    today_d = date.today()
                    summary_rows, total_fee2, total_net = [], 0.0, 0.0
                    for amt, dd in zip(amounts, due_dates):
                        fee2, _ = calc_fee(float(amt), dd, batch_rate, batch_basis)
                        net2 = float(amt)-fee2; total_fee2+=fee2; total_net+=net2
                        summary_rows.append({"תאריך":fmt_date(dd),"סכום":fmt_ils(amt),"עמלה":fmt_ils(fee2),"נטו":fmt_ils(net2)})
                    st.session_state.batch_summary = {"rows":summary_rows,"total_fee":total_fee2,"total_net":total_net,"count":len(amounts),"rate_val":batch_rate,"rate_basis":batch_basis}
                    invalidate_cache(); st.session_state.add_mode=None; st.session_state.batch_df=None; st.rerun()


def render_clients():
    st.markdown('<div class="section-title">הלקוחות שלי</div>', unsafe_allow_html=True)
    st.markdown('<div class="neon-bar"></div>', unsafe_allow_html=True)
    u = current_user()
    rows = [r for r in cached_obligo(u) if r["cnt"]>0]
    if not rows:
        st.markdown('<div class="glass">אין עדיין צ\'קים ⬆️</div>', unsafe_allow_html=True); return

    for i, r in enumerate(rows):
        bg, txt = CLIENT_PALETTE[i%len(CLIENT_PALETTE)]
        st.markdown(f"""<div class="client-card" style="background:rgba(30,35,42,.85);">
            <div><div class="client-name">{r['name']}</div>
            <div style="font-size:.78rem;color:#8c6a45;font-weight:600;">{r['cnt']} צ'קים</div></div>
            <div class="client-obligo">{fmt_ils(r['obligo'])}</div>
        </div>""", unsafe_allow_html=True)
        with st.expander("צפייה בצ'קים"):
            for ch in cached_checks(u, r["id"]):
                color = STATUS_COLORS.get(ch["status"],"#888")
                remind_str = f" | תזכורת: {fmt_date(ch['remind_on'])}" if ch["remind_on"] else ""
                cc1, cc2 = st.columns([3,2])
                with cc1:
                    st.markdown(f"""<div style="padding:5px 0;">
                        <span style="font-weight:700;direction:ltr;color:#e59a65;">{fmt_ils(ch['amount'])}</span><br>
                        <span style="font-size:.78rem;color:#8c6a45;">פירעון: {fmt_date(ch['due_date'])}{remind_str}</span>
                        <span class="pill" style="background:{color}22;color:{color};border:1px solid {color}66;">{ch['status']}</span>
                    </div>""", unsafe_allow_html=True)
                with cc2:
                    new_st = st.selectbox("סטטוס", STATUSES, index=STATUSES.index(ch["status"]),
                                          key=f"st_{ch['id']}", label_visibility="collapsed")
                    st.markdown('<div class="btn-sm">', unsafe_allow_html=True)
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("✓", key=f"upd_{ch['id']}", use_container_width=True):
                            update_status(ch["id"], new_st); invalidate_cache(); st.rerun()
                    with b2:
                        if st.button("🗑", key=f"del_{ch['id']}", use_container_width=True):
                            delete_check(ch["id"]); invalidate_cache(); st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)


# ─── Main ───
def main():
    init_db()
    inject_css()

    if "current_user" not in st.session_state:
        st.session_state.current_user = "admin"
    if "screen" not in st.session_state:
        st.session_state.screen = "home"

    screen = st.session_state.screen

    if screen == "home":
        render_home_screen()
    elif screen == "calc":
        render_calculator()
    elif screen == "mgmt":
        render_back_button()
        render_kpi()
        render_upcoming_reminder()
        render_add_check_form()
        render_clients()
    elif screen == "dash":
        render_dashboard()


if __name__ == "__main__":
    main()
