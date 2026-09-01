import sys
import os
import time
import io
import sqlite3
import datetime
import base64
import json
import re
import random
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

    # Seed Default User
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

# --- AUDIO GENERATION & AVATAR ENGINE ---
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
    <div style="font-family:'Plus Jakarta Sans', sans-serif; display:flex; align-items:center; gap:10px; background:rgba(255,111,0,0.06); padding:8px 14px; border-radius:10px; border:1px dashed #FF8F00; margin: 6px 0;">
        <button id="autoTypeBtn" onclick="toggleAutoType()" style="background:#E65100; color:white; border:none; padding:6px 16px; border-radius:18px; font-weight:bold; cursor:pointer; font-size:0.8rem;">
            🎙️ Auto-Type Voice
        </button>
        <span id="autoTypeStatus" style="font-size:0.8rem; color:#AAA;">Speak in Sanskrit, Hindi, Telugu, or English... {target_input_hint}</span>
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
                document.getElementById('autoTypeStatus').innerText = 'Transcribing your voice live...';
            }};
            recognition.onresult = function(e) {{
                var spoken = e.results[0][0].transcript;
                document.getElementById('autoTypeStatus').innerText = 'Recognized: ' + spoken;
                var inputs = window.parent.document.querySelectorAll('textarea, input[type=text]');
                if(inputs.length > 0) {{
                    var target = inputs[inputs.length - 1];
                    target.value = spoken;
                    target.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}
            }};
            recognition.onend = function() {{
                isRec = false;
                document.getElementById('autoTypeBtn').style.background = '#E65100';
                document.getElementById('autoTypeBtn').innerText = '🎙️ Auto-Type Voice';
            }};
        }}
        function toggleAutoType() {{
            if(recognition) {{
                if(isRec) {{ recognition.stop(); }} else {{ recognition.start(); }}
            }}
        }}
    </script>
    """, height=50)

# --- CSS STYLES (HIGH-CONTRAST HIGHLIGHTING) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
    
    .hero-banner {
        background: linear-gradient(135deg, #BF360C 0%, #E65100 50%, #1A0A00 100%);
        border-radius: 16px;
        padding: 16px 22px;
        color: #FFFFFF;
        box-shadow: 0 6px 22px rgba(230, 81, 0, 0.3);
        margin-bottom: 15px;
    }
    .game-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 143, 0, 0.25);
        border-radius: 14px;
        padding: 18px;
        margin-bottom: 12px;
    }
    /* HIGH-CONTRAST SOLID ANSWER & EXPLANATION BOX */
    .answer-box {
        background: #081C10 !important;
        border: 2px solid #2E7D32 !important;
        border-radius: 12px;
        padding: 16px 20px;
        margin-top: 14px;
        color: #FFFFFF !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3);
    }
    .answer-header {
        color: #81C784 !important;
        font-size: 1.15rem;
        font-weight: 800;
        margin: 0 0 10px 0;
    }
    .answer-badge {
        background: #FFD54F !important;
        color: #000000 !important;
        font-weight: 800 !important;
        padding: 2px 10px;
        border-radius: 6px;
        display: inline-block;
        font-size: 1rem;
    }
    .explanation-callout {
        background: rgba(255, 255, 255, 0.08) !important;
        border-left: 4px solid #81C784 !important;
        padding: 10px 14px;
        border-radius: 0 8px 8px 0;
        margin-top: 10px;
        font-size: 0.95rem;
        line-height: 1.6;
        color: #FFFFFF !important;
    }
    .motto-badge {
        background: linear-gradient(145deg, #3E2723, #1A0C00);
        border-left: 4px solid #FF8F00;
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 10px;
    }
</style>
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

# --- APP HERO ---
st.markdown("""
<div class="hero-banner">
    <h2 style="margin:0; font-weight:800;">🚩 Saṃskṛta-Krīḍā-Guruḥ (संस्कृत-क्रीडा-गुरुः)</h2>
    <p style="margin:2px 0 0 0; opacity:0.92; font-size:0.9rem;">Comprehensive Gamified AI • High-Contrast Explanations • Amarakośa • Rūpa Matrix • Chandaḥ</p>
</div>
""", unsafe_allow_html=True)

# --- 7 MASTER TABS ---
tab_roleplay, tab_trans, tab_amara, tab_rupa, tab_chandas, tab_motto, tab_samskriti = st.tabs([
    "💬 1. Saṃbhāṣaṇa (Roleplay)",
    "🌐 2. Anuvāda-Setu (Translator)",
    "📖 3. Amarakośa-Vyūha (Thesaurus)",
    "🏛️ 4. Rūpa-Sādhana (Grammar Arena)",
    "🕉️ 5. Chandaḥ & Śikṣā (Phonetics)",
    "🚩 6. Saṃsthā-Dhyeya (Mottos)",
    "🛕 7. Saṃskṛti-Jñāna (Vedas & Festivals)"
])

# =========================================================
# TAB 1: SAMBHĀṢAṆA (ROLEPLAY CONVERSATION)
# =========================================================
with tab_roleplay:
    st.markdown("#### 💬 Live Dialogue with AI Guru (सजीव-सम्भाषणम्)")
    scenario = st.selectbox(
        "Select Roleplay Context / प्रसङ्गः:",
        [
            "At Gurukula / Classroom (गुरुकुलम् - शिष्टाचारः)",
            "At the Market (विपणिः - शाकक्रयणम् / Purchasing Vegetables)",
            "Vedic Debate & Philosophy (शास्त्रार्थ-सभा)",
            "Welcoming Guests at Home (अतिथि-सत्कारः)",
            "Open Free Sanskrit Dialogue (मुक्त-सम्भाषणम्)"
        ]
    )
    
    for idx, msg in enumerate(st.session_state.chat_history):
        role = "assistant" if msg["role"] == "model" else "user"
        with st.chat_message(role):
            st.markdown(msg["content"])
            if role == "assistant" and "[संस्कृतम्]:" in msg["content"]:
                s_part = msg["content"].split("[संस्कृतम्]:")[1].split("[")[0].strip()
                aud_b64 = get_speech_audio_b64(s_part, t_info["tld"], t_info["slow"])
                if aud_b64:
                    st.audio(f"data:audio/mp3;base64,{aud_b64}", format="audio/mp3")

    render_autotype_mic("into the roleplay box below")
    
    if user_prompt := st.chat_input("Speak or type in Sanskrit / English / Telugu..."):
        if not api_key:
            st.warning("⚠️ Enter Gemini API Key in the sidebar.")
            st.stop()
            
        client = genai.Client(api_key=api_key)
        is_dev = any("\u0900" <= char <= "\u097f" for char in user_prompt)
        prompt_formatted = user_prompt if is_dev else f"{user_prompt} ({transliterate(user_prompt, sanscript.ITRANS, sanscript.DEVANAGARI)})"
        
        st.session_state.chat_history.append({"role": "user", "content": prompt_formatted})
        with st.chat_message("user"):
            st.markdown(prompt_formatted)
            
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
                    st.markdown(reply_text)
                    st.session_state.chat_history.append({"role": "model", "content": reply_text})
                    update_user_xp(st.session_state.user_session_id, 10)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

# =========================================================
# TAB 2: ANUVĀDA-SETU (TRANSLATOR)
# =========================================================
with tab_trans:
    st.markdown("#### 🌐 Multi-Sentence & Paragraph Batch Translator (अनुवाद-सेतुः)")
    t_dir = st.radio("Direction:", ["Any Language ➔ Sanskrit (संस्कृतम्)", "Sanskrit ➔ Regional Language / English"], horizontal=True)
    
    render_autotype_mic("into the translation box")
    t_input = st.text_area("Enter complete paragraph or sentences:", value="Knowledge gives humility. From humility comes worthiness. With wealth comes righteousness, and then happiness.", height=120)
    
    if st.button("🚀 Translate & Dissect Paragraph / सविस्तरम् अनुवादं कुरु", use_container_width=True) and t_input.strip():
        if not api_key:
            st.warning("⚠️ Enter Gemini API Key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Analyzing syntax, Sandhi, and vocabulary..."):
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
                    with st.expander(f"Sentence #{idx}: {item.get('original', '')[:60]}...", expanded=True):
                        st.markdown(f"**संस्कृतम्:** ### {item.get('sanskrit')}")
                        st.markdown(f"**IAST:** *{item.get('iast')}*")
                        st.markdown(f"**पदच्छेदः (Word Split):** `{item.get('padaccheda')}`")
                        st.caption(f"💡 व्याकरणम्: {item.get('grammar_note')}")
                        
                        aud_b64 = get_speech_audio_b64(item.get('sanskrit', ''))
                        if aud_b64:
                            st.audio(f"data:audio/mp3;base64,{aud_b64}", format="audio/mp3")
            except Exception as e:
                st.error(f"Translation Error: {str(e)}")

# =========================================================
# TAB 3: AMARAKOŚA-VYŪHA (THESAURUS GAMES + HIGHLIGHTED KEYS)
# =========================================================
with tab_amara:
    st.markdown("#### 📖 अमरकोश-व्यूहः (Amarakośa Thesaurus & Synonym Arena)")
    amara_game = st.selectbox("Choose Amarakośa Challenge:", ["1. Synonym Matching (पर्यायपद-मेलनम्)", "2. Odd One Out (विजातीय-पद-चयनम्)", "3. Word Hunt & Śloka Clues"])
    
    if amara_game.startswith("1"):
        st.markdown("""
        <div class="game-card">
            <h4 style="color:#FF8F00; margin:0 0 6px 0;">🎯 Match the Classical Synonyms</h4>
            <p style="font-size:0.88rem; color:#DDD;">Find the matching Amarakośa synonym for each base word.</p>
        </div>
        """, unsafe_allow_html=True)
        
        c1, c2 = st.columns(2)
        with c1:
            st.info("Word 1: **अग्निः (Fire)** ➔ ?")
            a1 = st.selectbox("Select match for अग्निः:", ["वैश्वानरः (Amarakośa)", "तोयदः", "शशाङ्कः", "पादपः"], key="am_1")
            st.info("Word 2: **सूर्यः (Sun)** ➔ ?")
            a2 = st.selectbox("Select match for सूर्यः:", ["दिनकरः / मार्तण्डः", "जलधिः", "पन्नगः", "गिरीन्द्रः"], key="am_2")
        with c2:
            st.info("Word 3: **सिंहः (Lion)** ➔ ?")
            a3 = st.selectbox("Select match for सिंहः:", ["मृगेन्द्रः / पञ्चाननः", "वारणः", "मर्कटः", "भुजङ्गः"], key="am_3")
            st.info("Word 4: **पृथिवी (Earth)** ➔ ?")
            a4 = st.selectbox("Select match for पृथिवी:", ["वसुन्धरा / मेदिनी", "गगनम्", "पवनः", "अर्णवः"], key="am_4")
            
        if st.button("Submit Amarakośa Matches / उत्तरं समर्पय", key="btn_amara"):
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
                
            # HIGH-CONTRAST ANSWER KEY
            st.markdown(f"""
            <div class="answer-box">
                <div class="answer-header">🔑 Complete Amarakośa Synonym Key:</div>
                <ul style="margin:0; padding-left:20px; font-size:0.98rem; line-height:1.9; color:#FFFFFF;">
                    <li><b>अग्निः (Fire):</b> <span class="answer-badge">वैश्वानरः / वह्निः / पावकः</span> {'✅' if is_a1 else '❌'}</li>
                    <li><b>सूर्यः (Sun):</b> <span class="answer-badge">दिनकरः / मार्तण्डः / भानुः</span> {'✅' if is_a2 else '❌'}</li>
                    <li><b>सिंहः (Lion):</b> <span class="answer-badge">मृगेन्द्रः / पञ्चाननः / केसरी</span> {'✅' if is_a3 else '❌'}</li>
                    <li><b>पृथिवी (Earth):</b> <span class="answer-badge">वसुन्धरा / मेदिनी / उर्वी</span> {'✅' if is_a4 else '❌'}</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)

    elif amara_game.startswith("2"):
        st.markdown("##### 🔍 Identify the Intruder (Which word is NOT a synonym?)")
        st.markdown("**Group:** `[चन्द्रः, हिमांशुः, सुधाकरः, भास्करः]`")
        intruder = st.radio("Which word does not belong to the group?", ["चन्द्रः (Moon)", "हिमांशुः (Moon)", "सुधाकरः (Moon)", "भास्करः (Sun - Intruder)"])
        if st.button("Check Intruder"):
            if "भास्करः" in intruder:
                st.success("✅ साधु! 'भास्करः' means Sun, while the rest are synonyms for the Moon. (+15 XP)")
                update_user_xp(st.session_state.user_session_id, 15)
            else:
                st.error("❌ Incorrect choice.")
            
            # HIGH-CONTRAST ANSWER & EXPLANATION
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
        st.markdown("##### 📜 Amarakośa Verse Clue & Word Hunt")
        st.code("खं नभो रोदसी चाभ्रं पुष्करं विष्णुपदं नमः। (अमरकोशः १.२.१)")
        ans_hunt = st.text_input("Which cosmic entity is described in this Amarakośa verse? (English/Sanskrit):")
        if st.button("Verify Clue"):
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
                    <b>Target Answer:</b> <span class="answer-badge">आकाशः / गगनम् (Sky / Space / Firmament)</span>
                </div>
                <div class="explanation-callout">
                    <b>Listed Amarakośa Synonyms in Verse:</b><br>
                    <i>खम् (Kham), नभः (Nabhaḥ), रोदसी (Rodasī), अभ्रम् (Abhram), पुष्करम् (Puṣkaram), विष्णुपदम् (Viṣṇupadam).</i>
                </div>
            </div>
            """, unsafe_allow_html=True)

# =========================================================
# TAB 4: RŪPA-SĀDHANA (GRAMMAR ARENA + HIGHLIGHTED KEYS)
# =========================================================
with tab_rupa:
    st.markdown("#### 🏛️ रूप-साधना (Śabdarūpa & Dhāturūpa Matrix Drills)")
    r_mode = st.radio("Select Grammar Discipline:", ["1. Śabdarūpa Declension Grid (शब्दरूपाणि)", "2. Dhāturūpa Tense Matcher (धातुरूपाणि)"], horizontal=True)
    
    if r_mode.startswith("1"):
        st.markdown("##### 🧩 Complete the Declension Grid for **'राम' (अकारान्त पुंल्लिङ्ग)**")
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

        if st.button("Validate Declension Matrix / रूप-परीक्षणम्"):
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
                
            # HIGH-CONTRAST MATRIX TABLE
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
        st.markdown("##### ⚡ Dhāturūpa Tense & Mood Classifier")
        dh_sample = st.selectbox("Analyze Verb Form:", ["पठिष्यति (Root: पठ्)", "अगच्छत् (Root: गम्)", "भवतु (Root: भू)", "कुर्यात् (Root: कृ)"])
        
        c_lakara = st.selectbox("Select the correct Lakāra (Tense/Mood):", [
            "लट् (Present Tense)",
            "लृट् (Future Tense)",
            "लङ् (Past Imperfect)",
            "लोट् (Imperative Mood)",
            "विधिलिङ् (Potential/Optative Mood)"
        ])
        if st.button("Submit Lakāra Assessment"):
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
# TAB 5: CHANDAḤ & ŚIKṢĀ (PHONETICS & METRES)
# =========================================================
with tab_chandas:
    st.markdown("#### 🕉️ छन्दः-शास्त्रम् एवं पाणिनीय-शिक्षा (Metre & Phonetic Spectrum)")
    
    st.markdown("##### 🌊 Live Vocal Pitch Spectrum (स्वर-तरङ्गिणी)")
    components.html("""
    <div style="font-family:sans-serif; background:#120B02; border:2px solid #FF8F00; border-radius:12px; padding:12px; color:#FFF;">
        <button id="pBtn" onclick="toggleAud()" style="background:#E65100; color:white; border:none; padding:6px 16px; border-radius:16px; font-weight:bold; cursor:pointer;">
            🔴 Activate Live Pitch Spectrum
        </button>
        <span id="pTxt" style="font-size:0.8rem; margin-left:10px; color:#AAA;">Tap to test your voice against the ideal harmonic.</span>
        <canvas id="c" width="600" height="90" style="width:100%; height:90px; background:#080401; margin-top:8px; border-radius:8px;"></canvas>
    </div>
    <script>
        var actx=null, an=null, mic=null, on=false, aid=null;
        async function toggleAud() {
            var b = document.getElementById("pBtn");
            if(!on) {
                try {
                    actx = new (window.AudioContext || window.webkitAudioContext)();
                    mic = await navigator.mediaDevices.getUserMedia({audio:true});
                    var s = actx.createMediaStreamSource(mic);
                    an = actx.createAnalyser(); an.fftSize = 1024;
                    s.connect(an); on=true; b.style.background="#2E7D32"; b.innerText="⏹️ Stop Visualizer";
                    draw();
                } catch(e){ alert(e.message); }
            } else {
                if(mic) mic.getTracks().forEach(t=>t.stop());
                if(actx) actx.close();
                cancelAnimationFrame(aid); on=false; b.style.background="#E65100"; b.innerText="🔴 Activate Live Pitch Spectrum";
            }
        }
        function draw() {
            if(!on) return;
            aid = requestAnimationFrame(draw);
            var cv = document.getElementById("c"), cx = cv.getContext("2d");
            var buf = an.frequencyBinCount, td = new Uint8Array(buf);
            an.getByteTimeDomainData(td);
            cx.fillStyle="#080401"; cx.fillRect(0,0,cv.width,cv.height);
            cx.lineWidth=2; cx.strokeStyle="#81C784"; cx.beginPath();
            var sw = cv.width*1.0/buf, x=0;
            for(var i=0;i<buf;i++) {
                var v = td[i]/128.0, y = v*(cv.height/2);
                if(i===0) cx.moveTo(x,y); else cx.lineTo(x,y);
                x += sw;
            }
            cx.lineTo(cv.width, cv.height/2); cx.stroke();
        }
    </script>
    """, height=155)

    st.write("---")
    st.markdown("##### 📜 Pingala Chandaḥ Verse Scansion Engine")
    v_scan = st.text_area("Enter Sanskrit verse for Laghu (।) & Guru (ऽ) syllabic scansion:", value="वागर्थाविव सम्प्रुक्तौ वागर्थप्रतिपत्तये।\nजगतः पितरौ वन्दे पार्वतीपरमेश्वरौ॥", height=70)
    if st.button("Scan Metre / छन्दो-विश्लेषणम्"):
        if not api_key:
            st.warning("⚠️ Enter Gemini API Key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Scansion in progress..."):
            try:
                res = generate_gemini_content(client, [{"role": "user", "parts": [{"text": f"Perform Pingala Chandas for: '{v_scan}'. Return: 1. Metre Name, 2. Laghu/Guru mapping, 3. Gana breakdown."}]}])
                st.markdown(res)
                update_user_xp(st.session_state.user_session_id, 20)
            except Exception as e:
                st.error(str(e))

# =========================================================
# TAB 6: SAṂSTHĀ-DHYEYA (ORGANIZATION MOTTOS + HIGHLIGHTED KEYS)
# =========================================================
with tab_motto:
    st.markdown("#### 🚩 संस्था-ध्येयवाक्य-क्रीडा (National & Global Sanskrit Mottos)")
    st.caption("Discover how modern institutions derive their guiding principles from timeless Sanskrit literature.")
    
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
            <h4 style="color:#FFD54F; margin:0;">🚩 "{m['motto']}"</h4>
            <div style="font-size:0.95rem; color:#FFF; margin-top:2px;"><b>Institution:</b> {m['org']}</div>
            <div style="font-size:0.85rem; color:#81C784;"><b>Scriptural Source:</b> {m['source']} | <i>"{m['meaning']}"</i></div>
        </div>
        """, unsafe_allow_html=True)
        
    st.write("---")
    st.markdown("##### 🎮 Quiz: Identify the Scriptural Source")
    m_quiz = st.radio("Where is the motto **'योगक्षेमं वहाम्यहम्'** taken from?", ["Bhagavad Gītā (Chapter 9)", "Muṇḍaka Upaniṣad", "Rāmāyaṇa", "Ṛgveda"])
    if st.button("Verify Motto Source"):
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
# TAB 7: SAṂSKṚTI-JÑĀNA (VEDAS, TITHIS & HIGHLIGHTED KEYS)
# =========================================================
with tab_samskriti:
    st.markdown("#### 🛕 संस्कृति-ज्ञानम् (Vedic Literature, Pañcāṅga Tithis & Festivals)")
    s_mode = st.selectbox("Select Cultural Domain:", ["1. Pañcāṅga Tithi & Festival Matcher", "2. Vedic Literature & Upaniṣad Tree", "3. True / False Cultural Lightning Quiz"])
    
    if s_mode.startswith("1"):
        st.markdown("##### 📅 Match the Vedic Tithi to its Festival:")
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            t1 = st.selectbox("1. श्रावण-पूर्णिमा (Śrāvaṇa Pūrṇimā):", ["रक्षाबन्धनम् / संस्कृत-दिनम्", "दीपावली", "होली", "विजयादशमी"])
            t2 = st.selectbox("2. कार्तिक-अमावास्या (Kārttika Amāvāsyā):", ["दीपावली (Dīpāvalī)", "महाशिवरात्रिः", "रामनवमी", "गणेश-चतुर्थी"])
        with col_f2:
            t3 = st.selectbox("3. फाल्गुन-पूर्णिमा (Phālguna Pūrṇimā):", ["होलिकोत्सवः (Holī)", "रथयात्रा", "मकर-सङ्क्रान्तिः", "गुरु-पूर्णिमा"])
            t4 = st.selectbox("4. भाद्रपद-शुक्ल-चतुर्थी:", ["विनायक-चतुर्थी (Ganesha Chaturthi)", "जन्माष्टमी", "दशहरा", "उगादिः"])
            
        if st.button("Submit Pañcāṅga Assessment"):
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
                <ul style="margin:0; padding-left:20px; font-size:0.98rem; line-height:1.9; color:#FFFFFF;">
                    <li><b>श्रावण-पूर्णिमा:</b> <span class="answer-badge">रक्षाबन्धनम् / विश्व-संस्कृत-दिनम्</span> {'✅' if is_t1 else '❌'}</li>
                    <li><b>कार्तिक-अमावास्या:</b> <span class="answer-badge">दीपावली (Lakṣmī Pūjana)</span> {'✅' if is_t2 else '❌'}</li>
                    <li><b>फाल्गुन-पूर्णिमा:</b> <span class="answer-badge">होलिकोत्सवः / कामदहनम्</span> {'✅' if is_t3 else '❌'}</li>
                    <li><b>भाद्रपद-शुक्ल-चतुर्थी:</b> <span class="answer-badge">विनायक-चतुर्थी (Ganesha Chaturthi)</span> {'✅' if is_t4 else '❌'}</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)

    elif s_mode.startswith("2"):
        st.markdown("##### 📜 Vedic Heritage Tree")
        st.markdown("""
        * **ऋग्वेदः:** ऐतरेयोपनिषद् • शाकल-शाखा • गायत्री-मन्त्रः (३.६२.१०)
        * **यजुर्वेदः (शुक्ल/कृष्ण):** ईशावास्योपनिषद्, बृहदारण्यकोपनिषद्, तैत्तिरीयोपनिषद्
        * **सामवेदः:** छान्दोग्योपनिषद्, केनोपनिषद् (गान-परम्परा)
        * **अथर्ववेदः:** मुण्डकोपनिषद्, माण्डूक्योपनिषद्, प्रश्नोपनिषद्
        """)
        q_v = st.radio("Which Upaniṣad contains the famous Mahāvākya **'अयमात्मा ब्रह्म'**?", ["माण्डूक्योपनिषद् (Atharvaveda)", "छान्दोग्योपनिषद्", "ईशावास्योपनिषद्"])
        if st.button("Submit Veda Quiz"):
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
        st.markdown("##### ⚡ True / False Lightning Drill")
        tf1 = st.radio("1. Pāṇini's Aṣṭādhyāyī contains approximately 4,000 grammatical sūtras.", ["True (सत्यम्)", "False (असत्यम्)"])
        tf2 = st.radio("2. The Gāyatrī Mantra is addressed to the solar deity Savitṛ in the Ṛgveda.", ["True (सत्यम्)", "False (असत्यम्)"])
        if st.button("Submit Lightning Quiz"):
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
                <ul style="margin:0; padding-left:20px; font-size:0.95rem; line-height:1.8; color:#FFFFFF;">
                    <li><b>Statement 1:</b> <span class="answer-badge">True</span> — The Aṣṭādhyāyī contains 3,959 (~4,000) sūtras arranged across 8 chapters. {'✅' if is_tf1 else '❌'}</li>
                    <li><b>Statement 2:</b> <span class="answer-badge">True</span> — The Gāyatrī Mantra (tat savitur vareṇyaṃ...) is from Ṛgveda Mandala 3, Sūkta 62, Verse 10, addressed to Savitṛ. {'✅' if is_tf2 else '❌'}</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
