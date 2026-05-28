# -*- coding: utf-8 -*-
"""
ניהול אובליגו ומחשבון פריטת צ'קים
Streamlit Web App — Mobile-first + Auth
Aurora Glassmorphism UI
"""

import sqlite3
from datetime import date, datetime, timedelta
from contextlib import closing

import streamlit as st
import streamlit_authenticator as stauth

st.set_page_config(
    page_title="ניהול צ'קים | פריטה",
    page_icon="💸",
    layout="centered",
    initial_sidebar_state="collapsed",
)

DB_PATH = "checks.db"

STATUSES = ["ממתין למזומן", "להפקדה", "בפריטה"]
STATUS_COLORS = {
    "ממתין למזומן": "#E8B890",
    "להפקדה":       "#40C8FF",
    "בפריטה":       "#FF6B9D",
}

CLIENT_PALETTE = [
    ("rgba(232,184,144,0.30)", "#1C1C24"),
    ("rgba(64,200,255,0.28)",  "#1C1C24"),
    ("rgba(123,60,240,0.30)",  "#ffffff"),
    ("rgba(64,220,160,0.28)",  "#1C1C24"),
    ("rgba(255,107,157,0.28)", "#1C1C24"),
    ("rgba(255,200,80,0.28)",  "#1C1C24"),
    ("rgba(80,220,220,0.28)",  "#1C1C24"),
]


# ─────────────────────────────────────────────
# DB
# ─────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_conn()) as conn, conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                name     TEXT NOT NULL,
                password TEXT NOT NULL,
                email    TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                name     TEXT NOT NULL,
                username TEXT NOT NULL DEFAULT 'admin',
                UNIQUE(name, username)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS checks (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                amount    REAL NOT NULL,
                due_date  TEXT NOT NULL,
                status    TEXT NOT NULL,
                remind_on TEXT,
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
            )
        """)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(clients)").fetchall()]
        if "username" not in cols:
            conn.execute("ALTER TABLE clients ADD COLUMN username TEXT NOT NULL DEFAULT 'admin'")
        indexes = [r[1] for r in conn.execute("PRAGMA index_list(clients)").fetchall()]
        if not any("name" in i and "username" in i for i in indexes):
            try:
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_name_user ON clients(name, username)"
                )
            except Exception:
                pass


def current_user():
    return st.session_state.get("current_user", "admin")


def add_client(name):
    name = name.strip()
    if not name:
        return None
    u = current_user()
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT OR IGNORE INTO clients (name, username) VALUES (?, ?)", (name, u)
        )
        row = conn.execute(
            "SELECT id FROM clients WHERE name=? AND username=?", (name, u)
        ).fetchone()
        return row["id"] if row else None


def get_clients():
    with closing(get_conn()) as conn:
        return conn.execute(
            "SELECT id, name FROM clients WHERE username=? ORDER BY name",
            (current_user(),),
        ).fetchall()


def add_check(client_id, amount, due_date, status, remind_on):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT INTO checks (client_id,amount,due_date,status,remind_on) VALUES (?,?,?,?,?)",
            (
                client_id,
                amount,
                due_date.isoformat(),
                status,
                remind_on.isoformat() if remind_on else None,
            ),
        )


def get_checks(client_id=None):
    u = current_user()
    q = """SELECT ch.*, cl.name AS client_name
           FROM checks ch JOIN clients cl ON cl.id=ch.client_id
           WHERE cl.username=?"""
    params = [u]
    if client_id is not None:
        q += " AND ch.client_id=?"
        params.append(client_id)
    q += " ORDER BY ch.due_date"
    with closing(get_conn()) as conn:
        return conn.execute(q, params).fetchall()


def update_status(check_id, status):
    with closing(get_conn()) as conn, conn:
        conn.execute("UPDATE checks SET status=? WHERE id=?", (status, check_id))


def delete_check(check_id):
    with closing(get_conn()) as conn, conn:
        conn.execute("DELETE FROM checks WHERE id=?", (check_id,))


def get_totals():
    u = current_user()
    with closing(get_conn()) as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(ch.amount),0) AS total, COUNT(ch.id) AS cnt
            FROM checks ch JOIN clients cl ON cl.id=ch.client_id
            WHERE cl.username=?
            """,
            (u,),
        ).fetchone()
        return row["total"], row["cnt"]


def get_client_obligo():
    with closing(get_conn()) as conn:
        return conn.execute(
            """
            SELECT cl.id, cl.name,
                   COALESCE(SUM(ch.amount),0) AS obligo,
                   COUNT(ch.id) AS cnt
            FROM clients cl
            LEFT JOIN checks ch ON ch.client_id=cl.id
            WHERE cl.username=?
            GROUP BY cl.id ORDER BY obligo DESC
            """,
            (current_user(),),
        ).fetchall()


def get_all_users_for_auth():
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT username, name, password, email FROM users"
        ).fetchall()
    creds = {"usernames": {}}
    for r in rows:
        creds["usernames"][r["username"]] = {
            "name":     r["name"],
            "password": r["password"],
            "email":    r["email"],
        }
    return creds


# ─────────────────────────────────────────────
# CSS — Aurora Glassmorphism
# ─────────────────────────────────────────────
def inject_css():
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

html, body, [class*="css"] { direction: rtl; }

/* ── Aurora Background ── */
.stApp {
    background:
        radial-gradient(ellipse at 12% 18%,  rgba(232,184,144,0.42) 0%, transparent 52%),
        radial-gradient(ellipse at 88% 78%,  rgba(64,180,255,0.38)  0%, transparent 52%),
        radial-gradient(ellipse at 68% 4%,   rgba(123,60,240,0.32)  0%, transparent 48%),
        radial-gradient(ellipse at 28% 92%,  rgba(64,220,180,0.22)  0%, transparent 44%),
        radial-gradient(ellipse at 55% 50%,  rgba(20,10,40,0.6)     0%, transparent 70%),
        #0C0C18;
    font-family: 'Inter', sans-serif;
    color: #1C1C24;
}

/* Make all Streamlit containers transparent so aurora bleeds through */
[data-testid="stAppViewContainer"],
[data-testid="stHeader"],
section[data-testid="stMain"],
[data-testid="stVerticalBlock"],
.main .block-container { background: transparent !important; }

#MainMenu, header, footer { visibility: hidden; }

.block-container {
    padding-top: 0 !important;
    padding-bottom: 5.5rem;
    max-width: 480px;
}

/* ── Frosted Glass Base ── */
.glass {
    background: rgba(255,255,255,0.14);
    backdrop-filter: blur(22px);
    -webkit-backdrop-filter: blur(22px);
    border: 1px solid rgba(255,255,255,0.28);
    border-radius: 24px;
    padding: 20px 22px;
    margin-bottom: 12px;
    box-shadow: 0 12px 28px rgba(0,0,0,0.18);
    color: #fff;
}

/* ── KPI ── */
.kpi {
    background: rgba(255,255,255,0.18);
    backdrop-filter: blur(28px);
    -webkit-backdrop-filter: blur(28px);
    border: 1px solid rgba(255,255,255,0.38);
    border-radius: 28px;
    padding: 32px 24px 26px;
    margin-bottom: 14px;
    text-align: center;
    box-shadow: 0 16px 36px rgba(0,0,0,0.20);
}
.kpi-label {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2.2px;
    color: rgba(255,255,255,0.6);
    text-transform: uppercase;
    margin-bottom: 10px;
}
.kpi-value {
    font-family: 'Inter', sans-serif;
    font-size: 3rem;
    font-weight: 900;
    line-height: 1;
    color: #fff;
    direction: ltr;
    display: block;
    letter-spacing: -2px;
    text-shadow: 0 2px 12px rgba(0,0,0,0.25);
}
.kpi-sub {
    font-size: 13px;
    color: rgba(255,255,255,0.55);
    margin-top: 10px;
    font-weight: 500;
}

/* ── pill ── */
.pill {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    margin-inline-start: 6px;
    letter-spacing: 0.3px;
    backdrop-filter: blur(8px);
}

/* ── Section Titles ── */
.section-title, .section-title-right {
    font-size: 22px;
    font-weight: 900;
    letter-spacing: -0.5px;
    color: #fff;
    margin: 22px 0 6px;
    text-align: right;
    text-shadow: 0 2px 12px rgba(0,0,0,0.35);
}
.neon-bar, .neon-bar-right {
    height: 2px;
    width: 32px;
    border-radius: 4px;
    background: rgba(255,255,255,0.45);
    margin-bottom: 16px;
    margin-right: 0;
}
.neon-bar { margin-right: auto; margin-left: auto; }

/* ── Client Cards ── */
.client-card {
    display: flex;
    justify-content: space-between;
    align-items: center;
    backdrop-filter: blur(22px);
    -webkit-backdrop-filter: blur(22px);
    border: 1px solid rgba(255,255,255,0.32);
    border-radius: 24px;
    padding: 18px 20px;
    margin-bottom: 10px;
    box-shadow: 0 8px 22px rgba(0,0,0,0.14);
}
.client-name  { font-weight: 800; font-size: 1rem; }
.client-obligo {
    font-weight: 900;
    font-size: 1.15rem;
    direction: ltr;
    letter-spacing: -0.5px;
}

/* ── Calculator Output ── */
.calc-out {
    border-radius: 24px;
    padding: 22px;
    margin-top: 10px;
    text-align: center;
    backdrop-filter: blur(22px);
    -webkit-backdrop-filter: blur(22px);
    border: 1px solid rgba(255,255,255,0.30);
    box-shadow: 0 8px 22px rgba(0,0,0,0.14);
}
.calc-out.fee { background: rgba(255,107,157,0.22); }
.calc-out.net { background: rgba(64,220,160,0.22); margin-top: 10px; }
.calc-out .lbl {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: rgba(255,255,255,0.6);
    margin-bottom: 8px;
}
.calc-out .big {
    font-family: 'Inter', sans-serif;
    font-size: 2.6rem;
    font-weight: 900;
    direction: ltr;
    line-height: 1.1;
    letter-spacing: -1.5px;
    color: #fff;
}

/* ── Home Navigation Buttons ── */
.home-nav-btn .stButton > button {
    border-radius: 28px !important;
    font-size: 1.2rem !important;
    font-weight: 900 !important;
    min-height: 90px !important;
    height: auto !important;
    padding: 26px 24px !important;
    letter-spacing: -0.3px !important;
    backdrop-filter: blur(22px) !important;
    -webkit-backdrop-filter: blur(22px) !important;
    box-shadow: 0 12px 32px rgba(0,0,0,0.22) !important;
    transition: all 0.18s ease !important;
}
.home-nav-btn .stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 18px 40px rgba(0,0,0,0.28) !important;
}
.home-nav-green .stButton > button {
    background: rgba(64,220,160,0.28) !important;
    color: #fff !important;
    border: 1px solid rgba(64,220,160,0.5) !important;
}
.home-nav-pink .stButton > button {
    background: rgba(123,60,240,0.30) !important;
    color: #fff !important;
    border: 1px solid rgba(123,60,240,0.45) !important;
}

/* ── Add Check Button ── */
.add-check-wrapper .stButton > button {
    border-radius: 50px !important;
    background: rgba(255,255,255,0.14) !important;
    backdrop-filter: blur(22px) !important;
    -webkit-backdrop-filter: blur(22px) !important;
    color: #fff !important;
    font-size: 1rem !important;
    font-weight: 800 !important;
    padding: 14px 0 !important;
    border: 1px solid rgba(255,255,255,0.30) !important;
    letter-spacing: 0.2px !important;
    box-shadow: 0 8px 22px rgba(0,0,0,0.20) !important;
}
.add-check-wrapper .stButton > button:hover {
    background: rgba(255,255,255,0.22) !important;
}

/* ── General Buttons ── */
.stButton > button {
    border-radius: 14px !important;
    border: 1px solid rgba(255,255,255,0.22) !important;
    background: rgba(255,255,255,0.12) !important;
    backdrop-filter: blur(16px) !important;
    -webkit-backdrop-filter: blur(16px) !important;
    color: #fff !important;
    font-weight: 700 !important;
    font-family: 'Inter', sans-serif !important;
    transition: all 0.15s ease !important;
    box-shadow: 0 4px 14px rgba(0,0,0,0.12) !important;
}
.stButton > button:hover {
    background: rgba(255,255,255,0.22) !important;
    box-shadow: 0 8px 22px rgba(0,0,0,0.20) !important;
}

/* ── Input Fields ── */
.stTextInput input,
.stNumberInput input,
.stDateInput input,
[data-baseweb="input"] input,
[data-baseweb="base-input"] input {
    color: #fff !important;
    background-color: rgba(255,255,255,0.12) !important;
    -webkit-text-fill-color: #fff !important;
    caret-color: #fff !important;
    border-radius: 14px !important;
    border: 1px solid rgba(255,255,255,0.22) !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
    direction: ltr !important;
    text-align: right !important;
}
.stTextInput div[data-baseweb="input"],
.stNumberInput div[data-baseweb="input"],
.stDateInput div[data-baseweb="input"],
div[data-baseweb="select"] > div {
    background-color: rgba(255,255,255,0.12) !important;
    border: 1px solid rgba(255,255,255,0.22) !important;
    border-radius: 14px !important;
    backdrop-filter: blur(16px) !important;
}
div[data-baseweb="select"] div { color: #fff !important; font-weight: 600 !important; }
input::placeholder { color: rgba(255,255,255,0.4) !important; opacity: 1 !important; }
ul[role="listbox"],
div[data-baseweb="popover"] {
    background-color: rgba(20,18,40,0.92) !important;
    backdrop-filter: blur(24px) !important;
    border: 1px solid rgba(255,255,255,0.2) !important;
    border-radius: 16px !important;
}
ul[role="listbox"] li { color: #fff !important; font-weight: 600 !important; }
label {
    color: rgba(255,255,255,0.55) !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
}

/* ── Radio Buttons ── */
div[data-testid="stRadio"] > div { gap: 10px !important; justify-content: center !important; }
div[data-testid="stRadio"] label {
    background: rgba(255,255,255,0.12) !important;
    backdrop-filter: blur(16px) !important;
    border: 1px solid rgba(255,255,255,0.22) !important;
    border-radius: 14px !important;
    padding: 10px 28px !important;
    font-size: 1rem !important;
    font-weight: 800 !important;
    color: #fff !important;
    cursor: pointer;
    transition: all 0.12s ease;
}
div[data-testid="stRadio"] label:hover {
    background: rgba(255,255,255,0.22) !important;
}
div[data-testid="stRadio"] input[type="radio"] { display: none !important; }
div[data-testid="stRadio"] div[data-baseweb="radio"] > div:first-child { display: none !important; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    justify-content: center;
    background: transparent !important;
}
.stTabs [data-baseweb="tab"] {
    background: rgba(255,255,255,0.10) !important;
    backdrop-filter: blur(16px) !important;
    border: 1px solid rgba(255,255,255,0.18) !important;
    border-radius: 14px !important;
    padding: 10px 24px !important;
    font-size: 0.95rem !important;
    font-weight: 700 !important;
    color: rgba(255,255,255,0.6) !important;
    min-width: 130px;
    text-align: center;
    transition: all 0.15s ease !important;
}
.stTabs [data-baseweb="tab"] p,
.stTabs [data-baseweb="tab"] span,
.stTabs [data-baseweb="tab"] div { color: rgba(255,255,255,0.6) !important; }
.stTabs [aria-selected="true"] {
    background: rgba(255,255,255,0.28) !important;
    border: 1px solid rgba(255,255,255,0.45) !important;
}
.stTabs [aria-selected="true"] p,
.stTabs [aria-selected="true"] span,
.stTabs [aria-selected="true"] div { color: #fff !important; }

/* ── Expander ── */
.streamlit-expanderHeader {
    background: rgba(255,255,255,0.12) !important;
    backdrop-filter: blur(16px) !important;
    border: 1px solid rgba(255,255,255,0.22) !important;
    border-radius: 14px !important;
    font-weight: 700 !important;
    color: #fff !important;
}
.streamlit-expanderContent {
    background: rgba(255,255,255,0.07) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255,255,255,0.14) !important;
    border-radius: 0 0 14px 14px !important;
}

/* ── Checkbox ── */
.stCheckbox label {
    color: #fff !important;
    font-weight: 700 !important;
    font-size: 0.95rem !important;
}

/* ── Number input large ── */
div[data-testid="stNumberInput"]:has(input[aria-label*="סכום"]) input,
#calc_amount input {
    font-size: 1.8rem !important;
    font-weight: 900 !important;
    text-align: center !important;
    letter-spacing: -1px !important;
    height: 64px !important;
}
</style>
""",
        unsafe_allow_html=True,
    )

    # Auto-select number inputs on focus
    st.components.v1.html(
        """
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
""",
        height=0,
    )


def fmt_ils(x):
    return f"₪{x:,.0f}"


# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────
def do_login(username, password):
    username = username.strip()
    with closing(get_conn()) as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
    if not user:
        return False, "שם משתמש לא קיים"
    if stauth.Hasher().check_pw(password, user["password"]):
        st.session_state["authentication_status"] = True
        st.session_state["username"] = user["username"]
        st.session_state["name"]     = user["name"]
        return True, ""
    return False, "סיסמה שגויה"


def render_auth_screen(authenticator):
    st.markdown(
        "<div style='height:40px'></div>"
        "<p style='text-align:center;font-size:11px;font-weight:700;letter-spacing:3.5px;"
        "color:rgba(255,255,255,0.5);text-transform:uppercase;margin-bottom:6px;'>CHECK MANAGEMENT</p>"
        "<h1 style='text-align:center;font-family:Inter,sans-serif;font-weight:900;"
        "font-size:3rem;letter-spacing:-2px;color:#fff;line-height:1;margin-bottom:6px;"
        "text-shadow:0 4px 20px rgba(0,0,0,0.4);'>"
        "CHECKFLOW</h1>"
        "<p style='text-align:center;color:rgba(255,255,255,0.5);font-size:0.9rem;"
        "font-weight:500;margin-bottom:32px;'>ניהול צ׳קים ופריטה</p>",
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
        st.markdown(
            "<p style='color:#fff;font-weight:800;font-size:1rem;margin-bottom:14px;'>"
            "צור חשבון חדש</p>",
            unsafe_allow_html=True,
        )
        with st.form("reg_form", clear_on_submit=True):
            r_user  = st.text_input("שם משתמש (אנגלית)", key="r_user")
            r_name  = st.text_input("שם מלא",             key="r_name")
            r_email = st.text_input("אימייל",              key="r_email")
            r_pass  = st.text_input("סיסמה (6+ תווים)", type="password", key="r_pass")
            r_pass2 = st.text_input("אימות סיסמה",      type="password", key="r_pass2")
            submitted = st.form_submit_button("הרשמה ✅", use_container_width=True)

        if submitted:
            r_user  = r_user.strip()
            r_name  = r_name.strip()
            r_email = r_email.strip()
            if not all([r_user, r_name, r_email, r_pass]):
                st.error("יש למלא את כל השדות.")
            elif len(r_pass) < 6:
                st.error("הסיסמה חייבת להכיל לפחות 6 תווים.")
            elif r_pass != r_pass2:
                st.error("הסיסמאות אינן תואמות.")
            else:
                with closing(get_conn()) as conn:
                    exists = conn.execute(
                        "SELECT 1 FROM users WHERE username=?", (r_user,)
                    ).fetchone()
                if exists:
                    st.error("שם המשתמש כבר קיים.")
                else:
                    hashed = stauth.Hasher().hash(r_pass)
                    with closing(get_conn()) as conn, conn:
                        conn.execute(
                            "INSERT INTO users (username,name,password,email) VALUES (?,?,?,?)",
                            (r_user, r_name, hashed, r_email),
                        )
                    st.success("נרשמת בהצלחה! עבור ללשונית 'כניסה' והתחבר. 🎉")


# ─────────────────────────────────────────────
# Home Screen
# ─────────────────────────────────────────────
def render_home_screen():
    st.markdown(
        "<div style='height:40px'></div>"
        "<p style='text-align:center;font-size:11px;font-weight:700;letter-spacing:3.5px;"
        "color:rgba(255,255,255,0.5);text-transform:uppercase;margin-bottom:6px;'>CHECK MANAGEMENT</p>"
        "<h1 style='text-align:center;font-family:Inter,sans-serif;font-weight:900;"
        "font-size:3rem;letter-spacing:-2px;color:#fff;line-height:1;margin-bottom:6px;"
        "text-shadow:0 4px 20px rgba(0,0,0,0.4);'>"
        "CHECKFLOW</h1>"
        "<p style='text-align:center;color:rgba(255,255,255,0.5);font-size:0.9rem;"
        "margin-bottom:32px;font-weight:500;'>ניהול צ׳קים ופריטה</p>",
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
    st.markdown('</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Floating Back Button — ZERO layout impact
# ─────────────────────────────────────────────
def render_back_button():
    """
    Injects a truly floating back button directly into the parent document via JS.
    The iframe has height=0, so no layout space is consumed whatsoever.
    The button navigates to ?s=home which triggers a Streamlit rerun.
    """
    st.components.v1.html(
        """
<script>
(function() {
    try {
        var doc = window.parent.document;
        // Remove any stale instance from previous renders
        var old = doc.getElementById('__cfb__');
        if (old) old.remove();

        var btn = doc.createElement('button');
        btn.id = '__cfb__';
        btn.innerHTML = '&#8592; ראשי';
        btn.style.cssText = [
            'position:fixed',
            'bottom:28px',
            'left:20px',
            'z-index:99999',
            'background:rgba(255,255,255,0.82)',
            'backdrop-filter:blur(22px)',
            '-webkit-backdrop-filter:blur(22px)',
            'color:#1C1C24',
            'border:1px solid rgba(255,255,255,0.65)',
            'border-radius:50px',
            'padding:11px 24px',
            'font-weight:800',
            'font-size:14px',
            'cursor:pointer',
            'box-shadow:0 8px 28px rgba(0,0,0,0.28)',
            'font-family:Inter,sans-serif',
            'letter-spacing:0.2px',
            'transition:all 0.15s ease',
            'direction:rtl'
        ].join(';');

        btn.addEventListener('mouseenter', function() {
            this.style.background = 'rgba(255,255,255,0.96)';
            this.style.transform  = 'translateY(-2px)';
            this.style.boxShadow  = '0 12px 36px rgba(0,0,0,0.32)';
        });
        btn.addEventListener('mouseleave', function() {
            this.style.background = 'rgba(255,255,255,0.82)';
            this.style.transform  = '';
            this.style.boxShadow  = '0 8px 28px rgba(0,0,0,0.28)';
        });
        btn.addEventListener('click', function() {
            var url = new URL(window.parent.location.href);
            url.searchParams.set('s', 'home');
            window.parent.location.href = url.toString();
        });

        doc.body.appendChild(btn);
    } catch(e) {
        console.warn('CheckFlow back-btn error:', e);
    }
})();
</script>
""",
        height=0,
    )


# ─────────────────────────────────────────────
# KPI
# ─────────────────────────────────────────────
def render_kpi():
    total, cnt = get_totals()
    st.markdown(
        f"""
<div class="kpi">
    <div class="kpi-label">סך הצ'קים שביד כרגע</div>
    <div class="kpi-value">{fmt_ils(total)}</div>
    <div class="kpi-sub">{cnt} צ'קים פיזיים בארנק 💸</div>
</div>
""",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────
# Add Check Form
# ─────────────────────────────────────────────
def render_add_check_form():
    clients = get_clients()
    st.markdown('<div class="add-check-wrapper">', unsafe_allow_html=True)
    if st.button(
        "➕  הוספת צ'ק חדש",
        use_container_width=True,
        key="open_add_form",
    ):
        st.session_state.add_form_open = not st.session_state.get("add_form_open", False)
    st.markdown("</div>", unsafe_allow_html=True)

    if not st.session_state.get("add_form_open", False):
        return

    names   = [c["name"] for c in clients]
    col_a, _ = st.columns([2, 1])
    with col_a:
        sel = st.selectbox("לקוח", ["— חדש —"] + names, key="add_client_sel")
    new_name = (
        st.text_input("שם לקוח חדש", key="new_client_name") if sel == "— חדש —" else None
    )

    amount = st.number_input(
        "סכום הצ'ק (₪)", min_value=0.0, step=100.0, format="%.0f", key="add_amount"
    )
    c1, c2 = st.columns(2)
    with c1:
        due = st.date_input(
            "תאריך פירעון",
            value=date.today() + timedelta(days=30),
            min_value=date.today(),
            key="add_due",
        )
    with c2:
        use_remind = st.checkbox("הוסף תזכורת", value=False, key="add_use_remind")

    remind = None
    if use_remind:
        remind = st.date_input(
            "תאריך תזכורת",
            value=date.today() + timedelta(days=30),
            min_value=date.today(),
            key="add_remind",
        )

    status = st.selectbox("סטטוס", STATUSES, key="add_status")

    if st.button("💾  שמירת צ'ק", use_container_width=True, key="save_check"):
        cid = (
            add_client(new_name or "")
            if sel == "— חדש —"
            else next((c["id"] for c in clients if c["name"] == sel), None)
        )
        if not cid:
            st.error("נא לבחור או להזין שם לקוח.")
        elif amount <= 0:
            st.error("נא להזין סכום גדול מאפס.")
        else:
            add_check(cid, amount, due, status, remind)
            st.success("הצ'ק נשמר ✅")
            st.session_state.add_form_open = False
            st.rerun()


# ─────────────────────────────────────────────
# Client List
# ─────────────────────────────────────────────
def render_clients():
    st.markdown('<div class="section-title">הלקוחות שלי</div>', unsafe_allow_html=True)
    st.markdown('<div class="neon-bar"></div>', unsafe_allow_html=True)

    rows = [r for r in get_client_obligo() if r["cnt"] > 0]
    if not rows:
        st.markdown(
            '<div class="glass">אין עדיין צ\'קים ⬆️</div>', unsafe_allow_html=True
        )
        return

    for i, r in enumerate(rows):
        bg, txt = CLIENT_PALETTE[i % len(CLIENT_PALETTE)]
        st.markdown(
            f"""
<div class="client-card" style="background:{bg};">
    <div>
        <div class="client-name" style="color:{txt};">{r['name']}</div>
        <div style="font-size:.82rem;color:{txt};opacity:0.7;font-weight:600;">
            {r['cnt']} צ'קים
        </div>
    </div>
    <div class="client-obligo" style="color:{txt};">{fmt_ils(r['obligo'])}</div>
</div>""",
            unsafe_allow_html=True,
        )

        with st.expander("צפייה בצ'קים"):
            for ch in get_checks(r["id"]):
                color      = STATUS_COLORS.get(ch["status"], "#aaa")
                remind_str = f" | תזכורת: {ch['remind_on']}" if ch["remind_on"] else ""
                cc1, cc2   = st.columns([3, 2])
                with cc1:
                    st.markdown(
                        f"""
<div style="padding:6px 0;">
    <span style="font-weight:900;direction:ltr;color:#fff;font-size:1.05rem;
        letter-spacing:-0.5px;">{fmt_ils(ch['amount'])}</span><br>
    <span style="font-size:.8rem;color:rgba(255,255,255,0.6);">
        פירעון: {ch['due_date']}{remind_str}</span>
    <span class="pill"
        style="background:{color}22;color:{color};border:1px solid {color}66;">
        {ch['status']}
    </span>
</div>""",
                        unsafe_allow_html=True,
                    )
                with cc2:
                    new_st = st.selectbox(
                        "סטטוס",
                        STATUSES,
                        index=STATUSES.index(ch["status"]),
                        key=f"st_{ch['id']}",
                        label_visibility="collapsed",
                    )
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("עדכן", key=f"upd_{ch['id']}", use_container_width=True):
                            update_status(ch["id"], new_st)
                            st.rerun()
                    with b2:
                        if st.button("🗑️", key=f"del_{ch['id']}", use_container_width=True):
                            delete_check(ch["id"])
                            st.rerun()


# ─────────────────────────────────────────────
# Calculator
# ─────────────────────────────────────────────
def render_calculator():
    st.markdown(
        '<div class="section-title-right">מחשבון פריטה (ניכיון)</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="neon-bar-right"></div>', unsafe_allow_html=True)

    if "fixed_rate"     not in st.session_state: st.session_state.fixed_rate     = 12.0
    if "rate_basis"     not in st.session_state: st.session_state.rate_basis     = "שנתית"
    if "rate_edit_open" not in st.session_state: st.session_state.rate_edit_open = False

    checks  = get_checks()
    options = ["— הזנה ידנית —"] + [
        f"{c['client_name']} | {fmt_ils(c['amount'])} | {c['due_date']}"
        for c in checks
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

    if st.session_state.get("_last_pick") != pick:
        st.session_state.calc_due    = default_due
        st.session_state.calc_amount = default_amount
        st.session_state._last_pick  = pick

    amount = st.number_input(
        "סכום הצ'ק (₪)",
        min_value=0.0,
        step=100.0,
        value=st.session_state.get("calc_amount", default_amount),
        format="%.0f",
        key="calc_amount",
    )

    due_date = st.date_input(
        "תאריך פירעון הצ'ק",
        key="calc_due",
        min_value=date.today(),
        help="החישוב מתחיל ממחר וכולל את יום הפירעון",
    )

    days = max((due_date - date.today()).days + 1, 0)

    # Days display — glassmorphic amber tint
    st.markdown(
        f"<div style='background:rgba(232,184,144,0.28);backdrop-filter:blur(22px);"
        f"-webkit-backdrop-filter:blur(22px);border:1px solid rgba(232,184,144,0.45);"
        f"border-radius:22px;padding:16px;text-align:center;margin:8px 0 12px;"
        f"box-shadow:0 8px 22px rgba(0,0,0,0.14);'>"
        f"<span style='font-size:11px;font-weight:700;letter-spacing:2px;color:rgba(255,255,255,0.6);"
        f"text-transform:uppercase;display:block;margin-bottom:4px;'>ימי זיכוי</span>"
        f"<span style='font-family:Inter,sans-serif;font-size:2.4rem;font-weight:900;"
        f"color:#fff;letter-spacing:-1.5px;'>{days}</span>"
        f"<span style='font-size:0.9rem;font-weight:600;color:rgba(255,255,255,0.6);'> ימים</span></div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div style='text-align:center;font-size:11px;font-weight:700;"
        "letter-spacing:2px;color:rgba(255,255,255,0.5);text-transform:uppercase;"
        "margin-bottom:10px;'>סוג הריבית</div>",
        unsafe_allow_html=True,
    )
    basis = st.radio(
        "סוג הריבית",
        ["חודשית", "שנתית"],
        index=["חודשית", "שנתית"].index(st.session_state.rate_basis),
        horizontal=True,
        key="basis_radio",
        label_visibility="collapsed",
    )
    st.session_state.rate_basis = basis

    rate_val = st.session_state.fixed_rate
    r1, r2   = st.columns([2, 1])
    with r1:
        # Rate display — glassmorphic gold tint
        st.markdown(
            f"<div style='background:rgba(255,200,80,0.22);backdrop-filter:blur(22px);"
            f"-webkit-backdrop-filter:blur(22px);border:1px solid rgba(255,200,80,0.40);"
            f"border-radius:22px;padding:16px;text-align:center;"
            f"box-shadow:0 8px 22px rgba(0,0,0,0.14);'>"
            f"<span style='font-size:11px;font-weight:700;letter-spacing:2px;"
            f"color:rgba(255,255,255,0.6);text-transform:uppercase;display:block;"
            f"margin-bottom:6px;'>ריבית קבועה ({basis})</span>"
            f"<span style='font-family:Inter,sans-serif;font-size:2rem;font-weight:900;"
            f"color:#fff;letter-spacing:-1px;'>{rate_val:.2f}%</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with r2:
        st.write("")
        st.write("")
        if st.button("✏️ שינוי", use_container_width=True, key="edit_rate"):
            st.session_state.rate_edit_open = not st.session_state.rate_edit_open

    if st.session_state.rate_edit_open:
        new_rate = st.number_input(
            "הזן ריבית (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(rate_val),
            step=0.1,
            format="%.2f",
            key="rate_input_manual",
        )
        if st.button("💾 שמירת הריבית", use_container_width=True, key="save_rate"):
            st.session_state.fixed_rate    = new_rate
            st.session_state.rate_edit_open = False
            st.rerun()

    fee = amount * (rate_val / 100.0) * (days / 30.0 if basis == "חודשית" else days / 365.0)
    net = amount - fee

    if days <= 0:
        st.markdown(
            "<div style='background:rgba(255,107,100,0.22);backdrop-filter:blur(22px);"
            "-webkit-backdrop-filter:blur(22px);border:1px solid rgba(255,107,100,0.38);"
            "border-radius:16px;padding:14px;text-align:center;font-size:13px;"
            "font-weight:700;color:rgba(255,255,255,0.85);margin:10px 0;'>"
            "⚠️ תאריך הפירעון עבר — אין ימי זיכוי.</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
<div class="calc-out fee">
    <div class="lbl">סך העמלה שיורדת</div>
    <div class="big">{fmt_ils(fee)}</div>
</div>
<div class="calc-out net">
    <div class="lbl">נטו מזומן שמתקבל</div>
    <div class="big">{fmt_ils(net)}</div>
</div>
""",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    init_db()
    inject_css()

    credentials   = get_all_users_for_auth()
    authenticator = stauth.Authenticate(
        credentials,
        cookie_name="checkflow_auth",
        key="checkflow_secret_key_2025",
        cookie_expiry_days=30,
    )

    auth_status = st.session_state.get("authentication_status")

    if auth_status is not True:
        render_auth_screen(authenticator)
        return

    # Sync current user
    st.session_state.current_user = st.session_state.get("username", "admin")

    # Sidebar — avatar only, no logout button
    with st.sidebar:
        name    = st.session_state.get("name", "")
        initial = name[0].upper() if name else "?"
        st.markdown(
            f"<div style='text-align:center;padding:16px 0;'>"
            f"<div style='width:52px;height:52px;border-radius:50%;"
            f"background:rgba(255,255,255,0.15);backdrop-filter:blur(22px);"
            f"-webkit-backdrop-filter:blur(22px);"
            f"display:flex;align-items:center;justify-content:center;"
            f"font-size:1.4rem;font-weight:900;color:#fff;margin:0 auto;"
            f"border:1px solid rgba(255,255,255,0.3);"
            f"box-shadow:0 8px 22px rgba(0,0,0,0.2);'>{initial}</div>"
            f"<p style='color:rgba(255,255,255,0.6);font-size:0.82rem;"
            f"font-weight:600;margin-top:10px;'>{name}</p>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # Sync screen from query params (supports browser back/forward)
    qp = st.query_params.get("s", None)
    if qp in ("home", "calc", "mgmt"):
        if st.session_state.get("screen") != qp:
            st.session_state.screen = qp

    if "screen" not in st.session_state:
        st.session_state.screen = "home"

    screen = st.session_state.screen

    # Push current screen into browser history
    st.components.v1.html(
        f"""
<script>
(function(){{
    var s   = "{screen}";
    var cur = new URLSearchParams(window.parent.location.search).get("s");
    if (cur !== s) window.parent.history.pushState({{screen:s}}, "", "?s=" + s);
}})();
</script>""",
        height=0,
    )

    if screen == "home":
        render_home_screen()
    elif screen == "calc":
        render_back_button()
        render_calculator()
    elif screen == "mgmt":
        render_back_button()
        render_kpi()
        render_add_check_form()
        render_clients()


if __name__ == "__main__":
    main()
