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

# Enforce UTF-8 encoding across all runtime environments
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

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Sambhāṣaṇa AI Pro | सम्भाषण-प्रशिक्षकः",
    page_icon="🚩",
    layout="wide",
    initial_sidebar_state="expanded",
)

ACTIVE_MODEL = "gemini-3.6-flash"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "sambhāṣaṇa_concurrency.db")

# --- DATABASE PERSISTENCE LAYER (SQLite WAL Mode) ---
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
    conn.commit()
    conn.close()

init_db()

if "user_session_id" not in st.session_state:
    st.session_state.user_session_id = f"user_{int(time.time()*1000)}"

def get_user_stats(uid):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT streak, xp FROM user_profile WHERE id = ?', (uid,))
    res = c.fetchone()
    if not res:
        c.execute('INSERT OR IGNORE INTO user_profile VALUES (?, "Learner", "Beginner", 1, 100, ?)',
                  (uid, str(datetime.date.today())))
        conn.commit()
        res = (1, 100)
    conn.close()
    return res

def update_user_xp(uid, xp_add=10):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE user_profile SET xp = xp + ? WHERE id = ?', (xp_add, uid))
    conn.commit()
    conn.close()

def get_user_vault(uid):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT word, meaning, dhatu, level, review_due FROM vocab_vault WHERE user_id = ? ORDER BY id DESC', (uid,))
    rows = c.fetchall()
    conn.close()
    return [{"word": r[0], "meaning": r[1], "dhatu": r[2], "level": r[3], "review_due": r[4]} for r in rows]

def save_single_word(uid, word, meaning, dhatu):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO vocab_vault (user_id, word, meaning, dhatu, level, review_due)
        VALUES (?, ?, ?, ?, "Learner", "Tomorrow")
    ''', (uid, word, meaning, dhatu))
    c.execute('UPDATE user_profile SET xp = xp + 15 WHERE id = ?', (uid,))
    conn.commit()
    conn.close()

def save_vault_bulk(uid, word_list):
    conn = get_db_connection()
    c = conn.cursor()
    added = 0
    for w in word_list:
        try:
            c.execute('''
                INSERT OR IGNORE INTO vocab_vault (user_id, word, meaning, dhatu, level, review_due)
                VALUES (?, ?, ?, ?, ?, "Tomorrow")
            ''', (uid, w['word'], w['meaning'], w.get('dhatu', w['word']), w.get('level', 'Beginner')))
            if c.rowcount > 0:
                added += 1
        except Exception:
            pass
    c.execute('UPDATE user_profile SET xp = xp + ? WHERE id = ?', (added * 5, uid))
    conn.commit()
    conn.close()
    return added

def save_user_feedback(uid, teacher_name, user_prompt, response_text, fb_type, remark):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO feedback_logs (timestamp, user_id, teacher_name, user_prompt, acharya_response, feedback_type, remark_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), uid, teacher_name, user_prompt, response_text, fb_type, remark))
    conn.commit()
    conn.close()

# --- CSS STYLING & TALKING AVATAR ANIMATION ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
    
    .header-box {
        background: linear-gradient(135deg, #E65100 0%, #BF360C 50%, #1A1A1A 100%);
        border-radius: 16px;
        padding: 16px 22px;
        color: #FFFFFF;
        box-shadow: 0 6px 20px rgba(230, 81, 0, 0.25);
        margin-bottom: 15px;
    }
    
    .avatar-wrapper {
        position: relative;
        width: 85px;
        height: 85px;
        margin: 0 auto;
    }
    
    .avatar-base {
        width: 85px;
        height: 85px;
        border-radius: 50%;
        object-fit: cover;
        border: 3px solid #FF8F00;
        box-shadow: 0 0 14px rgba(255, 143, 0, 0.4);
        transition: all 0.3s ease;
    }
    
    .talking-lip {
        position: absolute;
        bottom: 14px;
        left: 50%;
        transform: translateX(-50%);
        width: 16px;
        height: 4px;
        background: #8D1414;
        border-radius: 50%;
        opacity: 0;
        transition: all 0.1s ease;
    }
    
    .is-speaking .talking-lip {
        opacity: 0.95;
        animation: mouthTalk 0.25s infinite alternate ease-in-out;
    }
    
    .is-speaking .avatar-base {
        box-shadow: 0 0 24px rgba(255, 111, 0, 0.9);
        transform: scale(1.03);
    }

    @keyframes mouthTalk {
        0% { height: 3px; width: 12px; }
        50% { height: 9px; width: 16px; background: #5C0B0B; }
        100% { height: 5px; width: 18px; }
    }
    
    .sentence-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 143, 0, 0.25);
        border-radius: 12px;
        padding: 14px 18px;
        margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)

# Helper: Load images from assets/ with fallback
def get_avatar_img(base_name, fallback_url):
    extensions = [".jpeg", ".jpg", ".png", ".JPEG", ".JPG", ".PNG"]
    assets_dir = os.path.join(BASE_DIR, "assets")
    for ext in extensions:
        local_p = os.path.join(assets_dir, base_name + ext)
        if os.path.isfile(local_p):
            try:
                mime = "image/jpeg" if ext.lower() in [".jpeg", ".jpg"] else "image/png"
                with open(local_p, "rb") as img_f:
                    b64 = base64.b64encode(img_f.read()).decode()
                    return f"data:{mime};base64,{b64}", f"Custom Asset ({base_name}{ext})"
            except Exception:
                pass
    return fallback_url, "Default Asset"

male_src, male_status = get_avatar_img("male_guru", "https://upload.wikimedia.org/wikipedia/commons/e/e3/Raja_Ravi_Varma_-_Sankaracharya.jpg")
female_src, female_status = get_avatar_img("female_guru", "https://dme2wmiz2suov.cloudfront.net/User(18985117)/2061981-Yadavabhyudayam_(9).png")
child_src, child_status = get_avatar_img("child_guru", "https://encrypted-tbn3.gstatic.com/licensed-image?q=tbn:ANd9GcQzrF7mhDcZqvcP2RO27fhrcZXbPYo76WyMLq97WTaUJbXdG3OP6XXd3kC2v3A7-6qYwUBpUaNci3jGXWs")

TEACHERS = {
    "Male Guru (आचार्यः वसिष्ठः)": {
        "title": "आचार्यः वसिष्ठः (Acharya Vasiṣṭha)",
        "desc": "Classical Guru • Deep Dignified Voice",
        "img": male_src,
        "status": male_status,
        "tld": "co.in",
        "slow": True
    },
    "Female Āchāryā (आचार्या गार्गी)": {
        "title": "आचार्या गार्गी (Acharyaa Gargi)",
        "desc": "Scholarly Preceptor • Warm Melodic Voice",
        "img": female_src,
        "status": female_status,
        "tld": "com",
        "slow": False
    },
    "Child Peer (बालकः ध्रुवः)": {
        "title": "बालकः ध्रुवः (Balaka Dhruva)",
        "desc": "Playful Peer • Cheerful Lively Voice",
        "img": child_src,
        "status": child_status,
        "tld": "co.uk",
        "slow": False
    }
}

# --- HIGH-SPEED IN-MEMORY TTS AUDIO GENERATOR ---
@st.cache_data(show_spinner=False, max_entries=200)
def get_speech_audio_b64(text: str, tld: str, slow: bool) -> str:
    try:
        tts = gTTS(text=text, lang='hi', tld=tld, slow=slow)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return base64.b64encode(fp.read()).decode()
    except Exception:
        return ""

def extract_complete_sanskrit_speech(reply_content: str) -> str:
    if "[संस्कृतम्]:" in reply_content:
        part = reply_content.split("[संस्कृतम्]:")[1]
        for marker in ["[IAST]:", "[English]:", "[✨ Say It Better]:", "[मार्गदर्शनम्]"]:
            if marker in part:
                part = part.split(marker)[0]
        return part.replace('*', '').replace('#', '').replace('-', '').strip()
    return ""

def render_talking_avatar(sanskrit_text: str, teacher_key: str, auto_play=True):
    clean_text = sanskrit_text.replace('*', '').replace('#', '').replace('-', '').replace('[', '').replace(']', '').strip()
    if not clean_text:
        return
    cfg = TEACHERS[teacher_key]
    audio_b64 = get_speech_audio_b64(clean_text, cfg["tld"], cfg["slow"])
    if not audio_b64:
        return
        
    elem_id = f"aud_{abs(hash(clean_text)) % 1000000}"
    st.markdown(f"""
    <div style="display:flex; align-items:center; gap:16px; margin: 10px 0; background:rgba(255,255,255,0.03); padding:12px; border-radius:14px; border:1px solid rgba(255,143,0,0.2);">
        <div class="avatar-wrapper" id="wrap_{elem_id}">
            <img src="{cfg['img']}" class="avatar-base"/>
            <div class="talking-lip"></div>
        </div>
        <div style="flex-grow:1;">
            <div style="font-size:0.78rem; color:#81C784; font-weight:700;">🟢 AI Preceptor Speaking ({cfg['title'].split('(')[0].strip()})</div>
            <div style="font-weight:700; color:#FF8F00; font-size:1.02rem;">{cfg['title']}</div>
            <audio id="{elem_id}" controls {'autoplay' if auto_play else ''} style="width:100%; height:36px; margin-top:5px;">
                <source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3">
            </audio>
        </div>
    </div>
    <script>
        (function(){{
            var aud = document.getElementById("{elem_id}");
            var wrp = document.getElementById("wrap_{elem_id}");
            if(aud && wrp){{
                aud.onplay = function(){{ wrp.classList.add("is-speaking"); }};
                aud.onpause = function(){{ wrp.classList.remove("is-speaking"); }};
                aud.onended = function(){{ wrp.classList.remove("is-speaking"); }};
            }}
        }})();
    </script>
    """, unsafe_allow_html=True)

# Helper: Sentence Splitter for Batch Translation
def split_into_sentences(text: str, max_limit=50):
    lines = text.split('\n')
    sentences = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = re.split(r'([.?!।॥]+)', line)
        temp = ""
        for p in parts:
            if re.match(r'^[.?!।॥]+$', p):
                temp += p
                if temp.strip():
                    sentences.append(temp.strip())
                temp = ""
            else:
                temp += p
        if temp.strip():
            sentences.append(temp.strip())
    return sentences[:max_limit]

# --- APP HERO ---
st.markdown("""
<div class="header-box">
    <h2 style="margin:0; font-weight:800;">🚩 Sambhāṣaṇa AI Enterprise (सम्भाषणम्)</h2>
    <p style="margin:2px 0 0 0; opacity:0.92; font-size:0.9rem;">Multi-Tenant Spoken Sanskrit Engine • 50-Sentence Batch Translator • High Latency Optimization</p>
</div>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
u_streak, u_xp = get_user_stats(st.session_state.user_session_id)

with st.sidebar:
    st.markdown("### 🎙️ **Teacher & Voice Profile**")
    selected_teacher = st.selectbox("Active Guide:", list(TEACHERS.keys()), index=0)
    t_info = TEACHERS[selected_teacher]
    
    st.markdown(f"""
    <div style="text-align:center; padding:10px; background:rgba(255,255,255,0.04); border-radius:12px; border:1px solid rgba(255,143,0,0.25);">
        <img src="{t_info['img']}" style="width:80px; height:80px; border-radius:50%; object-fit:cover; border:3px solid #FF8F00; margin-bottom:6px;"/>
        <div style="font-weight:700; color:#FF8F00;">{t_info['title']}</div>
        <div style="font-size:0.75rem; opacity:0.8;">{t_info['desc']}</div>
        <div style="font-size:0.7rem; color:#81C784; margin-top:4px;">Image: {t_info['status']}</div>
    </div>
    """, unsafe_allow_html=True)
    
    api_key = st.text_input(
        "Google Gemini API Key",
        type="password",
        placeholder="Paste AIza... key here",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Free key from aistudio.google.com/apikey"
    )
    
    target_tier = st.selectbox(
        "Student Tier / स्तरः",
        ["Beginner (प्रथमा)", "Intermediate (मध्यमा)", "Advanced (उत्तमा)"],
        index=0
    )
    
    st.markdown("---")
    st.markdown("### 🏆 **Database User Stats**")
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.metric("🔥 Streak", f"{u_streak} Days")
    with col_p2:
        st.metric("⭐ Points", f"{u_xp} XP")
    
    if st.button("🔄 Reset Conversation", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.turn_count = 0
        st.rerun()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "turn_count" not in st.session_state:
    st.session_state.turn_count = 0

FAST_SYSTEM_PROMPT = f"""You are '{t_info['title']}', a high-performance interactive conversational Sanskrit tutor.
Student Tier: {target_tier}.

Pedagogical Rules:
1. Converse dynamically in authentic spoken Sarala Samskritam.
2. Keep response to 2-3 spoken sentences.
3. Conclude by asking a natural conversational question.

Mandatory Response Format:
[संस्कृतम्]: <Your spoken Sanskrit reply>
[IAST]: <Romanized transliteration>
[English]: <English meaning>
[✨ Say It Better]: <Short idiomatic Sanskrit alternative>
[मार्गदर्शनम्] (Include only if student made a grammatical error):
- 💡 Correction & rule
"""

# --- 5 PRODUCTION TABS ---
tab_roleplay, tab_bulk_vocab, tab_shiksha, tab_chandas, tab_trans = st.tabs([
    "💬 1. Oral Roleplay",
    "📚 2. Bulk PDF Vocabulary",
    "🎙️ 3. Śikṣā Phonetics",
    "🕉️ 4. Svara & Chandaḥ",
    "🌐 5. Sentence-by-Sentence Batch Translator (50 Sentences)"
])

# =========================================================
# TAB 1: HIGH-ACCURACY ORAL ROLEPLAY
# =========================================================
with tab_roleplay:
    st.markdown("#### 💬 Situational Conversational Immersion (सजीव-सम्भाषणम्)")
    
    scenario = st.selectbox(
        "Conversation Scenario / प्रसङ्गः:",
        [
            "At Gurukula / Classroom (पाठशाला - शिष्टाचारः)",
            "At the Market (विपणिः - शाकक्रयणम् / Purchasing Vegetables)",
            "Travel & Directions (यात्रा - मार्गनिर्देशनम्)",
            "Welcoming Guests (अतिथि-सत्कारः)",
            "Open Free Dialogue (मुक्त-सम्भाषणम्)"
        ]
    )
    
    for idx, msg in enumerate(st.session_state.chat_history):
        role = "assistant" if msg["role"] == "model" else "user"
        with st.chat_message(role):
            st.markdown(msg["content"])
            if role == "assistant":
                full_s = extract_complete_sanskrit_speech(msg["content"])
                if full_s:
                    render_talking_avatar(full_s, selected_teacher, auto_play=False)
                
                with st.expander(f"📝 Remark / Feedback on Response #{idx // 2 + 1}"):
                    with st.form(key=f"rem_form_{idx}"):
                        fb_type = st.selectbox(
                            "Classification:",
                            [
                                "⚠️ Grammar / Sūtra Error (व्याकरण-दोषः)",
                                "⚠️ Inaccurate Translation (अनुवाद-दोषः)",
                                "⚠️ Sandhi / Spelling Mistake (सन्धि/वर्ण-दोषः)",
                                "💡 Suggestion / Better Word (सुझावः)",
                                "✅ Auspicious & Correct (उत्कृष्टम्)"
                            ],
                            key=f"fb_sel_{idx}"
                        )
                        fb_text = st.text_area("Write remarks / corrections:", key=f"fb_txt_{idx}", placeholder="e.g. In line 1, 'गच्छामि' should be used...")
                        if st.form_submit_button("💾 Save Remark"):
                            prior_user = st.session_state.chat_history[idx - 1]["content"] if idx > 0 else "N/A"
                            save_user_feedback(st.session_state.user_session_id, selected_teacher, prior_user, msg["content"], fb_type, fb_text)
                            st.success("✅ Remark saved successfully into the database!")

    st.markdown("##### 🎙️ **Speak into Microphone (वदतु):**")
    user_audio = st.audio_input("Record continuous voice to Acharya:", key=f"mic_turn_{st.session_state.turn_count}")

    if user_audio is not None:
        if not api_key:
            st.warning("⚠️ Enter your Gemini API key in the sidebar.")
            st.stop()

        client = genai.Client(api_key=api_key)
        audio_bytes = user_audio.getvalue()
        
        st.session_state.chat_history.append({"role": "user", "content": "🎙️ *[Continuous Spoken Voice Submitted]*"})
        with st.chat_message("user"):
            st.audio(user_audio, format="audio/wav")

        with st.chat_message("assistant"):
            with st.spinner("आचार्यः शृणोति एवं चिन्तयति..."):
                t_start = time.time()
                try:
                    resp = client.models.generate_content(
                        model=ACTIVE_MODEL,
                        contents=[{
                            "role": "user",
                            "parts": [
                                {"inline_data": {"mime_type": "audio/wav", "data": audio_bytes}},
                                {"text": f"{FAST_SYSTEM_PROMPT}\nScenario: {scenario}. Transcribe student audio and reply comprehensively."}
                            ]
                        }],
                        config={"temperature": 0.2, "max_output_tokens": 500}
                    )
                    reply_text = resp.text
                    latency = round(time.time() - t_start, 2)
                    
                    st.markdown(reply_text)
                    st.caption(f"⚡ *Response Latency: {latency}s*")
                    
                    full_s = extract_complete_sanskrit_speech(reply_text)
                    if full_s:
                        render_talking_avatar(full_s, selected_teacher, auto_play=True)
                    
                    st.session_state.chat_history.append({"role": "model", "content": reply_text})
                    st.session_state.turn_count += 1
                    update_user_xp(st.session_state.user_session_id, 10)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    if text_input := st.chat_input("Type in Sanskrit, English, or Telugu (e.g. mama nama, katham asti)..."):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key in the sidebar.")
            st.stop()

        client = genai.Client(api_key=api_key)
        is_dev = any("\u0900" <= char <= "\u097f" for char in text_input)
        display_text = text_input if is_dev else f"{text_input} ({transliterate(text_input, sanscript.ITRANS, sanscript.DEVANAGARI)})"

        st.session_state.chat_history.append({"role": "user", "content": display_text})
        with st.chat_message("user"):
            st.markdown(display_text)

        contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": str(m["content"])}]} for m in st.session_state.chat_history]

        with st.chat_message("assistant"):
            with st.spinner("चिन्तयति..."):
                t_start = time.time()
                try:
                    resp = client.models.generate_content(
                        model=ACTIVE_MODEL,
                        contents=contents,
                        config={"system_instruction": FAST_SYSTEM_PROMPT, "temperature": 0.2, "max_output_tokens": 500}
                    )
                    reply_text = resp.text
                    latency = round(time.time() - t_start, 2)
                    
                    st.markdown(reply_text)
                    st.caption(f"⚡ *Response Latency: {latency}s*")
                    
                    full_s = extract_complete_sanskrit_speech(reply_text)
                    if full_s:
                        render_talking_avatar(full_s, selected_teacher, auto_play=True)
                        
                    st.session_state.chat_history.append({"role": "model", "content": reply_text})
                    st.session_state.turn_count += 1
                    update_user_xp(st.session_state.user_session_id, 5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

# =========================================================
# TAB 2: BULK PDF VOCABULARY EXTRACTOR
# =========================================================
with tab_bulk_vocab:
    st.markdown("#### 📚 Bulk PDF Sanskrit Vocabulary Ingestion Engine")
    col_pdf1, col_pdf2 = st.columns([1, 1])
    with col_pdf1:
        uploaded_pdf = st.file_uploader("Upload Sanskrit PDF File:", type=["pdf"])
        max_words = st.slider("Max Words to Extract:", min_value=10, max_value=50, value=25)
        
        if uploaded_pdf is not None and st.button("⚡ Extract & Save into Vault", use_container_width=True):
            if not api_key:
                st.warning("⚠️ Enter your Gemini API key in the sidebar.")
                st.stop()
            
            with st.spinner("Extracting text and analyzing Sanskrit morphology..."):
                try:
                    pdf_reader = PdfReader(uploaded_pdf)
                    extracted_text = ""
                    for page_idx in range(min(8, len(pdf_reader.pages))):
                        text = pdf_reader.pages[page_idx].extract_text()
                        if text:
                            extracted_text += text + "\n"
                    
                    if not extracted_text.strip():
                        st.error("No readable text found in PDF.")
                        st.stop()
                    
                    client = genai.Client(api_key=api_key)
                    PROMPT_BULK = f"""Extract {max_words} unique Sanskrit words from this text.
Return a STRICT JSON array of objects with keys: "word", "meaning", "dhatu", "level".
Example:
[
  {{"word": "गच्छति", "meaning": "goes", "dhatu": "गम्", "level": "Beginner"}}
]
Text:
{extracted_text[:4000]}
"""
                    resp = client.models.generate_content(
                        model=ACTIVE_MODEL,
                        contents=[{"role": "user", "parts": [{"text": PROMPT_BULK}]}],
                        config={"temperature": 0.1, "response_mime_type": "application/json"}
                    )
                    
                    parsed_vocab = json.loads(resp.text)
                    added = save_vault_bulk(st.session_state.user_session_id, parsed_vocab)
                    st.success(f"🎉 Successfully saved {added} words into your Database Vault!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error processing PDF: {str(e)}")

        st.markdown("---")
        with st.form("manual_add"):
            st.markdown("##### ➕ **Add Single Word:**")
            vw = st.text_input("Sanskrit Word (पदम्):")
            vm = st.text_input("Meaning (अर्थः):")
            vd = st.text_input("Root / Stem (धातुः):")
            if st.form_submit_button("Save Word (+15 XP)") and vw and vm:
                save_single_word(st.session_state.user_session_id, vw, vm, vd if vd else vw)
                st.success(f"Saved '{vw}'!")
                st.rerun()

    with col_pdf2:
        st.markdown("##### 🗄️ **Persistent Vocabulary Database Vault:**")
        v_list = get_user_vault(st.session_state.user_session_id)
        st.caption(f"Total Words in Vault: **{len(v_list)}**")
        search_query = st.text_input("🔍 Search Vault:", placeholder="Filter words...")
        filtered = [x for x in v_list if search_query.lower() in x['word'].lower() or search_query.lower() in x['meaning'].lower()] if search_query else v_list
        for itm in filtered[:30]:
            st.markdown(f"• **{itm['word']}** — *{itm['meaning']}* | Root: `{itm['dhatu']}` | ⏳ `{itm['review_due']}`")

# =========================================================
# TAB 3: ŚIKṢĀ PHONETICS
# =========================================================
with tab_shiksha:
    st.markdown("#### 🎙️ पाणिनीय-शिक्षा एवं उच्चारण-परीक्षकः (Phonetic Accent Coach)")
    drill = st.selectbox("Choose Target Phrase to Master:", [
        "सत्यं वद, धर्मं चर। (Speak truth, practice righteousness)",
        "विद्या ददाति विनयं विनयाद्याति पात्रताम्। (Knowledge gives humility)",
        "वृक्षात् फलानि भूमौ पतन्ति। (Fruits fall from tree - Mahāprāṇa 'ph')",
        "अहं प्रतिदिनं प्रातः पञ्चवादने उत्तिष्ठामि। (I wake at 5 AM - Retroflex 'ṣṭh')"
    ])
    phrase = drill.split('(')[0].strip()
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.markdown(f"##### 🔊 **1. Master Chanting ({t_info['title']}):**")
        render_talking_avatar(phrase, selected_teacher, auto_play=False)
    with col_s2:
        st.markdown("##### 🎙️ **2. Record Your Voice:**")
        rec_sh = st.audio_input("Chant the phrase:", key="shiksha_mic")

    if rec_sh is not None:
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Analyzing phonetic acoustics..."):
            try:
                resp = client.models.generate_content(
                    model=ACTIVE_MODEL,
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": rec_sh.getvalue()}},
                            {"text": f"Evaluate student pronunciation against target: '{phrase}'. Return: 1. Score out of 100, 2. Articulation points (Dental vs Retroflex), 3. Mahaprana breath release, 4. Vowel duration (Hrasva/Dirgha), 5. Tongue placement tip."}
                        ]
                    }],
                    config={"max_output_tokens": 400}
                )
                st.markdown(resp.text)
                update_user_xp(st.session_state.user_session_id, 15)
            except Exception as e:
                st.error(f"Error: {str(e)}")

# =========================================================
# TAB 4: SVARA & CHANDAḤ ENGINE
# =========================================================
with tab_chandas:
    st.markdown("#### 🕉️ वैदिक-स्वर एवं छन्दो-विश्लेषकः (Pingala Chandaḥ Engine)")
    verse_input = st.text_area("Enter Verse for Scansion:", value="धर्मक्षेत्रे कुरुक्षेत्रे समवेता युयुत्सवः।\nमामकाः पाण्डवाश्चैव किमकुर्वत सञ्जय॥", height=80)
    
    if st.button("Scan Metre & Pitch / छन्दो-परीक्षणम्", use_container_width=True):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Analyzing scansion..."):
            try:
                res = client.models.generate_content(
                    model=ACTIVE_MODEL,
                    contents=[{"role": "user", "parts": [{"text": f"Perform Pingala Chandaḥ scansion on: '{verse_input}'. Identify metre name (Anuṣṭubh, Triṣṭubh, etc.), Laghu (।) / Guru (ऽ) syllabic mapping, Gana breakdown, and Vedic Svara rules."}]}],
                    config={"max_output_tokens": 450}
                )
                st.markdown(res.text)
                update_user_xp(st.session_state.user_session_id, 20)
            except Exception as e:
                st.error(f"Error: {str(e)}")

# =========================================================
# TAB 5: SENTENCE-BY-SENTENCE BATCH TRANSLATOR (UP TO 50 SENTENCES)
# =========================================================
with tab_trans:
    st.markdown("#### 🌐 Sentence-by-Sentence Batch Translator (Up to 50 Sentences at Once)")
    st.caption("Paste whole essays, paragraphs, or lists. The engine automatically splits into distinct sentences, translates each individually, provides Padaccheda/Sandhi breakdown, and enables audio playback.")
    
    col_t1, col_t2 = st.columns([1, 1])
    with col_t1:
        trans_direction = st.radio("Translation Direction:", ["Any Language ➔ Sanskrit (संस्कृतम्)", "Sanskrit (संस्कृतम्) ➔ Any Language"], horizontal=True)
    with col_t2:
        if trans_direction.startswith("Sanskrit"):
            target_lang = st.selectbox("Translate to Target Language:", ["Telugu (తెలుగు)", "Hindi (हिन्दी)", "English", "Tamil (தமிழ்)", "Kannada (ಕನ್ನಡ)", "Marathi (मराठी)"])
        else:
            target_lang = "Sanskrit (Devanagari + IAST)"
    
    input_text = st.text_area(
        "Enter sentences or paragraph (Max 50 sentences):",
        value="Speak Without Pressure. Take the quiz and start speaking your chosen language with an AI tutor today. Praktika helps you practice without pressure and turn short lessons into real progress.",
        height=140
    )
    
    detected_sentences = split_into_sentences(input_text, max_limit=50)
    st.caption(f"📊 **Detected Sentences to Process:** `{len(detected_sentences)}` (Max batch: 50)")

    if st.button("🚀 Translate Sentence-by-Sentence / वाक्यशः अनुवादं कुरु", use_container_width=True) and input_text.strip():
        if not api_key:
            st.warning("⚠️ Enter your Gemini API key in the sidebar.")
            st.stop()
        
        client = genai.Client(api_key=api_key)
        with st.spinner(f"Translating {len(detected_sentences)} sentences sentence-by-sentence with grammatical Sandhi split..."):
            try:
                # Prepare JSON batch payload for Gemini-3.6-Flash
                BATCH_PROMPT = f"""You are a Sanskrit Grammatical Translation Engine.
Translate the following array of {len(detected_sentences)} sentences individually.
Direction: {trans_direction} (Target: {target_lang}).

Input sentences array:
{json.dumps(detected_sentences, ensure_ascii=False)}

Return a STRICT JSON array of objects with exact keys:
- "sentence_num": integer (1, 2, 3...)
- "source_sentence": original sentence
- "translated_sentence": translated sentence in target script
- "iast": Romanized IAST transliteration
- "padaccheda": Word-by-word grammatical Sandhi split with root meanings

Ensure pure, natural, idiomatic translation for every single sentence.
"""
                resp = client.models.generate_content(
                    model=ACTIVE_MODEL,
                    contents=[{"role": "user", "parts": [{"text": BATCH_PROMPT}]}],
                    config={"temperature": 0.1, "response_mime_type": "application/json"}
                )
                
                batch_results = json.loads(resp.text)
                st.success(f"🎉 Successfully translated all {len(batch_results)} sentences!")
                
                # --- DISPLAY SENTENCE-BY-SENTENCE RESULTS ---
                for item in batch_results:
                    s_num = item.get("sentence_num", 1)
                    src_s = item.get("source_sentence", "")
                    tr_s = item.get("translated_sentence", "")
                    iast_s = item.get("iast", "")
                    pada_s = item.get("padaccheda", "")
                    
                    st.markdown(f"""
                    <div class="sentence-card">
                        <div style="font-weight:800; color:#FF8F00; font-size:0.95rem; margin-bottom:4px;">
                            Sentence #{s_num}
                        </div>
                        <div style="font-size:0.95rem; opacity:0.85; margin-bottom:8px;">
                            <b>Original:</b> {src_s}
                        </div>
                        <div style="font-size:1.15rem; color:#FFF; font-weight:700; margin-bottom:4px;">
                            <b>अनुवादः:</b> {tr_s}
                        </div>
                        <div style="font-size:0.88rem; color:#FFD54F; margin-bottom:6px;">
                            <b>IAST:</b> <i>{iast_s}</i>
                        </div>
                        <div style="font-size:0.82rem; color:#81C784; background:rgba(255,255,255,0.02); padding:6px 10px; border-radius:6px;">
                            <b>पदच्छेदः एवं सन्धिविश्लेषणम् (Grammar):</b> {pada_s}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Individual audio player for each translated sentence
                    if trans_direction.startswith("Any"):
                        audio_b64 = get_speech_audio_b64(tr_s, t_info["tld"], t_info["slow"])
                        if audio_b64:
                            st.audio(f"data:audio/mp3;base64,{audio_b64}", format="audio/mp3")

                # Export option
                export_text = ""
                for it in batch_results:
                    export_text += f"[{it.get('sentence_num')}] Source: {it.get('source_sentence')}\nTranslation: {it.get('translated_sentence')}\nIAST: {it.get('iast')}\nPadaccheda: {it.get('padaccheda')}\n\n"
                
                st.download_button(
                    label="📥 Download All Translated Sentences (.txt)",
                    data=export_text,
                    file_name="sanskrit_batch_translation.txt",
                    mime="text/plain",
                    use_container_width=True
                )

            except Exception as e:
                st.error(f"Translation Error: {str(e)}")
