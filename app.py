# -*- coding: utf-8 -*-
"""
ניהול אובליגו ומחשבון פריטת צ'קים
Streamlit Web App — Mobile-first + Supabase/Postgres
"""

import os
from datetime import date, datetime, timedelta
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
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
# DB — Postgres
# ─────────────────────────────────────────────
def get_db_url():
    url = st.secrets.get("DATABASE_URL", os.environ.get("DATABASE_URL", ""))
    if not url:
        st.error("❌ חסר DATABASE_URL ב-secrets. הוסף אותו ב-Streamlit Cloud.")
        st.stop()
    return url


@contextmanager
def get_conn():
    conn = psycopg2.connect(get_db_url(), cursor_factory=psycopg2.extras.RealDictCursor)
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


def get_cashflow_forecast():
    """תחזית תזרים — סכום צ'קים לפי חודש"""
    u = current_user()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                DATE_TRUNC('month', ch.due_date) AS month,
                SUM(ch.amount) AS total,
                COUNT(ch.id) AS cnt
            FROM checks ch JOIN clients cl ON cl.id=ch.client_id
            WHERE cl.username=%s
              AND ch.due_date >= CURRENT_DATE
            GROUP BY 1 ORDER BY 1
        """, (u,))
        return cur.fetchall()


def get_status_breakdown():
    """פירוט לפי סטטוס"""
    u = current_user()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ch.status,
                   SUM(ch.amount) AS total,
                   COUNT(ch.id) AS cnt
            FROM checks ch JOIN clients cl ON cl.id=ch.client_id
            WHERE cl.username=%s
            GROUP BY ch.status
        """, (u,))
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


# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

    html, body, [class*="css"] { direction: rtl; }

    .stApp {
        background: #708D9F;
        font-family: 'Inter', sans-serif;
        color: #000000;
    }
    #MainMenu, header, footer { visibility: hidden; }
    .block-container {
        padding-top: 0 !important;
        padding-bottom: 5rem;
        max-width: 480px;
    }

    .kpi {
        background: #C4CEFF;
        border-radius: 32px;
        padding: 28px 24px 22px;
        margin-bottom: 6px;
        text-align: center;
    }
    .kpi-label { font-size: 12px; font-weight: 600; letter-spacing: 1.5px; color: #5A5AA3; text-transform: uppercase; margin-bottom: 6px; }
    .kpi-value { font-family: 'Inter', sans-serif; font-size: 3rem; font-weight: 900; line-height: 1; color: #000000; direction: ltr; display: block; letter-spacing: -2px; }
    .kpi-sub { font-size: 13px; color: #6B6BA8; margin-top: 8px; font-weight: 500; }

    .glass { background: rgba(255,255,255,0.15); border-radius: 28px; padding: 20px 22px; margin-bottom: 6px; }
    .pill { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; margin-inline-start: 6px; }

    .section-title { font-size: 22px; font-weight: 900; letter-spacing: -0.5px; color: #fff; margin: 20px 0 6px; text-align: right; }
    .section-title-right { font-size: 22px; font-weight: 900; letter-spacing: -0.5px; color: #fff; margin: 10px 0 6px; text-align: right; }
    .neon-bar, .neon-bar-right { height: 3px; width: 36px; border-radius: 3px; background: #fff; margin-bottom: 16px; margin-right: 0; }
    .neon-bar { margin-right: auto; margin-left: auto; }

    .client-card { display: flex; justify-content: space-between; align-items: center; background: #F0F0F5; border-radius: 22px; padding: 16px 18px; margin-bottom: 6px; }
    .client-name { font-weight: 800; font-size: 1rem; color: #000; }
    .client-obligo { font-weight: 900; font-size: 1.15rem; color: #000; direction: ltr; letter-spacing: -0.5px; }

    .calc-out { border-radius: 28px; padding: 20px 22px; margin-top: 6px; text-align: center; }
    .calc-out.fee { background: #FFD6E8; }
    .calc-out.net { background: #D6F5E0; margin-top: 6px; }
    .calc-out .lbl { font-size: 12px; font-weight: 600; letter-spacing: 1.2px; text-transform: uppercase; color: #8A8A93; margin-bottom: 6px; }
    .calc-out .big { font-family: 'Inter', sans-serif; font-size: 2.6rem; font-weight: 900; direction: ltr; line-height: 1.1; letter-spacing: -1.5px; color: #000; }

    /* דשבורד תזרים */
    .forecast-card { background: #E8E4FF; border-radius: 22px; padding: 16px 18px; margin-bottom: 6px; }
    .forecast-month { font-size: 11px; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; color: #5A5AA3; margin-bottom: 4px; }
    .forecast-amount { font-size: 1.4rem; font-weight: 900; color: #000; direction: ltr; }
    .forecast-bar-bg { background: rgba(0,0,0,0.08); border-radius: 99px; height: 6px; margin-top: 8px; }
    .forecast-bar-fill { background: #5A5AA3; border-radius: 99px; height: 6px; }

    .status-card { border-radius: 18px; padding: 14px 16px; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center; }

    .stButton > button { border-radius: 16px !important; border: none !important; background: #EFEFEF !important; color: #000 !important; font-weight: 700 !important; font-family: 'Inter', sans-serif !important; transition: opacity .15s ease !important; }
    .stButton > button:hover { opacity: 0.82 !important; }

    .home-nav-btn .stButton > button { border-radius: 28px !important; font-size: 1.25rem !important; font-weight: 900 !important; min-height: 90px !important; height: auto !important; padding: 26px 24px !important; }
    .home-nav-green .stButton > button { background: #D6F5E0 !important; color: #000 !important; }
    .home-nav-pink .stButton > button { background: #E8E4FF !important; color: #000 !important; }
    .home-nav-blue .stButton > button { background: #C8E8FF !important; color: #000 !important; }

    .btn-single .stButton > button { border-radius: 50px !important; background: #000 !important; color: #fff !important; font-size: 0.95rem !important; font-weight: 800 !important; padding: 12px 0 !important; }
    .btn-batch .stButton > button { border-radius: 50px !important; background: #E8E4FF !important; color: #000 !important; font-size: 0.95rem !important; font-weight: 800 !important; padding: 12px 0 !important; }

    .reminder-card { background: #FFF3C8; border-radius: 22px; padding: 16px 18px; margin-bottom: 8px; }
    .reminder-title { font-size: 11px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: #8A6A00; margin-bottom: 8px; }
    .reminder-row { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; border-bottom: 1px solid rgba(0,0,0,0.06); }
    .reminder-row:last-child { border-bottom: none; }

    .btn-sm .stButton > button { padding: 3px 8px !important; font-size: 0.75rem !important; border-radius: 8px !important; min-height: 0 !important; height: auto !important; font-weight: 700 !important; }

    .back-btn { position: fixed !important; bottom: 28px !important; left: 20px !important; z-index: 9999 !important; }
    .back-btn .stButton > button { border-radius: 50px !important; background: rgba(255,255,255,0.92) !important; color: #000 !important; font-size: 0.82rem !important; font-weight: 800 !important; padding: 10px 20px !important; height: auto !important; min-height: 0 !important; box-shadow: 0 4px 20px rgba(0,0,0,0.18) !important; }

    .stTextInput input, .stNumberInput input, .stDateInput input,
    [data-baseweb="input"] input, [data-baseweb="base-input"] input {
        color: #000 !important; background-color: #F0F0F5 !important;
        -webkit-text-fill-color: #000 !important; caret-color: #000 !important;
        border-radius: 14px !important; border: none !important;
        font-weight: 600 !important; font-size: 1rem !important;
        direction: rtl !important; text-align: right !important;
    }
    .stTextInput div[data-baseweb="input"], .stNumberInput div[data-baseweb="input"],
    .stDateInput div[data-baseweb="input"], div[data-baseweb="select"] > div {
        background-color: #F0F0F5 !important; border: none !important; border-radius: 14px !important;
    }
    div[data-baseweb="select"] div { color: #000 !important; font-weight: 600 !important; }
    input::placeholder { color: #AEAEB8 !important; opacity: 1 !important; }
    label { color: #000 !important; font-weight: 700 !important; font-size: 0.85rem !important; }

    div[data-testid="stRadio"] > div { gap: 10px !important; justify-content: center !important; }
    div[data-testid="stRadio"] label { background: #F0F0F5 !important; border: none !important; border-radius: 14px !important; padding: 10px 28px !important; font-size: 1rem !important; font-weight: 800 !important; color: #000 !important; cursor: pointer; }
    div[data-testid="stRadio"] input[type="radio"] { display: none !important; }
    div[data-testid="stRadio"] div[data-baseweb="radio"] > div:first-child { display: none !important; }

    .stTabs [data-baseweb="tab-list"] { gap: 6px; justify-content: center; background: transparent !important; }
    .stTabs [data-baseweb="tab"] { background: #EFEFEF !important; border-radius: 14px !important; padding: 10px 24px !important; border: none !important; font-size: 0.95rem !important; font-weight: 700 !important; color: #8A8A93 !important; min-width: 130px; text-align: center; }
    .stTabs [aria-selected="true"] { background: #000 !important; color: #fff !important; }
    .stTabs [aria-selected="true"] p, .stTabs [aria-selected="true"] span, .stTabs [aria-selected="true"] div { color: #fff !important; }

    .streamlit-expanderHeader { background: #F0F0F5 !important; border-radius: 14px !important; font-weight: 700 !important; color: #000 !important; border: none !important; }
    .streamlit-expanderContent { background: #F7F7F9 !important; border: none !important; }

    ul[role="listbox"], div[data-baseweb="popover"] { background-color: #fff !important; border-radius: 16px !important; }
    ul[role="listbox"] li { color: #000 !important; font-weight: 600 !important; }
    </style>
    """, unsafe_allow_html=True)

    st.components.v1.html("""
    <script>
    function attachSelectAll() {
        var inputs = window.parent.document.querySelectorAll('input[type="number"]');
        inputs.forEach(function(inp) {
            if (inp._sa) return; inp._sa = true;
            inp.addEventListener('focus', function() { var s=this; setTimeout(function(){ s.select(); },50); });
        });
    }
    attachSelectAll(); setInterval(attachSelectAll, 600);
    </script>
    """, height=0)


def fmt_ils(x):
    return f"₪{x:,.0f}"


def fmt_date(d):
    if not d:
        return ""
    try:
        if isinstance(d, str):
            d = datetime.fromisoformat(d).date()
        return d.strftime("%d.%m.%Y")
    except Exception:
        return str(d)


def calc_fee(amount, due_date, rate_val, rate_basis):
    days = max((due_date - date.today()).days + 1, 0)
    if rate_basis == "חודשית":
        fee = float(amount) * (rate_val / 100.0) * (days / 30.0)
    else:
        fee = float(amount) * (rate_val / 100.0) * (days / 365.0)
    return fee, days


# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────
def render_auth_screen():
    st.markdown(
        "<div style='height:40px'></div>"
        "<p style='text-align:center;font-size:12px;font-weight:700;letter-spacing:3px;"
        "color:rgba(255,255,255,0.7);text-transform:uppercase;margin-bottom:4px;'>CHECK MANAGEMENT</p>"
        "<h1 style='text-align:center;font-family:Inter,sans-serif;font-weight:900;"
        "font-size:3rem;letter-spacing:-2px;color:#fff;line-height:1;margin-bottom:4px;'>"
        "CHECKFLOW</h1>"
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
# דשבורד תזרים
# ─────────────────────────────────────────────
def render_dashboard():
    st.markdown('<div class="section-title">📊 דשבורד תזרים</div>', unsafe_allow_html=True)
    st.markdown('<div class="neon-bar"></div>', unsafe_allow_html=True)

    # סה"כ לפי סטטוס
    status_rows = get_status_breakdown()
    if status_rows:
        st.markdown("<div style='margin-bottom:10px;'>", unsafe_allow_html=True)
        status_bg = {"ממתין למזומן": "#FFF3C8", "להפקדה": "#D6F5E0", "בפריטה": "#FFD6E8"}
        for r in status_rows:
            bg = status_bg.get(r["status"], "#F0F0F5")
            color = STATUS_COLORS.get(r["status"], "#000")
            st.markdown(f"""
            <div class="status-card" style="background:{bg};">
                <div>
                    <span style="font-weight:800;font-size:0.95rem;color:#000;">{r['status']}</span>
                    <span style="font-size:12px;color:#888;font-weight:600;margin-right:8px;">{r['cnt']} צ'קים</span>
                </div>
                <span style="font-weight:900;font-size:1.1rem;color:#000;direction:ltr;">{fmt_ils(r['total'])}</span>
            </div>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # תחזית חודשית
    forecast = get_cashflow_forecast()
    if not forecast:
        st.markdown('<div class="glass" style="text-align:center;color:#fff;">אין צ\'קים עתידיים 📭</div>', unsafe_allow_html=True)
        return

    max_amount = max(r["total"] for r in forecast) or 1

    st.markdown("<div style='font-size:13px;font-weight:700;color:rgba(255,255,255,0.8);margin-bottom:8px;'>פירעונות לפי חודש</div>", unsafe_allow_html=True)
    for r in forecast:
        month_dt = r["month"]
        if hasattr(month_dt, "strftime"):
            month_label = month_dt.strftime("%B %Y")
            # עברית
            month_he = {
                "January": "ינואר", "February": "פברואר", "March": "מרץ",
                "April": "אפריל", "May": "מאי", "June": "יוני",
                "July": "יולי", "August": "אוגוסט", "September": "ספטמבר",
                "October": "אוקטובר", "November": "נובמבר", "December": "דצמבר",
            }
            for en, he in month_he.items():
                month_label = month_label.replace(en, he)
        else:
            month_label = str(month_dt)[:7]

        pct = int((r["total"] / max_amount) * 100)
        st.markdown(f"""
        <div class="forecast-card">
            <div class="forecast-month">{month_label} · {r['cnt']} צ'קים</div>
            <div class="forecast-amount">{fmt_ils(r['total'])}</div>
            <div class="forecast-bar-bg">
                <div class="forecast-bar-fill" style="width:{pct}%;"></div>
            </div>
        </div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# מסך ראשי
# ─────────────────────────────────────────────
def render_home_screen():
    st.markdown(
        "<div style='height:40px'></div>"
        "<p style='text-align:center;font-size:12px;font-weight:700;letter-spacing:3px;"
        "color:rgba(255,255,255,0.7);text-transform:uppercase;margin-bottom:4px;'>CHECK MANAGEMENT</p>"
        "<h1 style='text-align:center;font-family:Inter,sans-serif;font-weight:900;"
        "font-size:3rem;letter-spacing:-2px;color:#fff;line-height:1;margin-bottom:4px;'>"
        "CHECKFLOW</h1>"
        "<p style='text-align:center;color:#8A8A93;font-size:0.9rem;margin-bottom:28px;"
        "font-weight:500;'>ניהול צ׳קים ופריטה</p>",
        unsafe_allow_html=True,
    )

    render_kpi()

    st.markdown('<div class="home-nav-btn home-nav-green">', unsafe_allow_html=True)
    if st.button("🧮  מחשבון פריטה", key="go_calc", use_container_width=True):
        st.session_state.screen = "calc"
        st.rerun()
    st.markdown('</div><div style="height:10px"></div>', unsafe_allow_html=True)

    st.markdown('<div class="home-nav-btn home-nav-pink">', unsafe_allow_html=True)
    if st.button("📋  ניהול צ׳קים", key="go_mgmt", use_container_width=True):
        st.session_state.screen = "mgmt"
        st.rerun()
    st.markdown('</div><div style="height:10px"></div>', unsafe_allow_html=True)

    st.markdown('<div class="home-nav-btn home-nav-blue">', unsafe_allow_html=True)
    if st.button("📊  דשבורד תזרים", key="go_dash", use_container_width=True):
        st.session_state.screen = "dash"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def render_back_button():
    st.markdown('<div class="back-btn">', unsafe_allow_html=True)
    if st.button("← ראשי", key="back_home"):
        st.session_state.screen = "home"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def render_kpi():
    total, cnt = get_totals()
    st.markdown(f"""
    <div class="kpi">
        <div class="kpi-label">סך הצ'קים שביד כרגע</div>
        <div class="kpi-value">{fmt_ils(total)}</div>
        <div class="kpi-sub">{cnt} צ'קים פיזיים בארנק 💸</div>
    </div>
    """, unsafe_allow_html=True)


def render_upcoming_reminder():
    upcoming = get_upcoming_checks(days_ahead=2)
    if not upcoming:
        return

    day_labels = {
        date.today(): "היום",
        date.today() + timedelta(days=1): "מחר",
        date.today() + timedelta(days=2): "מחרתיים",
    }

    total_checks = sum(len(v) for v in upcoming.values())
    total_amount = sum(ch["amount"] for v in upcoming.values() for ch in v)

    st.markdown(
        f"<div class='reminder-card'>"
        f"<div class='reminder-title'>⏰ פירעונות קרובים</div>"
        f"<div style='display:flex;justify-content:space-between;'>"
        f"<span style='font-weight:800;font-size:1rem;color:#000;'>{total_checks} צ'קים</span>"
        f"<span style='font-weight:900;font-size:1rem;color:#000;'>{fmt_ils(total_amount)}</span>"
        f"</div></div>",
        unsafe_allow_html=True
    )

    expanded = st.session_state.get("reminder_open", False)
    if st.button("📋 פרטים מלאים" if not expanded else "✖ סגור", key="toggle_reminder"):
        st.session_state.reminder_open = not expanded
        st.rerun()

    if not st.session_state.get("reminder_open", False):
        return

    for d, checks in sorted(upcoming.items()):
        label = day_labels.get(d, d.strftime("%d.%m"))
        day_sum = sum(ch["amount"] for ch in checks)
        bg_map = {
            date.today(): "#D6F5E0",
            date.today() + timedelta(days=1): "#E8E4FF",
            date.today() + timedelta(days=2): "#FFF3C8",
        }
        bg = bg_map.get(d, "#F0F0F5")
        rows_html = "".join(
            f"<div class='reminder-row'>"
            f"<span style='font-weight:700;color:#000;'>{ch['client_name']}</span>"
            f"<span style='font-weight:900;color:#000;'>{fmt_ils(ch['amount'])}</span>"
            f"</div>"
            for ch in checks
        )
        st.markdown(
            f"<div style='background:{bg};border-radius:18px;padding:14px 16px;margin-bottom:6px;'>"
            f"<div style='font-size:11px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;"
            f"color:#555;margin-bottom:8px;'>{label} — {d.strftime('%d.%m.%Y')} | {fmt_ils(day_sum)}</div>"
            f"{rows_html}</div>",
            unsafe_allow_html=True
        )


def render_add_check_form():
    clients = get_clients()
    names = [c["name"] for c in clients]

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

    if "batch_summary" in st.session_state and st.session_state.batch_summary:
        import pandas as pd
        bs = st.session_state.batch_summary
        st.markdown(
            f"<div style='background:#D6F5E0;border-radius:22px;padding:18px 20px;margin-bottom:10px;'>"
            f"<div style='font-size:11px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;"
            f"color:#2A7A4A;margin-bottom:10px;'>✅ {bs['count']} צ'קים נשמרו</div>",
            unsafe_allow_html=True
        )
        st.dataframe(pd.DataFrame(bs["rows"]), use_container_width=True, hide_index=True)
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;padding:10px 4px 4px;"
            f"font-weight:800;font-size:1rem;color:#000;'>"
            f"<span>סהכ עמלות: {fmt_ils(bs['total_fee'])}</span>"
            f"<span>סהכ נטו: {fmt_ils(bs['total_net'])}</span>"
            f"</div></div>",
            unsafe_allow_html=True
        )
        if st.button("✖ סגור סיכום", key="close_summary"):
            st.session_state.batch_summary = None
            st.rerun()

    mode = st.session_state.get("add_mode")
    if not mode:
        return

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    sel = st.selectbox("לקוח", ["— חדש —"] + names, key="add_client_sel")
    new_name = st.text_input("שם לקוח חדש", key="new_client_name", placeholder="הזן שם לקוח...") if sel == "— חדש —" else None

    if mode == "single":
        amount = st.number_input("סכום הצ'ק (₪)", min_value=0.0, step=100.0, format="%.0f", key="add_amount")
        c1, c2 = st.columns(2)
        with c1:
            due = st.date_input("תאריך פירעון", value=date.today() + timedelta(days=30), min_value=date.today(), key="add_due")
        with c2:
            use_remind = st.checkbox("הוסף תזכורת", value=False, key="add_use_remind")
        remind = st.date_input("תאריך תזכורת", value=date.today() + timedelta(days=30), min_value=date.today(), key="add_remind") if use_remind else None
        status = st.selectbox("סטטוס", STATUSES, key="add_status")

        ra, rb = st.columns(2)
        with ra:
            single_rate = st.number_input("ריבית (%)", min_value=0.0, max_value=100.0,
                                          value=float(st.session_state.get("fixed_rate", 12.0)),
                                          step=0.1, format="%.2f", key="single_rate")
        with rb:
            single_basis = st.radio("בסיס", ["חודשית", "שנתית"],
                                    index=["חודשית", "שנתית"].index(st.session_state.get("rate_basis", "שנתית")),
                                    key="single_basis", horizontal=True)
        st.session_state.fixed_rate = single_rate
        st.session_state.rate_basis = single_basis

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
            cid = add_client(new_name or "") if sel == "— חדש —" else next((c["id"] for c in clients if c["name"] == sel), None)
            if not cid:
                st.error("נא לבחור או להזין שם לקוח.")
            elif amount <= 0:
                st.error("נא להזין סכום גדול מאפס.")
            else:
                add_check(cid, amount, due, status, remind)
                st.session_state.add_mode = None
                st.rerun()

    elif mode == "batch":
        import pandas as pd
        amount_base = st.number_input("סכום לכל צ'ק (₪)", min_value=0.0, step=100.0, format="%.0f", key="batch_amount")
        b1, b2, b3 = st.columns(3)
        with b1:
            first_date = st.date_input("תאריך ראשון", value=date.today() + timedelta(days=30), min_value=date.today(), key="batch_first")
        with b2:
            count = st.number_input("מספר צ'קים", min_value=2, max_value=36, value=4, step=1, key="batch_count", format="%d")
        with b3:
            gap = st.number_input("קפיצה (ימים)", min_value=1, max_value=90, value=30, step=1, key="batch_gap", format="%d")
        status = st.selectbox("סטטוס", STATUSES, key="batch_status")

        ba, bb = st.columns(2)
        with ba:
            batch_rate = st.number_input("ריבית (%)", min_value=0.0, max_value=100.0,
                                         value=float(st.session_state.get("fixed_rate", 12.0)),
                                         step=0.1, format="%.2f", key="batch_rate")
        with bb:
            batch_basis = st.radio("בסיס", ["חודשית", "שנתית"],
                                   index=["חודשית", "שנתית"].index(st.session_state.get("rate_basis", "שנתית")),
                                   key="batch_basis", horizontal=True)
        st.session_state.fixed_rate = batch_rate
        st.session_state.rate_basis = batch_basis

        if st.button("🔄 צור טבלת עריכה", use_container_width=True, key="gen_table"):
            rows = [{"#": i+1, "סכום (₪)": float(amount_base), "תאריך": (first_date + timedelta(days=int(gap)*i)).isoformat()} for i in range(int(count))]
            st.session_state.batch_df = pd.DataFrame(rows)[["#", "סכום (₪)", "תאריך"]]

        if "batch_df" in st.session_state and st.session_state.batch_df is not None:
            edited = st.data_editor(
                st.session_state.batch_df, use_container_width=True, hide_index=True,
                column_config={
                    "#": st.column_config.NumberColumn(disabled=True, width="small"),
                    "סכום (₪)": st.column_config.NumberColumn(min_value=0, format="%.0f"),
                    "תאריך": st.column_config.TextColumn(),
                }, key="batch_editor"
            )

            if st.button("💾 שמור את כל הצ'קים", use_container_width=True, key="save_batch"):
                cid = add_client(new_name or "") if sel == "— חדש —" else next((c["id"] for c in clients if c["name"] == sel), None)
                if not cid:
                    st.error("נא לבחור או להזין שם לקוח.")
                else:
                    amounts = edited["סכום (₪)"].tolist()
                    due_dates = [datetime.fromisoformat(str(d)).date() for d in edited["תאריך"].tolist()]
                    add_checks_batch(cid, amounts, due_dates, status)

                    rate_val = st.session_state.get("fixed_rate", 12.0)
                    rate_basis = st.session_state.get("rate_basis", "שנתית")
                    today = date.today()
                    summary_rows, total_fee, total_net = [], 0.0, 0.0
                    for amt, dd in zip(amounts, due_dates):
                        days = max((dd - today).days + 1, 0)
                        fee = float(amt) * (rate_val/100.0) * (days/30.0 if rate_basis=="חודשית" else days/365.0)
                        net = float(amt) - fee
                        total_fee += fee; total_net += net
                        summary_rows.append({"תאריך": fmt_date(dd), "סכום": fmt_ils(amt), "עמלה": fmt_ils(fee), "נטו": fmt_ils(net)})

                    st.session_state.batch_summary = {"rows": summary_rows, "total_fee": total_fee, "total_net": total_net, "count": len(amounts)}
                    st.session_state.add_mode = None
                    st.session_state.batch_df = None
                    st.rerun()


CLIENT_PALETTE = [
    ("#E8E4FF", "#5A5AA3"), ("#D6F5E0", "#2A7A4A"), ("#FFD6E8", "#8A2A50"),
    ("#E8F5A3", "#5A6800"), ("#FFF3C8", "#8A6A00"), ("#C8E8FF", "#1A5A8A"), ("#FFE8D6", "#8A3A00"),
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
            <div><div class="client-name">{r['name']}</div>
            <div style="font-size:.82rem;color:{txt};font-weight:600;">{r['cnt']} צ'קים</div></div>
            <div class="client-obligo">{fmt_ils(r['obligo'])}</div>
        </div>""", unsafe_allow_html=True)

        with st.expander("צפייה בצ'קים"):
            for ch in get_checks(r["id"]):
                color = STATUS_COLORS.get(ch["status"], "#888")
                remind_str = f" | תזכורת: {fmt_date(ch['remind_on'])}" if ch["remind_on"] else ""
                cc1, cc2 = st.columns([3, 2])
                with cc1:
                    st.markdown(f"""
                    <div style="padding:6px 0;">
                        <span style="font-weight:700;direction:ltr;">{fmt_ils(ch['amount'])}</span><br>
                        <span style="font-size:.8rem;color:rgba(255,255,255,0.75);">פירעון: {fmt_date(ch['due_date'])}{remind_str}</span>
                        <span class="pill" style="background:{color}22;color:{color};border:1px solid {color}66;">{ch['status']}</span>
                    </div>""", unsafe_allow_html=True)
                with cc2:
                    new_st = st.selectbox("סטטוס", STATUSES, index=STATUSES.index(ch["status"]),
                                          key=f"st_{ch['id']}", label_visibility="collapsed")
                    st.markdown('<div class="btn-sm">', unsafe_allow_html=True)
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("✓", key=f"upd_{ch['id']}", use_container_width=True):
                            update_status(ch["id"], new_st); st.rerun()
                    with b2:
                        if st.button("🗑", key=f"del_{ch['id']}", use_container_width=True):
                            delete_check(ch["id"]); st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)


def render_calculator():
    st.markdown('<div class="section-title-right">מחשבון פריטה (ניכיון)</div>', unsafe_allow_html=True)
    st.markdown('<div class="neon-bar-right"></div>', unsafe_allow_html=True)

    if "fixed_rate" not in st.session_state: st.session_state.fixed_rate = 12.0
    if "rate_basis" not in st.session_state: st.session_state.rate_basis = "שנתית"
    if "rate_edit_open" not in st.session_state: st.session_state.rate_edit_open = False

    checks = get_checks()
    options = ["— הזנה ידנית —"] + [f"{c['client_name']} | {fmt_ils(c['amount'])} | {fmt_date(c['due_date'])}" for c in checks]
    pick = st.selectbox("בחר צ'ק קיים (או הזנה ידנית)", options, key="calc_pick")

    default_amount = 10000.0
    default_due = date.today() + timedelta(days=30)
    if pick != "— הזנה ידנית —":
        idx = options.index(pick) - 1
        ch = checks[idx]
        default_amount = float(ch["amount"])
        try:
            default_due = ch["due_date"] if isinstance(ch["due_date"], date) else datetime.fromisoformat(str(ch["due_date"])).date()
        except:
            pass

    if st.session_state.get("_last_pick") != pick:
        st.session_state.calc_due = default_due
        st.session_state.calc_amount = default_amount
        st.session_state._last_pick = pick

    amount = st.number_input("סכום הצ'ק (₪)", min_value=0.0, step=100.0,
                             value=st.session_state.get("calc_amount", default_amount),
                             format="%.0f", key="calc_amount")
    due_date = st.date_input("תאריך פירעון הצ'ק", key="calc_due", min_value=date.today())

    days = max((due_date - date.today()).days + 1, 0)
    st.markdown(
        f"<div style='background:#E8F5A3;border-radius:22px;padding:16px;text-align:center;margin:6px 0 10px;'>"
        f"<span style='font-size:11px;font-weight:700;letter-spacing:1.2px;color:#5A6800;text-transform:uppercase;display:block;margin-bottom:2px;'>ימי זיכוי</span>"
        f"<span style='font-family:Inter,sans-serif;font-size:2.4rem;font-weight:900;color:#000;letter-spacing:-1.5px;'>{days}</span>"
        f"<span style='font-size:0.9rem;font-weight:600;color:#5A6800;'> ימים</span></div>",
        unsafe_allow_html=True)

    basis = st.radio("סוג הריבית", ["חודשית", "שנתית"],
                     index=["חודשית", "שנתית"].index(st.session_state.rate_basis),
                     horizontal=True, key="basis_radio", label_visibility="collapsed")
    st.session_state.rate_basis = basis

    rate_val = st.session_state.fixed_rate
    r1, r2 = st.columns([2, 1])
    with r1:
        st.markdown(
            f"<div style='background:#FFF3C8;border-radius:22px;padding:16px;text-align:center;'>"
            f"<span style='font-size:11px;font-weight:700;letter-spacing:1.2px;color:#8A6A00;text-transform:uppercase;display:block;margin-bottom:4px;'>ריבית קבועה ({basis})</span>"
            f"<span style='font-size:2rem;font-weight:900;color:#000;letter-spacing:-1px;'>{rate_val:.2f}%</span>"
            f"</div>", unsafe_allow_html=True)
    with r2:
        st.write(""); st.write("")
        if st.button("✏️ שינוי ריבית", use_container_width=True, key="edit_rate"):
            st.session_state.rate_edit_open = not st.session_state.rate_edit_open

    if st.session_state.rate_edit_open:
        new_rate = st.number_input("הזן ריבית (%)", min_value=0.0, max_value=100.0,
                                   value=float(rate_val), step=0.1, format="%.2f", key="rate_input_manual")
        if st.button("💾 שמירת הריבית", use_container_width=True, key="save_rate"):
            st.session_state.fixed_rate = new_rate
            st.session_state.rate_edit_open = False
            st.rerun()

    fee = amount * (rate_val/100.0) * (days/30.0 if basis == "חודשית" else days/365.0)
    net = amount - fee

    st.markdown(f"""
    <div class="calc-out fee"><div class="lbl">סך העמלה שיורדת</div><div class="big">{fmt_ils(fee)}</div></div>
    <div class="calc-out net"><div class="lbl">נטו מזומן שמתקבל</div><div class="big">{fmt_ils(net)}</div></div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
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
