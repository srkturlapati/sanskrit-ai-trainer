import sys
import os
import time
import io
import sqlite3
import datetime
import base64
import asyncio

# Enforce UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from google import genai
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate
from gtts import gTTS
import edge_tts
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

# --- DATABASE PERSISTENCE LAYER (SQLite) ---
DB_FILE = os.path.join(BASE_DIR, "sambhāṣaṇa_master.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_profile (
            id INTEGER PRIMARY KEY,
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
            word TEXT UNIQUE,
            meaning TEXT,
            dhatu TEXT,
            level TEXT,
            review_due TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS feedback_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            teacher_name TEXT,
            user_prompt TEXT,
            acharya_response TEXT,
            feedback_type TEXT,
            remark_text TEXT
        )
    ''')
    c.execute('SELECT COUNT(*) FROM user_profile')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO user_profile VALUES (1, "Sanskrit Learner", "Beginner", 1, 150, ?)', (str(datetime.date.today()),))
        default_vocab = [
            ("अस्तु", "Alright / Let it be", "अस् (to be)", "Beginner", "Today"),
            ("धन्यवादः", "Thank you", "धन्य + वाद्", "Beginner", "Tomorrow"),
            ("पुनर्मिलामः", "See you again", "मिल् (to meet)", "Beginner", "In 3 Days")
        ]
        c.executemany('INSERT OR IGNORE INTO vocab_vault (word, meaning, dhatu, level, review_due) VALUES (?, ?, ?, ?, ?)', default_vocab)
    conn.commit()
    conn.close()

init_db()

def get_user():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT username, level, streak, xp FROM user_profile WHERE id = 1')
    res = c.fetchone()
    conn.close()
    return res if res else ("Learner", "Beginner", 1, 150)

def update_xp(add_xp=10):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE user_profile SET xp = xp + ? WHERE id = 1', (add_xp,))
    conn.commit()
    conn.close()

def get_vault():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT word, meaning, dhatu, level, review_due FROM vocab_vault ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()
    return [{"word": r[0], "meaning": r[1], "dhatu": r[2], "level": r[3], "review_due": r[4]} for r in rows]

def save_word(word, meaning, dhatu):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO vocab_vault (word, meaning, dhatu, level, review_due) VALUES (?, ?, ?, "Learner", "Tomorrow")', (word, meaning, dhatu))
    c.execute('UPDATE user_profile SET xp = xp + 15 WHERE id = 1')
    conn.commit()
    conn.close()

def save_feedback(teacher_name, user_prompt, response_text, fb_type, remark):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO feedback_logs (timestamp, teacher_name, user_prompt, acharya_response, feedback_type, remark_text)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), teacher_name, user_prompt, response_text, fb_type, remark))
    conn.commit()
    conn.close()

def get_all_feedbacks():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, timestamp, teacher_name, feedback_type, remark_text, acharya_response FROM feedback_logs ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()
    return rows

# --- UI & AVATAR CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
    
    .header-box {
        background: linear-gradient(135deg, #E65100 0%, #BF360C 50%, #212121 100%);
        border-radius: 16px;
        padding: 20px 24px;
        color: #FFFFFF;
        box-shadow: 0 8px 24px rgba(230, 81, 0, 0.25);
        margin-bottom: 20px;
    }
    
    .avatar-wrapper {
        position: relative;
        width: 120px;
        height: 120px;
        margin: 0 auto;
    }
    
    .avatar-base {
        width: 120px;
        height: 120px;
        border-radius: 50%;
        object-fit: cover;
        border: 4px solid #FF8F00;
        box-shadow: 0 0 20px rgba(255, 143, 0, 0.4);
        transition: all 0.3s ease;
    }
    
    .talking-lip {
        position: absolute;
        bottom: 22px;
        left: 50%;
        transform: translateX(-50%);
        width: 22px;
        height: 6px;
        background: #8D1414;
        border-radius: 50%;
        opacity: 0;
        transition: all 0.1s ease;
    }
    
    .is-speaking .talking-lip {
        opacity: 0.95;
        animation: mouthTalk 0.28s infinite alternate ease-in-out;
    }
    
    .is-speaking .avatar-base {
        box-shadow: 0 0 30px rgba(255, 111, 0, 0.9);
        transform: scale(1.04);
        border-color: #FFD54F;
    }

    @keyframes mouthTalk {
        0% { height: 4px; width: 18px; border-radius: 50%; }
        50% { height: 14px; width: 22px; border-radius: 40%; background: #5C0B0B; }
        100% { height: 8px; width: 24px; border-radius: 50%; }
    }

    .voice-prompt-box {
        background: rgba(255, 111, 0, 0.08);
        border: 2px dashed #FF8F00;
        border-radius: 14px;
        padding: 16px;
        margin-top: 20px;
        text-align: center;
    }

    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        background: rgba(76, 175, 80, 0.15);
        color: #81C784;
        border: 1px solid #4CAF50;
        margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)

# Helper: Load images from assets/ with absolute path
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
    return fallback_url, "Default Web Fallback"

male_src, male_status = get_avatar_img("male_guru", "https://upload.wikimedia.org/wikipedia/commons/e/e3/Raja_Ravi_Varma_-_Sankaracharya.jpg")
female_src, female_status = get_avatar_img("female_guru", "https://dme2wmiz2suov.cloudfront.net/User(18985117)/2061981-Yadavabhyudayam_(9).png")
child_src, child_status = get_avatar_img("child_guru", "https://encrypted-tbn3.gstatic.com/licensed-image?q=tbn:ANd9GcQzrF7mhDcZqvcP2RO27fhrcZXbPYo76WyMLq97WTaUJbXdG3OP6XXd3kC2v3A7-6qYwUBpUaNci3jGXWs")

# --- DISTINCT NEURAL VOICES CONFIGURATION ---
TEACHERS = {
    "Male Guru (आचार्यः वसिष्ठः)": {
        "title": "आचार्यः वसिष्ठः (Acharya Vasiṣṭha)",
        "desc": "Classical Guru • Deep, Authoritative Neural Voice",
        "img": male_src,
        "status": male_status,
        "voice": "hi-IN-MadhurNeural",
        "rate": "+0%",
        "pitch": "-4Hz"
    },
    "Female Āchāryā (आचार्या गार्गी)": {
        "title": "आचार्या गार्गी (Acharyaa Gargi)",
        "desc": "Scholarly Preceptor • Clear, Melodic Neural Voice",
        "img": female_src,
        "status": female_status,
        "voice": "hi-IN-SwaraNeural",
        "rate": "+0%",
        "pitch": "+0Hz"
    },
    "Child Peer (बालकः ध्रुवः)": {
        "title": "बालकः ध्रुवः (Balaka Dhruva)",
        "desc": "Playful Young Peer • Fast, High-Pitched Child Voice",
        "img": child_src,
        "status": child_status,
        "voice": "hi-IN-SwaraNeural",
        "rate": "+15%",
        "pitch": "+25Hz"
    }
}

# --- ASYNC HIGH-FIDELITY TTS ENGINE ---
async def generate_speech_bytes(text: str, voice_name: str, rate: str, pitch: str) -> bytes:
    communicate = edge_tts.Communicate(text, voice_name, rate=rate, pitch=pitch)
    mp3_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_data += chunk["data"]
    return mp3_data

def synthesize_voice(clean_text: str, teacher_key: str) -> bytes:
    cfg = TEACHERS[teacher_key]
    try:
        # Generate distinct neural voice
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_bytes = loop.run_until_complete(generate_speech_bytes(clean_text, cfg["voice"], cfg["rate"], cfg["pitch"]))
        loop.close()
        if audio_bytes:
            return audio_bytes
    except Exception:
        pass
    
    # Fallback to gTTS if network is restricted
    try:
        tts = gTTS(text=clean_text, lang='hi', slow=(teacher_key.startswith("Male")))
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        return fp.getvalue()
    except Exception:
        return b""

# Helper: Extract the ENTIRE Sanskrit speech block completely
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
    try:
        raw_audio = synthesize_voice(clean_text, teacher_key)
        if not raw_audio:
            return
        audio_b64 = base64.b64encode(raw_audio).decode()
        
        elem_id = f"audio_{int(time.time()*1000)}"
        st.markdown(f"""
        <div style="display:flex; align-items:center; gap:16px; margin: 12px 0; background:rgba(255,255,255,0.03); padding:12px; border-radius:14px; border:1px solid rgba(255,143,0,0.2);">
            <div class="avatar-wrapper" id="wrap_{elem_id}">
                <img src="{cfg['img']}" class="avatar-base"/>
                <div class="talking-lip"></div>
            </div>
            <div style="flex-grow:1;">
                <div class="status-badge">🟢 AI Voice Speaking ({cfg['title'].split('(')[0].strip()})</div>
                <div style="font-weight:700; color:#FF8F00; font-size:1.05rem;">{cfg['title']}</div>
                <audio id="{elem_id}" controls {'autoplay' if auto_play else ''} style="width:100%; height:36px; margin-top:6px;">
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
    except Exception:
        pass

# --- APP HERO ---
st.markdown("""
<div class="header-box">
    <h2 style="margin:0; font-weight:800;">🚩 Sambhāṣaṇa AI Pro (सम्भाषण-प्रशिक्षकः)</h2>
    <p style="margin:4px 0 0 0; opacity:0.9;">Complete Neural Voice Engine • Distinct Male/Female/Child Personas • Continuous Loop</p>
</div>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
u_name, u_lvl, u_strk, u_xp = get_user()

with st.sidebar:
    st.markdown("### 🎙️ **Teacher & Neural Voice**")
    selected_teacher = st.selectbox("Active Guide:", list(TEACHERS.keys()), index=0)
    t_info = TEACHERS[selected_teacher]
    
    st.markdown(f"""
    <div style="text-align:center; padding:10px; background:rgba(255,255,255,0.04); border-radius:12px; border:1px solid rgba(255,143,0,0.25);">
        <img src="{t_info['img']}" style="width:90px; height:90px; border-radius:50%; object-fit:cover; border:3px solid #FF8F00; margin-bottom:6px;"/>
        <div style="font-weight:700; color:#FF8F00;">{t_info['title']}</div>
        <div style="font-size:0.75rem; opacity:0.8;">{t_info['desc']}</div>
        <div style="font-size:0.7rem; color:#81C784; margin-top:4px;">Voice: {t_info['voice']}</div>
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
        "Proficiency Level / स्तरः",
        ["Beginner (प्रथमा)", "Intermediate (मध्यमा)", "Advanced (उत्तमा)"],
        index=0
    )
    
    st.markdown("---")
    st.markdown("### 🏆 **Student Database Profile**")
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.metric("🔥 Day Streak", f"{u_strk} Days")
    with col_p2:
        st.metric("⭐ Saved XP", f"{u_xp} XP")
    
    if st.button("🔄 Start New Conversation", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.turn_count = 0
        st.rerun()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "turn_count" not in st.session_state:
    st.session_state.turn_count = 0

FAST_SYSTEM_PROMPT = f"""You are '{t_info['title']}', an interactive conversational Sanskrit tutor speaking with the student.
Student Tier: {target_tier}.

CRITICAL RULES:
1. Speak in pure, clear spoken Sarala Samskritam.
2. Keep the response to 2-4 complete sentences.
3. Conclude with a question to prompt the student to speak next.

MANDATORY FORMAT:
[संस्कृतम्]: <Complete spoken Sanskrit sentences>
[IAST]: <Romanized transliteration>
[English]: <English meaning>
[✨ Say It Better]: <One short idiomatic Sanskrit upgrade>
[मार्गदर्शनम्] (Only if student made an error):
- 💡 Correction & rule
"""

tab_roleplay, tab_shiksha, tab_chandas, tab_vault, tab_trans, tab_feedback = st.tabs([
    "💬 1. Continuous Oral Roleplay",
    "🎙️ 2. Śikṣā Coach",
    "🕉️ 3. Svara & Chandaḥ",
    "🧠 4. SRS Vault",
    "🌐 5. Translator",
    "📝 6. Remarks Log (अभिप्रायः)"
])

# =========================================================
# TAB 1: CONTINUOUS ORAL ROLEPLAY
# =========================================================
with tab_roleplay:
    st.markdown("#### 💬 Live Conversation with AI Tutor (सजीव-सम्भाषणम्)")
    
    scenario = st.selectbox(
        "Select Scenario / प्रसङ्गः:",
        [
            "At Gurukula / Classroom (पाठशाला - शिष्टाचारः)",
            "At the Market (विपणिः - शाकक्रयणम् / Purchasing Vegetables)",
            "Travel & Directions (यात्रा - मार्गनिर्देशनम्)",
            "Welcoming Guests (अतिथि-सत्कारः)",
            "Open Free Dialogue (मुक्त-सम्भाषणम्)"
        ]
    )
    
    # 1. Display Chat History with Complete Talking Avatar Audio
    for idx, msg in enumerate(st.session_state.chat_history):
        role = "assistant" if msg["role"] == "model" else "user"
        with st.chat_message(role):
            st.markdown(msg["content"])
            if role == "assistant":
                full_sanskrit = extract_complete_sanskrit_speech(msg["content"])
                if full_sanskrit:
                    render_talking_avatar(full_sanskrit, selected_teacher, auto_play=False)
                
                # Remarks Widget
                with st.expander(f"📝 Remark / Feedback on Response #{idx // 2 + 1}"):
                    fb_type = st.selectbox(
                        "Remark Type:",
                        [
                            "✅ Correct & Auspicious (उत्कृष्टम्)",
                            "⚠️ Grammar / Sūtra Error (व्याकरण-दोषः)",
                            "⚠️ Inaccurate Translation (अनुवाद-दोषः)",
                            "⚠️ Sandhi / Spelling Mistake (सन्धि/वर्ण-दोषः)",
                            "💡 Suggestion for Improvement (सुझावः)"
                        ],
                        key=f"fb_type_{idx}"
                    )
                    user_remark = st.text_area("Your Note / Correction:", key=f"remark_{idx}", placeholder="e.g. In sentence 1, 'गच्छामि' is better...")
                    if st.button("💾 Save Remark", key=f"btn_fb_{idx}"):
                        prior_user_msg = st.session_state.chat_history[idx - 1]["content"] if idx > 0 else "N/A"
                        save_feedback(selected_teacher, prior_user_msg, msg["content"], fb_type, user_remark)
                        st.success("✅ Remark saved into SQLite database! (View in Tab 6)")

    # 2. CONTINUOUS MICROPHONE PROMPTER
    st.markdown("""
    <div class="voice-prompt-box">
        <h4 style="margin:0; color:#FF8F00;">🎙️ अधुना भवान् वदतु (Your Turn to Speak)</h4>
        <p style="margin:4px 0 10px 0; opacity:0.85; font-size:0.9rem;">Press record, speak your sentence or question to Acharya, and tap stop.</p>
    </div>
    """, unsafe_allow_html=True)
    
    user_audio = st.audio_input("Record voice to Acharya:", key=f"mic_turn_{st.session_state.turn_count}")

    # Process Audio Input
    if user_audio is not None:
        if not api_key:
            st.warning("⚠️ Enter your Gemini API key in the sidebar.")
            st.stop()

        client = genai.Client(api_key=api_key)
        audio_bytes = user_audio.getvalue()
        
        st.session_state.chat_history.append({"role": "user", "content": "🎙️ *[Spoken Question Submitted]*"})
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
                                {"text": f"{FAST_SYSTEM_PROMPT}\nScenario: {scenario}. Listen to student speech and reply directly."}
                            ]
                        }],
                        config={"temperature": 0.2, "max_output_tokens": 600}
                    )
                    reply_text = resp.text
                    latency = round(time.time() - t_start, 2)
                    
                    st.markdown(reply_text)
                    st.caption(f"⚡ *Response Latency: {latency}s*")
                    
                    full_sanskrit = extract_complete_sanskrit_speech(reply_text)
                    if full_sanskrit:
                        render_talking_avatar(full_sanskrit, selected_teacher, auto_play=True)
                    
                    st.session_state.chat_history.append({"role": "model", "content": reply_text})
                    st.session_state.turn_count += 1
                    update_xp(10)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    # Text Input as alternative
    if text_input := st.chat_input("Or type here (e.g. mama nama, katham asti...):"):
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
                        config={"system_instruction": FAST_SYSTEM_PROMPT, "temperature": 0.2, "max_output_tokens": 600}
                    )
                    reply_text = resp.text
                    latency = round(time.time() - t_start, 2)
                    
                    st.markdown(reply_text)
                    st.caption(f"⚡ *Response Latency: {latency}s*")
                    
                    full_sanskrit = extract_complete_sanskrit_speech(reply_text)
                    if full_sanskrit:
                        render_talking_avatar(full_sanskrit, selected_teacher, auto_play=True)
                        
                    st.session_state.chat_history.append({"role": "model", "content": reply_text})
                    st.session_state.turn_count += 1
                    update_xp(5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

# =========================================================
# TAB 2: ŚIKṢĀ PHONETIC COACH
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
                    }]
                )
                st.markdown(resp.text)
                update_xp(15)
            except Exception as e:
                st.error(f"Error: {str(e)}")

# =========================================================
# TAB 3: SVARA & CHANDAḤ METRE ENGINE
# =========================================================
with tab_chandas:
    st.markdown("#### 🕉️ वैदिक-स्वर एवं छन्दो-विश्लेषकः (Pingala Chandaḥ Engine)")
    
    verse = st.text_area(
        "Enter Verse / Mantra for Scansion:",
        value="धर्मक्षेत्रे कुरुक्षेत्रे समवेता युयुत्सवः।\nमामकाः पाण्डवाश्चैव किमकुर्वत सञ्जय॥",
        height=80
    )
    if st.button("Scan Metre & Pitch / छन्दो-परीक्षणम्", use_container_width=True):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Scanning syllables..."):
            try:
                resp = client.models.generate_content(
                    model=ACTIVE_MODEL,
                    contents=[{"role": "user", "parts": [{"text": f"Perform Pingala Chandaḥ scansion on: '{verse}'. Identify metre name (Anuṣṭubh, Triṣṭubh, etc.), Laghu (।) / Guru (ऽ) syllabic mapping, Gana breakdown, and Vedic Svara rules."}]}]
                )
                st.markdown(resp.text)
                update_xp(20)
            except Exception as e:
                st.error(f"Error: {str(e)}")

# =========================================================
# TAB 4: PERSISTENT SRS VOCABULARY VAULT
# =========================================================
with tab_vault:
    st.markdown("#### 🧠 Spaced Repetition (SRS) Vocabulary Database")
    
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        st.markdown("##### ➕ **Add Word to Database Vault:**")
        with st.form("vault_entry"):
            vw = st.text_input("Sanskrit Word (पदम्):")
            vm = st.text_input("Meaning (अर्थः):")
            vd = st.text_input("Root / Stem (धातुः/प्रातिपदिकम्):")
            if st.form_submit_button("Save Word (+15 XP)") and vw and vm:
                save_word(vw, vm, vd if vd else vw)
                st.success(f"Word '{vw}' permanently saved to SQLite database!")
                st.rerun()

    with col_v2:
        st.markdown("##### 📚 **Saved Word Cards (SQLite):**")
        v_list = get_vault()
        for itm in v_list:
            st.markdown(f"• **{itm['word']}** — {itm['meaning']} | *Root:* `{itm['dhatu']}` | ⏳ Due: `{itm['review_due']}`")

# =========================================================
# TAB 5: UNIVERSAL TRANSLATOR
# =========================================================
with tab_trans:
    st.markdown("#### 🌐 Universal Multi-Language ↔ Sanskrit Translator")
    
    trans_dir = st.radio("Direction", ["Any Language ➔ Sanskrit", "Sanskrit ➔ Any Language"], horizontal=True)
    if trans_dir == "Sanskrit ➔ Any Language":
        t_lang = st.selectbox("Target Language:", ["Telugu (తెలుగు)", "Hindi (हिन्दी)", "English", "Tamil (தமிழ்)", "Kannada (ಕನ್ನಡ)"])
    
    t_in = st.text_area("Enter sentence to translate:", height=70)
    
    if st.button("Translate / अनुवादं कुरु", use_container_width=True) and t_in.strip():
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Translating..."):
            prompt = "Translate into Sanskrit with full sentence, IAST, and Padaccheda." if trans_dir.startswith("Any") else f"Translate into {t_lang} with Sandhi split and word meanings."
            try:
                resp = client.models.generate_content(
                    model=ACTIVE_MODEL,
                    contents=[{"role": "user", "parts": [{"text": f"{prompt}\nInput: {t_in}"}]}],
                    config={"temperature": 0.2}
                )
                st.markdown(resp.text)
                if "संस्कृतम्" in resp.text:
                    full_s = extract_complete_sanskrit_speech(resp.text)
                    if full_s:
                        render_talking_avatar(full_s, selected_teacher, auto_play=False)
            except Exception as e:
                st.error(f"Error: {str(e)}")

# =========================================================
# TAB 6: REMARKS & FEEDBACK LOG ARCHIVE
# =========================================================
with tab_feedback:
    st.markdown("#### 📝 अभिप्राय-पञ्जिका (Teacher & Student Remarks Archive)")
    st.caption("All reported errors, corrections, and notes are permanently stored here in the database.")
    
    logs = get_all_feedbacks()
    if not logs:
        st.info("No remarks recorded yet. You can submit remarks directly under any Acharya response in Tab 1.")
    else:
        for f_id, f_time, f_teacher, f_type, f_rem, f_resp in logs:
            with st.expander(f"📌 [{f_time}] {f_type} — {f_teacher}"):
                st.markdown(f"**Remark / Note:**\n{f_rem if f_rem else '*(No written note provided)*'}")
                st.markdown("---")
                st.markdown(f"**Acharya Response Inspected:**\n```\n{f_resp}\n```")
