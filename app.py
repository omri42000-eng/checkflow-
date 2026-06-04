def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Plus+Jakarta+Sans:wght@600;800&family=Outfit:wght@800;900&display=swap');

    :root {
        /* פלטת צבעים פרועה - Cyber Neon */
        --bg-cyber-dark: #0a0512;
        --neon-purple:   #bd00ff;
        --neon-blue:     #00d1ff;
        --neon-pink:     #ff007a;
        --neon-amber:    #ffb800;
        
        /* אפקטים של זכוכית שבורה וחומרים עתידניים */
        --glass-cyber:   rgba(15, 8, 28, 0.45);
        --glass-border:  rgba(0, 209, 255, 0.3);
        --text-primary:  #ffffff;
        --text-neon-glow: 0 0 10px rgba(0, 209, 255, 0.6);
    }

    html, body, [class*="css"] { direction: rtl; }

    /* ─── רקע פרוע: שילוב לייזרים וזכוכית נוזלית שבורה ─── */
    .stApp {
        background: 
            radial-gradient(ellipse at 80% 20%, rgba(255, 0, 122, 0.25), transparent 45%),
            radial-gradient(ellipse at 15% 75%, rgba(189, 0, 255, 0.3), transparent 50%),
            linear-gradient(135deg, rgba(0, 209, 255, 0.08) 0%, transparent 100%),
            var(--bg-cyber-dark);
        background-image: 
            radial-gradient(rgba(0, 209, 255, 0.1) 1px, transparent 0),
            radial-gradient(rgba(255, 0, 122, 0.1) 1px, transparent 0);
        background-size: 24px 24px;
        background-position: 0 0, 12px 12px;
        background-attachment: fixed;
        font-family: 'Plus Jakarta Sans', sans-serif;
        color: var(--text-primary);
    }
    
    #MainMenu, header, footer { visibility: hidden; }
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 5rem;
        max-width: 460px;
    }

    /* ─── כותרת CHECKFLOW כרום מטאלית תלת-ממדית משוגעת ─── */
    h1 {
        font-family: 'Orbitron', sans-serif !important;
        font-weight: 900 !important;
        font-size: 3.5rem !important;
        text-align: center;
        text-transform: uppercase;
        letter-spacing: -2px !important;
        background: linear-gradient(180deg, #ffffff 0%, #a6afb8 45%, #00d1ff 50%, #bd00ff 100%);
        -webkit-background-clip: text !important;
        background-clip: text !important;
        -webkit-text-fill-color: transparent !important;
        filter: drop-shadow(0px 4px 12px rgba(189, 0, 255, 0.6)) drop-shadow(0px 0px 30px rgba(0, 209, 255, 0.4));
        transform: skewX(-4deg) rotate(-1deg);
        margin-bottom: 30px !important;
    }

    /* ─── כרטיס הנתונים המרכזי (KPI) - תצוגה דיגיטלית רוטטת ─── */
    .kpi {
        background: var(--glass-cyber);
        -webkit-backdrop-filter: blur(25px);
        backdrop-filter: blur(25px);
        border: 2px solid #ff007a;
        border-radius: 24px;
        padding: 30px 20px;
        margin-bottom: 20px;
        box-shadow: 0 0 25px rgba(255, 0, 122, 0.3), inset 0 0 15px rgba(255, 0, 122, 0.2);
        position: relative;
        overflow: hidden;
        transform: rotate(0.5deg);
    }
    .kpi::before {
        content: ""; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%;
        background: linear-gradient(45deg, transparent, rgba(0, 209, 255, 0.15), transparent);
        transform: rotate(45deg); animation: laser-sweep 4s linear infinite;
    }
    @keyframes laser-sweep {
        0% { transform: translate(-30%, -30%) rotate(45deg); }
        100% { transform: translate(30%, 30%) rotate(45deg); }
    }
    .kpi-label {
        font-family: 'Orbitron', sans-serif;
        font-size: 11px; font-weight: 900; letter-spacing: 2px;
        color: var(--neon-blue); text-shadow: var(--text-neon-glow);
        margin-bottom: 12px;
    }
    .kpi-value {
        font-family: 'Orbitron', sans-serif;
        font-size: 3.2rem; font-weight: 900;
        color: #ffffff; text-shadow: 0 0 20px rgba(0, 209, 255, 0.85);
        letter-spacing: -1px;
    }
    .kpi-sub {
        font-size: 13px; color: #a6afb8; font-weight: 600; margin-top: 10px;
    }

    /* ─── כפתורי ניווט מסך הבית - אלכסוניים ודינמיים ─── */
    .home-nav-btn .stButton > button {
        border-radius: 16px !important;
        font-family: 'Orbitron', sans-serif !important;
        font-size: 1.3rem !important;
        font-weight: 900 !important;
        min-height: 76px !important;
        transition: all 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275) !important;
        text-transform: uppercase;
        box-shadow: 0 10px 25px rgba(0,0,0,0.4) !important;
    }
    /* כפתור מנצנץ כחול */
    .home-nav-green .stButton > button {
        background: linear-gradient(135deg, rgba(0, 210, 255, 0.3), rgba(189, 0, 255, 0.2)) !important;
        border: 2px solid var(--neon-blue) !important;
        color: #ffffff !important;
        text-shadow: 0 0 8px var(--neon-blue);
        transform: skewX(-6deg);
    }
    .home-nav-green .stButton > button:hover {
        background: linear-gradient(135deg, rgba(0, 210, 255, 0.5), rgba(189, 0, 255, 0.4)) !important;
        box-shadow: 0 0 25px var(--neon-blue) !important;
        transform: skewX(-6deg) scale(1.03) translateY(-2px) !important;
    }
    /* כפתור מנצנץ פינק */
    .home-nav-pink .stButton > button {
        background: linear-gradient(135deg, rgba(255, 0, 122, 0.3), rgba(10, 5, 18, 0.2)) !important;
        border: 2px solid var(--neon-pink) !important;
        color: #ffffff !important;
        text-shadow: 0 0 8px var(--neon-pink);
        transform: skewX(6deg);
    }
    .home-nav-pink .stButton > button:hover {
        background: linear-gradient(135deg, rgba(255, 0, 122, 0.5), rgba(189, 0, 255, 0.3)) !important;
        box-shadow: 0 0 25px var(--neon-pink) !important;
        transform: skewX(6deg) scale(1.03) translateY(-2px) !important;
    }

    /* ─── כרטיסים כלליים ולוח שנה (Glassmorphism אגרסיבי) ─── */
    .glass, .reminder-card {
        background: var(--glass-cyber);
        -webkit-backdrop-filter: blur(20px);
        backdrop-filter: blur(20px);
        border: 1px solid var(--glass-border);
        border-radius: 20px;
        padding: 20px;
        margin-bottom: 12px;
        box-shadow: 0 15px 35px rgba(0,0,0,0.5);
    }
    .reminder-card { border-color: var(--neon-amber); box-shadow: 0 0 15px rgba(255, 184, 0, 0.15); }
    .reminder-title { font-family: 'Orbitron', sans-serif; color: var(--neon-amber); font-weight: 900; }

    /* ─── פלט מחשבון - תוצאות קיצוניות ─── */
    .calc-out {
        border-radius: 20px; padding: 22px; margin-top: 12px; text-align: center;
        background: rgba(10, 5, 24, 0.7);
        border: 2px solid var(--glass-border);
    }
    .calc-out.fee { border-color: var(--neon-pink); box-shadow: 0 0 20px rgba(255, 0, 122, 0.2); }
    .calc-out.net { border-color: #00ff66; box-shadow: 0 0 20px rgba(0, 255, 102, 0.2); }
    .calc-out .big {
        font-family: 'Orbitron', sans-serif; font-size: 2.8rem; font-weight: 900;
    }
    .calc-out.fee .big { color: var(--neon-pink); text-shadow: 0 0 10px var(--neon-pink); }
    .calc-out.net .big { color: #00ff66; text-shadow: 0 0 10px #00ff66; }

    /* ─── שדות קלט דיגיטליים מעוצבים כחומרה עתידנית ─── */
    .stTextInput input, .stNumberInput input, .stDateInput input, [data-baseweb="input"] input {
        color: #ffffff !important;
        background-color: rgba(5, 2, 10, 0.85) !important;
        border: 1px solid var(--neon-blue) !important;
        border-radius: 10px !important;
        font-family: 'Orbitron', sans-serif;
        font-weight: 700 !important;
        box-shadow: inset 0 0 8px rgba(0, 209, 255, 0.2) !important;
    }
    .stTextInput input:focus, .stNumberInput input:focus {
        border-color: var(--neon-pink) !important;
        box-shadow: 0 0 12px rgba(255, 0, 122, 0.5) !important;
    }
    
    /* פקדים מיוחדים (Radio / Tabs) */
    div[data-testid="stRadio"] label:has(input:checked) {
        background: linear-gradient(135deg, var(--neon-purple), var(--neon-pink)) !important;
        box-shadow: 0 0 15px var(--neon-pink) !important;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, var(--neon-blue), var(--neon-purple)) !important;
        box-shadow: 0 0 15px var(--neon-blue) !important;
    }

    /* ─── כרטיס לקוח מודולרי ─── */
    .client-card {
        background: rgba(189, 0, 255, 0.08);
        border: 1px solid rgba(189, 0, 255, 0.3);
        border-radius: 16px; padding: 16px; margin-bottom: 10px;
        box-shadow: 0 8px 20px rgba(0,0,0,0.3);
    }
    .client-name { font-weight: 800; font-size: 1.1rem; color: #ffffff; }
    .client-obligo { font-family: 'Orbitron', sans-serif; font-weight: 900; color: var(--neon-blue); }

    /* כפתור חזרה צף קשוח */
    .back-btn .stButton > button {
        border-radius: 30px !important;
        border: 2px solid var(--neon-purple) !important;
        background: var(--bg-cyber-dark) !important;
        color: #ffffff !important;
        font-family: 'Orbitron', sans-serif !important;
        box-shadow: 0 0 15px rgba(189, 0, 255, 0.4) !important;
    }
    </style>
    """, unsafe_allow_html=True)
