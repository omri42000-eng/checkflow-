# -*- coding: utf-8 -*-
"""
CHECK-ME — ניהול צ'קים ופריטה
Streamlit Web App — Mobile-first + Auth + Biometric
Aurora Glassmorphism UI + BI & Risk Management
"""

import sqlite3, json
from datetime import date, datetime, timedelta
from contextlib import closing

import streamlit as st
import streamlit_authenticator as stauth

st.set_page_config(
    page_title="CHECK-ME | ניהול צ'קים",
    page_icon="💳",
    layout="centered",
    initial_sidebar_state="collapsed",
)

DB_PATH = "checks.db"

STATUSES     = ["ממתין למזומן", "להפקדה", "בפריטה"]
STATUSES_ALL = ["ממתין למזומן", "להפקדה", "בפריטה", "חזר"]

STATUS_COLORS = {
    "ממתין למזומן": "#E8B890",
    "להפקדה":       "#40C8FF",
    "בפריטה":       "#FF6B9D",
    "חזר":          "#FF4444",
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


# ═══════════════════════════════════════════
# DB
# ═══════════════════════════════════════════
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_conn()) as conn, conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username                TEXT PRIMARY KEY,
                name                    TEXT NOT NULL,
                password                TEXT NOT NULL,
                email                   TEXT NOT NULL,
                webauthn_credential_id  TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                name                   TEXT NOT NULL,
                username               TEXT NOT NULL DEFAULT 'admin',
                total_returned_checks  INTEGER NOT NULL DEFAULT 0,
                total_late_payments    INTEGER NOT NULL DEFAULT 0,
                total_successful_deals INTEGER NOT NULL DEFAULT 0,
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

        # ── Migrations ──
        # Each entry: (table, column, full DDL fragment after ADD COLUMN)
        _migrations = [
            ("users",   "webauthn_credential_id", "TEXT"),                        # nullable — no NOT NULL
            ("clients", "username",               "TEXT NOT NULL DEFAULT 'admin'"),
            ("clients", "total_returned_checks",  "INTEGER NOT NULL DEFAULT 0"),
            ("clients", "total_late_payments",    "INTEGER NOT NULL DEFAULT 0"),
            ("clients", "total_successful_deals", "INTEGER NOT NULL DEFAULT 0"),
        ]
        for table, col, ddl in _migrations:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if col not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")

        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_name_user ON clients(name, username)"
            )
        except Exception:
            pass


# ─── Credit Score ────────────────────────────
def calc_credit_score(returned: int, late: int, successful: int) -> int:
    score = 100 - returned * 25 - late * 10 + (successful // 5) * 5
    return max(0, min(100, int(score)))

def score_to_stars(score: int) -> int:
    return max(1, min(5, (score + 19) // 20))

def score_to_color(score: int) -> str:
    if score >= 80: return "#4DDC96"
    if score >= 60: return "#FFD060"
    return "#FF5555"

def render_stars(score: int) -> str:
    stars = score_to_stars(score)
    c = score_to_color(score)
    return (f"<span style='color:{c};font-size:.95rem;letter-spacing:1px;'>{'★'*stars}</span>"
            f"<span style='color:rgba(255,255,255,0.18);font-size:.95rem;'>{'☆'*(5-stars)}</span>")


# ─── Users ───────────────────────────────────
def current_user():
    return st.session_state.get("current_user", "admin")

def get_all_users_for_auth():
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT username,name,password,email FROM users").fetchall()
    creds = {"usernames": {}}
    for r in rows:
        creds["usernames"][r["username"]] = {
            "name": r["name"], "password": r["password"], "email": r["email"]
        }
    return creds

def do_login(username, password):
    username = username.strip()
    with closing(get_conn()) as conn:
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not user:
        return False, "שם משתמש לא קיים"
    if stauth.Hasher().check_pw(password, user["password"]):
        st.session_state.update({"authentication_status": True,
                                  "username": user["username"], "name": user["name"]})
        return True, ""
    return False, "סיסמה שגויה"


# ─── WebAuthn ────────────────────────────────
def store_webauthn_credential(username: str, cred_id: str):
    with closing(get_conn()) as conn, conn:
        conn.execute("UPDATE users SET webauthn_credential_id=? WHERE username=?",
                     (cred_id, username))

def get_webauthn_cred_map() -> dict:
    """Returns {username: credential_id_b64} for all users who enrolled biometrics."""
    with closing(get_conn()) as conn:
        rows = conn.execute(
            "SELECT username,webauthn_credential_id FROM users "
            "WHERE webauthn_credential_id IS NOT NULL"
        ).fetchall()
    return {r["username"]: r["webauthn_credential_id"] for r in rows}

def get_user_by_webauthn_cred(cred_id: str):
    with closing(get_conn()) as conn:
        return conn.execute(
            "SELECT username,name FROM users WHERE webauthn_credential_id=?", (cred_id,)
        ).fetchone()

def current_user_has_webauthn() -> bool:
    uname = st.session_state.get("username", "")
    if not uname:
        return False
    with closing(get_conn()) as conn:
        row = conn.execute(
            "SELECT webauthn_credential_id FROM users WHERE username=?", (uname,)
        ).fetchone()
    return bool(row and row["webauthn_credential_id"])


# ─── Clients ─────────────────────────────────
def add_client(name):
    name = name.strip()
    if not name: return None
    u = current_user()
    with closing(get_conn()) as conn, conn:
        conn.execute("INSERT OR IGNORE INTO clients (name,username) VALUES (?,?)", (name, u))
        row = conn.execute("SELECT id FROM clients WHERE name=? AND username=?", (name, u)).fetchone()
        return row["id"] if row else None

def get_clients():
    with closing(get_conn()) as conn:
        return conn.execute(
            "SELECT id,name FROM clients WHERE username=? ORDER BY name", (current_user(),)
        ).fetchall()

def get_client_obligo():
    with closing(get_conn()) as conn:
        return conn.execute("""
            SELECT cl.id, cl.name,
                   COALESCE(SUM(ch.amount),0) AS obligo,
                   COUNT(ch.id) AS cnt,
                   cl.total_returned_checks,
                   cl.total_late_payments,
                   cl.total_successful_deals
            FROM clients cl
            LEFT JOIN checks ch ON ch.client_id=cl.id
            WHERE cl.username=?
            GROUP BY cl.id ORDER BY obligo DESC
        """, (current_user(),)).fetchall()

def increment_client_counter(client_id, field):
    allowed = {"total_returned_checks", "total_late_payments", "total_successful_deals"}
    if field not in allowed: return
    with closing(get_conn()) as conn, conn:
        conn.execute(f"UPDATE clients SET {field}={field}+1 WHERE id=?", (client_id,))


# ─── Checks ──────────────────────────────────
def add_check(client_id, amount, due_date, status, remind_on):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT INTO checks (client_id,amount,due_date,status,remind_on) VALUES (?,?,?,?,?)",
            (client_id, amount, due_date.isoformat(), status,
             remind_on.isoformat() if remind_on else None),
        )

def get_checks(client_id=None):
    u = current_user()
    q = ("SELECT ch.*,cl.name AS client_name FROM checks ch "
         "JOIN clients cl ON cl.id=ch.client_id WHERE cl.username=?")
    p = [u]
    if client_id is not None:
        q += " AND ch.client_id=?"; p.append(client_id)
    q += " ORDER BY ch.due_date"
    with closing(get_conn()) as conn:
        return conn.execute(q, p).fetchall()

def update_status(check_id, status):
    with closing(get_conn()) as conn, conn:
        conn.execute("UPDATE checks SET status=? WHERE id=?", (status, check_id))

def delete_check(check_id):
    with closing(get_conn()) as conn, conn:
        conn.execute("DELETE FROM checks WHERE id=?", (check_id,))

def mark_check_returned(check_id):
    with closing(get_conn()) as conn:
        row = conn.execute("SELECT client_id FROM checks WHERE id=?", (check_id,)).fetchone()
    if row: increment_client_counter(row["client_id"], "total_returned_checks")
    delete_check(check_id)

def mark_check_successful(check_id):
    with closing(get_conn()) as conn:
        row = conn.execute("SELECT client_id FROM checks WHERE id=?", (check_id,)).fetchone()
    if row: increment_client_counter(row["client_id"], "total_successful_deals")
    delete_check(check_id)

def record_late_payment(client_id):
    increment_client_counter(client_id, "total_late_payments")

def get_totals():
    with closing(get_conn()) as conn:
        row = conn.execute("""
            SELECT COALESCE(SUM(ch.amount),0) AS total, COUNT(ch.id) AS cnt
            FROM checks ch JOIN clients cl ON cl.id=ch.client_id
            WHERE cl.username=?
        """, (current_user(),)).fetchone()
        return row["total"], row["cnt"]


def fmt_ils(x):
    return f"₪{x:,.0f}"


# ═══════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════
def inject_css():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
html,body,[class*="css"]{ direction:rtl; }

.stApp {
    background:
        radial-gradient(ellipse at 12% 18%,  rgba(232,184,144,.42) 0%,transparent 52%),
        radial-gradient(ellipse at 88% 78%,  rgba(64,180,255,.38)  0%,transparent 52%),
        radial-gradient(ellipse at 68%  4%,  rgba(123,60,240,.32)  0%,transparent 48%),
        radial-gradient(ellipse at 28% 92%,  rgba(64,220,180,.22)  0%,transparent 44%),
        radial-gradient(ellipse at 55% 50%,  rgba(20,10,40,.6)     0%,transparent 70%),
        #0C0C18;
    font-family:'Inter',sans-serif;
}
[data-testid="stAppViewContainer"],[data-testid="stHeader"],
section[data-testid="stMain"],[data-testid="stVerticalBlock"],
.main .block-container{ background:transparent!important; }
#MainMenu,header,footer{ visibility:hidden; }
.block-container{ padding-top:0!important; padding-bottom:5.5rem; max-width:480px; }

/* ── Fix forms & tab panels ── */
[data-testid="stForm"]{
    background:rgba(255,255,255,.10)!important;
    backdrop-filter:blur(24px)!important; -webkit-backdrop-filter:blur(24px)!important;
    border-radius:22px!important; border:1px solid rgba(255,255,255,.22)!important;
    padding:18px!important;
}
.stTabs [data-baseweb="tab-panel"]{ background:transparent!important; padding:16px 0 0!important; }

/* ── Glass ── */
.glass{
    background:rgba(255,255,255,.14);
    backdrop-filter:blur(22px); -webkit-backdrop-filter:blur(22px);
    border:1px solid rgba(255,255,255,.28); border-radius:24px;
    padding:20px 22px; margin-bottom:12px;
    box-shadow:0 12px 28px rgba(0,0,0,.18); color:#fff;
}

/* ── KPI ── */
.kpi{
    background:rgba(255,255,255,.18);
    backdrop-filter:blur(28px); -webkit-backdrop-filter:blur(28px);
    border:1px solid rgba(255,255,255,.38); border-radius:28px;
    padding:32px 24px 26px; margin-bottom:14px; text-align:center;
    box-shadow:0 16px 36px rgba(0,0,0,.20);
}
.kpi-label{ font-size:11px;font-weight:700;letter-spacing:2.2px;color:rgba(255,255,255,.6);text-transform:uppercase;margin-bottom:10px; }
.kpi-value{ font-family:'Inter',sans-serif;font-size:3rem;font-weight:900;line-height:1;color:#fff;direction:ltr;display:block;letter-spacing:-2px; }
.kpi-sub  { font-size:13px;color:rgba(255,255,255,.55);margin-top:10px;font-weight:500; }

/* ── pill ── */
.pill{ display:inline-block;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:700;margin-inline-start:6px; }

/* ── Section titles ── */
.section-title,.section-title-right{
    font-size:22px;font-weight:900;letter-spacing:-.5px;
    color:#fff;margin:22px 0 6px;text-align:right;
    text-shadow:0 2px 12px rgba(0,0,0,.35);
}
.neon-bar,.neon-bar-right{
    height:2px;width:32px;border-radius:4px;
    background:rgba(255,255,255,.45);margin-bottom:16px;margin-right:0;
}
.neon-bar{ margin-right:auto;margin-left:auto; }

/* ── Client cards ── */
.client-card{
    display:flex;justify-content:space-between;align-items:flex-start;
    backdrop-filter:blur(22px); -webkit-backdrop-filter:blur(22px);
    border:1px solid rgba(255,255,255,.32); border-radius:24px;
    padding:18px 20px; margin-bottom:10px;
    box-shadow:0 8px 22px rgba(0,0,0,.14);
}
.client-name  { font-weight:800;font-size:1rem; }
.client-obligo{ font-weight:900;font-size:1.15rem;direction:ltr;letter-spacing:-.5px;padding-top:2px; }

/* ── Alert banners ── */
.alert-obligo{
    background:rgba(255,160,40,.22);border:1px solid rgba(255,160,40,.48);
    border-radius:12px;padding:7px 12px;font-size:11px;font-weight:700;
    color:#FFB84D;margin-top:8px;line-height:1.4;
}
.alert-risk{
    background:rgba(255,60,60,.22);border:1px solid rgba(255,60,60,.48);
    border-radius:12px;padding:7px 12px;font-size:11px;font-weight:700;
    color:#FF7070;margin-top:6px;line-height:1.4;
}

/* ── Calc output ── */
.calc-out{
    border-radius:24px;padding:22px;margin-top:10px;text-align:center;
    backdrop-filter:blur(22px); -webkit-backdrop-filter:blur(22px);
    border:1px solid rgba(255,255,255,.30);
    box-shadow:0 8px 22px rgba(0,0,0,.14);
}
.calc-out.fee{ background:rgba(255,107,157,.22); }
.calc-out.net{ background:rgba(64,220,160,.22);margin-top:10px; }
.calc-out .lbl{ font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,.6);margin-bottom:8px; }
.calc-out .big{ font-family:'Inter',sans-serif;font-size:2.6rem;font-weight:900;direction:ltr;line-height:1.1;letter-spacing:-1.5px;color:#fff; }

/* ── Home nav buttons ── */
.home-nav-btn .stButton>button{
    border-radius:28px!important;font-size:1.2rem!important;font-weight:900!important;
    min-height:90px!important;height:auto!important;padding:26px 24px!important;
    backdrop-filter:blur(22px)!important; -webkit-backdrop-filter:blur(22px)!important;
    box-shadow:0 12px 32px rgba(0,0,0,.22)!important;transition:all .18s ease!important;
}
.home-nav-btn .stButton>button:hover{ transform:translateY(-2px)!important;box-shadow:0 18px 40px rgba(0,0,0,.28)!important; }
.home-nav-green .stButton>button{ background:rgba(64,220,160,.28)!important;color:#fff!important;border:1px solid rgba(64,220,160,.5)!important; }
.home-nav-pink  .stButton>button{ background:rgba(123,60,240,.30)!important;color:#fff!important;border:1px solid rgba(123,60,240,.45)!important; }

/* ── Add check button ── */
.add-check-wrapper .stButton>button{
    border-radius:50px!important;background:rgba(255,255,255,.14)!important;
    backdrop-filter:blur(22px)!important; -webkit-backdrop-filter:blur(22px)!important;
    color:#fff!important;font-size:1rem!important;font-weight:800!important;
    padding:14px 0!important;border:1px solid rgba(255,255,255,.30)!important;
    box-shadow:0 8px 22px rgba(0,0,0,.20)!important;
}
.add-check-wrapper .stButton>button:hover{ background:rgba(255,255,255,.22)!important; }

/* ── General buttons ── */
.stButton>button{
    border-radius:14px!important;border:1px solid rgba(255,255,255,.22)!important;
    background:rgba(255,255,255,.12)!important;
    backdrop-filter:blur(16px)!important; -webkit-backdrop-filter:blur(16px)!important;
    color:#fff!important;font-weight:700!important;font-family:'Inter',sans-serif!important;
    transition:all .15s ease!important;box-shadow:0 4px 14px rgba(0,0,0,.12)!important;
}
.stButton>button:hover{ background:rgba(255,255,255,.22)!important;box-shadow:0 8px 22px rgba(0,0,0,.20)!important; }

/* ── Input fields — dark text on frosted white ── */
.stTextInput input,.stNumberInput input,.stDateInput input,
[data-baseweb="input"] input,[data-baseweb="base-input"] input{
    color:#1C1C24!important;background-color:rgba(255,255,255,.85)!important;
    -webkit-text-fill-color:#1C1C24!important;caret-color:#1C1C24!important;
    border-radius:14px!important;border:1px solid rgba(255,255,255,.5)!important;
    font-weight:600!important;font-size:1rem!important;direction:ltr!important;text-align:right!important;
}
.stTextInput div[data-baseweb="input"],.stNumberInput div[data-baseweb="input"],
.stDateInput div[data-baseweb="input"]{
    background-color:rgba(255,255,255,.85)!important;
    border:1px solid rgba(255,255,255,.5)!important;border-radius:14px!important;
}
div[data-baseweb="select"]>div{
    background-color:rgba(255,255,255,.14)!important;
    border:1px solid rgba(255,255,255,.25)!important;border-radius:14px!important;
    backdrop-filter:blur(16px)!important;
}
div[data-baseweb="select"] div{ color:#fff!important;font-weight:600!important; }
input::placeholder{ color:rgba(80,80,100,.6)!important;opacity:1!important; }
ul[role="listbox"],div[data-baseweb="popover"]{
    background-color:rgba(20,18,40,.92)!important;backdrop-filter:blur(24px)!important;
    border:1px solid rgba(255,255,255,.2)!important;border-radius:16px!important;
}
ul[role="listbox"] li{ color:#fff!important;font-weight:600!important; }
label{ color:rgba(255,255,255,.6)!important;font-weight:600!important;font-size:.82rem!important; }

/* ── Radio ── */
div[data-testid="stRadio"]>div{ gap:10px!important;justify-content:center!important; }
div[data-testid="stRadio"] label{
    background:rgba(255,255,255,.12)!important;backdrop-filter:blur(16px)!important;
    border:1px solid rgba(255,255,255,.22)!important;border-radius:14px!important;
    padding:10px 28px!important;font-size:1rem!important;font-weight:800!important;
    color:#fff!important;cursor:pointer;transition:all .12s ease;
}
div[data-testid="stRadio"] label:hover{ background:rgba(255,255,255,.22)!important; }
div[data-testid="stRadio"] input[type="radio"]{ display:none!important; }
div[data-testid="stRadio"] div[data-baseweb="radio"]>div:first-child{ display:none!important; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"]{ gap:8px;justify-content:center;background:transparent!important; }
.stTabs [data-baseweb="tab"]{
    background:rgba(255,255,255,.10)!important;backdrop-filter:blur(16px)!important;
    border:1px solid rgba(255,255,255,.18)!important;border-radius:14px!important;
    padding:10px 24px!important;font-size:.95rem!important;font-weight:700!important;
    color:rgba(255,255,255,.7)!important;min-width:130px;text-align:center;
}
.stTabs [data-baseweb="tab"] p,.stTabs [data-baseweb="tab"] span,
.stTabs [data-baseweb="tab"] div{ color:rgba(255,255,255,.7)!important; }
.stTabs [aria-selected="true"]{ background:rgba(255,255,255,.28)!important;border:1px solid rgba(255,255,255,.45)!important; }
.stTabs [aria-selected="true"] p,.stTabs [aria-selected="true"] span,
.stTabs [aria-selected="true"] div{ color:#fff!important; }

/* ── Expander ── */
.streamlit-expanderHeader{
    background:rgba(255,255,255,.12)!important;backdrop-filter:blur(16px)!important;
    border:1px solid rgba(255,255,255,.22)!important;border-radius:14px!important;
    font-weight:700!important;color:#fff!important;
}
.streamlit-expanderContent{
    background:rgba(255,255,255,.07)!important;backdrop-filter:blur(12px)!important;
    border:1px solid rgba(255,255,255,.14)!important;border-radius:0 0 14px 14px!important;
}

/* ── Checkbox ── */
.stCheckbox label{ color:#fff!important;font-weight:700!important;font-size:.95rem!important; }

/* ── Big number input ── */
div[data-testid="stNumberInput"]:has(input[aria-label*="סכום"]) input{
    font-size:1.8rem!important;font-weight:900!important;text-align:center!important;
    letter-spacing:-1px!important;height:64px!important;
}
</style>
""", unsafe_allow_html=True)

    st.components.v1.html("""
<script>
function attachSelectAll(){
    window.parent.document.querySelectorAll('input[type="number"]').forEach(function(inp){
        if(inp._sa)return; inp._sa=true;
        inp.addEventListener('focus',function(){ var s=this; setTimeout(function(){s.select();},50); });
    });
}
attachSelectAll(); setInterval(attachSelectAll,600);
</script>""", height=0)


# ═══════════════════════════════════════════
# WebAuthn JS helpers
# ═══════════════════════════════════════════

def inject_webauthn_register(username: str):
    """
    Injects a WebAuthn registration call into the parent document.
    On success navigates to ?wa_reg=<credId>&wa_user=<username>
    """
    st.components.v1.html(f"""
<script>
(function(){{
    async function doRegister(){{
        if(!window.parent.PublicKeyCredential){{
            alert('הדפדפן אינו תומך בכניסה ביומטרית');return;
        }}
        var challenge=new Uint8Array(32); crypto.getRandomValues(challenge);
        try{{
            var cred=await window.parent.navigator.credentials.create({{publicKey:{{
                challenge:challenge,
                rp:{{name:"Check-Me"}},
                user:{{
                    id:new TextEncoder().encode("{username}"),
                    name:"{username}",displayName:"{username}"
                }},
                pubKeyCredParams:[
                    {{alg:-7,type:"public-key"}},
                    {{alg:-257,type:"public-key"}}
                ],
                authenticatorSelection:{{
                    authenticatorAttachment:"platform",
                    userVerification:"required",residentKey:"preferred"
                }},
                timeout:60000
            }}}});
            var credId=btoa(String.fromCharCode(...new Uint8Array(cred.rawId)))
                .replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=/g,'');
            var url=new URL(window.parent.location.href);
            url.searchParams.set('wa_reg',credId);
            url.searchParams.set('wa_user','{username}');
            window.parent.location.href=url.toString();
        }}catch(e){{
            if(e.name!=='NotAllowedError') alert('שגיאה: '+e.message);
        }}
    }}
    doRegister();
}})();
</script>""", height=0)


def inject_webauthn_login_button(cred_map: dict):
    """
    Injects a floating biometric login button into parent document.
    cred_map: {username: credId_b64_urlsafe}
    """
    if not cred_map:
        return
    cred_json = json.dumps([{"u": u, "c": c} for u, c in cred_map.items()])
    st.components.v1.html(f"""
<script>
(function(){{
    var doc=window.parent.document;
    var old=doc.getElementById('__wabtn__'); if(old)old.remove();

    var wrapper=doc.createElement('div');
    wrapper.id='__wabtn__';
    wrapper.style.cssText=[
        'position:fixed','bottom:28px','right:20px','z-index:99999',
        'display:flex','flex-direction:column','align-items:center','gap:4px'
    ].join(';');

    var btn=doc.createElement('button');
    btn.innerHTML='<span style="font-size:1.6rem;display:block;">&#x1F4F1;</span>'
                 +'<span style="font-size:10px;font-weight:800;letter-spacing:.5px;">BIOMETRIC</span>';
    btn.style.cssText=[
        'background:rgba(255,255,255,0.14)',
        'backdrop-filter:blur(22px)','-webkit-backdrop-filter:blur(22px)',
        'color:#fff','border:1px solid rgba(255,255,255,.35)',
        'border-radius:20px','padding:12px 18px',
        'font-family:Inter,sans-serif','cursor:pointer',
        'box-shadow:0 8px 28px rgba(0,0,0,.28)',
        'transition:all .15s ease','text-align:center','min-width:70px'
    ].join(';');
    btn.addEventListener('mouseenter',function(){{
        this.style.background='rgba(255,255,255,.24)';
        this.style.transform='translateY(-2px)';
    }});
    btn.addEventListener('mouseleave',function(){{
        this.style.background='rgba(255,255,255,.14)';
        this.style.transform='';
    }});

    btn.addEventListener('click',async function(){{
        if(!window.parent.PublicKeyCredential){{
            alert('הדפדפן אינו תומך בכניסה ביומטרית'); return;
        }}
        var credMap={cred_json};
        var allowCreds=credMap.map(function(x){{
            var raw=x.c.replace(/-/g,'+').replace(/_/g,'/');
            while(raw.length%4)raw+='=';
            return{{id:Uint8Array.from(atob(raw),function(c){{return c.charCodeAt(0)}}),type:'public-key'}};
        }});
        var challenge=new Uint8Array(32); crypto.getRandomValues(challenge);
        try{{
            var assertion=await window.parent.navigator.credentials.get({{publicKey:{{
                challenge:challenge,
                allowCredentials:allowCreds,
                userVerification:'required',
                timeout:60000
            }}}});
            var usedId=btoa(String.fromCharCode(...new Uint8Array(assertion.rawId)))
                .replace(/\\+/g,'-').replace(/\\//g,'_').replace(/=/g,'');
            var matched=credMap.find(function(x){{return x.c===usedId;}});
            if(matched){{
                var url=new URL(window.parent.location.href);
                url.searchParams.set('wa_auth',matched.u);
                window.parent.location.href=url.toString();
            }}
        }}catch(e){{
            if(e.name!=='NotAllowedError') alert('שגיאת אימות: '+e.message);
        }}
    }});

    wrapper.appendChild(btn);
    doc.body.appendChild(wrapper);
}})();
</script>""", height=0)


# ═══════════════════════════════════════════
# Auth Screen
# ═══════════════════════════════════════════
def render_auth_screen(authenticator):
    st.markdown(
        "<div style='height:40px'></div>"
        "<p style='text-align:center;font-size:11px;font-weight:700;letter-spacing:4px;"
        "color:rgba(255,255,255,.5);text-transform:uppercase;margin-bottom:6px;'>CHECK MANAGEMENT</p>"
        "<h1 style='text-align:center;font-family:Inter,sans-serif;font-weight:900;"
        "font-size:3.2rem;letter-spacing:-3px;color:#fff;line-height:1;margin-bottom:6px;"
        "text-shadow:0 4px 24px rgba(0,0,0,.5);'>CHECK<span style=\"color:rgba(255,255,255,.55)\">-</span>ME</h1>"
        "<p style='text-align:center;color:rgba(255,255,255,.5);font-size:.9rem;"
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
            if ok: st.rerun()
            else:  st.error(msg)

    with tab_register:
        st.markdown("<p style='color:#fff;font-weight:800;font-size:1rem;margin-bottom:14px;'>צור חשבון חדש</p>",
                    unsafe_allow_html=True)
        with st.form("reg_form", clear_on_submit=True):
            r_user  = st.text_input("שם משתמש (אנגלית)", key="r_user")
            r_name  = st.text_input("שם מלא",             key="r_name")
            r_email = st.text_input("אימייל",              key="r_email")
            r_pass  = st.text_input("סיסמה (6+ תווים)", type="password", key="r_pass")
            r_pass2 = st.text_input("אימות סיסמה",      type="password", key="r_pass2")
            submitted = st.form_submit_button("הרשמה ✅", use_container_width=True)
        if submitted:
            r_user=r_user.strip(); r_name=r_name.strip(); r_email=r_email.strip()
            if not all([r_user,r_name,r_email,r_pass]):
                st.error("יש למלא את כל השדות.")
            elif len(r_pass)<6:
                st.error("הסיסמה חייבת להכיל לפחות 6 תווים.")
            elif r_pass!=r_pass2:
                st.error("הסיסמאות אינן תואמות.")
            else:
                with closing(get_conn()) as conn:
                    exists=conn.execute("SELECT 1 FROM users WHERE username=?",(r_user,)).fetchone()
                if exists:
                    st.error("שם המשתמש כבר קיים.")
                else:
                    hashed=stauth.Hasher().hash(r_pass)
                    with closing(get_conn()) as conn,conn:
                        conn.execute("INSERT INTO users(username,name,password,email) VALUES(?,?,?,?)",
                                     (r_user,r_name,hashed,r_email))
                    st.success("נרשמת בהצלחה! עבור ללשונית 'כניסה' והתחבר. 🎉")


# ═══════════════════════════════════════════
# Shared components
# ═══════════════════════════════════════════
def render_kpi():
    total, cnt = get_totals()
    st.markdown(
        f'<div class="kpi">'
        f'<div class="kpi-label">סך הצ\'קים שביד כרגע</div>'
        f'<div class="kpi-value">{fmt_ils(total)}</div>'
        f'<div class="kpi-sub">{cnt} צ\'קים פיזיים בארנק 💸</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_back_button():
    """
    Floating back-button injected into the parent document as a plain <a href> tag.
    An anchor with href is the most reliable cross-browser navigation method —
    no location.href assignment, no JS click handler, no CSP issues.
    height=0 so the iframe takes zero layout space.
    """
    st.components.v1.html("""
<script>
(function(){
    try{
        var doc=window.parent.document;
        var old=doc.getElementById('__cfb__'); if(old)old.remove();

        var a=doc.createElement('a');
        a.id='__cfb__';
        a.href='?s=home';
        a.innerHTML='&#8592; &#x05E8;&#x05D0;&#x05E9;&#x05D9;';
        a.style.cssText=[
            'position:fixed','bottom:28px','left:20px','z-index:99999',
            'background:rgba(255,255,255,.82)',
            'backdrop-filter:blur(22px)','-webkit-backdrop-filter:blur(22px)',
            'color:#1C1C24','border:1px solid rgba(255,255,255,.65)',
            'border-radius:50px','padding:11px 24px',
            'font-weight:800','font-size:14px','cursor:pointer',
            'box-shadow:0 8px 28px rgba(0,0,0,.28)',
            'font-family:Inter,sans-serif','text-decoration:none',
            'display:inline-flex','align-items:center',
            'transition:all .15s ease','direction:rtl','line-height:1'
        ].join(';');
        a.addEventListener('mouseenter',function(){
            this.style.background='rgba(255,255,255,.97)';
            this.style.transform='translateY(-2px)';
            this.style.boxShadow='0 12px 36px rgba(0,0,0,.35)';
        });
        a.addEventListener('mouseleave',function(){
            this.style.background='rgba(255,255,255,.82)';
            this.style.transform='';
            this.style.boxShadow='0 8px 28px rgba(0,0,0,.28)';
        });
        doc.body.appendChild(a);
    }catch(e){console.warn('back-btn:',e);}
})();
</script>""", height=0)


# ═══════════════════════════════════════════
# Home Screen
# ═══════════════════════════════════════════
def render_home_screen():
    st.markdown(
        "<div style='height:40px'></div>"
        "<p style='text-align:center;font-size:11px;font-weight:700;letter-spacing:4px;"
        "color:rgba(255,255,255,.5);text-transform:uppercase;margin-bottom:6px;'>CHECK MANAGEMENT</p>"
        "<h1 style='text-align:center;font-family:Inter,sans-serif;font-weight:900;"
        "font-size:3.2rem;letter-spacing:-3px;color:#fff;line-height:1;margin-bottom:6px;"
        "text-shadow:0 4px 24px rgba(0,0,0,.5);'>CHECK<span style=\"color:rgba(255,255,255,.55)\">-</span>ME</h1>"
        "<p style='text-align:center;color:rgba(255,255,255,.5);font-size:.9rem;"
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

    # ── Biometric enrollment option ──
    has_bio = current_user_has_webauthn()
    bio_label = "🔏 עדכון כניסה ביומטרית" if has_bio else "🔏 הפעלת כניסה ביומטרית (טביעת אצבע)"
    bio_status = "✅ פעיל" if has_bio else "לא מוגדר"
    with st.expander(f"הגדרות אבטחה — {bio_status}"):
        st.markdown(
            f"<p style='color:rgba(255,255,255,.7);font-size:.85rem;margin-bottom:12px;'>"
            f"כניסה ביומטרית מאפשרת כניסה מהירה ללא סיסמה — רק עם טביעת אצבע או זיהוי פנים.<br>"
            f"<b>סטטוס:</b> <span style='color:{('#4DDC96' if has_bio else '#FF7070')};'>{bio_status}</span>"
            f"</p>",
            unsafe_allow_html=True,
        )
        if st.button(bio_label, use_container_width=True, key="enable_bio"):
            st.session_state["_trigger_register"] = True
            st.rerun()

    # Trigger WebAuthn registration if button was pressed
    if st.session_state.pop("_trigger_register", False):
        inject_webauthn_register(st.session_state.get("username", ""))
        st.info("📱 הפעל את חיישן הטביעה בהנחיית המכשיר…")


# ═══════════════════════════════════════════
# Add Check Form
# ═══════════════════════════════════════════
def render_add_check_form():
    clients = get_clients()
    st.markdown('<div class="add-check-wrapper">', unsafe_allow_html=True)
    if st.button("➕  הוספת צ'ק חדש", use_container_width=True, key="open_add_form"):
        st.session_state.add_form_open = not st.session_state.get("add_form_open", False)
    st.markdown("</div>", unsafe_allow_html=True)

    if not st.session_state.get("add_form_open", False):
        return

    names = [c["name"] for c in clients]
    col_a, _ = st.columns([2,1])
    with col_a:
        sel = st.selectbox("לקוח", ["— חדש —"]+names, key="add_client_sel")
    new_name = st.text_input("שם לקוח חדש", key="new_client_name") if sel=="— חדש —" else None

    amount = st.number_input("סכום הצ'ק (₪)", min_value=0.0, step=100.0, format="%.0f", key="add_amount")
    c1, c2 = st.columns(2)
    with c1:
        due = st.date_input("תאריך פירעון", value=date.today()+timedelta(days=30),
                            min_value=date.today(), key="add_due")
    with c2:
        use_remind = st.checkbox("הוסף תזכורת", value=False, key="add_use_remind")
    remind = None
    if use_remind:
        remind = st.date_input("תאריך תזכורת", value=date.today()+timedelta(days=30),
                               min_value=date.today(), key="add_remind")
    status = st.selectbox("סטטוס", STATUSES, key="add_status")

    if st.button("💾  שמירת צ'ק", use_container_width=True, key="save_check"):
        cid = (add_client(new_name or "") if sel=="— חדש —"
               else next((c["id"] for c in clients if c["name"]==sel), None))
        if not cid:      st.error("נא לבחור או להזין שם לקוח.")
        elif amount<=0:  st.error("נא להזין סכום גדול מאפס.")
        else:
            add_check(cid, amount, due, status, remind)
            st.success("הצ'ק נשמר ✅")
            st.session_state.add_form_open = False
            st.rerun()


# ═══════════════════════════════════════════
# Client List + BI
# ═══════════════════════════════════════════
def render_clients():
    st.markdown('<div class="section-title">הלקוחות שלי</div>', unsafe_allow_html=True)
    st.markdown('<div class="neon-bar"></div>', unsafe_allow_html=True)

    rows = [r for r in get_client_obligo()
            if r["cnt"]>0 or r["total_returned_checks"]>0 or r["total_successful_deals"]>0]

    if not rows:
        st.markdown('<div class="glass">אין עדיין צ\'קים ⬆️</div>', unsafe_allow_html=True)
        return

    for i, r in enumerate(rows):
        bg, txt = CLIENT_PALETTE[i % len(CLIENT_PALETTE)]
        score  = calc_credit_score(r["total_returned_checks"],r["total_late_payments"],r["total_successful_deals"])
        scolor = score_to_color(score)
        stars  = render_stars(score)

        alerts_html = ""
        if r["cnt"]>3:
            alerts_html += (f"<div class='alert-obligo'>⚠️ {r['cnt']} צ'קים פתוחים — שקול סיכון אובליגו!</div>")
        if score<60:
            alerts_html += (f"<div class='alert-risk'>🔴 ציון אמינות נמוך ({score}/100) — לא מומלץ לקבל צ'קים נוספים!</div>")

        score_badge = (f"<span style='font-size:11px;font-weight:800;color:{scolor};"
                       f"background:rgba(0,0,0,.18);border-radius:8px;padding:2px 7px;"
                       f"margin-inline-end:4px;'>{score}</span>")

        card_html = (
            f'<div class="client-card" style="background:{bg};">'
            f'<div style="flex:1;">'
            f'<div class="client-name" style="color:{txt};">{r["name"]}</div>'
            f'<div style="display:flex;align-items:center;gap:6px;margin-top:5px;flex-wrap:wrap;">'
            f'<span style="font-size:.82rem;color:{txt};opacity:.7;font-weight:600;">{r["cnt"]} &#x05E6;\'&#x05E7;&#x05D9;&#x05DD; |</span>'
            f'{stars} {score_badge}'
            f'</div>'
            f'{alerts_html}'
            f'</div>'
            f'<div class="client-obligo" style="color:{txt};margin-inline-start:14px;">{fmt_ils(r["obligo"])}</div>'
            f'</div>'
        )
        st.markdown(card_html, unsafe_allow_html=True)

        label_expand = (f"פעיל:{r['cnt']} · חזרות:{r['total_returned_checks']} "
                        f"· איחורים:{r['total_late_payments']} · הצלחות:{r['total_successful_deals']}")
        with st.expander(label_expand):
            checks_of_client = get_checks(r["id"])
            if not checks_of_client:
                st.markdown("<p style='color:rgba(255,255,255,.5);font-size:.85rem;text-align:center;padding:10px 0;'>אין צ'קים פעילים</p>",
                            unsafe_allow_html=True)
            else:
                for ch in checks_of_client:
                    color      = STATUS_COLORS.get(ch["status"], "#aaa")
                    remind_str = f" | תזכורת: {ch['remind_on']}" if ch["remind_on"] else ""
                    check_html = (
                        f'<div style="background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);'
                        f'border-radius:16px;padding:12px 14px;margin-bottom:8px;">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
                        f'<span style="font-weight:900;direction:ltr;color:#fff;font-size:1.1rem;">{fmt_ils(ch["amount"])}</span>'
                        f'<span class="pill" style="background:{color}22;color:{color};border:1px solid {color}66;">{ch["status"]}</span>'
                        f'</div>'
                        f'<span style="font-size:.8rem;color:rgba(255,255,255,.55);">&#x05E4;&#x05D9;&#x05E8;&#x05E2;&#x05D5;&#x05DF;: {ch["due_date"]}{remind_str}</span>'
                        f'</div>'
                    )
                    st.markdown(check_html, unsafe_allow_html=True)

                    col_sel, col_upd = st.columns([3,2])
                    with col_sel:
                        new_st = st.selectbox("סטטוס", STATUSES_ALL,
                                              index=STATUSES_ALL.index(ch["status"]) if ch["status"] in STATUSES_ALL else 0,
                                              key=f"st_{ch['id']}", label_visibility="collapsed")
                    with col_upd:
                        if st.button("עדכן", key=f"upd_{ch['id']}", use_container_width=True):
                            if new_st=="חזר":
                                mark_check_returned(ch["id"])
                                st.toast("↩️ צ'ק סומן כחזר — ציון עודכן", icon="⚠️")
                            else:
                                update_status(ch["id"], new_st)
                            st.rerun()

                    ca, cb, cc = st.columns(3)
                    with ca:
                        if st.button("✅ נפרע", key=f"ok_{ch['id']}", use_container_width=True):
                            mark_check_successful(ch["id"]); st.toast("✅ עסקה מוצלחת!"); st.rerun()
                    with cb:
                        if st.button("🕐 איחור", key=f"late_{ch['id']}", use_container_width=True):
                            record_late_payment(ch["client_id"]); st.toast("🕐 איחור תועד"); st.rerun()
                    with cc:
                        if st.button("🗑️", key=f"del_{ch['id']}", use_container_width=True):
                            delete_check(ch["id"]); st.rerun()

                    st.markdown("<hr style='border:none;border-top:1px solid rgba(255,255,255,.08);margin:6px 0;'>",
                                unsafe_allow_html=True)

            hist_html = (
                f'<div style="background:rgba(255,255,255,.06);border-radius:14px;padding:12px 14px;margin-top:8px;">'
                f'<div style="font-size:11px;font-weight:700;letter-spacing:1.5px;color:rgba(255,255,255,.45);'
                f'text-transform:uppercase;margin-bottom:10px;">&#x05D4;&#x05D9;&#x05E1;&#x05D8;&#x05D5;&#x05E8;&#x05D9;&#x05D9;&#x05EA; &#x05D0;&#x05DE;&#x05D9;&#x05E0;&#x05D5;&#x05EA;</div>'
                f'<div style="display:flex;justify-content:space-around;text-align:center;">'
                f'<div><div style="font-size:1.4rem;font-weight:900;color:#FF5555;">{r["total_returned_checks"]}</div>'
                f'<div style="font-size:10px;color:rgba(255,255,255,.45);font-weight:600;">&#x05D7;&#x05D6;&#x05E8;&#x05D5;&#x05EA;</div></div>'
                f'<div><div style="font-size:1.4rem;font-weight:900;color:#FFB060;">{r["total_late_payments"]}</div>'
                f'<div style="font-size:10px;color:rgba(255,255,255,.45);font-weight:600;">&#x05D0;&#x05D9;&#x05D7;&#x05D5;&#x05E8;&#x05D9;&#x05DD;</div></div>'
                f'<div><div style="font-size:1.4rem;font-weight:900;color:#4DDC96;">{r["total_successful_deals"]}</div>'
                f'<div style="font-size:10px;color:rgba(255,255,255,.45);font-weight:600;">&#x05D4;&#x05E6;&#x05DC;&#x05D7;&#x05D5;&#x05EA;</div></div>'
                f'<div><div style="font-size:1.4rem;font-weight:900;color:{scolor};">{score}</div>'
                f'<div style="font-size:10px;color:rgba(255,255,255,.45);font-weight:600;">&#x05E6;&#x05D9;&#x05D5;&#x05DF;</div></div>'
                f'</div></div>'
            )
            st.markdown(hist_html, unsafe_allow_html=True)


# ═══════════════════════════════════════════
# Calculator
# ═══════════════════════════════════════════
def render_calculator():
    st.markdown('<div class="section-title-right">מחשבון פריטה (ניכיון)</div>', unsafe_allow_html=True)
    st.markdown('<div class="neon-bar-right"></div>', unsafe_allow_html=True)

    if "fixed_rate"     not in st.session_state: st.session_state.fixed_rate     = 12.0
    if "rate_basis"     not in st.session_state: st.session_state.rate_basis     = "שנתית"
    if "rate_edit_open" not in st.session_state: st.session_state.rate_edit_open = False

    checks  = get_checks()
    options = ["— הזנה ידנית —"] + [
        f"{c['client_name']} | {fmt_ils(c['amount'])} | {c['due_date']}" for c in checks
    ]
    pick = st.selectbox("בחר צ'ק קיים (או הזנה ידנית)", options, key="calc_pick")

    default_amount = 10000.0
    default_due    = date.today()+timedelta(days=30)
    if pick!="— הזנה ידנית —":
        idx = options.index(pick)-1
        ch  = checks[idx]
        default_amount = float(ch["amount"])
        try:    default_due = datetime.fromisoformat(ch["due_date"]).date()
        except: default_due = date.today()+timedelta(days=30)

    if st.session_state.get("_last_pick")!=pick:
        st.session_state.calc_due    = default_due
        st.session_state.calc_amount = default_amount
        st.session_state._last_pick  = pick

    amount   = st.number_input("סכום הצ'ק (₪)", min_value=0.0, step=100.0,
                               value=st.session_state.get("calc_amount",default_amount),
                               format="%.0f", key="calc_amount")
    due_date = st.date_input("תאריך פירעון הצ'ק", key="calc_due",
                             min_value=date.today(),
                             help="החישוב מתחיל ממחר וכולל את יום הפירעון")

    days = max((due_date-date.today()).days+1, 0)
    st.markdown(
        f"<div style='background:rgba(232,184,144,.28);backdrop-filter:blur(22px);"
        f"-webkit-backdrop-filter:blur(22px);border:1px solid rgba(232,184,144,.45);"
        f"border-radius:22px;padding:16px;text-align:center;margin:8px 0 12px;"
        f"box-shadow:0 8px 22px rgba(0,0,0,.14);'>"
        f"<span style='font-size:11px;font-weight:700;letter-spacing:2px;color:rgba(255,255,255,.6);"
        f"text-transform:uppercase;display:block;margin-bottom:4px;'>ימי זיכוי</span>"
        f"<span style='font-family:Inter,sans-serif;font-size:2.4rem;font-weight:900;"
        f"color:#fff;letter-spacing:-1.5px;'>{days}</span>"
        f"<span style='font-size:.9rem;font-weight:600;color:rgba(255,255,255,.6);'> ימים</span></div>",
        unsafe_allow_html=True)

    st.markdown("<div style='text-align:center;font-size:11px;font-weight:700;"
                "letter-spacing:2px;color:rgba(255,255,255,.5);text-transform:uppercase;"
                "margin-bottom:10px;'>סוג הריבית</div>", unsafe_allow_html=True)
    basis = st.radio("סוג הריבית", ["חודשית","שנתית"],
                     index=["חודשית","שנתית"].index(st.session_state.rate_basis),
                     horizontal=True, key="basis_radio", label_visibility="collapsed")
    st.session_state.rate_basis = basis

    rate_val = st.session_state.fixed_rate
    r1, r2   = st.columns([2,1])
    with r1:
        st.markdown(
            f"<div style='background:rgba(255,200,80,.22);backdrop-filter:blur(22px);"
            f"-webkit-backdrop-filter:blur(22px);border:1px solid rgba(255,200,80,.40);"
            f"border-radius:22px;padding:16px;text-align:center;"
            f"box-shadow:0 8px 22px rgba(0,0,0,.14);'>"
            f"<span style='font-size:11px;font-weight:700;letter-spacing:2px;"
            f"color:rgba(255,255,255,.6);text-transform:uppercase;display:block;margin-bottom:6px;'>"
            f"ריבית קבועה ({basis})</span>"
            f"<span style='font-family:Inter,sans-serif;font-size:2rem;font-weight:900;"
            f"color:#fff;letter-spacing:-1px;'>{rate_val:.2f}%</span></div>",
            unsafe_allow_html=True)
    with r2:
        st.write(""); st.write("")
        if st.button("✏️ שינוי", use_container_width=True, key="edit_rate"):
            st.session_state.rate_edit_open = not st.session_state.rate_edit_open

    if st.session_state.rate_edit_open:
        new_rate = st.number_input("הזן ריבית (%)", min_value=0.0, max_value=100.0,
                                   value=float(rate_val), step=0.1, format="%.2f", key="rate_input_manual")
        if st.button("💾 שמירת הריבית", use_container_width=True, key="save_rate"):
            st.session_state.fixed_rate    = new_rate
            st.session_state.rate_edit_open = False
            st.rerun()

    fee = amount*(rate_val/100.0)*(days/30.0 if basis=="חודשית" else days/365.0)
    net = amount-fee

    if days<=0:
        st.markdown("<div style='background:rgba(255,107,100,.22);backdrop-filter:blur(22px);"
                    "-webkit-backdrop-filter:blur(22px);border:1px solid rgba(255,107,100,.38);"
                    "border-radius:16px;padding:14px;text-align:center;font-size:13px;"
                    "font-weight:700;color:rgba(255,255,255,.85);margin:10px 0;'>"
                    "⚠️ תאריך הפירעון עבר — אין ימי זיכוי.</div>", unsafe_allow_html=True)

    st.markdown(
        f'<div class="calc-out fee"><div class="lbl">&#x05E1;&#x05DA; &#x05D4;&#x05E2;&#x05DE;&#x05DC;&#x05D4; &#x05E9;&#x05D9;&#x05D5;&#x05E8;&#x05D3;&#x05EA;</div><div class="big">{fmt_ils(fee)}</div></div>'
        f'<div class="calc-out net"><div class="lbl">&#x05E0;&#x05D8;&#x05D5; &#x05DE;&#x05D6;&#x05D5;&#x05DE;&#x05DF; &#x05E9;&#x05DE;&#x05EA;&#x05E7;&#x05D1;&#x05DC;</div><div class="big">{fmt_ils(net)}</div></div>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════
# Main
# ═══════════════════════════════════════════
def main():
    init_db()
    inject_css()

    credentials   = get_all_users_for_auth()
    authenticator = stauth.Authenticate(
        credentials,
        cookie_name="checkme_auth",
        key="checkme_secret_2025",
        cookie_expiry_days=30,
    )

    # ── Handle WebAuthn login callback ──
    wa_auth = st.query_params.get("wa_auth")
    if wa_auth and st.session_state.get("authentication_status") is not True:
        user = get_user_by_webauthn_cred(wa_auth)
        if user:
            st.session_state.update({
                "authentication_status": True,
                "username": user["username"],
                "name":     user["name"],
            })
            st.query_params.clear()
            st.rerun()

    # ── Handle WebAuthn registration callback ──
    wa_reg  = st.query_params.get("wa_reg")
    wa_user = st.query_params.get("wa_user")
    if wa_reg and wa_user and st.session_state.get("authentication_status") is True:
        store_webauthn_credential(wa_user, wa_reg)
        st.query_params.clear()
        st.toast("✅ כניסה ביומטרית הופעלה בהצלחה!", icon="🔏")
        st.rerun()

    auth_status = st.session_state.get("authentication_status")

    if auth_status is not True:
        render_auth_screen(authenticator)
        # Show biometric login button if any user has enrolled
        cred_map = get_webauthn_cred_map()
        if cred_map:
            inject_webauthn_login_button(cred_map)
        return

    # ── Logged in ──
    st.session_state.current_user = st.session_state.get("username", "admin")

    # ── NAVIGATION: session state only — query params only on initial cold load ──
    # (Avoid the bug where query param overrides session navigation)
    if "screen" not in st.session_state:
        qp = st.query_params.get("s", "home")
        st.session_state.screen = qp if qp in ("home","calc","mgmt") else "home"

    screen = st.session_state.screen

    # Push to browser history bar (cosmetic only)
    st.components.v1.html(f"""<script>
(function(){{
    var s="{screen}",cur=new URLSearchParams(window.parent.location.search).get("s");
    if(cur!==s) window.parent.history.pushState({{screen:s}},"","?s="+s);
}})();
</script>""", height=0)

    # ── Render ──
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
