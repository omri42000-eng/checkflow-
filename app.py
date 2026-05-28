# -*- coding: utf-8 -*-
"""
ניהול אובליגו ומחשבון פריטת צ'קים — MVP לעצמאים
Streamlit Web App (Mobile-first)
עיצוב: Dark cyberpunk / glassmorphism / neon
"""

import sqlite3
from datetime import date, datetime
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


# ----------------------------------------------------------------------------
# שכבת נתונים (SQLite)
# ----------------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with closing(get_conn()) as conn, conn:
        # טבלת משתמשים
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                password TEXT NOT NULL,
                email TEXT NOT NULL
            )
        """)
        # טבלת לקוחות קשורה למשתמש
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
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
                FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE
            )
        """)

def add_client(name):
    name = name.strip()
    username = st.session_state.get("current_user", "admin")
    if not name:
        return None
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT OR IGNORE INTO clients (name, username) VALUES (?, ?)", (name, username)
        )
        row = conn.execute(
            "SELECT id FROM clients WHERE name = ? AND username = ?", (name, username)
        ).fetchone()
        return row["id"] if row else None

def get_clients():
    username = st.session_state.get("current_user", "admin")
    with closing(get_conn()) as conn:
        return conn.execute(
            "SELECT id, name FROM clients WHERE username = ? ORDER BY name", (username,)
        ).fetchall()


def add_check(client_id, amount, due_date, status, remind_on):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """INSERT INTO checks (client_id, amount, due_date, status, remind_on)
               VALUES (?, ?, ?, ?, ?)""",
            (client_id, amount, due_date.isoformat(), status,
             remind_on.isoformat() if remind_on else None),
        )


def get_checks(client_id=None):
    username = st.session_state.get("current_user", "admin")
    q = """SELECT ch.*, cl.name AS client_name
           FROM checks ch 
           JOIN clients cl ON cl.id = ch.client_id 
           WHERE cl.username = ?"""
    params = [username]
    
    if client_id is not None:
        q += " AND ch.client_id = ?"
        params.append(client_id)
        
    q += " ORDER BY ch.due_date"
    with closing(get_conn()) as conn:
        return conn.execute(q, params).fetchall()


def update_status(check_id, status):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "UPDATE checks SET status = ? WHERE id = ?", (status, check_id)
        )


def delete_check(check_id):
    with closing(get_conn()) as conn, conn:
        conn.execute("DELETE FROM checks WHERE id = ?", (check_id,))


def get_totals():
    username = st.session_state.get("current_user", "admin")
    with closing(get_conn()) as conn:
        row = conn.execute("""
            SELECT COALESCE(SUM(ch.amount),0) AS total, COUNT(ch.id) AS cnt 
            FROM checks ch
            JOIN clients cl ON cl.id = ch.client_id
            WHERE cl.username = ?
        """, (username,)).fetchone()
        return row["total"], row["cnt"]


def get_client_obligo():
    username = st.session_state.get("current_user", "admin")
    with closing(get_conn()) as conn:
        return conn.execute("""
            SELECT cl.id, cl.name,
                   COALESCE(SUM(ch.amount),0) AS obligo,
                   COUNT(ch.id) AS cnt
            FROM clients cl
            LEFT JOIN checks ch ON ch.client_id = cl.id
            WHERE cl.username = ?
            GROUP BY cl.id
            ORDER BY obligo DESC
        """, (username,)).fetchall()


# ----------------------------------------------------------------------------
# CSS
# ----------------------------------------------------------------------------
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
    #MainMenu, header, footer {visibility: hidden;}
    .block-container { padding-top: 1.2rem; padding-bottom: 4rem; max-width: 480px; }

    .glass {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 22px;
        padding: 18px 20px;
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(14px);
        box-shadow: 0 8px 30px rgba(0,0,0,0.45);
        margin-bottom: 14px;
    }

    /* KPI */
    .kpi {
        position: relative;
        background: linear-gradient(145deg, rgba(57,255,20,0.06), rgba(255,45,149,0.05));
        border: 1.5px solid rgba(57,255,20,0.45);
        border-radius: 26px;
        padding: 22px 24px;
        box-shadow: 0 0 24px rgba(57,255,20,0.25), inset 0 0 24px rgba(57,255,20,0.06);
        margin-bottom: 18px;
        overflow: hidden;
        text-align: center;
    }
    .kpi-label { font-size: 0.85rem; color: #9aa3b2; letter-spacing: 1px; }
    .kpi-value {
        font-family: 'Orbitron', sans-serif;
        font-size: 2.6rem; font-weight: 800; line-height: 1.1;
        color: #eafff0;
        text-shadow: 0 0 18px rgba(57,255,20,0.55);
        direction: ltr;
        text-align: center;
        display: block;
        width: 100%;
    }
    .kpi-sub { font-size: 0.95rem; color: #c6ccd8; margin-top: 6px; }
    .pill {
        display:inline-block; padding: 3px 12px; border-radius: 999px;
        font-size: 0.78rem; font-weight: 600; margin-inline-start: 6px;
    }

    .section-title {
        font-weight: 800; font-size: 1.15rem; margin: 8px 2px 10px;
        color: #f3f5fa; text-align: center;
    }
    .section-title-right {
        font-weight: 800; font-size: 1.15rem; margin: 8px 2px 10px;
        color: #f3f5fa; text-align: right;
    }
    .neon-bar {
        height: 3px; width: 46px; border-radius: 3px;
        background: linear-gradient(90deg, #39FF14, #FF2D95, #FF9F1C);
        box-shadow: 0 0 12px rgba(255,45,149,0.6); margin-bottom: 14px;
        margin-right: auto; margin-left: auto;
    }
    .neon-bar-right {
        height: 3px; width: 46px; border-radius: 3px;
        background: linear-gradient(90deg, #39FF14, #FF2D95, #FF9F1C);
        box-shadow: 0 0 12px rgba(255,45,149,0.6); margin-bottom: 14px;
        margin-right: 0; margin-left: auto;
    }

    /* כרטיס לקוח */
    .client-card {
        display:flex; justify-content:space-between; align-items:center;
        background: rgba(255,255,255,0.035);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px; padding: 14px 16px; margin-bottom: 10px;
    }
    .client-name { font-weight: 700; font-size: 1.05rem; }
    .client-obligo {
        font-family:'Orbitron',sans-serif; font-weight:700;
        color:#FF9F1C; text-shadow: 0 0 12px rgba(255,159,28,0.5); direction:ltr;
    }

    /* פלט מחשבון */
    .calc-out {
        border-radius: 22px; padding: 18px 20px; margin-top: 8px; text-align:center;
    }
    .calc-out.fee {
        background: linear-gradient(145deg, rgba(255,45,149,0.10), rgba(255,45,149,0.03));
        border: 1.5px solid rgba(255,45,149,0.5);
        box-shadow: 0 0 22px rgba(255,45,149,0.25);
    }
    .calc-out.net {
        background: linear-gradient(145deg, rgba(57,255,20,0.10), rgba(57,255,20,0.03));
        border: 1.5px solid rgba(57,255,20,0.5);
        box-shadow: 0 0 22px rgba(57,255,20,0.3); margin-top:14px;
    }
    .calc-out .lbl { font-size: 0.9rem; color:#aeb5c2; letter-spacing:.5px; }
    .calc-out .big {
        font-family:'Orbitron',sans-serif; font-size:2.4rem; font-weight:800;
        direction:ltr; line-height:1.15;
    }
    .fee .big { color:#ffb3da; text-shadow:0 0 18px rgba(255,45,149,.55); }
    .net .big { color:#c9ffd6; text-shadow:0 0 18px rgba(57,255,20,.6); }

    /* כפתורים כלליים */
    .stButton > button {
        border-radius: 14px; border: 1px solid rgba(255,255,255,0.12);
        background: rgba(255,255,255,0.05); color:#eef1f7; font-weight:700;
        transition: all .15s ease;
    }
    .stButton > button:hover {
        border-color: rgba(57,255,20,0.6);
        box-shadow: 0 0 16px rgba(57,255,20,0.3); color:#fff;
    }

    /* כפתורי מסך הבית הגדולים */
    .home-btn-green > button {
        width: 100% !important;
        height: 140px !important;
        border-radius: 22px !important;
        background: radial-gradient(circle at 35% 35%, rgba(200,255,160,0.2) 0%, rgba(57,255,20,0.15) 40%, rgba(8,50,3,0.6) 90%) !important;
        border: 2px solid rgba(57,255,20,0.5) !important;
        box-shadow: 0 0 24px rgba(57,255,20,0.2) !important;
        color: #e2ffe0 !important;
        font-size: 1.4rem !important;
        font-weight: 800 !important;
    }
    .home-btn-green > button:hover {
        box-shadow: 0 0 40px rgba(57,255,20,0.5) !important;
        border-color: #39FF14 !important;
        transform: scale(1.02);
    }

    .home-btn-pink > button {
        width: 100% !important;
        height: 140px !important;
        border-radius: 22px !important;
        background: radial-gradient(circle at 35% 35%, rgba(255,190,225,0.2) 0%, rgba(255,45,149,0.15) 40%, rgba(55,3,28,0.6) 90%) !important;
        border: 2px solid rgba(255,45,149,0.5) !important;
        box-shadow: 0 0 24px rgba(255,45,149,0.2) !important;
        color: #ffe4f3 !important;
        font-size: 1.4rem !important;
        font-weight: 800 !important;
    }
    .home-btn-pink > button:hover {
        box-shadow: 0 0 40px rgba(255,45,149,0.5) !important;
        border-color: #FF2D95 !important;
        transform: scale(1.02);
    }

    /* כפתור הוספת צ'ק */
    .add-check-wrapper > button {
        border-radius: 50px !important;
        background: linear-gradient(145deg, #e8003a, #c0002e) !important;
        border: none !important;
        color: #fff !important;
        font-size: 1.15rem !important;
        font-weight: 800 !important;
        padding: 14px 0 !important;
        box-shadow: 0 0 22px rgba(232,0,58,0.5) !important;
    }

    /* שדות קלט */
    .stTextInput input, .stNumberInput input, .stDateInput input {
        color: #ffffff !important;
        background-color: rgba(20,22,30,0.92) !important;
        border-radius: 12px !important;
    }
    </style>
    """, unsafe_allow_html=True)


def fmt_ils(x):
    return f"₪{x:,.0f}"


# ----------------------------------------------------------------------------
# מסך ראשי — שני כפתורים מעוצבים נייטיב
# ----------------------------------------------------------------------------
def render_home_screen():
    st.markdown(
        "<div style='height: 40px;'></div>"
        "<h1 style='text-align:center;font-family:Orbitron;font-weight:800;font-size:2.6rem;"
        "background:linear-gradient(90deg,#39FF14,#FF2D95,#FF9F1C);"
        "-webkit-background-clip:text;-webkit-text-fill-color:transparent;"
        "margin-bottom:6px;'>CHECKFLOW</h1>"
        "<p style='text-align:center;color:#9aa3b2;font-size:1rem;margin-bottom:40px;'>"
        "ניהול צ׳קים ופריטה</p>",
        unsafe_allow_html=True,
    )

    # יצירת הניווט באמצעות כפתורי Streamlit תואמי עיצוב הסייברפאנק
    st.markdown('<div class="home-btn-pink">', unsafe_allow_html=True)
    if st.button("📋\n\nניהול צ׳קים", key="nav_mgmt"):
        st.session_state.screen = "mgmt"
        st.rerun()
    st.markdown('</div><div style="height:25px;"></div>', unsafe_allow_html=True)

    st.markdown('<div class="home-btn-green">', unsafe_allow_html=True)
    if st.button("🧮\n\nמחשבון פריטה", key="nav_calc"):
        st.session_state.screen = "calc"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# רכיבי ניהול
# ----------------------------------------------------------------------------
def render_kpi():
    total, cnt = get_totals()
    st.markdown(f"""
    <div class="kpi">
        <div class="kpi-label">סך הצ'קים שביד כרגע</div>
        <div class="kpi-value">{fmt_ils(total)}</div>
        <div class="kpi-sub">{cnt} צ'קים פיזיים בארנק 💸</div>
    </div>
    """, unsafe_allow_html=True)


def render_add_check_form():
    clients = get_clients()

    st.markdown('<div class="add-check-wrapper">', unsafe_allow_html=True)
    if st.button("➕  הוספת צ'ק חדש", use_container_width=True, key="open_add_form"):
        st.session_state.add_form_open = not st.session_state.get("add_form_open", False)
    st.markdown('</div>', unsafe_allow_html=True)

    if not st.session_state.get("add_form_open", False):
        return

    with st.container():
        names = [c["name"] for c in clients]
        col_a, col_b = st.columns([2, 1])
        with col_a:
            sel = st.selectbox("לקוח", ["— חדש —"] + names, key="add_client_sel")
        with col_b:
            st.write("")
        if sel == "— חדש —":
            new_name = st.text_input("שם לקוח חדש", key="new_client_name")
        else:
            new_name = None

        amount = st.number_input("סכום הצ'ק (₪)", min_value=0.0, step=100.0,
                                 format="%.0f", key="add_amount")
        c1, c2 = st.columns(2)
        with c1:
            due = st.date_input("תאריך פירעון", value=date.today(), key="add_due")
        with c2:
            use_remind = st.checkbox("הוסף תזכורת", value=False, key="add_use_remind")

        remind = None
        if use_remind:
            remind = st.date_input("תאריך תזכורת", value=date.today(), key="add_remind")

        status = st.selectbox("סטטוס", STATUSES, key="add_status")

        if st.button("💾  שמירת צ'ק", use_container_width=True, key="save_check"):
            if sel == "— חדש —":
                cid = add_client(new_name or "")
            else:
                cid = next((c["id"] for c in clients if c["name"] == sel), None)
            if not cid:
                st.error("נא לבחור או להזין שם לקוח.")
            elif amount <= 0:
                st.error("נא להזין סכום גדול מאפס.")
            else:
                add_check(cid, amount, due, status, remind)
                st.success("הצ'ק נשמר ✅")
                st.session_state.add_form_open = False
                st.rerun()


def render_clients():
    st.markdown('<div class="section-title">הלקוחות שלי</div>', unsafe_allow_html=True)
    st.markdown('<div class="neon-bar"></div>', unsafe_allow_html=True)

    rows = get_client_obligo()
    rows = [r for r in rows if r["cnt"] > 0]
    if not rows:
        st.markdown('<div class="glass">אין עדיין צ\'קים. הוסף צ\'ק ראשון למעלה ⬆️</div>',
                    unsafe_allow_html=True)
        return

    for r in rows:
        st.markdown(f"""
        <div class="client-card">
            <div>
                <div class="client-name">{r['name']}</div>
                <div style="font-size:.82rem;color:#9aa3b2;">{r['cnt']} צ'קים</div>
            </div>
            <div class="client-obligo">{fmt_ils(r['obligo'])}</div>
        </div>
        """, unsafe_allow_html=True)

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
                    </div>
                    """, unsafe_allow_html=True)
                with cc2:
                    new_st = st.selectbox(
                        "סטטוס", STATUSES,
                        index=STATUSES.index(ch["status"]),
                        key=f"st_{ch['id']}", label_visibility="collapsed",
                    )
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("עדכן", key=f"upd_{ch['id']}",
                                     use_container_width=True):
                            update_status(ch["id"], new_st)
                            st.rerun()
                    with b2:
                        if st.button("🗑️", key=f"del_{ch['id']}",
                                     use_container_width=True):
                            delete_check(ch["id"])
                            st.rerun()


# ----------------------------------------------------------------------------
# מחשבון פריטה
# ----------------------------------------------------------------------------
def render_calculator():
    st.markdown('<div class="section-title-right">מחשבון פריטה (ניכיון)</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="neon-bar-right"></div>', unsafe_allow_html=True)

    if "fixed_rate" not in st.session_state:
        st.session_state.fixed_rate = 12.0
    if "rate_basis" not in st.session_state:
        st.session_state.rate_basis = "שנתית"
    if "rate_edit_open" not in st.session_state:
        st.session_state.rate_edit_open = False

    checks = get_checks()
    options = ["— הזנה ידנית —"] + [
        f"{c['client_name']} | {fmt_ils(c['amount'])} | {c['due_date']}"
        for c in checks
    ]
    pick = st.selectbox("בחר צ'ק קיים (או הזנה ידנית)", options, key="calc_pick")

    default_amount = 10000.0
    default_due = date.today()
    if pick != "— הזנה ידנית —":
        idx = options.index(pick) - 1
        ch = checks[idx]
        default_amount = float(ch["amount"])
        try:
            default_due = datetime.fromisoformat(ch["due_date"]).date()
        except Exception:
            default_due = date.today()

    amount = st.number_input("סכום הצ'ק (₪)", min_value=0.0, step=100.0,
                             value=default_amount, format="%.0f", key="calc_amount")

    if st.session_state.get("_last_pick") != pick:
        st.session_state.calc_due = default_due
        st.session_state._last_pick = pick

    due_date = st.date_input(
        "תאריך פירעון הצ'ק", key="calc_due",
        help="החישוב מתחיל ממחר וכולל את יום הפירעון עצמו",
    )

    days = max((due_date - date.today()).days + 1, 0)

    st.markdown(
        f"<div style='text-align:center;margin:4px 0 12px;'>"
        f"<span style='font-size:.85rem;color:#9aa3b2;'>ימי זיכוי שחושבו</span><br>"
        f"<span style='font-family:Orbitron;font-size:2rem;font-weight:800;"
        f"color:#39FF14;text-shadow:0 0 14px rgba(57,255,20,.5);'>{days}</span>"
        f"<span style='font-size:.9rem;color:#9aa3b2;'> ימים</span></div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div style='text-align:center;font-weight:800;font-size:1.05rem;"
        "color:#f3f5fa;margin-bottom:6px;'>סוג הריבית</div>",
        unsafe_allow_html=True,
    )
    basis = st.radio(
        "סוג הריבית", ["חודשית", "שנתית"],
        index=["חודשית", "שנתית"].index(st.session_state.rate_basis),
        horizontal=True, key="basis_radio", label_visibility="collapsed",
    )
    st.session_state.rate_basis = basis

    rate_val = st.session_state.fixed_rate

    r1, r2 = st.columns([2, 1])
    with r1:
        st.markdown(
            f"<div class='glass' style='margin-bottom:0;padding:14px 16px;text-align:center;'>"
            f"<span style='font-size:.82rem;color:#9aa3b2;'>ריבית קבועה ({basis})</span><br>"
            f"<span style='font-family:Orbitron;font-size:1.8rem;font-weight:800;"
            f"color:#FF9F1C;text-shadow:0 0 12px rgba(255,159,28,.5);'>"
            f"{rate_val:.2f}%</span></div>",
            unsafe_allow_html=True,
        )
    with r2:
        st.write("")
        st.write("")
        if st.button("✏️ שינוי ריבית", use_container_width=True, key="edit_rate"):
            st.session_state.rate_edit_open = not st.session_state.rate_edit_open

    if st.session_state.rate_edit_open:
        new_rate = st.number_input(
            "הזן ריבית (%)",
            min_value=0.0, max_value=100.0,
            value=float(st.session_state.fixed_rate),
            step=0.1, format="%.2f",
            key="rate_input_manual",
        )
        if st.button("💾 שמירת הריבית", use_container_width=True, key="save_rate"):
            st.session_state.fixed_rate = new_rate
            st.session_state.rate_edit_open = False
            st.rerun()

    if basis == "חודשית":
        fee = amount * (rate_val / 100.0) * (days / 30.0)
    else:
        fee = amount * (rate_val / 100.0) * (days / 365.0)
    net = amount - fee

    if days <= 0:
        st.markdown(
            "<div style='text-align:center;color:#FF9F1C;font-size:.9rem;"
            "margin:10px 0 0;'>⚠️ תאריך הפירעון עבר — אין ימי זיכוי.</div>",
            unsafe_allow_html=True,
        )

    st.markdown(f"""
    <div class="calc-out fee">
        <div class="lbl">סך העמלה שיורדת</div>
        <div class="big">{fmt_ils(fee)}</div>
    </div>
    <div class="calc-out net">
        <div class="lbl">נטו מזומן שמתקבל</div>
        <div class="big">{fmt_ils(net)}</div>
    </div>
    """, unsafe_allow_html=True)


def render_back_button():
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)
    st.markdown('<div class="back-btn">', unsafe_allow_html=True)
    if st.button("← חזרה למסך הראשי", key="back_home", use_container_width=False):
        st.session_state.screen = "home"
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# אימות משתמשים (Authentication Layer)
# ----------------------------------------------------------------------------
def get_all_users_for_auth():
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT username, name, password, email FROM users").fetchall()
        credentials = {"usernames": {}}
        for r in rows:
            credentials["usernames"][r["username"]] = {
                "name": r["name"],
                "password": r["password"],
                "email": r["email"]
            }
        return credentials

def register_new_user(authenticator):
    """מנגנון הרשמה חסין לחלוטין - ללא שימוש ברכיבים פנימיים של הספרייה"""
    try:
        # הצגת טופס הרישום ללא קאפצ'ה
        result = authenticator.register_user(location='main', captcha=False)
        
        if result:
            # ברגע שהרישום מצליח, הנתונים של המשתמש החדש נשמרים אוטומטית 
            # בתוך ה-session_state של האפליקציה. נשלוף אותם ישירות משם!
            
            # נמצא את שם המשתמש שנרשם (הספרייה שומרת את כולם במילון credentials)
            # בגרסאות החדשות אפשר לגשת לזה דרך המבנה הראשי של ה-auth שהזנו בהתחלה
            usernames_dict = authenticator.credentials.get('usernames', {})
            
            if usernames_dict:
                # לוקחים את המשתמש האחרון שהתווסף
                new_username = list(usernames_dict.keys())[-1]
                user_data = usernames_dict[new_username]
                
                username = new_username
                name = user_data.get('name', '')
                hashed_password = user_data.get('password', '')
                email = user_data.get('email', '')
                
                # שמירה בטוחה במסד הנתונים של ה-SQLite שלך
                with closing(get_conn()) as conn, conn:
                    conn.execute(
                        "INSERT OR IGNORE INTO users (username, name, password, email) VALUES (?, ?, ?, ?)",
                        (username, name, hashed_password, email)
                    )
                st.success('נרשמת בהצלחה! כעת ניתן להסיר את ה-V מההרשמה ולהתחבר.')
                st.rerun()
            else:
                st.error("הרישום הצליח אך לא ניתן היה לקרוא את הנתונים השמורים. נסה להתחבר.")
                
    except Exception as e:
        st.error(f'שגיאה בהרשמה: {e}')
# ----------------------------------------------------------------------------
# Main (פונקציית הניהול המרכזית המאוחדת)
# ----------------------------------------------------------------------------
def main():
    init_db()
    inject_css()

    # 1. טעינת המשתמשים
    credentials = get_all_users_for_auth()

    # 2. אתחול ה-Authenticator
    authenticator = stauth.Authenticate(
        credentials,
        cookie_name='checkflow_cookie',
        key='some_signature_key',
        cookie_expiry_days=30
    )

    # 3. מסך כניסה בגרסה החדשה (מחזיר סטטוס, והוא מעדכן אוטומטית גם את session_state)
    authentication_status = authenticator.login(location='main')

    # 4. בדיקת סטטוס החיבור בדיוק לפי המשתנים המעודכנים
    if st.session_state.get("authentication_status") == False:
        st.error('שם המשתמש או הסיסמה שגויים.')
        if st.checkbox("אין לך חשבון? הירשם כאן", key="reg_cb_fail"):
            register_new_user(authenticator)
            
    elif st.session_state.get("authentication_status") is None:
        st.warning('אנא התחבר כדי לצפות בנתונים.')
        if st.checkbox("אין לך חשבון? הירשם כאן", key="reg_cb_none"):
            register_new_user(authenticator)

    elif st.session_state.get("authentication_status"):
        # שמירת שם המשתמש שהתחבר בהצלחה לתוך הסשן שלנו
        st.session_state.current_user = st.session_state.get("username")
        
        # יצירת כפתור התנתקות קטן ומעוצב בסיידבר
        authenticator.logout('התנתק', 'sidebar')
        
        # ניהול מסכי האפליקציה הרגילים שלך
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
            render_add_check_form()
            render_clients()


if __name__ == "__main__":
    main()
