import sys
import os
import time
import io
import sqlite3
import datetime
import base64
import json
import re
from pypdf import PdfReader

# Enforce UTF-8 encoding across runtime environments
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from google import genai
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate
from gtts import gTTS
import streamlit as st
import streamlit.components.v1 as components

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Saṃskṛta-Krīḍā-Guruḥ | संस्कृत-क्रीडा-गुरुः",
    page_icon="🚩",
    layout="wide",
    initial_sidebar_state="expanded",
)

ACTIVE_MODEL = "gemini-3.6-flash"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "sanskrit_guru_master.db")

# --- RESILIENT GEMINI CALLER ---
def generate_gemini_content(client, contents, config=None, is_json=False, max_retries=3):
    cfg = config.copy() if config else {}
    if is_json:
        cfg["response_mime_type"] = "application/json"

    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(
                model=ACTIVE_MODEL,
                contents=contents,
                config=cfg if cfg else None
            )
            return resp.text
        except Exception as e:
            err_str = str(e)
            if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise e

# --- DATABASE PERSISTENCE LAYER ---
def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA cache_size = 10000;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_profile (
            id TEXT PRIMARY KEY,
            username TEXT,
            level TEXT,
            streak INTEGER,
            xp INTEGER,
            last_active TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS vocab_vault (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            word TEXT,
            meaning TEXT,
            dhatu TEXT,
            level TEXT,
            review_due TEXT,
            interval_days INTEGER DEFAULT 1,
            repetition_count INTEGER DEFAULT 0,
            next_review_date TEXT,
            UNIQUE(user_id, word)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS feedback_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            user_id TEXT,
            teacher_name TEXT,
            user_prompt TEXT,
            acharya_response TEXT,
            feedback_type TEXT,
            remark_text TEXT
        )
    ''')
    
    # Safe Column Migration
    c.execute("PRAGMA table_info(vocab_vault)")
    existing_cols = [col[1] for col in c.fetchall()]
    for col_name, col_type in [("interval_days", "INTEGER DEFAULT 1"), ("repetition_count", "INTEGER DEFAULT 0"), ("next_review_date", "TEXT")]:
        if col_name not in existing_cols:
            try: c.execute(f"ALTER TABLE vocab_vault ADD COLUMN {col_name} {col_type}")
            except Exception: pass

    today_str = str(datetime.date.today())
    c.execute('SELECT COUNT(*) FROM user_profile')
    if c.fetchone()[0] == 0:
        c.execute('INSERT OR IGNORE INTO user_profile VALUES ("default_user", "संस्कृत-जिज्ञासुः (Learner)", "Beginner (प्रथमा)", 1, 150, ?)', (today_str,))
    
    conn.commit()
    conn.close()

init_db()

if "user_session_id" not in st.session_state:
    st.session_state.user_session_id = "default_user"

def get_user_stats(uid):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT streak, xp, level, username FROM user_profile WHERE id = ?', (uid,))
    res = c.fetchone()
    if not res:
        c.execute('INSERT OR IGNORE INTO user_profile VALUES (?, "संस्कृत-जिज्ञासुः", "Beginner (प्रथमा)", 1, 150, ?)',
                  (uid, str(datetime.date.today())))
        conn.commit()
        res = (1, 150, "Beginner (प्रथमा)", "संस्कृत-जिज्ञासुः")
    conn.close()
    return res

def update_user_xp(uid, xp_add=10):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE user_profile SET xp = xp + ? WHERE id = ?', (xp_add, uid))
    conn.commit()
    conn.close()

# --- AUDIO GENERATION ENGINE ---
@st.cache_data(show_spinner=False, max_entries=200)
def get_speech_audio_b64(text: str, tld: str = "co.in", slow: bool = False) -> str:
    try:
        clean_text = text.replace('*', '').replace('#', '').replace('-', '').replace('[', '').replace(']', '').strip()
        tts = gTTS(text=clean_text, lang='hi', tld=tld, slow=slow)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return base64.b64encode(fp.read()).decode()
    except Exception:
        return ""

def render_autotype_mic(target_input_hint=""):
    components.html(f"""
    <div style="font-family:'Plus Jakarta Sans', sans-serif; display:flex; align-items:center; gap:12px; background:linear-gradient(135deg, #2D1400 0%, #170A00 100%); padding:10px 16px; border-radius:12px; border:1.5px solid #FF8F00; margin: 8px 0; box-shadow: 0 4px 12px rgba(0,0,0,0.3);">
        <button id="autoTypeBtn" onclick="toggleAutoType()" style="background:linear-gradient(135deg, #E65100, #FF6D00); color:white; border:none; padding:7px 18px; border-radius:20px; font-weight:700; cursor:pointer; font-size:0.85rem; box-shadow: 0 2px 6px rgba(0,0,0,0.3);">
            🎙️ Auto-Type Voice
        </button>
        <span id="autoTypeStatus" style="font-size:0.82rem; color:#FFD54F; font-weight:600;">Speak in Sanskrit, Hindi, Telugu, or English... {target_input_hint}</span>
    </div>
    <script>
        var recognition = null;
        var isRec = false;
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {{
            var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognition = new SR();
            recognition.continuous = false;
            recognition.interimResults = false;
            recognition.lang = 'hi-IN';
            
            recognition.onstart = function() {{
                isRec = true;
                document.getElementById('autoTypeBtn').style.background = '#2E7D32';
                document.getElementById('autoTypeBtn').innerText = '🔴 Listening...';
                document.getElementById('autoTypeStatus').innerText = 'Transcribing your voice live into the text box...';
            }};
            recognition.onresult = function(e) {{
                var spoken = e.results[0][0].transcript;
                document.getElementById('autoTypeStatus').innerText = 'Transcribed: ' + spoken;
                var inputs = window.parent.document.querySelectorAll('textarea, input[type=text]');
                if(inputs.length > 0) {{
                    var target = inputs[inputs.length - 1];
                    target.value = spoken;
                    target.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}
            }};
            recognition.onend = function() {{
                isRec = false;
                document.getElementById('autoTypeBtn').style.background = 'linear-gradient(135deg, #E65100, #FF6D00)';
                document.getElementById('autoTypeBtn').innerText = '🎙️ Auto-Type Voice';
            }};
        }}
        function toggleAutoType() {{
            if(recognition) {{
                if(isRec) {{ recognition.stop(); }} else {{ recognition.start(); }}
            }}
        }}
    </script>
    """, height=58)

# --- MODERN GAMIFICATION THEME (MULTI-TAB COLOR MATRICES) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap');
    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
    
    /* Hero Header */
    .hero-banner {
        background: linear-gradient(135deg, #BF360C 0%, #E65100 40%, #210C00 100%);
        border-radius: 18px;
        padding: 20px 26px;
        color: #FFFFFF;
        box-shadow: 0 10px 30px rgba(230, 81, 0, 0.4);
        margin-bottom: 20px;
        border: 2px solid #FF8F00;
    }

    /* TAB 1: SAFFRON & FLAME THEME */
    .theme-tab1 {
        background: linear-gradient(145deg, #2A1202 0%, #150900 100%) !important;
        border: 2px solid #FF8F00 !important;
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 6px 20px rgba(255, 111, 0, 0.25);
        color: #FFFFFF !important;
    }
    .theme-tab1 h3, .theme-tab1 h4 { color: #FFB300 !important; font-weight: 800; }

    /* TAB 2: EMERALD & JADE THEME */
    .theme-tab2 {
        background: linear-gradient(145deg, #022415 0%, #00120A 100%) !important;
        border: 2px solid #00E676 !important;
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 6px 20px rgba(0, 230, 118, 0.25);
        color: #FFFFFF !important;
    }
    .theme-tab2 h3, .theme-tab2 h4 { color: #69F0AE !important; font-weight: 800; }

    /* TAB 3: AMETHYST & PURPLE THEME */
    .theme-tab3 {
        background: linear-gradient(145deg, #240033 0%, #12001A 100%) !important;
        border: 2px solid #D500F9 !important;
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 6px 20px rgba(213, 0, 249, 0.25);
        color: #FFFFFF !important;
    }
    .theme-tab3 h3, .theme-tab3 h4 { color: #EA80FC !important; font-weight: 800; }

    /* TAB 4: RUBY & CRIMSON THEME */
    .theme-tab4 {
        background: linear-gradient(145deg, #33000E 0%, #170006 100%) !important;
        border: 2px solid #FF1744 !important;
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 6px 20px rgba(255, 23, 68, 0.25);
        color: #FFFFFF !important;
    }
    .theme-tab4 h3, .theme-tab4 h4 { color: #FF80AB !important; font-weight: 800; }

    /* TAB 5: SAPPHIRE & CELESTIAL BLUE THEME */
    .theme-tab5 {
        background: linear-gradient(145deg, #001E3D 0%, #000F1F 100%) !important;
        border: 2px solid #00B0FF !important;
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 6px 20px rgba(0, 176, 255, 0.25);
        color: #FFFFFF !important;
    }
    .theme-tab5 h3, .theme-tab5 h4 { color: #80D8FF !important; font-weight: 800; }

    /* TAB 6: SURYA GOLD & AMBER THEME */
    .theme-tab6 {
        background: linear-gradient(145deg, #332600 0%, #1A1300 100%) !important;
        border: 2px solid #FFD600 !important;
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 6px 20px rgba(255, 214, 0, 0.25);
        color: #FFFFFF !important;
    }
    .theme-tab6 h3, .theme-tab6 h4 { color: #FFE57F !important; font-weight: 800; }

    /* TAB 7: TEMPLE TEAL & SANDALWOOD THEME */
    .theme-tab7 {
        background: linear-gradient(145deg, #002B33 0%, #00141A 100%) !important;
        border: 2px solid #00E5FF !important;
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 6px 20px rgba(0, 229, 255, 0.25);
        color: #FFFFFF !important;
    }
    .theme-tab7 h3, .theme-tab7 h4 { color: #84FFFF !important; font-weight: 800; }

    /* Option Selection Cards (Dropdowns & Radios) */
    .option-card {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 12px;
        padding: 14px 18px;
        margin-bottom: 12px;
    }
    .option-title {
        font-weight: 800;
        font-size: 1rem;
        margin-bottom: 6px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* Structured Response Cards (Roleplay) */
    .roleplay-card {
        background: #140A02 !important;
        border: 2px solid #FF8F00 !important;
        border-radius: 14px;
        padding: 18px 22px;
        margin: 12px 0;
        color: #FFFFFF !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
    }
    .roleplay-sanskrit {
        font-size: 1.4rem;
        font-weight: 800;
        color: #FFE082 !important;
        line-height: 1.5;
        margin-bottom: 10px;
    }

    /* High-Contrast Solid Answer & Explanation Box */
    .answer-box {
        background: #081C10 !important;
        border: 2px solid #2E7D32 !important;
        border-radius: 14px;
        padding: 18px 22px;
        margin-top: 16px;
        color: #FFFFFF !important;
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.45);
    }
    .answer-header {
        color: #81C784 !important;
        font-size: 1.2rem;
        font-weight: 800;
        margin: 0 0 10px 0;
    }
    .answer-badge {
        background: #FFD54F !important;
        color: #000000 !important;
        font-weight: 900 !important;
        padding: 4px 12px;
        border-radius: 6px;
        display: inline-block;
        font-size: 1.05rem;
    }
    .explanation-callout {
        background: rgba(255, 255, 255, 0.08) !important;
        border-left: 4px solid #81C784 !important;
        padding: 12px 16px;
        border-radius: 0 10px 10px 0;
        margin-top: 10px;
        font-size: 0.98rem;
        line-height: 1.6;
        color: #FFFFFF !important;
    }

    /* Custom Buttons per theme */
    div.stButton > button {
        border-radius: 24px !important;
        font-weight: 800 !important;
        font-size: 1rem !important;
        padding: 10px 24px !important;
        transition: all 0.3s ease !important;
        border: none !important;
        box-shadow: 0 4px 14px rgba(0,0,0,0.3) !important;
    }
    div.stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 20px rgba(0,0,0,0.4) !important;
    }
</style>
""", unsafe_allow_html=True)

# Helper function to parse roleplay reply into high-contrast card
def render_highlighted_roleplay_card(content_text):
    sanskrit = ""
    iast = ""
    english = ""
    tip = ""
    
    if "[संस्कृतम्]:" in content_text:
        try:
            sanskrit = content_text.split("[संस्कृतम्]:")[1].split("[IAST]:")[0].strip()
            if "[IAST]:" in content_text:
                iast = content_text.split("[IAST]:")[1].split("[English]:")[0].strip()
            if "[English]:" in content_text:
                english = content_text.split("[English]:")[1].split("[✨ Say It Better]:")[0].strip()
            if "[✨ Say It Better]:" in content_text:
                tip = content_text.split("[✨ Say It Better]:")[1].strip()
        except Exception:
            sanskrit = content_text
    else:
        sanskrit = content_text

    st.markdown(f"""
    <div class="roleplay-card">
        <div style="font-size:0.85rem; font-weight:800; color:#FF8F00; text-transform:uppercase; letter-spacing:1px; margin-bottom:6px;">
            🚩 संस्कृत-सम्भाषणम् (Spoken Sanskrit)
        </div>
        <div class="roleplay-sanskrit">{sanskrit}</div>
        {f'<div style="color:#80D8FF; font-size:0.95rem; font-style:italic; margin-bottom:6px;"><b>IAST:</b> {iast}</div>' if iast else ''}
        {f'<div style="color:#A5D6A7; font-size:1rem; font-weight:600; margin-bottom:8px;"><b>अर्थः (Meaning):</b> {english}</div>' if english else ''}
        {f'<div style="background:rgba(255,255,255,0.06); border-left:4px solid #CE93D8; padding:8px 12px; border-radius:0 8px 8px 0; color:#F3E5F5; font-size:0.9rem;">💡 <b>Say It Better / सुभाषितम्:</b> {tip}</div>' if tip else ''}
    </div>
    """, unsafe_allow_html=True)

# --- SIDEBAR: GURU PROFILE & XP TRACKER ---
u_streak, u_xp, u_level, u_name = get_user_stats(st.session_state.user_session_id)

TEACHERS = {
    "आचार्यः वसिष्ठः (Acharya Vasiṣṭha)": {"tld": "co.in", "slow": True, "desc": "Classical Sage • Deep Vedic Cadence"},
    "आचार्या गार्गी (Acharyaa Gargi)": {"tld": "com", "slow": False, "desc": "Philosophical Preceptor • Melodic & Clear"},
    "बालकः ध्रुवः (Balaka Dhruva)": {"tld": "co.uk", "slow": False, "desc": "Young Companion • Fast & Playful"}
}

with st.sidebar:
    st.markdown("### 🚩 **संस्कृत-AI-गुरुः**")
    selected_teacher_name = st.selectbox("Active Preceptor / गुरुः:", list(TEACHERS.keys()), index=0)
    t_info = TEACHERS[selected_teacher_name]
    st.caption(t_info["desc"])
    
    api_key = st.text_input(
        "Google Gemini API Key",
        type="password",
        placeholder="Paste AIza... key here",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Free API key from aistudio.google.com"
    )
    
    target_tier = st.selectbox("Proficiency Level / स्तरः:", ["Beginner (प्रथमा)", "Intermediate (मध्यमा)", "Advanced (उत्तमा)"])
    
    st.markdown("---")
    st.markdown("### 🏆 **Student Gamification Hub**")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.metric("🔥 Daily Streak", f"{u_streak} Days")
    with col_s2:
        st.metric("⭐ Accumulated XP", f"{u_xp} XP")
    
    st.caption(f"Rank: **{u_level}**")
    
    if st.button("🔄 Clear Active Session", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# --- APP HERO BANNER ---
st.markdown("""
<div class="hero-banner">
    <h2 style="margin:0; font-weight:900; letter-spacing:0.5px;">🚩 Saṃskṛta-Krīḍā-Guruḥ (संस्कृत-क्रीडा-गुरुः)</h2>
    <p style="margin:4px 0 0 0; opacity:0.95; font-size:0.95rem;">Multi-Themed Gamified Sanskrit AI • Amarakośa • Rūpa Arena • Chandaḥ • Mottos • Pañcāṅga</p>
</div>
""", unsafe_allow_html=True)

# --- 7 MASTER TABS ---
tab_roleplay, tab_trans, tab_amara, tab_rupa, tab_chandas, tab_motto, tab_samskriti = st.tabs([
    "💬 1. Saṃbhāṣaṇa (Roleplay)",
    "🌐 2. Anuvāda-Setu (Translator)",
    "📖 3. Amarakośa-Vyūha (Thesaurus)",
    "🏛️ 4. Rūpa-Sādhana (Grammar Arena)",
    "🕉️ 5. Chandaḥ Engine (Metre)",
    "🚩 6. Saṃsthā-Dhyeya (Mottos)",
    "🛕 7. Saṃskṛti-Jñāna (Vedas & Festivals)"
])

# =========================================================
# TAB 1: SAFFRON & FLAME THEME (ROLEPLAY)
# =========================================================
with tab_roleplay:
    st.markdown("""
    <div class="theme-tab1">
        <h3>💬 Saṃbhāṣaṇa Arena (सजीव-सम्भाषणम्)</h3>
        <p style="color:#DDD; margin:0;">Immerse yourself in authentic spoken Sanskrit dialogues with real-time feedback.</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="option-card"><div class="option-title" style="color:#FFB300;">🎭 Choose Roleplay Context:</div>', unsafe_allow_html=True)
    scenario = st.selectbox(
        "Select Scenario:",
        [
            "At Gurukula / Classroom (गुरुकुलम् - शिष्टाचारः)",
            "At the Market (विपणिः - शाकक्रयणम् / Purchasing Vegetables)",
            "Vedic Debate & Philosophy (शास्त्रार्थ-सभा)",
            "Welcoming Guests at Home (अतिथि-सत्कारः)",
            "Open Free Sanskrit Dialogue (मुक्त-सम्भाषणम्)"
        ],
        label_visibility="collapsed"
    )
    st.markdown('</div>', unsafe_allow_html=True)
    
    for idx, msg in enumerate(st.session_state.chat_history):
        role = "assistant" if msg["role"] == "model" else "user"
        if role == "user":
            with st.chat_message("user"):
                st.markdown(f"**🗣️ You:** {msg['content']}")
        else:
            with st.chat_message("assistant"):
                render_highlighted_roleplay_card(msg["content"])
                if "[संस्कृतम्]:" in msg["content"]:
                    s_part = msg["content"].split("[संस्कृतम्]:")[1].split("[")[0].strip()
                    aud_b64 = get_speech_audio_b64(s_part, t_info["tld"], t_info["slow"])
                    if aud_b64:
                        st.audio(f"data:audio/mp3;base64,{aud_b64}", format="audio/mp3")

    render_autotype_mic("into the roleplay prompt")
    
    if user_prompt := st.chat_input("Speak or type in Sanskrit / English / Telugu..."):
        if not api_key:
            st.warning("⚠️ Enter Gemini API Key in the sidebar.")
            st.stop()
            
        client = genai.Client(api_key=api_key)
        is_dev = any("\u0900" <= char <= "\u097f" for char in user_prompt)
        prompt_formatted = user_prompt if is_dev else f"{user_prompt} ({transliterate(user_prompt, sanscript.ITRANS, sanscript.DEVANAGARI)})"
        
        st.session_state.chat_history.append({"role": "user", "content": prompt_formatted})
        with st.chat_message("user"):
            st.markdown(f"**🗣️ You:** {prompt_formatted}")
            
        with st.chat_message("assistant"):
            with st.spinner("गुरुः चिन्तयति..."):
                system_prompt = f"""You are '{selected_teacher_name}', an encouraging Sanskrit guru.
Level: {target_tier}. Scenario: {scenario}.
Respond in 2-3 spoken sentences in Sarala Samskritam. Finish with a friendly question.
Format:
[संस्कृतम्]: <Sanskrit reply>
[IAST]: <Romanized>
[English]: <Meaning>
[✨ Say It Better]: <Idiomatic alternative>
"""
                try:
                    contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": str(m["content"])}]} for m in st.session_state.chat_history]
                    reply_text = generate_gemini_content(client, contents, config={"system_instruction": system_prompt, "temperature": 0.2, "max_output_tokens": 450})
                    render_highlighted_roleplay_card(reply_text)
                    st.session_state.chat_history.append({"role": "model", "content": reply_text})
                    update_user_xp(st.session_state.user_session_id, 10)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

# =========================================================
# TAB 2: EMERALD JADE THEME (TRANSLATOR)
# =========================================================
with tab_trans:
    st.markdown("""
    <div class="theme-tab2">
        <h3>🌐 Anuvāda-Setu (अनुवाद-सेतुः)</h3>
        <p style="color:#C8E6C9; margin:0;">Sentence-by-Sentence Universal Translation with Sandhi Split and Paninian Grammar.</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="option-card"><div class="option-title" style="color:#00E676;">🔄 Translation Direction:</div>', unsafe_allow_html=True)
    t_dir = st.radio("Select Direction:", ["Any Language ➔ Sanskrit (संस्कृतम्)", "Sanskrit ➔ Regional Language / English"], horizontal=True, label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)
    
    render_autotype_mic("into the translation box")
    t_input = st.text_area("Enter complete paragraph or sentences:", value="Knowledge gives humility. From humility comes worthiness. With wealth comes righteousness, and then happiness.", height=110)
    
    if st.button("🚀 Translate & Dissect Paragraph / अनुवादं कुरु", use_container_width=True) and t_input.strip():
        if not api_key:
            st.warning("⚠️ Enter Gemini API Key in the sidebar.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Translating and parsing morphology..."):
            try:
                t_prompt = f"""Translate the following text. Split sentence-by-sentence.
Direction: {t_dir}.
Return a JSON array of objects with keys:
- "original": original sentence
- "sanskrit": translated Sanskrit (Devanagari)
- "iast": Romanized transliteration
- "padaccheda": Sandhi and word-by-word grammatical dissection
- "grammar_note": key Paninian rule or Vibhakti applied

Text:
{t_input}
"""
                resp_json = generate_gemini_content(client, [{"role": "user", "parts": [{"text": t_prompt}]}], is_json=True)
                results = json.loads(resp_json)
                st.success(f"🎉 Translated {len(results)} sentences successfully! (+15 XP)")
                update_user_xp(st.session_state.user_session_id, 15)
                
                for idx, item in enumerate(results, 1):
                    st.markdown(f"""
                    <div style="background:#001A0E; border:2px solid #00E676; border-radius:14px; padding:18px; margin-bottom:14px; color:#FFFFFF; box-shadow:0 4px 14px rgba(0,230,118,0.25);">
                        <div style="font-size:0.85rem; font-weight:800; color:#00E676; text-transform:uppercase;">
                            Sentence #{idx}
                        </div>
                        <div style="font-size:0.95rem; color:#DDD; margin-top:4px;">
                            <b>Original:</b> {item.get('original')}
                        </div>
                        <div style="font-size:1.4rem; font-weight:800; color:#FFE082; margin:6px 0;">
                            {item.get('sanskrit')}
                        </div>
                        <div style="font-size:0.95rem; color:#80D8FF; font-style:italic;">
                            <b>IAST:</b> {item.get('iast')}
                        </div>
                        <div style="background:rgba(255,255,255,0.06); border:1px dashed #00E676; padding:8px 12px; border-radius:8px; color:#C8E6C9; font-size:0.92rem; margin-top:8px;">
                            <b>पदच्छेदः एवं व्याकरणम्:</b> {item.get('padaccheda')} • <i>{item.get('grammar_note')}</i>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    aud_b64 = get_speech_audio_b64(item.get('sanskrit', ''))
                    if aud_b64:
                        st.audio(f"data:audio/mp3;base64,{aud_b64}", format="audio/mp3")
            except Exception as e:
                st.error(f"Translation Error: {str(e)}")

# =========================================================
# TAB 3: AMETHYST PURPLE THEME (AMARAKOŚA)
# =========================================================
with tab_amara:
    st.markdown("""
    <div class="theme-tab3">
        <h3>📖 Amarakośa-Vyūha (अमरकोश-व्यूहः)</h3>
        <p style="color:#E1BEE7; margin:0;">Synonym Challenges, Thesaurus Mazes, and Ancient Word Hunt Games.</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="option-card"><div class="option-title" style="color:#EA80FC;">🔮 Select Challenge Mode:</div>', unsafe_allow_html=True)
    amara_game = st.selectbox("Choose Mode:", ["1. Synonym Matching (पर्यायपद-मेलनम्)", "2. Odd One Out (विजातीय-पद-चयनम्)", "3. Word Hunt & Śloka Clues"], label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)
    
    if amara_game.startswith("1"):
        st.markdown('<div class="option-card"><div class="option-title" style="color:#EA80FC;">🎯 Match the Amarakośa Synonyms:</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("<b>1. अग्निः (Fire) ➔</b>", unsafe_allow_html=True)
            a1 = st.selectbox("Match for अग्निः:", ["वैश्वानरः (Amarakośa)", "तोयदः", "शशाङ्कः", "पादपः"], key="am_1", label_visibility="collapsed")
            st.markdown("<b>2. सूर्यः (Sun) ➔</b>", unsafe_allow_html=True)
            a2 = st.selectbox("Match for सूर्यः:", ["दिनकरः / मार्तण्डः", "जलधिः", "पन्नगः", "गिरीन्द्रः"], key="am_2", label_visibility="collapsed")
        with c2:
            st.markdown("<b>3. सिंहः (Lion) ➔</b>", unsafe_allow_html=True)
            a3 = st.selectbox("Match for सिंहः:", ["मृगेन्द्रः / पञ्चाननः", "वारणः", "मर्कटः", "भुजङ्गः"], key="am_3", label_visibility="collapsed")
            st.markdown("<b>4. पृथिवी (Earth) ➔</b>", unsafe_allow_html=True)
            a4 = st.selectbox("Match for पृथिवी:", ["वसुन्धरा / मेदिनी", "गगनम्", "पवनः", "अर्णवः"], key="am_4", label_visibility="collapsed")
        st.markdown('</div>', unsafe_allow_html=True)
            
        if st.button("Submit Amarakośa Matches / उत्तरं समर्पय", key="btn_amara", use_container_width=True):
            is_a1 = a1.startswith("वैश्वानरः")
            is_a2 = a2.startswith("दिनकरः")
            is_a3 = a3.startswith("मृगेन्द्रः")
            is_a4 = a4.startswith("वसुन्धरा")
            score = is_a1 + is_a2 + is_a3 + is_a4
            
            if score == 4:
                st.balloons()
                st.success("🏆 सम्पूर्णं सत्यम्! All 4 synonyms matched accurately! (+40 XP)")
                update_user_xp(st.session_state.user_session_id, 40)
            else:
                st.warning(f"Score: {score}/4.")
                
            st.markdown(f"""
            <div class="answer-box">
                <div class="answer-header">🔑 Complete Amarakośa Synonym Key:</div>
                <ul style="margin:0; padding-left:20px; font-size:1rem; line-height:2.0; color:#FFFFFF;">
                    <li><b>अग्निः (Fire):</b> <span class="answer-badge">वैश्वानरः / वह्निः / पावकः</span> {'✅' if is_a1 else '❌'}</li>
                    <li><b>सूर्यः (Sun):</b> <span class="answer-badge">दिनकरः / मार्तण्डः / भानुः</span> {'✅' if is_a2 else '❌'}</li>
                    <li><b>सिंहः (Lion):</b> <span class="answer-badge">मृगेन्द्रः / पञ्चाननः / केसरी</span> {'✅' if is_a3 else '❌'}</li>
                    <li><b>पृथिवी (Earth):</b> <span class="answer-badge">वसुन्धरा / मेदिनी / उर्वी</span> {'✅' if is_a4 else '❌'}</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)

    elif amara_game.startswith("2"):
        st.markdown('<div class="option-card"><div class="option-title" style="color:#EA80FC;">🔍 Identify the Intruder Word:</div>', unsafe_allow_html=True)
        st.markdown("**Group:** `[चन्द्रः, हिमांशुः, सुधाकरः, भास्करः]`")
        intruder = st.radio("Which word does NOT belong to the group?", ["चन्द्रः (Moon)", "हिमांशुः (Moon)", "सुधाकरः (Moon)", "भास्करः (Sun - Intruder)"])
        st.markdown('</div>', unsafe_allow_html=True)
        
        if st.button("Check Intruder / उत्तरं पश्य", use_container_width=True):
            if "भास्करः" in intruder:
                st.success("✅ साधु! 'भास्करः' means Sun, while the rest are synonyms for the Moon. (+15 XP)")
                update_user_xp(st.session_state.user_session_id, 15)
            else:
                st.error("❌ Incorrect choice.")
            
            st.markdown("""
            <div class="answer-box">
                <div class="answer-header">🔑 Correct Answer & Detailed Explanation:</div>
                <div style="margin-bottom:8px; font-size:1.05rem; color:#FFFFFF;">
                    <b>Correct Intruder:</b> <span class="answer-badge">भास्करः (The Sun)</span>
                </div>
                <div class="explanation-callout">
                    <b>विवरणम् (Explanation):</b><br>
                    • <b>भास्करः</b> means the <b>Sun</b> (भास् + करः = maker of light).<br>
                    • <i>चन्द्रः, हिमांशुः</i> (he of cool rays), and <i>सुधाकरः</i> (mine of nectar) are all classical Amarakośa synonyms for the <b>Moon (शशाङ्कः)</b>.
                </div>
            </div>
            """, unsafe_allow_html=True)

    else:
        st.markdown('<div class="option-card"><div class="option-title" style="color:#EA80FC;">📜 Amarakośa Verse Clue & Word Hunt:</div>', unsafe_allow_html=True)
        st.code("खं नभो रोदसी चाभ्रं पुष्करं विष्णुपदं नमः। (अमरकोशः १.२.१)")
        ans_hunt = st.text_input("Which cosmic entity is described in this Amarakośa verse? (English/Sanskrit):")
        st.markdown('</div>', unsafe_allow_html=True)
        
        if st.button("Verify Word Hunt / समाधानं पश्य", use_container_width=True):
            is_right = any(k in ans_hunt.lower() for k in ["sky", "space", "आकाश", "गगन", "द्यौः", "खम्", "नभः"])
            if is_right:
                st.success("🎉 उत्कृष्टम्! Correctly identified! (+25 XP)")
                update_user_xp(st.session_state.user_session_id, 25)
            else:
                st.error("❌ Incorrect identification.")
            
            st.markdown("""
            <div class="answer-box">
                <div class="answer-header">🔑 Correct Solution & Lexicon Note:</div>
                <div style="margin-bottom:8px; font-size:1.05rem; color:#FFFFFF;">
                    <b>Target Entity:</b> <span class="answer-badge">आकाशः / गगनम् (Sky / Space / Firmament)</span>
                </div>
                <div class="explanation-callout">
                    <b>Listed Amarakośa Synonyms in Verse:</b><br>
                    <i>खम् (Kham), नभः (Nabhaḥ), रोदसी (Rodasī), अभ्रम् (Abhram), पुष्करम् (Puṣkaram), विष्णुपदम् (Viṣṇupadam).</i>
                </div>
            </div>
            """, unsafe_allow_html=True)

# =========================================================
# TAB 4: RUBY CRIMSON THEME (RŪPA ARENA)
# =========================================================
with tab_rupa:
    st.markdown("""
    <div class="theme-tab4">
        <h3>🏛️ Rūpa-Sādhana (रूप-साधना)</h3>
        <p style="color:#FFCDD2; margin:0;">Declension Grid Matrices (Śabdarūpa) & Verb Tense Conjugations (Dhāturūpa).</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="option-card"><div class="option-title" style="color:#FF5252;">⚔️ Select Grammar Discipline:</div>', unsafe_allow_html=True)
    r_mode = st.radio("Select Discipline:", ["1. Śabdarūpa Declension Grid (शब्दरूपाणि)", "2. Dhāturūpa Tense Matcher (धातुरूपाणि)"], horizontal=True, label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)
    
    if r_mode.startswith("1"):
        st.markdown('<div class="option-card"><div class="option-title" style="color:#FF5252;">🧩 Complete the Declension Grid for \'राम\' (Masculine):</div>', unsafe_allow_html=True)
        col_g1, col_g2, col_g3 = st.columns(3)
        with col_g1:
            st.caption("प्रथमा (Nominative):")
            r1 = st.text_input("एकवचनम्:", value="रामः", disabled=True)
            r2 = st.text_input("द्विवचनम् (Fill):", key="r_dvi")
            r3 = st.text_input("बहुवचनम् (Fill):", key="r_bahu")
        with col_g2:
            st.caption("तृतीया (Instrumental):")
            r4 = st.text_input("एकवचनम् (Fill):", key="r_inst_1")
            r5 = st.text_input("द्विवचनम्:", value="रामाभ्याम्", disabled=True)
            r6 = st.text_input("बहुवचनम् (Fill):", key="r_inst_3")
        with col_g3:
            st.caption("सप्तमी (Locative):")
            r7 = st.text_input("एकवचनम् (Fill):", key="r_loc_1")
            r8 = st.text_input("द्विवचनम् (Fill):", key="r_loc_2")
            r9 = st.text_input("बहुवचनम्:", value="रामेषु", disabled=True)
        st.markdown('</div>', unsafe_allow_html=True)

        if st.button("Validate Declension Matrix / रूप-परीक्षणम्", use_container_width=True):
            c_dvi = (r2.strip() in ["रामौ", "ramau"])
            c_bahu = (r3.strip() in ["रामाः", "ramaah", "ramAH"])
            c_inst1 = (r4.strip() in ["रामेण", "ramena", "rameNa"])
            c_inst3 = (r6.strip() in ["रामैः", "ramaih", "ramaiH"])
            c_loc1 = (r7.strip() in ["रामे", "rame"])
            c_loc2 = (r8.strip() in ["रामयोः", "ramayoh", "ramayoH"])
            
            total_corr = c_dvi + c_bahu + c_inst1 + c_inst3 + c_loc1 + c_loc2
            if total_corr == 6:
                st.balloons()
                st.success("🏆 सम्पूर्णं शुद्धम्! All 6 declension slots are perfectly accurate! (+50 XP)")
                update_user_xp(st.session_state.user_session_id, 50)
            else:
                st.warning(f"Score: {total_corr}/6 correct.")
                
            st.markdown(f"""
            <div class="answer-box">
                <div class="answer-header">🔑 Complete Śabdarūpa Answer Key (राम - Masculine):</div>
                <table style="width:100%; border-collapse:collapse; color:#FFFFFF; font-size:0.95rem; margin-top:8px;">
                    <tr style="border-bottom:2px solid #2E7D32; background:rgba(255,255,255,0.05);">
                        <th style="text-align:left; padding:8px;">विभक्तिः (Case)</th>
                        <th style="text-align:left; padding:8px;">एकवचनम्</th>
                        <th style="text-align:left; padding:8px;">द्विवचनम्</th>
                        <th style="text-align:left; padding:8px;">बहुवचनम्</th>
                    </tr>
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.1);">
                        <td style="padding:8px;"><b>प्रथमा (Nom):</b></td>
                        <td style="padding:8px; color:#AAA;">रामः</td>
                        <td style="padding:8px;"><span class="answer-badge">रामौ</span> {'✅' if c_dvi else '❌'}</td>
                        <td style="padding:8px;"><span class="answer-badge">रामाः</span> {'✅' if c_bahu else '❌'}</td>
                    </tr>
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.1);">
                        <td style="padding:8px;"><b>तृतीया (Inst):</b></td>
                        <td style="padding:8px;"><span class="answer-badge">रामेण</span> {'✅' if c_inst1 else '❌'}</td>
                        <td style="padding:8px; color:#AAA;">रामाभ्याम्</td>
                        <td style="padding:8px;"><span class="answer-badge">रामैः</span> {'✅' if c_inst3 else '❌'}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px;"><b>सप्तमी (Loc):</b></td>
                        <td style="padding:8px;"><span class="answer-badge">रामे</span> {'✅' if c_loc1 else '❌'}</td>
                        <td style="padding:8px;"><span class="answer-badge">रामयोः</span> {'✅' if c_loc2 else '❌'}</td>
                        <td style="padding:8px; color:#AAA;">रामेषु</td>
                    </tr>
                </table>
            </div>
            """, unsafe_allow_html=True)

    else:
        st.markdown('<div class="option-card"><div class="option-title" style="color:#FF5252;">⚡ Dhāturūpa Tense & Mood Classifier:</div>', unsafe_allow_html=True)
        dh_sample = st.selectbox("Analyze Verb Form:", ["पठिष्यति (Root: पठ्)", "अगच्छत् (Root: गम्)", "भवतु (Root: भू)", "कुर्यात् (Root: कृ)"])
        c_lakara = st.selectbox("Select the correct Lakāra (Tense/Mood):", [
            "लट् (Present Tense)",
            "लृट् (Future Tense)",
            "लङ् (Past Imperfect)",
            "लोट् (Imperative Mood)",
            "विधिलिङ् (Potential/Optative Mood)"
        ])
        st.markdown('</div>', unsafe_allow_html=True)
        
        if st.button("Submit Lakāra Assessment / लकार-निर्णयः", use_container_width=True):
            correct_map = {
                "पठिष्यति (Root: पठ्)": ("लृट् (Future Tense)", "Identified by the future suffix '-ष्यति' (लृट्-लकारः)."),
                "अगच्छत् (Root: गम्)": ("लङ् (Past Imperfect)", "Identified by the augment 'अ-' prefix and halanta ending (लङ्-लकारः)."),
                "भवतु (Root: भू)": ("लोट् (Imperative Mood)", "Identified by command/benedictive ending '-तु' (लोट्-लकारः)."),
                "कुर्यात् (Root: कृ)": ("विधिलिङ् (Potential/Optative Mood)", "Identified by potential optative ending '-यात्' (विधिलिङ्-लकारः).")
            }
            target_ans, target_rule = correct_map[dh_sample]
            
            if target_ans.split()[0] in c_lakara:
                st.success("✅ साधु! Correct Lakāra identified accurately! (+20 XP)")
                update_user_xp(st.session_state.user_session_id, 20)
            else:
                st.error("❌ Incorrect Lakāra.")
                
            st.markdown(f"""
            <div class="answer-box">
                <div class="answer-header">🔑 Correct Verb Analysis & Lakāra Key:</div>
                <div style="margin-bottom:8px; font-size:1.05rem; color:#FFFFFF;">
                    <b>Target Verb:</b> <span style="color:#FFD54F;">{dh_sample}</span><br>
                    <b>Correct Lakāra:</b> <span class="answer-badge">{target_ans}</span>
                </div>
                <div class="explanation-callout">
                    <b>Pāṇinian Rule & Marker:</b><br>
                    <i>{target_rule}</i>
                </div>
            </div>
            """, unsafe_allow_html=True)

# =========================================================
# TAB 5: SAPPHIRE BLUE THEME (CHANDAḤ METRE)
# =========================================================
with tab_chandas:
    st.markdown("""
    <div class="theme-tab5">
        <h3>🕉️ Pingala Chandaḥ-Śāstram (छन्दो-विश्लेषकः)</h3>
        <p style="color:#B3E5FC; margin:0;">Metrical Scansion with Laghu (।) and Guru (ऽ) Syllabic Breakdown and Gana Formations.</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="option-card"><div class="option-title" style="color:#40C4FF;">📜 Verse Input for Scansion:</div>', unsafe_allow_html=True)
    v_scan = st.text_area(
        "Enter Sanskrit verse:",
        value="वागर्थाविव सम्प्रुक्तौ वागर्थप्रतिपत्तये।\nजगतः पितरौ वन्दे पार्वतीपरमेश्वरौ॥",
        height=90,
        label_visibility="collapsed"
    )
    st.markdown('</div>', unsafe_allow_html=True)
    
    if st.button("🚀 Scan Metre & Ganas / छन्दो-विश्लेषणम्", use_container_width=True):
        if not api_key:
            st.warning("⚠️ Enter Gemini API Key in the sidebar.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Scansion in progress..."):
            try:
                res = generate_gemini_content(
                    client,
                    [{"role": "user", "parts": [{"text": f"Perform Pingala Chandas scansion on: '{v_scan}'. Return: 1. Metre Name, 2. Laghu (।) and Guru (ऽ) syllabic mapping per pāda, 3. Gana breakdown (e.g. ma-ya-ra-sa), 4. Metric rule definition."}]}]
                )
                st.markdown(f"""
                <div style="background:#001729; border:2px solid #00B0FF; border-radius:14px; padding:20px; color:#FFFFFF; box-shadow:0 4px 16px rgba(0,176,255,0.3);">
                    <div style="font-size:1.15rem; font-weight:800; color:#80D8FF; margin-bottom:10px;">
                        📜 Pingala Metrical Scansion Report:
                    </div>
                    <div style="font-size:0.98rem; color:#FFFFFF; line-height:1.7;">
                        {res}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                update_user_xp(st.session_state.user_session_id, 20)
            except Exception as e:
                st.error(str(e))

# =========================================================
# TAB 6: SURYA GOLD THEME (MOTTOS)
# =========================================================
with tab_motto:
    st.markdown("""
    <div class="theme-tab6">
        <h3>🚩 Saṃsthā-Dhyeyavākya (संस्था-ध्येयवाक्यानि)</h3>
        <p style="color:#FFF9C4; margin:0;">National, Global & Academic Sanskrit Mottos with Scriptural Origins.</p>
    </div>
    """, unsafe_allow_html=True)
    
    mottos_db = [
        {"motto": "सत्यमेव जयते", "meaning": "Truth alone triumphs", "org": "Republic of India (भारत-सर्वकारः)", "source": "Muṇḍaka Upaniṣad (३.१.६)"},
        {"motto": "योगक्षेमं वहाम्यहम्", "meaning": "I secure what they have and provide what they lack", "org": "Life Insurance Corporation of India (LIC)", "source": "Bhagavad Gītā (९.२२)"},
        {"motto": "धर्मो रक्षति रक्षितः", "meaning": "Dharma protects those who protect it", "org": "Supreme Court / R&AW / NLSIU", "source": "Mahābhārata (Vana Parva)"},
        {"motto": "नभःस्पृशं दीप्तम्", "meaning": "Touch the Sky with Glory", "org": "Indian Air Force (भारतीय-वायुसेना)", "source": "Bhagavad Gītā (११.२४)"},
        {"motto": "विद्यामृतमश्नुते", "meaning": "Attain immortality through knowledge", "org": "NCERT", "source": "Īśāvāsya Upaniṣad (११)"},
        {"motto": "शं नो वरुणः", "meaning": "May the Lord of Oceans be auspicious unto us", "org": "Indian Navy (भारतीय-नौसेना)", "source": "Taittirīya Upaniṣad (१.१.१)"}
    ]
    
    for m in mottos_db:
        st.markdown(f"""
        <div class="motto-badge">
            <h4 style="color:#FFD54F; margin:0; font-size:1.15rem;">🚩 "{m['motto']}"</h4>
            <div style="font-size:0.95rem; color:#FFF; margin-top:2px;"><b>Institution:</b> {m['org']}</div>
            <div style="font-size:0.88rem; color:#FFE082;"><b>Scriptural Source:</b> {m['source']} | <i>"{m['meaning']}"</i></div>
        </div>
        """, unsafe_allow_html=True)
        
    st.markdown('<div class="option-card"><div class="option-title" style="color:#FFD600;">🎮 Quiz: Identify the Scriptural Origin:</div>', unsafe_allow_html=True)
    m_quiz = st.radio("Where is the motto **'योगक्षेमं वहाम्यहम्'** taken from?", ["Bhagavad Gītā (Chapter 9)", "Muṇḍaka Upaniṣad", "Rāmāyaṇa", "Ṛgveda"])
    st.markdown('</div>', unsafe_allow_html=True)
    
    if st.button("Verify Motto Source / स्रोत-परीक्षणम्", use_container_width=True):
        is_correct = ("Bhagavad Gītā" in m_quiz)
        if is_correct:
            st.success("🎉 उत्कृष्टम्! Correct scriptural source identified! (+25 XP)")
            update_user_xp(st.session_state.user_session_id, 25)
        else:
            st.error("❌ Incorrect choice.")
            
        st.markdown("""
        <div class="answer-box">
            <div class="answer-header">🔑 Correct Source & Verse Details:</div>
            <div style="margin-bottom:8px; font-size:1.05rem; color:#FFFFFF;">
                <b>Correct Source:</b> <span class="answer-badge">Bhagavad Gītā (Chapter 9, Verse 22)</span>
            </div>
            <div class="explanation-callout">
                <b>Full Śloka:</b><br>
                <i>अनन्याश्चिन्तयन्तो मां ये जनाः पर्युपासते। तेषां नित्याभियुक्तानां <b>योगक्षेमं वहाम्यहम्</b>॥</i><br>
                <b>Meaning:</b> <i>"To those who worship Me with single-minded devotion, I carry what they lack and preserve what they have."</i>
            </div>
        </div>
        """, unsafe_allow_html=True)

# =========================================================
# TAB 7: TEMPLE TEAL THEME (VEDAS & PAÑCĀṄGA)
# =========================================================
with tab_samskriti:
    st.markdown("""
    <div class="theme-tab7">
        <h3>🛕 Saṃskṛti-Jñāna (संस्कृति-ज्ञानम्)</h3>
        <p style="color:#B2EBF2; margin:0;">Vedic Literature Trees, Pañcāṅga Tithis, and Traditional Festivals.</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="option-card"><div class="option-title" style="color:#00E5FF;">🛕 Select Cultural Domain:</div>', unsafe_allow_html=True)
    s_mode = st.selectbox("Select Domain:", ["1. Pañcāṅga Tithi & Festival Matcher", "2. Vedic Literature & Upaniṣad Tree", "3. True / False Cultural Lightning Quiz"], label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)
    
    if s_mode.startswith("1"):
        st.markdown('<div class="option-card"><div class="option-title" style="color:#00E5FF;">📅 Match the Vedic Tithi to its Festival:</div>', unsafe_allow_html=True)
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            st.markdown("<b>1. श्रावण-पूर्णिमा (Śrāvaṇa Pūrṇimā):</b>", unsafe_allow_html=True)
            t1 = st.selectbox("Tithi 1:", ["रक्षाबन्धनम् / संस्कृत-दिनम्", "दीपावली", "होली", "विजयादशमी"], label_visibility="collapsed")
            st.markdown("<b>2. कार्तिक-अमावास्या (Kārttika Amāvāsyā):</b>", unsafe_allow_html=True)
            t2 = st.selectbox("Tithi 2:", ["दीपावली (Dīpāvalī)", "महाशिवरात्रिः", "रामनवमी", "गणेश-चतुर्थी"], label_visibility="collapsed")
        with col_f2:
            st.markdown("<b>3. फाल्गुन-पूर्णिमा (Phālguna Pūrṇimā):</b>", unsafe_allow_html=True)
            t3 = st.selectbox("Tithi 3:", ["होलिकोत्सवः (Holī)", "रथयात्रा", "मकर-सङ्क्रान्तिः", "गुरु-पूर्णिमा"], label_visibility="collapsed")
            st.markdown("<b>4. भाद्रपद-शुक्ल-चतुर्थी:</b>", unsafe_allow_html=True)
            t4 = st.selectbox("Tithi 4:", ["विनायक-चतुर्थी (Ganesha Chaturthi)", "जन्माष्टमी", "दशहरा", "उगादिः"], label_visibility="collapsed")
        st.markdown('</div>', unsafe_allow_html=True)
            
        if st.button("Submit Pañcāṅga Assessment / तिथि-निर्णयः", use_container_width=True):
            is_t1 = t1.startswith("रक्षाबन्धनम्")
            is_t2 = t2.startswith("दीपावली")
            is_t3 = t3.startswith("होलिकोत्सवः")
            is_t4 = t4.startswith("विनायक")
            f_score = is_t1 + is_t2 + is_t3 + is_t4
            
            if f_score == 4:
                st.balloons()
                st.success("🏆 सम्पूर्णं सत्यम्! All 4 Pañcāṅga festival dates matched accurately! (+40 XP)")
                update_user_xp(st.session_state.user_session_id, 40)
            else:
                st.warning(f"Score: {f_score}/4.")
                
            st.markdown(f"""
            <div class="answer-box">
                <div class="answer-header">🔑 Pañcāṅga & Tithi Answer Key:</div>
                <ul style="margin:0; padding-left:20px; font-size:1rem; line-height:2.0; color:#FFFFFF;">
                    <li><b>श्रावण-पूर्णिमा:</b> <span class="answer-badge">रक्षाबन्धनम् / विश्व-संस्कृत-दिनम्</span> {'✅' if is_t1 else '❌'}</li>
                    <li><b>कार्तिक-अमावास्या:</b> <span class="answer-badge">दीपावली (Lakṣmī Pūjana)</span> {'✅' if is_t2 else '❌'}</li>
                    <li><b>फाल्गुन-पूर्णिमा:</b> <span class="answer-badge">होलिकोत्सवः / कामदहनम्</span> {'✅' if is_t3 else '❌'}</li>
                    <li><b>भाद्रपद-शुक्ल-चतुर्थी:</b> <span class="answer-badge">विनायक-चतुर्थी (Ganesha Chaturthi)</span> {'✅' if is_t4 else '❌'}</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)

    elif s_mode.startswith("2"):
        st.markdown("""
        <div style="background:rgba(255,255,255,0.05); border:1px solid #00E5FF; border-radius:12px; padding:14px; margin-bottom:12px;">
            <h4 style="color:#00E5FF; margin:0 0 6px 0;">📜 Vedic Lineage Tree:</h4>
            <ul style="margin:0; padding-left:20px; color:#DDD; font-size:0.95rem;">
                <li><b>ऋग्वेदः:</b> ऐतरेयोपनिषद् • गायत्री-मन्त्रः (३.६२.१०)</li>
                <li><b>यजुर्वेदः:</b> ईशावास्योपनिषद्, बृहदारण्यकोपनिषद्, तैत्तिरीयोपनिषद्</li>
                <li><b>सामवेदः:</b> छान्दोग्योपनिषद्, केनोपनिषद् (गान-परम्परा)</li>
                <li><b>अथर्ववेदः:</b> मुण्डकोपनिषद्, माण्डूक्योपनिषद्, प्रश्नोपनिषद्</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown('<div class="option-card"><div class="option-title" style="color:#00E5FF;">❓ Mahāvākya Identification Quiz:</div>', unsafe_allow_html=True)
        q_v = st.radio("Which Upaniṣad contains the famous Mahāvākya **'अयमात्मा ब्रह्म'**?", ["माण्डूक्योपनिषद् (Atharvaveda)", "छान्दोग्योपनिषद्", "ईशावास्योपनिषद्"])
        st.markdown('</div>', unsafe_allow_html=True)
        
        if st.button("Submit Veda Quiz / वेदोपनिषत्-परीक्षणम्", use_container_width=True):
            is_right = ("माण्डूक्योपनिषद्" in q_v)
            if is_right:
                st.success("✅ सत्यम्! Correct Upaniṣadic source identified! (+20 XP)")
                update_user_xp(st.session_state.user_session_id, 20)
            else:
                st.error("❌ Incorrect choice.")
                
            st.markdown("""
            <div class="answer-box">
                <div class="answer-header">🔑 Mahāvākya & Upaniṣad Key:</div>
                <div style="margin-bottom:8px; font-size:1.05rem; color:#FFFFFF;">
                    <b>Correct Answer:</b> <span class="answer-badge">माण्डूक्योपनिषद् (Māṇḍūkya Upaniṣad, Verse 2)</span>
                </div>
                <div class="explanation-callout">
                    <b>Four Primary Upaniṣadic Mahāvākyas:</b><br>
                    • <i>प्रज्ञानं ब्रह्म</i> (Aitareya Upaniṣad - Ṛgveda)<br>
                    • <i>अहं ब्रह्मास्मि</i> (Bṛhadāraṇyaka Upaniṣad - Śukla Yajurveda)<br>
                    • <i>तत्त्वमसि</i> (Chāndogya Upaniṣad - Sāmaveda)<br>
                    • <b>अयमात्मा ब्रह्म</b> (Māṇḍūkya Upaniṣad - Atharvaveda)
                </div>
            </div>
            """, unsafe_allow_html=True)

    else:
        st.markdown('<div class="option-card"><div class="option-title" style="color:#00E5FF;">⚡ True / False Lightning Drill:</div>', unsafe_allow_html=True)
        tf1 = st.radio("1. Pāṇini's Aṣṭādhyāyī contains approximately 4,000 grammatical sūtras.", ["True (सत्यम्)", "False (असत्यम्)"])
        tf2 = st.radio("2. The Gāyatrī Mantra is addressed to the solar deity Savitṛ in the Ṛgveda.", ["True (सत्यम्)", "False (असत्यम्)"])
        st.markdown('</div>', unsafe_allow_html=True)
        
        if st.button("Submit Lightning Quiz / सत्यासत्य-परीक्षणम्", use_container_width=True):
            is_tf1 = tf1.startswith("True")
            is_tf2 = tf2.startswith("True")
            if is_tf1 and is_tf2:
                st.success("🏆 Both statements are verified as True! (+30 XP)")
                update_user_xp(st.session_state.user_session_id, 30)
            else:
                st.warning("Review the facts below.")
                
            st.markdown(f"""
            <div class="answer-box">
                <div class="answer-header">🔑 Fact Check & Answer Key:</div>
                <ul style="margin:0; padding-left:20px; font-size:0.98rem; line-height:1.9; color:#FFFFFF;">
                    <li><b>Statement 1:</b> <span class="answer-badge">True</span> — The Aṣṭādhyāyī contains 3,959 (~4,000) sūtras arranged across 8 chapters. {'✅' if is_tf1 else '❌'}</li>
                    <li><b>Statement 2:</b> <span class="answer-badge">True</span> — The Gāyatrī Mantra (tat savitur vareṇyaṃ...) is from Ṛgveda Mandala 3, Sūkta 62, Verse 10, addressed to Savitṛ. {'✅' if is_tf2 else '❌'}</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
