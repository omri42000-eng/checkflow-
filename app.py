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
    "ממתין למזומן": "#FF9F1C",
    "להפקדה": "#39FF14",
    "בפריטה": "#FF2D95",
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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

    html, body, [class*="css"] { direction: rtl; }

    /* ─── רקע ─── */
    .stApp {
        background: #F7F7F9;
        font-family: 'Inter', sans-serif;
        color: #000000;
    }
    #MainMenu, header, footer { visibility: hidden; }
    .block-container {
        padding-top: 0 !important;
        padding-bottom: 5rem;
        max-width: 480px;
    }

    /* ─── KPI ─── */
    .kpi {
        background: #C4CEFF;
        border-radius: 32px;
        padding: 28px 24px 22px;
        margin-bottom: 6px;
        text-align: center;
        border: none;
    }
    .kpi-label {
        font-size: 12px; font-weight: 600; letter-spacing: 1.5px;
        color: #5A5AA3; text-transform: uppercase; margin-bottom: 6px;
    }
    .kpi-value {
        font-family: 'Inter', sans-serif;
        font-size: 3rem; font-weight: 900; line-height: 1;
        color: #000000; direction: ltr; display: block;
        letter-spacing: -2px;
    }
    .kpi-sub {
        font-size: 13px; color: #6B6BA8; margin-top: 8px; font-weight: 500;
    }

    /* ─── כרטיסים כלליים ─── */
    .glass {
        background: #FFFFFF;
        border-radius: 28px;
        padding: 20px 22px;
        margin-bottom: 6px;
        border: none;
    }

    /* ─── pill ─── */
    .pill {
        display: inline-block; padding: 2px 10px; border-radius: 999px;
        font-size: 11px; font-weight: 700; margin-inline-start: 6px;
        letter-spacing: 0.3px;
    }

    /* ─── כותרות סקשן ─── */
    .section-title {
        font-size: 22px; font-weight: 900; letter-spacing: -0.5px;
        color: #000; margin: 20px 0 6px; text-align: right;
    }
    .section-title-right {
        font-size: 22px; font-weight: 900; letter-spacing: -0.5px;
        color: #000; margin: 10px 0 6px; text-align: right;
    }
    .neon-bar, .neon-bar-right {
        height: 3px; width: 36px; border-radius: 3px;
        background: #000; margin-bottom: 16px; margin-right: 0;
    }
    .neon-bar { margin-right: auto; margin-left: auto; }

    /* ─── כרטיס לקוח ─── */
    .client-card {
        display: flex; justify-content: space-between; align-items: center;
        background: #F0F0F5;
        border-radius: 22px; padding: 16px 18px; margin-bottom: 6px;
        border: none;
    }
    .client-name { font-weight: 800; font-size: 1rem; color: #000; }
    .client-obligo {
        font-weight: 900; font-size: 1.15rem;
        color: #000; direction: ltr; letter-spacing: -0.5px;
    }

    /* ─── פלט מחשבון ─── */
    .calc-out {
        border-radius: 28px; padding: 20px 22px;
        margin-top: 6px; text-align: center; border: none;
    }
    .calc-out.fee { background: #FFD6E8; }
    .calc-out.net { background: #D6F5E0; margin-top: 6px; }
    .calc-out .lbl {
        font-size: 12px; font-weight: 600; letter-spacing: 1.2px;
        text-transform: uppercase; color: #8A8A93; margin-bottom: 6px;
    }
    .calc-out .big {
        font-family: 'Inter', sans-serif; font-size: 2.6rem;
        font-weight: 900; direction: ltr; line-height: 1.1;
        letter-spacing: -1.5px; color: #000;
    }

    /* ─── כפתורים כלליים ─── */
    .stButton > button {
        border-radius: 16px !important;
        border: none !important;
        background: #EFEFEF !important;
        color: #000 !important;
        font-weight: 700 !important;
        font-family: 'Inter', sans-serif !important;
        transition: opacity .15s ease !important;
    }
    .stButton > button:hover { opacity: 0.82 !important; }

    /* ─── כפתורי ניווט מסך הבית ─── */
    .home-nav-btn .stButton > button {
        border-radius: 28px !important;
        font-size: 1.25rem !important;
        font-weight: 900 !important;
        min-height: 90px !important;
        height: auto !important;
        padding: 26px 24px !important;
        letter-spacing: -0.3px !important;
        border: none !important;
    }
    .home-nav-green .stButton > button {
        background: #D6F5E0 !important;
        color: #000 !important;
    }
    .home-nav-pink .stButton > button {
        background: #E8E4FF !important;
        color: #000 !important;
    }

    /* ─── כפתור הוספת צ'ק ─── */
    .add-check-wrapper .stButton > button {
        border-radius: 50px !important;
        background: #000 !important;
        color: #fff !important;
        font-size: 1rem !important;
        font-weight: 800 !important;
        padding: 14px 0 !important;
        border: none !important;
        letter-spacing: 0.2px !important;
    }
    .add-check-wrapper .stButton > button:hover { opacity: 0.80 !important; }

    /* ─── כפתור חזרה ─── */
    .back-btn { display: inline-block; margin-bottom: 10px; }
    .back-btn .stButton > button {
        border-radius: 50px !important;
        background: #EFEFEF !important;
        color: #8A8A93 !important;
        font-size: 0.80rem !important;
        font-weight: 700 !important;
        padding: 5px 16px !important;
        height: auto !important;
        min-height: 0 !important;
        line-height: 1.6 !important;
        border: none !important;
    }

    /* ─── שדות קלט ─── */
    .stTextInput input,
    .stNumberInput input,
    .stDateInput input,
    [data-baseweb="input"] input,
    [data-baseweb="base-input"] input {
        color: #000 !important;
        background-color: #F0F0F5 !important;
        -webkit-text-fill-color: #000 !important;
        caret-color: #000 !important;
        border-radius: 14px !important;
        border: none !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        direction: ltr !important;
        text-align: right !important;
    }
    .stTextInput div[data-baseweb="input"],
    .stNumberInput div[data-baseweb="input"],
    .stDateInput div[data-baseweb="input"],
    div[data-baseweb="select"] > div {
        background-color: #F0F0F5 !important;
        border: none !important;
        border-radius: 14px !important;
    }
    div[data-baseweb="select"] div { color: #000 !important; font-weight: 600 !important; }
    input::placeholder { color: #AEAEB8 !important; opacity: 1 !important; }
    ul[role="listbox"], div[data-baseweb="popover"] { background-color: #fff !important; border-radius: 16px !important; }
    ul[role="listbox"] li { color: #000 !important; font-weight: 600 !important; }
    label { color: #8A8A93 !important; font-weight: 600 !important; font-size: 0.82rem !important; }

    /* ─── רדיו ריבית ─── */
    div[data-testid="stRadio"] > div { gap: 10px !important; justify-content: center !important; }
    div[data-testid="stRadio"] label {
        background: #F0F0F5 !important;
        border: none !important;
        border-radius: 14px !important;
        padding: 10px 28px !important;
        font-size: 1rem !important;
        font-weight: 800 !important;
        color: #000 !important;
        cursor: pointer;
        transition: background .12s ease;
    }
    div[data-testid="stRadio"] label:hover { background: #E8E4FF !important; }
    div[data-testid="stRadio"] input[type="radio"] { display: none !important; }
    div[data-testid="stRadio"] div[data-baseweb="radio"] > div:first-child { display: none !important; }

    /* ─── טאבים ─── */
    .stTabs [data-baseweb="tab-list"] { gap: 6px; justify-content: center; background: transparent !important; }
    .stTabs [data-baseweb="tab"] {
        background: #EFEFEF !important; border-radius: 14px !important;
        padding: 10px 24px !important; border: none !important;
        font-size: 0.95rem !important; font-weight: 700 !important;
        color: #8A8A93 !important; min-width: 130px; text-align: center;
    }
    .stTabs [data-baseweb="tab"] p,
    .stTabs [data-baseweb="tab"] span,
    .stTabs [data-baseweb="tab"] div { color: #8A8A93 !important; }
    .stTabs [aria-selected="true"] {
        background: #000 !important; color: #fff !important;
    }
    .stTabs [aria-selected="true"] p,
    .stTabs [aria-selected="true"] span,
    .stTabs [aria-selected="true"] div { color: #fff !important; }

    /* ─── expander ─── */
    .streamlit-expanderHeader {
        background: #F0F0F5 !important;
        border-radius: 14px !important;
        font-weight: 700 !important; color: #000 !important;
        border: none !important;
    }
    .streamlit-expanderContent {
        background: #F7F7F9 !important;
        border: none !important;
    }

    /* ─── checkbox ─── */
    .stCheckbox label { color: #000 !important; font-weight: 700 !important; font-size: 0.95rem !important; }
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
    return f"₪{x:,.0f}"


# ─────────────────────────────────────────────
# מסך התחברות / הרשמה
# ─────────────────────────────────────────────
def render_auth_screen(authenticator):
    st.markdown(
        "<div style='height:40px'></div>"
        "<p style='text-align:center;font-size:12px;font-weight:700;letter-spacing:3px;"
        "color:#8A8A93;text-transform:uppercase;margin-bottom:4px;'>CHECK MANAGEMENT</p>"
        "<h1 style='text-align:center;font-family:Inter,sans-serif;font-weight:900;"
        "font-size:3rem;letter-spacing:-2px;color:#000;line-height:1;margin-bottom:4px;'>"
        "CHECKFLOW</h1>"
        "<p style='text-align:center;color:#8A8A93;font-size:0.9rem;"
        "font-weight:500;margin-bottom:24px;'>ניהול צ׳קים ופריטה</p>",
        unsafe_allow_html=True,
    )

    tab_login, tab_register = st.tabs(["🔑  כניסה", "📝  הרשמה"])

    with tab_login:
        authenticator.login(location="main")
        status = st.session_state.get("authentication_status")
        if status is False:
            st.error("שם משתמש או סיסמה שגויים ❌")
        elif status is None:
            st.info("אנא הכנס שם משתמש וסיסמה")

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
        "<div style='height:40px'></div>"
        "<p style='text-align:center;font-size:12px;font-weight:700;letter-spacing:3px;"
        "color:#8A8A93;text-transform:uppercase;margin-bottom:4px;'>CHECK MANAGEMENT</p>"
        "<h1 style='text-align:center;font-family:Inter,sans-serif;font-weight:900;"
        "font-size:3rem;letter-spacing:-2px;color:#000;line-height:1;margin-bottom:4px;'>"
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
    st.markdown('</div><div style="height:14px"></div>', unsafe_allow_html=True)

    st.markdown('<div class="home-nav-btn home-nav-pink">', unsafe_allow_html=True)
    if st.button("📋  ניהול צ׳קים", key="go_mgmt", use_container_width=True):
        st.session_state.screen = "mgmt"
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
def render_add_check_form():
    clients = get_clients()
    st.markdown('<div class="add-check-wrapper">', unsafe_allow_html=True)
    if st.button("➕  הוספת צ'ק חדש", use_container_width=True, key="open_add_form"):
        st.session_state.add_form_open = not st.session_state.get("add_form_open", False)
    st.markdown('</div>', unsafe_allow_html=True)

    if not st.session_state.get("add_form_open", False):
        return

    names = [c["name"] for c in clients]
    col_a, _ = st.columns([2, 1])
    with col_a:
        sel = st.selectbox("לקוח", ["— חדש —"] + names, key="add_client_sel")
    new_name = st.text_input("שם לקוח חדש", key="new_client_name") if sel == "— חדש —" else None

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

    if st.button("💾  שמירת צ'ק", use_container_width=True, key="save_check"):
        cid = add_client(new_name or "") if sel == "— חדש —" else \
              next((c["id"] for c in clients if c["name"] == sel), None)
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
# רשימת לקוחות
# ─────────────────────────────────────────────
def render_clients():
    st.markdown('<div class="section-title">הלקוחות שלי</div>', unsafe_allow_html=True)
    st.markdown('<div class="neon-bar"></div>', unsafe_allow_html=True)

    rows = [r for r in get_client_obligo() if r["cnt"] > 0]
    if not rows:
        st.markdown('<div class="glass">אין עדיין צ\'קים ⬆️</div>', unsafe_allow_html=True)
        return

    for r in rows:
        st.markdown(f"""
        <div class="client-card">
            <div>
                <div class="client-name">{r['name']}</div>
                <div style="font-size:.82rem;color:#9aa3b2;">{r['cnt']} צ'קים</div>
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
                        <span style="font-size:.8rem;color:#9aa3b2;">
                            פירעון: {ch['due_date']}{remind_str}</span>
                        <span class="pill" style="background:{color}22;color:{color};
                            border:1px solid {color}66;">{ch['status']}</span>
                    </div>""", unsafe_allow_html=True)
                with cc2:
                    new_st = st.selectbox("סטטוס", STATUSES,
                                          index=STATUSES.index(ch["status"]),
                                          key=f"st_{ch['id']}", label_visibility="collapsed")
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
        f"<div style='background:#E8F5A3;border-radius:22px;padding:16px;text-align:center;margin:6px 0 10px;'>"
        f"<span style='font-size:11px;font-weight:700;letter-spacing:1.2px;color:#5A6800;"
        f"text-transform:uppercase;display:block;margin-bottom:2px;'>ימי זיכוי</span>"
        f"<span style='font-family:Inter,sans-serif;font-size:2.4rem;font-weight:900;"
        f"color:#000;letter-spacing:-1.5px;'>{days}</span>"
        f"<span style='font-size:0.9rem;font-weight:600;color:#5A6800;'> ימים</span></div>",
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
            f"<div style='background:#FFF3C8;border-radius:22px;padding:16px;text-align:center;margin-bottom:0;'>"
            f"<span style='font-size:11px;font-weight:700;letter-spacing:1.2px;color:#8A6A00;"
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
        st.markdown("<div style='background:#FFE8D6;border-radius:16px;padding:12px;"
                    "text-align:center;font-size:13px;font-weight:700;color:#8A3A00;"
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

    # אם אין משתמשים בכלל — מסך הרשמה בלבד
    with closing(get_conn()) as conn:
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    auth_status = st.session_state.get("authentication_status")

    if auth_status is not True:
        render_auth_screen(authenticator)
        return

    # מחובר
    st.session_state.current_user = st.session_state.get("username", "admin")

    # כפתור התנתקות בסיידבר
    with st.sidebar:
        st.markdown(f"👤 **{st.session_state.get('name', '')}**")
        authenticator.logout("התנתק 🚪")

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
        render_add_check_form()
        render_clients()


if __name__ == "__main__":
    main()
