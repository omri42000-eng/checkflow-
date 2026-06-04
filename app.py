# -*- coding: utf-8 -*-
"""
ניהול אובליגו ומחשבון פריטת צ'קים
Streamlit Web App — Mobile-first + Auth
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
    "ממתין למזומן": "#e59a65",
    "להפקדה":       "#7de8a0",
    "בפריטה":       "#f0c080",
}


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

        # Migration: הוספת עמודת username אם לא קיימת (DB ישן)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(clients)").fetchall()]
        if "username" not in cols:
            conn.execute("ALTER TABLE clients ADD COLUMN username TEXT NOT NULL DEFAULT 'admin'")

        # Migration: הוספת unique index אם לא קיים
        indexes = [r[1] for r in conn.execute("PRAGMA index_list(clients)").fetchall()]
        if not any("name" in i and "username" in i for i in indexes):
            try:
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_name_user ON clients(name, username)")
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
            (current_user(),)
        ).fetchall()


def add_check(client_id, amount, due_date, status, remind_on):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT INTO checks (client_id,amount,due_date,status,remind_on) VALUES (?,?,?,?,?)",
            (client_id, amount, due_date.isoformat(), status,
             remind_on.isoformat() if remind_on else None),
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
        row = conn.execute("""
            SELECT COALESCE(SUM(ch.amount),0) AS total, COUNT(ch.id) AS cnt
            FROM checks ch JOIN clients cl ON cl.id=ch.client_id
            WHERE cl.username=?
        """, (u,)).fetchone()
        return row["total"], row["cnt"]


def get_client_obligo():
    with closing(get_conn()) as conn:
        return conn.execute("""
            SELECT cl.id, cl.name,
                   COALESCE(SUM(ch.amount),0) AS obligo,
                   COUNT(ch.id) AS cnt
            FROM clients cl
            LEFT JOIN checks ch ON ch.client_id=cl.id
            WHERE cl.username=?
            GROUP BY cl.id ORDER BY obligo DESC
        """, (current_user(),)).fetchall()


def get_all_users_for_auth():
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT username, name, password, email FROM users"
        ).fetchall()
    creds = {"usernames": {}}
    for r in rows:
        creds["usernames"][r["username"]] = {
            "name": r["name"],
            "password": r["password"],
            "email": r["email"],
        }
    return creds


# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Comfortaa:wght@700&family=Noto+Sans+Hebrew:wght@400;600;700;800&display=swap');

    :root {
        /* פלטת נחושת-שיש */
        --bg-deep:       #041424;
        --bg-navy:       #0b243a;
        --bg-card:       rgba(30,35,42,0.92);
        --copper-light:  #e59a65;
        --copper-base:   #c07a45;
        --copper-dark:   #8c4f2b;
        --gold-text:     #dec599;
        --stone-light:   #eae4dc;
        --stone-base:    #ded4c9;
        --text-on-stone: #704429;
        --text-primary:  #f2e8d9;
        --text-secondary: rgba(222,197,153,0.65);
        --text-muted:    rgba(222,197,153,0.40);
        --border-copper: rgba(229,154,101,0.40);
        --border-copper-strong: rgba(229,154,101,0.70);
        --radius-card:   22px;
        --shadow-heavy:  0 16px 48px rgba(0,0,0,0.60);
        --shadow-copper: 0 8px 24px rgba(140,79,43,0.35);
    }

    html, body, [class*="css"] { direction: rtl; }

    /* ─── רקע שיש ─── */
    .stApp {
        background-color: var(--bg-deep);
        background-image:
            url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='600' height='600'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='600' height='600' filter='url(%23n)' opacity='0.06'/%3E%3C/svg%3E"),
            radial-gradient(ellipse at 30% 20%, rgba(14,52,88,0.8) 0%, transparent 55%),
            radial-gradient(ellipse at 75% 80%, rgba(8,30,55,0.9) 0%, transparent 50%),
            linear-gradient(160deg, #041424 0%, #0b243a 40%, #041424 100%);
        background-attachment: fixed;
        font-family: 'Noto Sans Hebrew', sans-serif;
        color: var(--text-primary);
    }
    #MainMenu, header, footer { visibility: hidden; }
    .block-container {
        padding-top: 0.5rem !important;
        padding-bottom: 5rem;
        max-width: 480px;
    }
    .block-container > div:first-child { margin-top: 0 !important; }
    [data-testid="stAppViewBlockContainer"] { padding-top: 0.5rem !important; }

    /* ─── KPI — כרטיס זכוכית מעושנת ─── */
    .kpi {
        background: var(--bg-card);
        border: 1px solid var(--border-copper);
        border-radius: var(--radius-card);
        padding: 24px 20px 20px;
        margin-bottom: 10px;
        text-align: center;
        box-shadow: var(--shadow-heavy), inset 0 1px 0 rgba(229,154,101,0.2);
        position: relative; overflow: hidden;
    }
    .kpi::before {
        content: "";
        position: absolute; top: 0; left: 0; right: 0; height: 1px;
        background: linear-gradient(90deg, transparent, var(--copper-light), transparent);
    }
    .kpi-label {
        font-size: 11px; font-weight: 700; letter-spacing: 1.8px;
        color: var(--text-secondary); text-transform: uppercase; margin-bottom: 8px;
    }
    .kpi-value {
        font-family: 'Comfortaa', sans-serif;
        font-size: 2.8rem; font-weight: 700; line-height: 1;
        background: linear-gradient(135deg, #f0c080 0%, #e59a65 40%, #dec599 100%);
        -webkit-background-clip: text; background-clip: text;
        -webkit-text-fill-color: transparent;
        direction: ltr; display: block; letter-spacing: -1px;
    }
    .kpi-sub {
        font-size: 13px; color: var(--text-secondary); margin-top: 8px; font-weight: 500;
    }

    /* ─── כרטיסים כלליים ─── */
    .glass {
        background: var(--bg-card);
        border: 1px solid var(--border-copper);
        border-radius: var(--radius-card);
        padding: 18px 20px;
        margin-bottom: 8px;
        box-shadow: var(--shadow-heavy);
        color: var(--text-primary);
    }

    /* ─── pill ─── */
    .pill {
        display: inline-block; padding: 3px 10px; border-radius: 999px;
        font-size: 11px; font-weight: 700; margin-inline-start: 6px;
    }

    /* ─── כותרות סקשן ─── */
    .section-title, .section-title-right {
        font-family: 'Noto Sans Hebrew', sans-serif;
        font-size: 20px; font-weight: 800;
        color: var(--copper-light); margin: 18px 0 4px; text-align: right;
    }
    .neon-bar, .neon-bar-right {
        height: 2px; width: 36px; border-radius: 2px;
        background: linear-gradient(90deg, var(--copper-light), var(--copper-dark));
        margin-bottom: 14px; box-shadow: 0 0 8px rgba(229,154,101,0.5);
    }
    .neon-bar { margin-right: auto; margin-left: auto; }

    /* ─── כרטיס לקוח ─── */
    .client-card {
        display: flex; justify-content: space-between; align-items: center;
        background: var(--bg-card);
        border: 1px solid var(--border-copper);
        border-radius: 18px; padding: 14px 16px; margin-bottom: 8px;
        box-shadow: var(--shadow-heavy);
        transition: transform .2s ease;
    }
    .client-card:hover { transform: translateY(-2px); }
    .client-name { font-weight: 700; font-size: 1rem; color: var(--text-primary); }
    .client-obligo {
        font-family: 'Comfortaa', sans-serif;
        font-weight: 700; font-size: 1.1rem;
        background: linear-gradient(135deg, #f0c080, #e59a65);
        -webkit-background-clip: text; background-clip: text;
        -webkit-text-fill-color: transparent;
        direction: ltr; letter-spacing: -0.3px;
    }

    /* ─── פלט מחשבון ─── */
    .calc-out {
        border-radius: 20px; padding: 18px 20px;
        margin-top: 8px; text-align: center;
        border: 1px solid var(--border-copper);
        box-shadow: var(--shadow-heavy);
    }
    .calc-out.fee { background: rgba(140,79,43,0.25); border-color: rgba(229,154,101,0.35); }
    .calc-out.net { background: rgba(20,60,40,0.40); border-color: rgba(100,200,120,0.30); margin-top: 8px; }
    .calc-out .lbl {
        font-size: 11px; font-weight: 700; letter-spacing: 1.2px;
        text-transform: uppercase; color: var(--text-secondary); margin-bottom: 6px;
    }
    .calc-out .big {
        font-family: 'Comfortaa', sans-serif; font-size: 2.4rem;
        font-weight: 700; direction: ltr; line-height: 1.1;
        letter-spacing: -1px;
    }
    .calc-out.fee .big {
        background: linear-gradient(135deg, #f0a370, #c07a45);
        -webkit-background-clip: text; background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .calc-out.net .big { color: #7de8a0; }

    /* ─── כפתורים כלליים — גוון אבן ─── */
    .stButton > button {
        border-radius: 14px !important;
        background: linear-gradient(180deg, #d4cbc2 0%, #c8bfb6 100%) !important;
        border: 1px solid rgba(255,255,255,0.35) !important;
        box-shadow:
            0 6px 16px rgba(0,0,0,0.45),
            inset 0 2px 3px rgba(255,255,255,0.60),
            inset 0 -3px 5px rgba(0,0,0,0.18) !important;
        color: #5a3018 !important;
        font-weight: 700 !important;
        font-family: 'Noto Sans Hebrew', sans-serif !important;
        transition: transform .15s ease, box-shadow .15s ease !important;
        min-height: 36px !important;
        padding: 6px 14px !important;
        font-size: 0.88rem !important;
        line-height: 1.3 !important;
    }
    .stButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow:
            0 8px 20px rgba(0,0,0,0.50),
            inset 0 2px 3px rgba(255,255,255,0.60),
            inset 0 -3px 5px rgba(0,0,0,0.18) !important;
    }
    .stButton > button:active {
        transform: translateY(1px) !important;
        box-shadow:
            0 2px 8px rgba(0,0,0,0.40),
            inset 0 2px 6px rgba(0,0,0,0.25) !important;
    }

    /* ─── כפתורי ניווט מסך הבית ─── */
    .home-nav-btn .stButton > button {
        border-radius: 24px !important;
        font-family: 'Noto Sans Hebrew', sans-serif !important;
        font-size: 1.3rem !important;
        font-weight: 800 !important;
        min-height: 72px !important;
        height: auto !important;
        padding: 18px 20px !important;
        background: linear-gradient(180deg, #eae4dc 0%, #ded4c9 100%) !important;
        border: 1px solid rgba(255,255,255,0.45) !important;
        box-shadow:
            0 10px 24px rgba(0,0,0,0.50),
            inset 0 2px 4px rgba(255,255,255,0.75),
            inset 0 -4px 6px rgba(0,0,0,0.18) !important;
        color: #704429 !important;
    }
    .home-nav-btn .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow:
            0 14px 30px rgba(0,0,0,0.55),
            inset 0 2px 4px rgba(255,255,255,0.75),
            inset 0 -4px 6px rgba(0,0,0,0.18) !important;
    }
    .home-nav-btn .stButton > button:active {
        transform: translateY(2px) !important;
        box-shadow:
            0 3px 10px rgba(0,0,0,0.45),
            inset 0 3px 8px rgba(0,0,0,0.28) !important;
    }
    /* הסרת override של green/pink — הכל אחיד עכשיו */
    .home-nav-green .stButton > button,
    .home-nav-pink  .stButton > button {
        background: linear-gradient(180deg, #eae4dc 0%, #ded4c9 100%) !important;
        border: 1px solid rgba(255,255,255,0.45) !important;
        color: #704429 !important;
    }

    /* ─── כפתורי הוספת צ'ק ─── */
    .btn-single .stButton > button,
    .btn-batch  .stButton > button {
        border-radius: 50px !important;
        font-size: 0.92rem !important;
        font-weight: 800 !important;
        padding: 10px 0 !important;
    }
    .btn-single .stButton > button {
        background: linear-gradient(135deg, #e59a65, #8c4f2b) !important;
        color: #fff1e0 !important;
        border: none !important;
    }
    .btn-batch .stButton > button {
        background: linear-gradient(180deg, #d4cbc2 0%, #c8bfb6 100%) !important;
        color: #5a3018 !important;
    }

    /* ─── כרטיס תזכורת ─── */
    .reminder-card {
        background: rgba(140,79,43,0.20);
        border: 1px solid var(--border-copper);
        border-radius: 18px; padding: 14px 16px; margin-bottom: 8px;
        box-shadow: var(--shadow-heavy);
    }
    .reminder-title {
        font-size: 11px; font-weight: 700; letter-spacing: 1.5px;
        text-transform: uppercase; color: var(--copper-light); margin-bottom: 8px;
    }
    .reminder-row {
        display: flex; justify-content: space-between; align-items: center;
        padding: 5px 0; border-bottom: 1px solid rgba(229,154,101,0.15);
    }
    .reminder-row:last-child { border-bottom: none; }

    /* ─── כפתורים קטנים ─── */
    .btn-sm .stButton > button {
        padding: 2px 6px !important;
        font-size: 0.72rem !important;
        border-radius: 9px !important;
        min-height: 0 !important;
        height: auto !important;
        font-weight: 700 !important;
        line-height: 1.4 !important;
    }

    /* ─── data frame ─── */
    .stDataFrame, [data-testid="stDataEditor"] {
        border-radius: 14px !important; overflow: hidden !important;
    }

    /* ─── כפתור חזרה צף ─── */
    .back-btn {
        position: fixed !important; bottom: 28px !important;
        left: 20px !important; z-index: 9999 !important;
    }
    .back-btn .stButton > button {
        border-radius: 50px !important;
        background: linear-gradient(180deg, #d4cbc2 0%, #c0b8af 100%) !important;
        border: 1px solid rgba(255,255,255,0.35) !important;
        color: #5a3018 !important;
        font-size: 0.82rem !important;
        font-weight: 800 !important;
        padding: 8px 18px !important;
        height: auto !important;
        min-height: 0 !important;
        box-shadow: 0 6px 20px rgba(0,0,0,0.50),
                    inset 0 2px 3px rgba(255,255,255,0.60) !important;
    }

    /* ─── שדות קלט ─── */
    .stTextInput input, .stNumberInput input,
    .stDateInput input, [data-baseweb="input"] input,
    [data-baseweb="base-input"] input, textarea {
        color: var(--gold-text) !important;
        background-color: rgba(4,20,36,0.80) !important;
        -webkit-text-fill-color: var(--gold-text) !important;
        caret-color: var(--copper-light) !important;
        border-radius: 12px !important;
        border: 1px solid var(--border-copper) !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        padding-top: 6px !important;
        padding-bottom: 6px !important;
        min-height: 0 !important;
        height: 38px !important;
    }
    .stTextInput div[data-baseweb="input"],
    .stNumberInput div[data-baseweb="input"],
    .stDateInput div[data-baseweb="input"],
    div[data-baseweb="base-input"],
    div[data-baseweb="select"] > div {
        background-color: rgba(4,20,36,0.80) !important;
        border: 1px solid var(--border-copper) !important;
        border-radius: 12px !important;
        min-height: 0 !important;
    }
    .stTextInput label, .stNumberInput label,
    .stDateInput label, .stSelectbox label {
        font-size: 0.78rem !important;
        margin-bottom: 2px !important;
        padding-bottom: 0 !important;
    }
    div[data-baseweb="select"] > div {
        min-height: 38px !important;
        padding-top: 4px !important; padding-bottom: 4px !important;
    }
    .stNumberInput button {
        background-color: rgba(4,20,36,0.80) !important;
        color: var(--copper-light) !important;
        border: 1px solid var(--border-copper) !important;
        padding: 2px 6px !important; min-height: 0 !important;
    }
    .stNumberInput button svg { fill: var(--copper-light) !important; }
    div[data-baseweb="select"] div { color: var(--gold-text) !important; font-weight: 600 !important; }
    input::placeholder { color: var(--text-muted) !important; opacity: 1 !important; }

    /* ─── RTL ─── */
    .stTextInput input, .stNumberInput input, .stDateInput input {
        text-align: right !important; direction: rtl !important;
    }
    .stSelectbox label, .stNumberInput label,
    .stTextInput label, .stDateInput label,
    .stCheckbox label { text-align: right !important; display: block !important; }
    ul[role="listbox"] {
        background-color: #0b1e30 !important;
        border: 1px solid var(--border-copper) !important;
        border-radius: 14px !important;
    }
    ul[role="listbox"] li { color: var(--gold-text) !important; font-weight: 600 !important; }
    label { color: var(--text-secondary) !important; font-weight: 700 !important; font-size: 0.82rem !important; }

    /* ─── לוח שנה ─── */
    div[data-baseweb="popover"],
    div[data-baseweb="popover"] > div,
    div[data-baseweb="calendar"],
    div[data-baseweb="datepicker"],
    [data-baseweb="calendar"],
    [data-baseweb="calendarheader"] {
        background-color: #0b1e30 !important;
        color: var(--gold-text) !important;
        border: 1px solid var(--border-copper) !important;
        border-radius: 18px !important;
    }
    div[data-baseweb="calendar"] *,
    div[data-baseweb="popover"] * {
        color: var(--gold-text) !important;
        -webkit-text-fill-color: var(--gold-text) !important;
        background-color: transparent !important;
    }
    div[data-baseweb="calendar"] [aria-selected="true"],
    div[data-baseweb="calendar"] button[aria-selected="true"] {
        background: linear-gradient(135deg, #c07a45, #8c4f2b) !important;
        border-radius: 50% !important;
        color: #fff1e0 !important;
        -webkit-text-fill-color: #fff1e0 !important;
    }
    div[data-baseweb="calendar"] button:not([aria-selected="true"]):hover {
        background: rgba(229,154,101,0.20) !important;
        border-radius: 50% !important;
    }

    /* ─── רדיו / בסיס שכ"ט ─── */
    div[data-testid="stRadio"] > div { gap: 8px !important; justify-content: center !important; }
    div[data-testid="stRadio"] label {
        background: rgba(4,20,36,0.80) !important;
        border: 1px solid var(--border-copper) !important;
        border-radius: 12px !important;
        padding: 8px 22px !important;
        font-size: 0.95rem !important; font-weight: 700 !important;
        cursor: pointer; transition: background .12s ease;
    }
    div[data-testid="stRadio"] label,
    div[data-testid="stRadio"] label *,
    div[data-testid="stRadio"] label p,
    div[data-testid="stRadio"] label span {
        color: var(--gold-text) !important;
        -webkit-text-fill-color: var(--gold-text) !important;
    }
    div[data-testid="stRadio"] label:has(input:checked) {
        background: linear-gradient(135deg, #c07a45, #8c4f2b) !important;
        border-color: transparent !important;
    }
    div[data-testid="stRadio"] label:has(input:checked) *,
    div[data-testid="stRadio"] label:has(input:checked) span {
        color: #fff1e0 !important;
        -webkit-text-fill-color: #fff1e0 !important;
    }
    div[data-testid="stRadio"] input[type="radio"] { display: none !important; }
    div[data-testid="stRadio"] div[data-baseweb="radio"] > div:first-child { display: none !important; }

    /* ─── טאבים ─── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px; justify-content: center;
        background: transparent !important;
    }
    .stTabs [data-baseweb="tab"] {
        background: rgba(4,20,36,0.80) !important;
        border-radius: 12px !important;
        padding: 8px 20px !important;
        border: 1px solid var(--border-copper) !important;
        font-size: 0.9rem !important; font-weight: 700 !important;
        color: var(--text-secondary) !important;
        min-width: 120px; text-align: center;
    }
    .stTabs [data-baseweb="tab"] p,
    .stTabs [data-baseweb="tab"] span,
    .stTabs [data-baseweb="tab"] div { color: var(--text-secondary) !important; }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #c07a45, #8c4f2b) !important;
        border: none !important;
    }
    .stTabs [aria-selected="true"] p,
    .stTabs [aria-selected="true"] span,
    .stTabs [aria-selected="true"] div { color: #fff1e0 !important; }

    /* ─── expander ─── */
    .streamlit-expanderHeader, details summary {
        background: rgba(4,20,36,0.80) !important;
        border-radius: 12px !important;
        font-weight: 700 !important;
        color: var(--gold-text) !important;
        border: 1px solid var(--border-copper) !important;
    }
    .streamlit-expanderContent, details {
        background: rgba(4,20,36,0.60) !important;
        border: 1px solid var(--border-copper) !important;
        border-radius: 12px !important;
    }
    details summary { color: var(--gold-text) !important; }

    /* ─── checkbox ─── */
    .stCheckbox label {
        color: var(--gold-text) !important;
        font-weight: 700 !important; font-size: 0.88rem !important;
    }

    /* ─── ריווח אנכי ─── */
    .element-container { margin-bottom: 6px !important; }
    div[data-testid="column"] .element-container { margin-bottom: 4px !important; }
    div[data-testid="stMarkdownContainer"] { margin-bottom: 2px !important; }

    /* ─── כפתור ✓ פעיל (בסיס שכ"ט) ─── */
    [data-testid="stButton"]:has(button p:contains("✓")) button {
        background: linear-gradient(135deg, #c07a45, #8c4f2b) !important;
        color: #fff1e0 !important;
        border-color: transparent !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # JS — סימון אוטומטי בלחיצה על שדה מספר
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
    """פורמט שקלים — שלמים לסכומים גדולים, עשרוניים לסכומים קטנים"""
    if abs(x) < 10:
        return f"₪{x:,.2f}"
    return f"₪{x:,.0f}"

def calc_fee(amount, due_date, rate_val, rate_basis):
    """חישוב שכר טרחה"""
    days = max((due_date - date.today()).days + 1, 0)
    if rate_basis in ("חודשית", "חודשי"):
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
    """צ'קים שפורעים היום + הימים הקרובים"""
    u = current_user()
    results = {}
    today = date.today()
    for i in range(days_ahead + 1):
        d = today + timedelta(days=i)
        with closing(get_conn()) as conn:
            rows = conn.execute("""
                SELECT ch.id, ch.amount, ch.due_date, ch.status, cl.name AS client_name
                FROM checks ch JOIN clients cl ON cl.id=ch.client_id
                WHERE cl.username=? AND DATE(ch.due_date)=DATE(?)
                ORDER BY cl.name
            """, (u, d.isoformat())).fetchall()
        if rows:
            results[d] = [dict(r) for r in rows]
    return results


def add_checks_batch(client_id, amounts, due_dates, status):
    """שמירת מקבץ צ'קים בבת אחת"""
    with closing(get_conn()) as conn, conn:
        for amt, dd in zip(amounts, due_dates):
            conn.execute(
                "INSERT INTO checks (client_id,amount,due_date,status,remind_on) VALUES (?,?,?,?,NULL)",
                (client_id, float(amt), dd.isoformat() if hasattr(dd, "isoformat") else str(dd), status)
            )


def do_login(username, password):
    """בדיקת סיסמה ישירה מ-DB"""
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
        "<div style='height:36px'></div>"
        "<h1 style='text-align:center;font-family:Comfortaa,sans-serif;font-weight:700;"
        "font-size:3.2rem;letter-spacing:2px;line-height:1;margin-bottom:28px;"
        "background:linear-gradient(135deg,#f0c080 0%,#e59a65 40%,#8c4f2b 70%,#dec599 100%);"
        "-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;"
        "filter:drop-shadow(2px 4px 8px rgba(0,0,0,0.7));'>"
        "CHECKFLOW</h1>",
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
                with closing(get_conn()) as conn:
                    exists = conn.execute("SELECT 1 FROM users WHERE username=?", (r_user,)).fetchone()
                if exists:
                    st.error("שם המשתמש כבר קיים.")
                else:
                    hashed = stauth.Hasher().hash(r_pass)
                    with closing(get_conn()) as conn, conn:
                        conn.execute(
                            "INSERT INTO users (username,name,password,email) VALUES (?,?,?,?)",
                            (r_user, r_name, hashed, r_email)
                        )
                    st.success("נרשמת בהצלחה! עבור ללשונית 'כניסה' והתחבר. 🎉")


# ─────────────────────────────────────────────
# מסך ראשי
# ─────────────────────────────────────────────
def render_home_screen():
    # בדיקת query param לתמיכה בכפתור חזור
    qp = st.query_params.get("s", None)
    if qp in ("calc", "mgmt"):
        st.session_state.screen = qp
        st.rerun()

    st.markdown(
        "<div style='height:36px'></div>"
        "<h1 style='text-align:center;font-family:Comfortaa,sans-serif;font-weight:700;"
        "font-size:3.2rem;letter-spacing:2px;line-height:1;margin-bottom:28px;"
        "background:linear-gradient(135deg,#f0c080 0%,#e59a65 40%,#8c4f2b 70%,#dec599 100%);"
        "-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;"
        "filter:drop-shadow(2px 4px 8px rgba(0,0,0,0.7));'>"
        "CHECKFLOW</h1>",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="home-nav-btn home-nav-green">', unsafe_allow_html=True)
    if st.button("🧮  מחשבון פריטה", key="go_calc", use_container_width=True):
        st.session_state.screen = "calc"
        st.rerun()
    st.markdown('</div><div style="height:14px"></div>', unsafe_allow_html=True)

    st.markdown('<div class="home-nav-btn home-nav-pink">', unsafe_allow_html=True)
    if st.button("📋  ניהול צ׳קים", key="go_mgmt", use_container_width=True):
        st.session_state.screen = "mgmt"
        st.rerun()
    st.markdown('</div><div style="height:20px"></div>', unsafe_allow_html=True)

    render_kpi()
    render_home_calendar()


def render_home_calendar():
    """יומן 2 הימים הקרובים עם צ'קים — מסך הבית"""
    u = current_user()
    today = date.today()

    # מצא את 2 התאריכים הקרובים ביותר שיש בהם צ'קים
    with closing(get_conn()) as conn:
        rows = conn.execute("""
            SELECT ch.id, ch.amount, ch.due_date, cl.name AS client_name
            FROM checks ch JOIN clients cl ON cl.id=ch.client_id
            WHERE cl.username=? AND DATE(ch.due_date) >= DATE(?)
            ORDER BY ch.due_date
        """, (u, today.isoformat())).fetchall()

    if not rows:
        return  # אין צ'קים קרובים בכלל — לא מציגים כלום

    # קיבוץ לפי תאריך
    from collections import defaultdict
    by_date = defaultdict(list)
    for r in rows:
        by_date[r["due_date"][:10]].append(dict(r))

    # 2 התאריכים הקרובים בלבד
    upcoming_dates = sorted(by_date.keys())[:2]
    if not upcoming_dates:
        return

    # תוויות ימים
    def day_label(d_str):
        d = date.fromisoformat(d_str)
        delta = (d - today).days
        if delta == 0:   return "היום"
        if delta == 1:   return "מחר"
        if delta == 2:   return "מחרתיים"
        # שמות ימי שבוע בעברית
        names = ["שני","שלישי","רביעי","חמישי","שישי","שבת","ראשון"]
        return names[d.weekday()]

    PALETTE = [
        ("rgba(140,79,43,0.22)", "rgba(229,154,101,0.35)", "#f2e8d9", "#BDB0FF"),
        ("rgba(192,122,69,0.20)",  "rgba(229,154,101,0.35)",  "#f2e8d9", "#FFDB8F"),
    ]

    st.markdown(
        "<div style='font-size:10px;font-weight:700;letter-spacing:2px;"
        "text-transform:uppercase;color:rgba(242,232,217,0.55);"
        "margin:14px 0 8px;text-align:right;'>📅 פירעונות קרובים</div>",
        unsafe_allow_html=True
    )

    for i, d_str in enumerate(upcoming_dates):
        checks_list = by_date[d_str]
        day_total   = sum(c["amount"] for c in checks_list)
        cnt         = len(checks_list)
        label       = day_label(d_str)
        bg, bd, txt_main, txt_accent = PALETTE[i % len(PALETTE)]
        d_fmt       = fmt_date(d_str)
        key_toggle  = f"cal_open_{d_str}"

        # כרטיס ראשי — תמיד גלוי
        st.markdown(
            f"<div style='background:{bg};border:1px solid {bd};border-radius:20px;"
            f"padding:14px 18px;margin-bottom:6px;backdrop-filter:blur(16px);"
            f"-webkit-backdrop-filter:blur(16px);box-shadow:0 12px 30px rgba(0,0,0,0.25);'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
            f"<div>"
            f"<div style='font-size:10px;font-weight:700;letter-spacing:1.5px;"
            f"text-transform:uppercase;color:{txt_accent};margin-bottom:2px;'>{label}</div>"
            f"<div style='font-size:0.82rem;font-weight:600;color:{txt_main};opacity:0.6;'>{d_fmt}</div>"
            f"</div>"
            f"<div style='text-align:left;'>"
            f"<div style='font-family:Comfortaa,sans-serif;font-size:1.15rem;font-weight:800;color:{txt_main};"
            f"letter-spacing:-0.5px;direction:ltr;'>{fmt_ils(day_total)}</div>"
            f"<div style='font-size:0.78rem;font-weight:600;color:{txt_accent};text-align:center;'>"
            f"{cnt} צ'קים</div>"
            f"</div></div></div>",
            unsafe_allow_html=True
        )

        # כפתור פרטים
        expanded = st.session_state.get(key_toggle, False)
        lbl_btn  = "▲ סגור" if expanded else f"▼ מי ומה ({cnt})"
        if st.button(lbl_btn, key=f"cal_btn_{d_str}", use_container_width=True):
            st.session_state[key_toggle] = not expanded
            st.rerun()

        if expanded:
            for ch in checks_list:
                st.markdown(
                    f"<div style='background:rgba(4,20,36,0.60);border:1px solid rgba(229,154,101,0.25);"
                    f"border-radius:14px;padding:10px 14px;margin-bottom:4px;display:flex;"
                    f"backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);"
                    f"justify-content:space-between;align-items:center;'>"
                    f"<span style='font-weight:800;font-size:0.9rem;color:#f2e8d9;'>{ch['client_name']}</span>"
                    f"<span style='font-weight:900;font-size:0.9rem;color:#f2e8d9;"
                    f"direction:ltr;'>{fmt_ils(ch['amount'])}</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)


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
        f"<span style='font-weight:800;font-size:1rem;color:#f2e8d9;'>{total_checks} צ'קים</span>"
        f"<span style='font-weight:900;font-size:1rem;color:#f0c080;direction:ltr;'>{fmt_ils(total_amount)}</span>"
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
            date.today():                     "rgba(40,100,65,0.25)",
            date.today() + timedelta(days=1): "rgba(140,79,43,0.22)",
            date.today() + timedelta(days=2): "rgba(255,200,87,0.16)",
        }
        bd_map  = {
            date.today():                     "rgba(100,200,130,0.30)",
            date.today() + timedelta(days=1): "rgba(229,154,101,0.35)",
            date.today() + timedelta(days=2): "rgba(229,154,101,0.35)",
        }
        bg = bg_map.get(d, "rgba(4,20,36,0.65)")
        bd = bd_map.get(d, "rgba(229,154,101,0.35)")
        date_str   = d.strftime("%d.%m.%Y")
        total_str  = fmt_ils(day_sum)
        header_day = (
            f"<div style='background:{bg};border:1px solid {bd};border-radius:18px;"
            f"padding:14px 16px;margin-bottom:6px;backdrop-filter:blur(14px);"
            f"-webkit-backdrop-filter:blur(14px);'>"
            f"<div style='font-size:11px;font-weight:700;letter-spacing:1.2px;"
            f"text-transform:uppercase;color:rgba(242,232,217,0.7);margin-bottom:8px;'>"
            f"{label} — {date_str} | {total_str}</div>"
        )
        rows_html = ""
        for ch in checks:
            rows_html += (
                "<div class='reminder-row'>"
                f"<span style='font-weight:700;color:#f2e8d9;'>{ch['client_name']}</span>"
                f"<span style='font-weight:900;color:#f2e8d9;direction:ltr;'>{fmt_ils(ch['amount'])}</span>"
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
        import pandas as pd

        total_checks_amount = sum(
            float(r["סכום"].replace("₪","").replace(",","")) for r in bs["rows"]
        )
        fee_str   = fmt_ils(bs["total_fee"])
        net_str   = fmt_ils(bs["total_net"])
        total_str = fmt_ils(total_checks_amount)

        # כותרת סיכום
        st.markdown(
            f"<div style='background:linear-gradient(135deg,#1A5A2A 0%,#2A7A4A 100%);"
            f"border-radius:24px;padding:20px 22px 16px;margin-bottom:6px;'>"
            f"<div style='font-size:10px;font-weight:700;letter-spacing:2px;"
            f"text-transform:uppercase;color:rgba(222,197,153,0.65);margin-bottom:6px;'>"
            f"✅ סיכום מקבץ — {bs['count']} צ'קים נשמרו</div>"
            f"<div style='font-size:10px;font-weight:600;color:rgba(222,197,153,0.55);"
            f"margin-bottom:14px;'>שכר טרחה {bs['rate_val']:.2f}% {bs['rate_basis']}</div>"
            # שלושה KPI
            f"<div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;'>"
            # סה"כ צ'קים
            f"<div style='background:rgba(255,255,255,0.12);border-radius:16px;"
            f"padding:12px 8px;text-align:center;'>"
            f"<div style='font-size:9px;font-weight:700;letter-spacing:1px;"
            f"text-transform:uppercase;color:rgba(222,197,153,0.60);margin-bottom:4px;'>סה\"כ</div>"
            f"<div style='font-size:1.05rem;font-weight:900;color:#fff1e0;"
            f"letter-spacing:-0.5px;direction:ltr;'>{total_str}</div></div>"
            # שכר טרחה
            f"<div style='background:rgba(255,60,60,0.22);border-radius:16px;"
            f"padding:12px 8px;text-align:center;'>"
            f"<div style='font-size:9px;font-weight:700;letter-spacing:1px;"
            f"text-transform:uppercase;color:rgba(255,180,180,0.8);margin-bottom:4px;'>שכ\"ט</div>"
            f"<div style='font-size:1.05rem;font-weight:900;color:#FFB3B3;"
            f"letter-spacing:-0.5px;direction:ltr;'>{fee_str}</div></div>"
            # נטו ללקוח
            f"<div style='background:rgba(80,255,160,0.15);border-radius:16px;"
            f"padding:12px 8px;text-align:center;'>"
            f"<div style='font-size:9px;font-weight:700;letter-spacing:1px;"
            f"text-transform:uppercase;color:rgba(180,255,210,0.8);margin-bottom:4px;'>ללקוח</div>"
            f"<div style='font-size:1.05rem;font-weight:900;color:#B3FFDA;"
            f"letter-spacing:-0.5px;direction:ltr;'>{net_str}</div></div>"
            f"</div></div>",
            unsafe_allow_html=True
        )

        # טבלת פירוט
        df_sum = pd.DataFrame(bs["rows"])
        st.dataframe(df_sum, use_container_width=True, hide_index=True)

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
        # שורה 1: סכום + תאריך
        sa, sb = st.columns(2)
        with sa:
            amount = st.number_input("סכום (₪)", min_value=0.0, step=100.0,
                                     format="%.0f", key="add_amount")
        with sb:
            due = st.date_input("תאריך פירעון",
                                value=date.today() + timedelta(days=30),
                                min_value=date.today(), key="add_due")

        # שורה 2: סטטוס + שכ"ט %
        sc, sd = st.columns(2)
        with sc:
            status = st.selectbox("סטטוס", STATUSES, key="add_status")
        with sd:
            single_rate = st.number_input('שכ"ט (%)', min_value=0.0, max_value=100.0,
                                          value=float(st.session_state.get("fixed_rate", 12.0)),
                                          step=0.1, format="%.2f", key="single_rate")
        st.session_state.fixed_rate = single_rate

        # שורה 3: בסיס toggle (2 כפתורי Streamlit) + תזכורת
        cur_basis = st.session_state.get("rate_basis", "שנתי")
        se, sf, sg = st.columns([2, 2, 2])
        with se:
            active_m = cur_basis == "חודשי"
            st.markdown(
                f"<div style='font-size:0.75rem;color:rgba(242,232,217,0.5);"
                f"text-align:right;margin-bottom:2px;'>בסיס</div>",
                unsafe_allow_html=True)
            if st.button(f"{'✓ ' if active_m else ''}חודשי",
                         key="basis_monthly", use_container_width=True):
                st.session_state.rate_basis = "חודשי"
                st.rerun()
        with sf:
            active_y = cur_basis == "שנתי"
            st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
            if st.button(f"{'✓ ' if active_y else ''}שנתי",
                         key="basis_yearly", use_container_width=True):
                st.session_state.rate_basis = "שנתי"
                st.rerun()
        with sg:
            st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
            use_remind = st.checkbox("🔔 תזכורת", value=False, key="add_use_remind")

        single_basis = st.session_state.get("rate_basis", "שנתי")
        st.session_state.rate_basis = single_basis

        if use_remind:
            remind = st.date_input("תאריך תזכורת",
                                   value=date.today() + timedelta(days=30),
                                   min_value=date.today(), key="add_remind")
        else:
            remind = None

        # ── תצוגה חיה ──
        if amount > 0:
            fee, days = calc_fee(amount, due, single_rate, single_basis)
            net = amount - fee
            st.markdown(
                f"<div style='background:rgba(4,20,36,0.65);border:1px solid rgba(229,154,101,0.35);"
                f"border-radius:18px;padding:14px 16px;backdrop-filter:blur(14px);"
                f"-webkit-backdrop-filter:blur(14px);"
                f"margin:8px 0;display:flex;justify-content:space-between;'>"
                f"<div style='text-align:center;'>"
                f"<div style='font-size:11px;font-weight:700;color:rgba(242,232,217,0.6);'>{days} ימים</div>"
                f"<div style='font-weight:900;font-size:1rem;color:#e59a65;direction:ltr;'>{fmt_ils(fee)}</div>"
                f"<div style='font-size:11px;color:rgba(242,232,217,0.6);'>שכ\u05dcט</div></div>"
                f"<div style='text-align:center;'>"
                f"<div style='font-size:11px;font-weight:700;color:rgba(79,227,161,0.9);'>נטו מזומן</div>"
                f"<div style='font-weight:900;font-size:1.2rem;color:#7de8a0;direction:ltr;'>{fmt_ils(net)}</div>"
                f"<div style='font-size:11px;color:rgba(79,227,161,0.9);'>מתקבל</div></div>"
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

        # שורה 1: סכום + תאריך ראשון
        bx, by = st.columns(2)
        with bx:
            amount_base = st.number_input("סכום (₪)", min_value=0.0, step=100.0,
                                          format="%.0f", key="batch_amount")
        with by:
            first_date = st.date_input("תאריך ראשון",
                                       value=date.today() + timedelta(days=30),
                                       min_value=date.today(), key="batch_first")

        # שורה 2: כמות + קפיצה + סטטוס
        b1, b2, b3 = st.columns(3)
        with b1:
            count = st.number_input("כמות", min_value=2, max_value=36,
                                    value=4, step=1, key="batch_count", format="%d")
        with b2:
            gap = st.number_input("קפיצה (י')", min_value=1, max_value=90,
                                  value=30, step=1, key="batch_gap", format="%d")
        with b3:
            status = st.selectbox("סטטוס", STATUSES, key="batch_status")

        # שורה 3: שכ"ט + בסיס
        ba, bb = st.columns(2)
        with ba:
            batch_rate = st.number_input("שכ\"ט (%)", min_value=0.0, max_value=100.0,
                                         value=float(st.session_state.get("fixed_rate", 12.0)),
                                         step=0.1, format="%.2f", key="batch_rate")
        with bb:
            cur_bb = st.session_state.get("rate_basis", "שנתי")
            bb1, bb2 = st.columns(2)
            with bb1:
                if st.button(f"{'✓ ' if cur_bb=='חודשי' else ''}חודשי",
                             key="batch_basis_m", use_container_width=True):
                    st.session_state.rate_basis = "חודשי"
                    st.rerun()
            with bb2:
                if st.button(f"{'✓ ' if cur_bb=='שנתי' else ''}שנתי",
                             key="batch_basis_y", use_container_width=True):
                    st.session_state.rate_basis = "שנתי"
                    st.rerun()
            batch_basis = st.session_state.get("rate_basis", "שנתי")
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
            df = st.session_state.batch_df.reset_index(drop=True)

            # CSS לטבלת מקבץ מינימלית
            st.markdown("""
            <style>
            .batch-table { width:100%; border-collapse:separate; border-spacing:0 4px; direction:rtl; }
            .batch-table th {
                font-size:11px; font-weight:700; letter-spacing:1.2px; text-transform:uppercase;
                color:rgba(242,232,217,0.5); padding:4px 10px; text-align:right;
            }
            .batch-table td {
                background:rgba(4,20,36,0.60); padding:11px 12px;
                font-size:0.95rem; font-weight:700; color:#f2e8d9;
                border-top:1px solid rgba(4,20,36,0.70);
                border-bottom:1px solid rgba(4,20,36,0.70);
            }
            .batch-table td:first-child { border-radius:14px 0 0 14px; border-right:1px solid rgba(4,20,36,0.70); }
            .batch-table td:last-child  { border-radius:0 14px 14px 0; border-left:1px solid rgba(4,20,36,0.70); text-align:left; direction:ltr; }
            .batch-table .num-col { color:#e59a65; font-size:0.82rem; font-weight:800; }
            .batch-table .date-col { color:#f0c080; cursor:pointer; }
            .batch-table .amt-col  { color:#7de8a0; font-family:'Outfit',sans-serif; letter-spacing:-0.3px; cursor:pointer; }
            .edit-panel { background:rgba(255,255,255,0.06); border:1px solid rgba(229,154,101,0.25);
                border-radius:16px; padding:12px 14px; margin:2px 0 6px; }
            </style>
            """, unsafe_allow_html=True)

            # render table header
            st.markdown(
                "<table class='batch-table'>"
                "<tr><th>#</th><th>תאריך 📅</th><th>סכום</th></tr>",
                unsafe_allow_html=True
            )
            # render rows (HTML only — Streamlit buttons outside table)
            for idx in range(len(df)):
                row      = df.iloc[idx]
                num      = int(row["#"])
                amt_val  = float(row["סכום (₪)"])
                date_val = str(row["תאריך"])
                try:
                    d_obj = datetime.fromisoformat(date_val).date()
                    date_disp = d_obj.strftime("%d.%m.%Y")
                except Exception:
                    d_obj = date.today()
                    date_disp = date_val

                st.markdown(
                    f"<tr>"
                    f"<td class='num-col'>#{num}</td>"
                    f"<td class='date-col'>{date_disp}</td>"
                    f"<td class='amt-col'>{fmt_ils(amt_val)}</td>"
                    f"</tr>",
                    unsafe_allow_html=True
                )
            st.markdown("</table>", unsafe_allow_html=True)

            # עורך שורה — נפתח בלחיצה על הכפתור לצד כל שורה
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            st.markdown(
                "<div style='font-size:11px;font-weight:700;letter-spacing:1px;"
                "color:rgba(242,232,217,0.45);text-align:right;margin-bottom:6px;'>"
                "לחץ על שורה לעריכה 👇</div>",
                unsafe_allow_html=True
            )

            for idx in range(len(df)):
                row      = df.iloc[idx]
                num      = int(row["#"])
                amt_val  = float(row["סכום (₪)"])
                date_val = str(row["תאריך"])
                try:
                    d_obj = datetime.fromisoformat(date_val).date()
                    date_disp = d_obj.strftime("%d.%m.%Y")
                except Exception:
                    d_obj = date.today()
                    date_disp = date_val

                open_key = f"batch_edit_open_{idx}"
                is_open  = st.session_state.get(open_key, False)
                lbl      = f"{'▲' if is_open else '▼'} צ'ק #{num} — {date_disp} | {fmt_ils(amt_val)}"

                st.markdown('<div class="btn-sm">', unsafe_allow_html=True)
                if st.button(lbl, key=f"batch_row_btn_{idx}", use_container_width=True):
                    # סגור כל שאר השורות, פתח/סגור את הנוכחית
                    for j in range(len(df)):
                        if j != idx:
                            st.session_state[f"batch_edit_open_{j}"] = False
                    st.session_state[open_key] = not is_open
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

                if is_open:
                    st.markdown("<div class='edit-panel'>", unsafe_allow_html=True)

                    # ── תאריך ──
                    st.markdown(
                        "<div style='font-size:10px;font-weight:700;letter-spacing:1px;"
                        "text-transform:uppercase;color:#f0c080;margin-bottom:4px;'>📅 תאריך</div>",
                        unsafe_allow_html=True
                    )
                    dcol1, dcol2 = st.columns(2)
                    with dcol1:
                        if st.button("− יום", key=f"dm_{idx}", use_container_width=True):
                            df.at[idx, "תאריך"] = (d_obj - timedelta(days=1)).isoformat()
                            st.session_state.batch_df = df
                            st.rerun()
                    with dcol2:
                        if st.button("+ יום", key=f"dp_{idx}", use_container_width=True):
                            df.at[idx, "תאריך"] = (d_obj + timedelta(days=1)).isoformat()
                            st.session_state.batch_df = df
                            st.rerun()

                    # ── סכום ──
                    st.markdown(
                        "<div style='font-size:10px;font-weight:700;letter-spacing:1px;"
                        "text-transform:uppercase;color:#7de8a0;margin:10px 0 4px;'>₪ סכום</div>",
                        unsafe_allow_html=True
                    )
                    new_amt = st.number_input(
                        "סכום חדש (₪)", min_value=0.0, step=50.0,
                        value=amt_val, format="%.0f",
                        key=f"amt_input_{idx}", label_visibility="collapsed"
                    )
                    acol1, acol2, acol3 = st.columns(3)
                    with acol1:
                        if st.button("− 100", key=f"am_{idx}", use_container_width=True):
                            df.at[idx, "סכום (₪)"] = max(0.0, amt_val - 100)
                            st.session_state.batch_df = df
                            st.rerun()
                    with acol2:
                        if st.button("+ 100", key=f"ap_{idx}", use_container_width=True):
                            df.at[idx, "סכום (₪)"] = amt_val + 100
                            st.session_state.batch_df = df
                            st.rerun()
                    with acol3:
                        if st.button("✓ שמור", key=f"amt_save_{idx}", use_container_width=True):
                            df.at[idx, "סכום (₪)"] = float(new_amt)
                            st.session_state.batch_df = df
                            st.session_state[open_key] = False
                            st.rerun()

                    st.markdown("</div>", unsafe_allow_html=True)

            edited = df

            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            if st.button("💾 שמור את כל הצ'קים", use_container_width=True, key="save_batch"):
                cid = add_client(new_name or "") if sel == "— חדש —" else                       next((c["id"] for c in clients if c["name"] == sel), None)
                if not cid:
                    st.error("נא לבחור או להזין שם לקוח.")
                else:
                    amounts   = edited["סכום (₪)"].tolist()
                    due_dates = [datetime.fromisoformat(str(d)).date() for d in edited["תאריך"].tolist()]
                    add_checks_batch(cid, amounts, due_dates, status)
                    saved = len(amounts)

                    # ── סיכום שכר טרחה לפי שיעור קבוע ──
                    rate_val   = st.session_state.get("fixed_rate", 12.0)
                    rate_basis = st.session_state.get("rate_basis", "שנתית")
                    today = date.today()
                    summary_rows = []
                    total_fee = 0.0
                    total_net = 0.0
                    for amt, dd in zip(amounts, due_dates):
                        days = max((dd - today).days + 1, 0)
                        if rate_basis in ("חודשית", "חודשי"):
                            fee = float(amt) * (rate_val / 100.0) * (days / 30.0)
                        else:
                            fee = float(amt) * (rate_val / 100.0) * (days / 365.0)
                        net = float(amt) - fee
                        total_fee += fee
                        total_net += net
                        summary_rows.append({
                            "תאריך": fmt_date(dd),
                            "סכום": fmt_ils(amt),
                            "שכר טרחה": fmt_ils(fee),
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
    ("rgba(229,154,101,0.18)", "rgba(240,192,128,0.95)"),
    ("rgba(100,180,130,0.14)", "rgba(150,220,170,0.95)"),
    ("rgba(180,120,80,0.18)",  "rgba(222,197,153,0.95)"),
    ("rgba(140,100,180,0.14)", "rgba(190,160,220,0.95)"),
    ("rgba(80,150,200,0.14)",  "rgba(140,200,230,0.95)"),
    ("rgba(200,130,80,0.16)",  "rgba(235,185,130,0.95)"),
    ("rgba(100,160,120,0.14)", "rgba(160,210,180,0.95)"),
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

        open_key = f"client_open_{r['id']}"
        is_open  = st.session_state.get(open_key, False)
        btn_lbl  = "✖ סגור פירוט" if is_open else "📋 צפייה בצ'קים"
        if st.button(btn_lbl, key=f"client_toggle_{r['id']}", use_container_width=True):
            st.session_state[open_key] = not is_open
            st.rerun()

        if is_open:
            for ch in get_checks(r["id"]):
                color = STATUS_COLORS.get(ch["status"], "#888")
                remind_str = f" | תזכורת: {ch['remind_on']}" if ch["remind_on"] else ""
                cc1, cc2 = st.columns([3, 2])
                with cc1:
                    st.markdown(f"""
                    <div style="padding:6px 0;">
                        <span style="font-family:'Outfit';font-weight:800;direction:ltr;font-size:1.05rem;color:#f2e8d9;">
                            {fmt_ils(ch['amount'])}</span><br>
                        <span style="font-size:.8rem;color:rgba(222,197,153,0.75);">
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
    # כותרת קומפקטית — לא תופסת מקום
    st.markdown(
        "<div style='display:flex;align-items:center;gap:10px;margin:6px 0 12px;'>"
        "<div style='width:3px;height:22px;border-radius:2px;"
        "background:linear-gradient(180deg,#4D8DFF,#9D8BFF);flex-shrink:0;'></div>"
        "<span style='font-family:Comfortaa,sans-serif;font-size:1.1rem;font-weight:800;"
        "color:#f2e8d9;letter-spacing:-0.3px;'>מחשבון פריטה</span>"
        "</div>",
        unsafe_allow_html=True
    )

    if "fixed_rate"    not in st.session_state: st.session_state.fixed_rate    = 12.0
    if "rate_basis"    not in st.session_state: st.session_state.rate_basis    = "שנתי"
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

    # ── סכום + תאריך — חצי-חצי ──
    ca, cb = st.columns(2)
    with ca:
        amount = st.number_input("סכום (₪)", min_value=0.0, step=100.0,
                                 value=st.session_state.get("calc_amount", default_amount),
                                 format="%.0f", key="calc_amount")
    with cb:
        due_date = st.date_input("תאריך פירעון", key="calc_due",
                                 min_value=date.today())

    # ── ימים + בסיס — שורה אחת ──
    days = max((due_date - date.today()).days + 1, 0)
    cur_basis_c = st.session_state.get("rate_basis", "שנתי")

    di, bm, by_ = st.columns([2, 1, 1])
    with di:
        st.markdown(
            f"<div style='background:rgba(140,79,43,0.22);border:1px solid rgba(229,154,101,0.35);"
            f"border-radius:14px;padding:8px;text-align:center;"
            f"backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);'>"
            f"<div style='font-size:9px;font-weight:700;color:rgba(242,232,217,0.5);"
            f"text-transform:uppercase;letter-spacing:1px;'>ימי זיכוי</div>"
            f"<div style='font-family:Comfortaa,sans-serif;font-size:1.7rem;font-weight:900;"
            f"color:#e59a65;letter-spacing:-1px;line-height:1;'>{days}</div>"
            f"</div>", unsafe_allow_html=True)
    with bm:
        st.markdown("<div style='height:2px'></div>", unsafe_allow_html=True)
        if st.button(f"{'✓ ' if cur_basis_c=='חודשי' else ''}חודשי",
                     key="calc_basis_m", use_container_width=True):
            st.session_state.rate_basis = "חודשי"
            st.rerun()
    with by_:
        st.markdown("<div style='height:2px'></div>", unsafe_allow_html=True)
        if st.button(f"{'✓ ' if cur_basis_c=='שנתי' else ''}שנתי",
                     key="calc_basis_y", use_container_width=True):
            st.session_state.rate_basis = "שנתי"
            st.rerun()

    basis = st.session_state.get("rate_basis", "שנתי")

    # ── שכר טרחה + כפתור עריכה — שורה אחת ──
    rate_val = st.session_state.fixed_rate
    rr1, rr2 = st.columns([3, 1])
    with rr1:
        st.markdown(
            f"<div style='background:rgba(192,122,69,0.20);border:1px solid rgba(229,154,101,0.35);"
            f"border-radius:16px;padding:10px 14px;display:flex;align-items:center;"
            f"justify-content:space-between;backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);'>"
            f"<span style='font-size:10px;font-weight:700;letter-spacing:1px;color:rgba(242,232,217,0.55);"
            f"text-transform:uppercase;'>שכ\"ט קבוע ({basis})</span>"
            f"<span style='font-family:Comfortaa,sans-serif;font-size:1.6rem;font-weight:900;"
            f"color:#f0c080;letter-spacing:-0.5px;'>{rate_val:.2f}%</span>"
            f"</div>", unsafe_allow_html=True)
    with rr2:
        st.write("")
        if st.button("✏️ עריכה", use_container_width=True, key="edit_rate"):
            st.session_state.rate_edit_open = not st.session_state.rate_edit_open

    if st.session_state.rate_edit_open:
        er1, er2 = st.columns([2, 1])
        with er1:
            new_rate = st.number_input("שכר טרחה (%)", min_value=0.0, max_value=100.0,
                                       value=float(rate_val), step=0.1, format="%.2f",
                                       key="rate_input_manual")
        with er2:
            st.write("")
            if st.button("💾 שמור", use_container_width=True, key="save_rate"):
                st.session_state.fixed_rate    = new_rate
                st.session_state.rate_edit_open = False
                st.rerun()

    fee = amount * (rate_val/100.0) * (days/30.0 if basis == "חודשי" else days/365.0)
    net = amount - fee

    if days <= 0:
        st.markdown("<div style='background:rgba(140,79,43,0.25);border:1px solid rgba(229,154,101,0.35);"
                    "border-radius:16px;padding:12px;backdrop-filter:blur(14px);"
                    "-webkit-backdrop-filter:blur(14px);"
                    "text-align:center;font-size:13px;font-weight:700;color:#f0a060;"
                    "margin:8px 0;'>⚠️ תאריך הפירעון עבר — אין ימי זיכוי.</div>",
                    unsafe_allow_html=True)

    fee_pct  = (fee / amount * 100) if amount > 0 else 0
    st.markdown(f"""
    <div class="calc-out fee"><div class="lbl">סך שכר הטרחה שיורד</div>
        <div class="big">{fmt_ils(fee)}</div>
        <div style="font-size:11px;color:rgba(255,111,165,0.7);margin-top:4px;">{days} ימים × {rate_val:.2f}% = {fee_pct:.3f}%</div>
    </div>
    <div class="calc-out net"><div class="lbl">נטו מזומן שמתקבל</div>
        <div class="big">{fmt_ils(net)}</div></div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    init_db()
    inject_css()

    # כניסה חופשית — ללא אימות
    if "current_user" not in st.session_state:
        st.session_state.current_user = "admin"

    # pushState לתמיכה בכפתור חזור
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


if __name__ == "__main__":
    main()
