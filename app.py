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
    @import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;600;800;900&family=Orbitron:wght@600;800&display=swap');

    html, body, [class*="css"] { direction: rtl; }
    .stApp {
        background:
            radial-gradient(1200px 600px at 80% -10%, rgba(255,45,149,0.10), transparent 60%),
            radial-gradient(1000px 500px at -10% 20%, rgba(57,255,20,0.08), transparent 55%),
            radial-gradient(900px 500px at 50% 120%, rgba(255,159,28,0.10), transparent 60%),
            #0c0d12;
        font-family: 'Heebo', sans-serif;
        color: #e8ebf2;
    }
    #MainMenu, header, footer { visibility: hidden; }
    .block-container { padding-top: 1.2rem; padding-bottom: 4rem; max-width: 480px; }

    .glass {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 22px; padding: 18px 20px;
        backdrop-filter: blur(14px);
        box-shadow: 0 8px 30px rgba(0,0,0,0.45);
        margin-bottom: 14px;
    }

    /* KPI */
    .kpi {
        background: linear-gradient(145deg, rgba(57,255,20,0.06), rgba(255,45,149,0.05));
        border: 1.5px solid rgba(57,255,20,0.45);
        border-radius: 26px; padding: 22px 24px;
        box-shadow: 0 0 24px rgba(57,255,20,0.25), inset 0 0 24px rgba(57,255,20,0.06);
        margin-bottom: 18px; text-align: center;
    }
    .kpi-label { font-size: 0.85rem; color: #9aa3b2; letter-spacing: 1px; }
    .kpi-value {
        font-family: 'Orbitron', sans-serif; font-size: 2.6rem; font-weight: 800;
        color: #eafff0; text-shadow: 0 0 18px rgba(57,255,20,0.55);
        direction: ltr; text-align: center; display: block; width: 100%;
    }
    .kpi-sub { font-size: 0.95rem; color: #c6ccd8; margin-top: 6px; }
    .pill {
        display:inline-block; padding: 3px 12px; border-radius: 999px;
        font-size: 0.78rem; font-weight: 600; margin-inline-start: 6px;
    }

    .section-title { font-weight:800; font-size:1.15rem; margin:8px 2px 10px; color:#f3f5fa; text-align:center; }
    .section-title-right { font-weight:800; font-size:1.15rem; margin:8px 2px 10px; color:#f3f5fa; text-align:right; }
    .neon-bar {
        height:3px; width:46px; border-radius:3px;
        background:linear-gradient(90deg,#39FF14,#FF2D95,#FF9F1C);
        box-shadow:0 0 12px rgba(255,45,149,0.6); margin:0 auto 14px;
    }
    .neon-bar-right {
        height:3px; width:46px; border-radius:3px;
        background:linear-gradient(90deg,#39FF14,#FF2D95,#FF9F1C);
        box-shadow:0 0 12px rgba(255,45,149,0.6); margin:0 0 14px auto;
    }

    .client-card {
        display:flex; justify-content:space-between; align-items:center;
        background:rgba(255,255,255,0.035); border:1px solid rgba(255,255,255,0.08);
        border-radius:18px; padding:14px 16px; margin-bottom:10px;
    }
    .client-name { font-weight:700; font-size:1.05rem; }
    .client-obligo {
        font-family:'Orbitron',sans-serif; font-weight:700;
        color:#FF9F1C; text-shadow:0 0 12px rgba(255,159,28,0.5); direction:ltr;
    }

    .calc-out { border-radius:22px; padding:18px 20px; margin-top:8px; text-align:center; }
    .calc-out.fee {
        background:linear-gradient(145deg,rgba(255,45,149,0.10),rgba(255,45,149,0.03));
        border:1.5px solid rgba(255,45,149,0.5); box-shadow:0 0 22px rgba(255,45,149,0.25);
    }
    .calc-out.net {
        background:linear-gradient(145deg,rgba(57,255,20,0.10),rgba(57,255,20,0.03));
        border:1.5px solid rgba(57,255,20,0.5); box-shadow:0 0 22px rgba(57,255,20,0.3); margin-top:14px;
    }
    .calc-out .lbl { font-size:0.9rem; color:#aeb5c2; letter-spacing:.5px; }
    .calc-out .big { font-family:'Orbitron',sans-serif; font-size:2.4rem; font-weight:800; direction:ltr; line-height:1.15; }
    .fee .big { color:#ffb3da; text-shadow:0 0 18px rgba(255,45,149,.55); }
    .net .big { color:#c9ffd6; text-shadow:0 0 18px rgba(57,255,20,.6); }

    /* כפתורים כלליים */
    .stButton > button {
        border-radius:14px; border:1px solid rgba(255,255,255,0.12);
        background:rgba(255,255,255,0.05); color:#eef1f7; font-weight:700;
        transition:all .15s ease;
    }
    .stButton > button:hover {
        border-color:rgba(57,255,20,0.6);
        box-shadow:0 0 16px rgba(57,255,20,0.3); color:#fff;
    }

    /* כפתורי ניווט מסך הבית */
    .home-nav-btn .stButton > button {
        border-radius:22px !important; font-size:1.3rem !important;
        font-weight:800 !important; min-height:80px !important;
        height:auto !important; padding:22px 24px !important;
        transition:transform .15s ease, box-shadow .15s ease !important;
    }
    .home-nav-btn .stButton > button:hover { transform:scale(1.02) !important; }
    .home-nav-green .stButton > button {
        background:linear-gradient(145deg,rgba(57,255,20,0.06),rgba(255,45,149,0.05)) !important;
        border:1.5px solid rgba(57,255,20,0.55) !important;
        box-shadow:0 0 24px rgba(57,255,20,0.3),inset 0 0 24px rgba(57,255,20,0.06) !important;
        color:#eafff0 !important; text-shadow:0 0 14px rgba(57,255,20,0.4) !important;
    }
    .home-nav-green .stButton > button:hover {
        border-color:rgba(57,255,20,0.85) !important;
        box-shadow:0 0 38px rgba(57,255,20,0.5),inset 0 0 28px rgba(57,255,20,0.10) !important;
    }
    .home-nav-pink .stButton > button {
        background:linear-gradient(145deg,rgba(255,45,149,0.07),rgba(57,255,20,0.04)) !important;
        border:1.5px solid rgba(255,45,149,0.55) !important;
        box-shadow:0 0 24px rgba(255,45,149,0.3),inset 0 0 24px rgba(255,45,149,0.06) !important;
        color:#ffe4f3 !important; text-shadow:0 0 14px rgba(255,45,149,0.4) !important;
    }
    .home-nav-pink .stButton > button:hover {
        border-color:rgba(255,45,149,0.85) !important;
        box-shadow:0 0 38px rgba(255,45,149,0.5),inset 0 0 28px rgba(255,45,149,0.10) !important;
    }

    /* כפתור הוספת צ'ק */
    .add-check-wrapper .stButton > button {
        border-radius:50px !important;
        background:linear-gradient(145deg,#e8003a,#c0002e) !important;
        border:none !important; color:#fff !important;
        font-size:1.15rem !important; font-weight:800 !important;
        padding:14px 0 !important; box-shadow:0 0 22px rgba(232,0,58,0.5) !important;
    }

    /* כפתור חזרה */
    .back-btn { display:inline-block; margin-bottom:8px; }
    .back-btn .stButton > button {
        border-radius:20px !important; background:rgba(255,255,255,0.06) !important;
        border:1px solid rgba(255,255,255,0.14) !important; color:#9aa3b2 !important;
        font-size:0.82rem !important; font-weight:600 !important;
        padding:4px 14px !important; height:auto !important;
        min-height:0 !important; line-height:1.6 !important;
    }

    /* שדות קלט */
    .stTextInput input, .stNumberInput input, .stDateInput input,
    [data-baseweb="input"] input, [data-baseweb="base-input"] input {
        color:#ffffff !important; background-color:rgba(20,22,30,0.92) !important;
        -webkit-text-fill-color:#ffffff !important; caret-color:#39FF14 !important;
        border-radius:12px !important; direction:ltr !important; text-align:right !important;
    }
    .stTextInput div[data-baseweb="input"],
    .stNumberInput div[data-baseweb="input"],
    .stDateInput div[data-baseweb="input"],
    div[data-baseweb="select"] > div {
        background-color:rgba(20,22,30,0.92) !important;
        border:1px solid rgba(255,255,255,0.18) !important; border-radius:12px !important;
    }
    div[data-baseweb="select"] div { color:#ffffff !important; }
    input::placeholder { color:#8b93a3 !important; opacity:1 !important; }
    ul[role="listbox"], div[data-baseweb="popover"] { background-color:#14161e !important; }
    ul[role="listbox"] li { color:#eef1f7 !important; }
    label { color:#c6ccd8 !important; font-weight:600 !important; }

    /* רדיו ריבית */
    div[data-testid="stRadio"] > div { gap:16px !important; justify-content:center !important; }
    div[data-testid="stRadio"] label {
        background:rgba(255,255,255,0.06) !important;
        border:1.5px solid rgba(255,255,255,0.2) !important;
        border-radius:14px !important; padding:10px 28px !important;
        font-size:1.05rem !important; font-weight:800 !important;
        color:#d0d6e2 !important; cursor:pointer; transition:all .15s ease;
    }
    div[data-testid="stRadio"] label:hover {
        background:rgba(57,255,20,0.10) !important;
        border-color:rgba(57,255,20,0.5) !important;
    }
    div[data-testid="stRadio"] input[type="radio"] { display:none !important; }
    div[data-testid="stRadio"] div[data-baseweb="radio"] > div:first-child { display:none !important; }

    /* טאבים */
    .stTabs [data-baseweb="tab-list"] { gap:8px; justify-content:center; }
    .stTabs [data-baseweb="tab"] {
        background:rgba(255,255,255,0.07); border-radius:16px; padding:12px 28px;
        border:1.5px solid rgba(255,255,255,0.15); font-size:1rem;
        font-weight:700; color:#d0d6e2 !important; min-width:140px; text-align:center;
    }
    .stTabs [aria-selected="true"] {
        background:linear-gradient(145deg,rgba(57,255,20,0.18),rgba(255,45,149,0.14));
        border-color:rgba(57,255,20,0.6); color:#ffffff !important;
    }

    /* מסך התחברות */
    .auth-box {
        background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.10);
        border-radius:26px; padding:28px 24px; margin-top:20px;
        box-shadow:0 8px 40px rgba(0,0,0,0.5);
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
    return f"₪{x:,.0f}"


# ─────────────────────────────────────────────
# מסך התחברות / הרשמה
# ─────────────────────────────────────────────
def render_auth_screen(authenticator):
    st.markdown(
        "<div style='height:40px'></div>"
        "<h1 style='text-align:center;font-family:Orbitron;font-weight:800;font-size:2.2rem;"
        "background:linear-gradient(90deg,#39FF14,#FF2D95,#FF9F1C);"
        "-webkit-background-clip:text;-webkit-text-fill-color:transparent;'>"
        "CHECKFLOW</h1>"
        "<p style='text-align:center;color:#9aa3b2;margin-bottom:24px;'>ניהול צ׳קים ופריטה</p>",
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
        "<div style='height:55px'></div>"
        "<h1 style='text-align:center;font-family:Orbitron;font-weight:800;font-size:2.2rem;"
        "background:linear-gradient(90deg,#39FF14,#FF2D95,#FF9F1C);"
        "-webkit-background-clip:text;-webkit-text-fill-color:transparent;"
        "margin-bottom:6px;'>CHECKFLOW</h1>"
        "<p style='text-align:center;color:#9aa3b2;font-size:1rem;margin-bottom:30px;'>"
        "ניהול צ׳קים ופריטה</p>",
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

    amount = st.number_input("סכום הצ'ק (₪)", min_value=0.0, step=100.0,
                             value=default_amount, format="%.0f", key="calc_amount")

    if st.session_state.get("_last_pick") != pick:
        st.session_state.calc_due  = default_due
        st.session_state._last_pick = pick

    due_date = st.date_input("תאריך פירעון הצ'ק", key="calc_due",
                             min_value=date.today(),
                             help="החישוב מתחיל ממחר וכולל את יום הפירעון")

    days = max((due_date - date.today()).days + 1, 0)
    st.markdown(
        f"<div style='text-align:center;margin:4px 0 12px;'>"
        f"<span style='font-size:.85rem;color:#9aa3b2;'>ימי זיכוי</span><br>"
        f"<span style='font-family:Orbitron;font-size:2rem;font-weight:800;"
        f"color:#39FF14;text-shadow:0 0 14px rgba(57,255,20,.5);'>{days}</span>"
        f"<span style='font-size:.9rem;color:#9aa3b2;'> ימים</span></div>",
        unsafe_allow_html=True)

    st.markdown("<div style='text-align:center;font-weight:800;font-size:1.05rem;"
                "color:#f3f5fa;margin-bottom:6px;'>סוג הריבית</div>", unsafe_allow_html=True)
    basis = st.radio("סוג הריבית", ["חודשית", "שנתית"],
                     index=["חודשית", "שנתית"].index(st.session_state.rate_basis),
                     horizontal=True, key="basis_radio", label_visibility="collapsed")
    st.session_state.rate_basis = basis

    rate_val = st.session_state.fixed_rate
    r1, r2 = st.columns([2, 1])
    with r1:
        st.markdown(
            f"<div class='glass' style='margin-bottom:0;padding:14px 16px;text-align:center;'>"
            f"<span style='font-size:.82rem;color:#9aa3b2;'>ריבית קבועה ({basis})</span><br>"
            f"<span style='font-family:Orbitron;font-size:1.8rem;font-weight:800;"
            f"color:#FF9F1C;text-shadow:0 0 12px rgba(255,159,28,.5);'>{rate_val:.2f}%</span>"
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
        st.markdown("<div style='text-align:center;color:#FF9F1C;font-size:.9rem;"
                    "margin:10px 0 0;'>⚠️ תאריך הפירעון עבר — אין ימי זיכוי.</div>",
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
