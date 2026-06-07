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

@contextmanager
def get_conn():
    try:
        conn = psycopg.connect(get_db_url(), row_factory=dict_row)
    except Exception as e:
        st.error(f"❌ שגיאת חיבור: {e}"); st.stop()
    try:
        yield conn; conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()

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

def invalidate_cache():
    cached_totals.clear(); cached_checks.clear(); cached_clients.clear()
    cached_obligo.clear(); cached_upcoming.clear(); cached_forecast.clear()
    cached_status_breakdown.clear()

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
.stApp{background:#041424;background-image:linear-gradient(135deg,#041424 0%,#0b243a 50%,#041424 100%);font-family:'Inter',sans-serif;color:#dec599;min-height:100vh}
#MainMenu,header,footer{visibility:hidden}
.block-container{padding-top:0!important;padding-bottom:6rem;max-width:480px}
.logo-title{font-family:'Comfortaa',sans-serif;font-weight:700;font-size:2.6rem;white-space:nowrap;background:linear-gradient(135deg,#e59a65 0%,#f0c090 40%,#b06a3b 70%,#e59a65 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;filter:drop-shadow(0px 3px 6px rgba(0,0,0,.7));display:block;text-align:center;line-height:1;margin-bottom:2px}
.kpi{background:rgba(30,35,42,.85);border:1px solid rgba(229,154,101,.25);border-radius:24px;padding:18px 20px 14px;margin-bottom:6px;text-align:center;box-shadow:0 8px 32px rgba(0,0,0,.4),inset 0 1px 0 rgba(229,154,101,.15)}
.kpi-label{font-size:10px;font-weight:700;letter-spacing:2px;color:#e59a65;text-transform:uppercase;margin-bottom:4px}
.kpi-value{font-family:'Inter',sans-serif;font-size:2.4rem;font-weight:900;line-height:1;background:linear-gradient(135deg,#f0c090 0%,#e59a65 50%,#dec599 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;display:block;letter-spacing:-2px;direction:ltr}
.kpi-sub{font-size:12px;color:#8c6a45;margin-top:6px;font-weight:500}
.glass{background:rgba(30,35,42,.7);border:1px solid rgba(229,154,101,.15);border-radius:22px;padding:18px 20px;margin-bottom:5px;box-shadow:0 4px 16px rgba(0,0,0,.3)}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:11px;font-weight:700;margin-inline-start:6px}
.section-title{font-size:20px;font-weight:900;letter-spacing:-.5px;color:#e59a65;margin:16px 0 4px;text-align:right}
.section-title-right{font-size:20px;font-weight:900;letter-spacing:-.5px;color:#e59a65;margin:8px 0 4px;text-align:right}
.neon-bar{height:2px;width:36px;border-radius:3px;background:linear-gradient(90deg,#e59a65,#b06a3b);margin:0 auto 14px}
.neon-bar-right{height:2px;width:36px;border-radius:3px;background:linear-gradient(90deg,#e59a65,#b06a3b);margin:0 0 14px auto}
.client-card{display:flex;justify-content:space-between;align-items:center;background:rgba(30,35,42,.85);border:1px solid rgba(229,154,101,.2);border-radius:20px;padding:14px 16px;margin-bottom:5px;box-shadow:0 4px 16px rgba(0,0,0,.3)}
.client-name{font-weight:800;font-size:.95rem;color:#dec599}
.client-obligo{font-weight:900;font-size:1.1rem;background:linear-gradient(135deg,#e59a65,#dec599);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;direction:ltr;letter-spacing:-.5px}
.calc-out{border-radius:22px;padding:18px 20px;margin-top:5px;text-align:center}
.calc-out.fee{background:rgba(140,42,80,.25);border:1px solid rgba(255,45,149,.2)}
.calc-out.net{background:rgba(42,122,74,.25);border:1px solid rgba(57,255,20,.2);margin-top:5px}
.calc-out .lbl{font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#8c6a45;margin-bottom:6px}
.calc-out .big{font-family:'Inter',sans-serif;font-size:2.4rem;font-weight:900;direction:ltr;line-height:1.1;letter-spacing:-1.5px;color:#dec599}
.reminder-card{background:rgba(139,106,0,.2);border:1px solid rgba(229,154,101,.25);border-radius:20px;padding:14px 16px;margin-bottom:6px}
.reminder-title{font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#e59a65;margin-bottom:8px}
.reminder-row{display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid rgba(229,154,101,.1)}
.reminder-row:last-child{border-bottom:none}
/* carousel */
.carousel-wrap{display:flex;gap:12px;overflow-x:auto;padding:8px 2px 12px;scrollbar-width:none;-ms-overflow-style:none}
.carousel-wrap::-webkit-scrollbar{display:none}
/* round nav buttons */
div[data-testid="column"] .stButton>button {
    border-radius: 50% !important;
    width: 100px !important;
    height: 100px !important;
    padding: 0 !important;
    font-size: 0.62rem !important;
    font-weight: 800 !important;
    line-height: 1.3 !important;
    white-space: pre-wrap !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    margin: 0 auto !important;
    animation: pulse-glow 2.5s ease-in-out infinite !important;
}
div[data-testid="column"]:nth-child(1) .stButton>button {
    background: linear-gradient(135deg,#1a3a2a,#0f4a22) !important;
    border-color: rgba(57,255,20,.4) !important;
    color: #6ddf8a !important;
    box-shadow: 0 0 20px rgba(57,255,20,.2), 0 8px 24px rgba(0,0,0,.5) !important;
    animation: pulse-green 2.5s ease-in-out infinite !important;
}
div[data-testid="column"]:nth-child(2) .stButton>button {
    background: linear-gradient(135deg,#3a2a1a,#4a1a0f) !important;
    border-color: rgba(229,154,101,.5) !important;
    color: #e59a65 !important;
    box-shadow: 0 0 20px rgba(229,154,101,.25), 0 8px 24px rgba(0,0,0,.5) !important;
    animation: pulse-copper 2.5s ease-in-out infinite !important;
    animation-delay: .4s !important;
}
div[data-testid="column"]:nth-child(3) .stButton>button {
    background: linear-gradient(135deg,#1a2a3a,#0f1a4a) !important;
    border-color: rgba(100,160,229,.4) !important;
    color: #90bfdf !important;
    box-shadow: 0 0 20px rgba(100,160,229,.2), 0 8px 24px rgba(0,0,0,.5) !important;
    animation: pulse-blue 2.5s ease-in-out infinite !important;
    animation-delay: .8s !important;
}
div[data-testid="column"] .stButton>button:hover {
    transform: scale(1.12) rotate(-3deg) !important;
    animation: none !important;
    box-shadow: 0 0 40px currentColor, 0 12px 32px rgba(0,0,0,.6) !important;
}
@keyframes pulse-green {
    0%,100% { box-shadow: 0 0 15px rgba(57,255,20,.2), 0 8px 24px rgba(0,0,0,.5); transform: scale(1); }
    50% { box-shadow: 0 0 35px rgba(57,255,20,.5), 0 8px 24px rgba(0,0,0,.5); transform: scale(1.06) rotate(2deg); }
}
@keyframes pulse-copper {
    0%,100% { box-shadow: 0 0 15px rgba(229,154,101,.2), 0 8px 24px rgba(0,0,0,.5); transform: scale(1); }
    50% { box-shadow: 0 0 35px rgba(229,154,101,.5), 0 8px 24px rgba(0,0,0,.5); transform: scale(1.06) rotate(-2deg); }
}
@keyframes pulse-blue {
    0%,100% { box-shadow: 0 0 15px rgba(100,160,229,.2), 0 8px 24px rgba(0,0,0,.5); transform: scale(1); }
    50% { box-shadow: 0 0 35px rgba(100,160,229,.5), 0 8px 24px rgba(0,0,0,.5); transform: scale(1.06) rotate(2deg); }
}
/* general buttons */
.stButton>button{border-radius:14px!important;border:1px solid rgba(229,154,101,.2)!important;background:rgba(30,35,42,.9)!important;color:#dec599!important;font-weight:700!important;font-family:'Inter',sans-serif!important;transition:all .12s ease!important;box-shadow:0 3px 10px rgba(0,0,0,.3)!important}
.stButton>button:hover{border-color:rgba(229,154,101,.5)!important}
.btn-single .stButton>button{border-radius:50px!important;background:linear-gradient(135deg,#e59a65 0%,#b06a3b 100%)!important;color:#fff!important;font-size:.92rem!important;font-weight:800!important;padding:13px 0!important;border:none!important;box-shadow:0 4px 16px rgba(176,106,59,.4)!important}
.btn-batch .stButton>button{border-radius:50px!important;background:rgba(30,35,42,.9)!important;color:#e59a65!important;font-size:.92rem!important;font-weight:800!important;padding:13px 0!important;border:1px solid rgba(229,154,101,.4)!important}
.btn-sm .stButton>button{padding:3px 8px!important;font-size:.75rem!important;border-radius:8px!important;min-height:0!important;height:auto!important;font-weight:700!important}
.back-btn{position:fixed!important;bottom:28px!important;left:20px!important;z-index:9999!important}
.back-btn .stButton>button{border-radius:50px!important;background:linear-gradient(135deg,#e59a65 0%,#b06a3b 100%)!important;color:#fff!important;font-size:.82rem!important;font-weight:800!important;padding:10px 22px!important;height:auto!important;min-height:0!important;border:none!important;box-shadow:0 4px 20px rgba(176,106,59,.5)!important}
/* inputs */
.stTextInput input,.stNumberInput input,.stDateInput input,[data-baseweb="input"] input,[data-baseweb="base-input"] input{color:#dec599!important;background-color:rgba(30,35,42,.9)!important;-webkit-text-fill-color:#dec599!important;caret-color:#e59a65!important;border-radius:12px!important;border:1px solid rgba(229,154,101,.2)!important;font-weight:600!important;font-size:.95rem!important;direction:rtl!important;text-align:right!important}
.stTextInput div[data-baseweb="input"],.stNumberInput div[data-baseweb="input"],.stDateInput div[data-baseweb="input"],div[data-baseweb="select"]>div{background-color:rgba(30,35,42,.9)!important;border:1px solid rgba(229,154,101,.2)!important;border-radius:12px!important}
div[data-baseweb="select"] div{color:#dec599!important;font-weight:600!important}
input::placeholder{color:#5a4030!important;opacity:1!important}
div[data-testid="stNumberInput"]:has(input[aria-label*="סכום"]) input{font-size:1.8rem!important;font-weight:900!important;text-align:center!important;letter-spacing:-1px!important;height:64px!important}
label{color:#8c6a45!important;font-weight:700!important;font-size:10px!important;letter-spacing:.8px!important;text-transform:uppercase!important;text-align:right!important;display:block!important}
/* radio basis buttons */
div[data-testid="stRadio"]>div{gap:8px!important;justify-content:center!important}
div[data-testid="stRadio"] label{background:rgba(30,35,42,.9)!important;border:1px solid rgba(229,154,101,.2)!important;border-radius:12px!important;padding:9px 22px!important;font-size:.9rem!important;font-weight:800!important;color:#dec599!important;cursor:pointer;text-transform:none!important;letter-spacing:0!important}
div[data-testid="stRadio"] label:hover{border-color:rgba(229,154,101,.5)!important}
div[data-testid="stRadio"] input[type="radio"]{display:none!important}
div[data-testid="stRadio"] div[data-baseweb="radio"]>div:first-child{display:none!important}
/* tabs */
.stTabs [data-baseweb="tab-list"]{gap:5px;justify-content:center;background:transparent!important}
.stTabs [data-baseweb="tab"]{background:rgba(30,35,42,.9)!important;border:1px solid rgba(229,154,101,.15)!important;border-radius:12px!important;padding:9px 20px!important;font-size:.88rem!important;font-weight:700!important;color:#8c6a45!important;min-width:110px;text-align:center}
.stTabs [data-baseweb="tab"] p,.stTabs [data-baseweb="tab"] span,.stTabs [data-baseweb="tab"] div{color:#8c6a45!important}
.stTabs [aria-selected="true"]{background:linear-gradient(135deg,#e59a65 0%,#b06a3b 100%)!important;border-color:transparent!important}
.stTabs [aria-selected="true"] p,.stTabs [aria-selected="true"] span,.stTabs [aria-selected="true"] div{color:#fff!important}
/* expander */
.streamlit-expanderHeader{background:rgba(30,35,42,.9)!important;border-radius:12px!important;font-weight:700!important;color:#dec599!important;border:1px solid rgba(229,154,101,.15)!important}
.streamlit-expanderContent{background:rgba(20,25,32,.8)!important;border:none!important}
.stCheckbox label{color:#dec599!important;font-weight:700!important;font-size:.88rem!important;text-transform:none!important;letter-spacing:0!important}
ul[role="listbox"],div[data-baseweb="popover"]{background-color:#0b1a2a!important;border:1px solid rgba(229,154,101,.2)!important;border-radius:14px!important}
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
.dash-day-card{background:rgba(30,35,42,.85);border:1px solid rgba(229,154,101,.2);border-radius:20px;padding:14px 16px;margin-bottom:6px;cursor:pointer;transition:border-color .15s}
.dash-day-card:hover{border-color:rgba(229,154,101,.5)}
.dash-month-card{background:rgba(30,35,42,.85);border:1px solid rgba(229,154,101,.15);border-radius:20px;padding:14px 16px;margin-bottom:5px}
.dash-bar-bg{background:rgba(255,255,255,.06);border-radius:99px;height:5px;margin-top:8px}
.dash-bar-fill{background:linear-gradient(90deg,#e59a65,#b06a3b);border-radius:99px;height:5px}
/* batch table row edit */
.batch-row{background:rgba(30,35,42,.85);border:1px solid rgba(229,154,101,.15);border-radius:14px;padding:12px 14px;margin-bottom:5px}
</style>""", unsafe_allow_html=True)

    st.components.v1.html("""<script>
function attachSelectAll(){
    var inputs=window.parent.document.querySelectorAll('input[type="number"]');
    inputs.forEach(function(inp){if(inp._sa)return;inp._sa=true;
    inp.addEventListener('focus',function(){var s=this;setTimeout(function(){s.select();},50);});});
}
attachSelectAll();setInterval(attachSelectAll,600);
</script>""", height=0)

@keyframes crazyAnim {
    0% { transform: scale(1) rotate(0deg); filter: hue-rotate(0deg); }
    25% { transform: scale(1.15) rotate(-10deg); background: #ff0055; } /* ורוד חריף */
    50% { transform: scale(0.9) rotate(10deg); background: #00ffaa; box-shadow: 0 0 25px #00ffaa; } /* טורקיז זוהר */
    75% { transform: scale(1.1) rotate(-5deg); background: #ffff00; } /* צהוב */
    100% { transform: scale(1) rotate(0deg); filter: hue-rotate(0deg); }
}

/* החלף את שם המחלקה 'my-big-button' בשם המחלקה של הכפתורים שלך */
.my-big-button:active {
    animation: crazyAnim 0.4s ease-in-out;
}

/* גרום לשורה לא לעטוף שורות חדשות */
.table-row-class {
    white-space: nowrap; 
    display: flex; /* אם אתה משתמש ב-divs, זה יסדר את הכפתור בצד */
    align-items: center;
    justify-content: space-between;
}

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
    st.markdown(
        "<div style='height:24px'></div>"
        "<p style='text-align:center;font-size:11px;font-weight:700;letter-spacing:3px;"
        "color:#8c6a45;text-transform:uppercase;margin-bottom:2px;'>CHECK MANAGEMENT</p>"
        "<h1><span class='logo-title'>CHECKFLOW</span></h1>",
        unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # 3 round nav buttons using Streamlit
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🧮\nמחשבון\nפריטה", key="go_calc", use_container_width=True):
            st.session_state.screen = "calc"; st.rerun()
    with c2:
        if st.button("📋\nניהול\nצ׳קים", key="go_mgmt", use_container_width=True):
            st.session_state.screen = "mgmt"; st.rerun()
    with c3:
        if st.button("📊\nדשבורד\nתזרים", key="go_dash", use_container_width=True):
            st.session_state.screen = "dash"; st.rerun()

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    render_kpi()


# ─── Dashboard ───
def render_dashboard():
    render_back_button()
    st.markdown('<div class="section-title">📊 דשבורד תזרים</div>', unsafe_allow_html=True)
    st.markdown('<div class="neon-bar"></div>', unsafe_allow_html=True)
    u = current_user()

    # Upcoming 2 days
    upcoming_raw = cached_upcoming(u)
    today = date.today()
    day_labels = {today.isoformat(): "היום", (today+timedelta(days=1)).isoformat(): "מחר",
                  (today+timedelta(days=2)).isoformat(): "מחרתיים"}
    day_colors = {today.isoformat(): "rgba(57,255,20,.12)", (today+timedelta(days=1)).isoformat(): "rgba(229,154,101,.12)",
                  (today+timedelta(days=2)).isoformat(): "rgba(255,45,149,.12)"}
    border_colors = {today.isoformat(): "rgba(57,255,20,.3)", (today+timedelta(days=1)).isoformat(): "rgba(229,154,101,.3)",
                     (today+timedelta(days=2)).isoformat(): "rgba(255,45,149,.3)"}

    if upcoming_raw:
        st.markdown("<div style='font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#8c6a45;margin-bottom:8px;'>פירעונות קרובים</div>", unsafe_allow_html=True)
        for d_str, checks in sorted(upcoming_raw.items()):
            label = day_labels.get(d_str, d_str)
            day_total = sum(ch["amount"] for ch in checks)
            bg = day_colors.get(d_str, "rgba(30,35,42,.85)")
            border = border_colors.get(d_str, "rgba(229,154,101,.2)")
            key = f"day_expand_{d_str}"
            expanded = st.session_state.get(key, False)

            da, db = st.columns([3, 1])
            with da:
                st.markdown(
                    f"<div style='background:{bg};border:1px solid {border};border-radius:18px;padding:12px 14px;'>"
                    f"<div style='font-size:14px;font-weight:800;color:#dec599;'>{label}</div>"
                    f"<div style='display:flex;justify-content:space-between;align-items:center;margin-top:4px;'>"
                    f"<span style='font-size:10px;color:#8c6a45;font-weight:700;'>{len(checks)} צ'קים</span>"
                    f"<span style='font-weight:900;font-size:1.1rem;color:#e59a65;direction:ltr;'>{fmt_ils(day_total)}</span>"
                    f"</div></div>", unsafe_allow_html=True)
            with db:
                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                if st.button("▼" if not expanded else "▲", key=f"btn_{key}", use_container_width=True):
                    st.session_state[key] = not expanded; st.rerun()
            if expanded:
                for ch in checks:
                    color = STATUS_COLORS.get(ch["status"], "#888")
                    st.markdown(
                        f"<div style='background:rgba(20,25,32,.8);border-radius:12px;padding:10px 14px;"
                        f"margin-bottom:4px;display:flex;justify-content:space-between;'>"
                        f"<span style='font-weight:700;color:#dec599;'>{ch['client_name']}</span>"
                        f"<div><span style='font-weight:900;color:#e59a65;direction:ltr;'>{fmt_ils(ch['amount'])}</span>"
                        f"<span class='pill' style='background:{color}22;color:{color};border:1px solid {color}66;'>{ch['status']}</span>"
                        f"</div></div>", unsafe_allow_html=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # Status breakdown
    status_rows = cached_status_breakdown(u)
    if status_rows:
        st.markdown("<div style='font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#8c6a45;margin-bottom:8px;'>לפי סטטוס</div>", unsafe_allow_html=True)
        status_bg = {"ממתין למזומן":"rgba(255,159,28,.15)","להפקדה":"rgba(57,255,20,.12)","בפריטה":"rgba(255,45,149,.12)"}
        for r in status_rows:
            bg = status_bg.get(r["status"],"rgba(30,35,42,.85)")
            color = STATUS_COLORS.get(r["status"],"#dec599")
            st.markdown(
                f"<div style='background:{bg};border:1px solid {color}33;border-radius:16px;"
                f"padding:12px 16px;margin-bottom:5px;display:flex;justify-content:space-between;align-items:center;'>"
                f"<div><span style='font-weight:800;font-size:.9rem;color:#dec599;'>{r['status']}</span>"
                f"<span style='font-size:10px;color:#8c6a45;font-weight:700;margin-right:8px;'>{r['cnt']} צ'קים</span></div>"
                f"<span style='font-weight:900;font-size:1rem;color:#e59a65;direction:ltr;'>{fmt_ils(r['total'])}</span>"
                f"</div>", unsafe_allow_html=True)

    # Monthly forecast
    forecast = cached_forecast(u)
    if forecast:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:10px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#8c6a45;margin-bottom:8px;'>תחזית חודשית</div>", unsafe_allow_html=True)
        max_amount = max(r["total"] for r in forecast) or 1
        month_he = {"January":"ינואר","February":"פברואר","March":"מרץ","April":"אפריל",
                    "May":"מאי","June":"יוני","July":"יולי","August":"אוגוסט",
                    "September":"ספטמבר","October":"אוקטובר","November":"נובמבר","December":"דצמבר"}
        for r in forecast:
            m = r["month"]
            label = m.strftime("%B %Y") if hasattr(m,"strftime") else str(m)[:7]
            for en,he in month_he.items(): label=label.replace(en,he)
            pct = int((r["total"]/max_amount)*100)
            st.markdown(
                f"<div class='dash-month-card'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                f"<div><div style='font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#8c6a45;'>{label}</div>"
                f"<div style='font-size:10px;color:#5a4030;'>{r['cnt']} צ'קים</div></div>"
                f"<div style='font-weight:900;font-size:1.2rem;color:#dec599;direction:ltr;'>{fmt_ils(r['total'])}</div></div>"
                f"<div class='dash-bar-bg'><div class='dash-bar-fill' style='width:{pct}%;'></div></div>"
                f"</div>", unsafe_allow_html=True)


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
        st.write(""); st.write("")
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
