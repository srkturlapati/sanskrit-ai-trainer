import sys
import os
import time
import io
import sqlite3
import datetime
import base64

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
import streamlit as st
import streamlit.components.v1 as components

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

# --- CSS & AVATAR TALKING ANIMATION ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
    
    .header-box {
        background: linear-gradient(135deg, #E65100 0%, #BF360C 50%, #212121 100%);
        border-radius: 16px;
        padding: 18px 24px;
        color: #FFFFFF;
        box-shadow: 0 8px 24px rgba(230, 81, 0, 0.25);
        margin-bottom: 18px;
    }
    
    .avatar-wrapper {
        position: relative;
        width: 110px;
        height: 110px;
        margin: 0 auto;
    }
    
    .avatar-base {
        width: 110px;
        height: 110px;
        border-radius: 50%;
        object-fit: cover;
        border: 4px solid #FF8F00;
        box-shadow: 0 0 18px rgba(255, 143, 0, 0.4);
        transition: all 0.3s ease;
    }
    
    .talking-lip {
        position: absolute;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        width: 20px;
        height: 5px;
        background: #8D1414;
        border-radius: 50%;
        opacity: 0;
        transition: all 0.1s ease;
    }
    
    .is-speaking .talking-lip {
        opacity: 0.95;
        animation: mouthTalk 0.26s infinite alternate ease-in-out;
    }
    
    .is-speaking .avatar-base {
        box-shadow: 0 0 28px rgba(255, 111, 0, 0.9);
        transform: scale(1.03);
        border-color: #FFD54F;
    }

    @keyframes mouthTalk {
        0% { height: 4px; width: 16px; border-radius: 50%; }
        50% { height: 12px; width: 20px; border-radius: 40%; background: #5C0B0B; }
        100% { height: 7px; width: 22px; border-radius: 50%; }
    }

    .status-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 16px;
        font-size: 0.78rem;
        font-weight: 600;
        background: rgba(76, 175, 80, 0.15);
        color: #81C784;
        border: 1px solid #4CAF50;
        margin-bottom: 6px;
    }
    
    .remark-box {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 143, 0, 0.2);
        border-radius: 10px;
        padding: 12px;
        margin-top: 8px;
    }
</style>
""", unsafe_allow_html=True)

# Helper: Load images from assets/ with absolute path fallback
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

TEACHERS = {
    "Male Guru (आचार्यः वसिष्ठः)": {
        "title": "आचार्यः वसिष्ठः (Acharya Vasiṣṭha)",
        "desc": "Classical Guru • Deep Pedagogical Voice",
        "img": male_src,
        "status": male_status,
        "tld": "co.in",
        "slow": True
    },
    "Female Āchāryā (आचार्या गार्गी)": {
        "title": "आचार्या गार्गी (Acharyaa Gargi)",
        "desc": "Scholarly Preceptor • Warm & Melodic Voice",
        "img": female_src,
        "status": female_status,
        "tld": "com",
        "slow": False
    },
    "Child Peer (बालकः ध्रुवः)": {
        "title": "बालकः ध्रुवः (Balaka Dhruva)",
        "desc": "Playful Young Peer • Fast & Cheerful Cadence",
        "img": child_src,
        "status": child_status,
        "tld": "co.uk",
        "slow": False
    }
}

# --- HIGH-SPEED IN-MEMORY TTS ENGINE ---
@st.cache_data(show_spinner=False, max_entries=100)
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
            <div class="status-badge">🟢 AI Tutor Speaking ({cfg['title'].split('(')[0].strip()})</div>
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

# --- CLIENT-SIDE LIVE SPEECH-TO-TEXT COMPONENT (AUTO-TYPE) ---
def render_live_speech_recognizer():
    components.html("""
    <div style="font-family:sans-serif; text-align:center; padding:8px; border-radius:10px; background:rgba(255,111,0,0.06); border:1px dashed #FF8F00;">
        <div style="font-size:0.88rem; color:#FF8F00; font-weight:700; margin-bottom:6px;">🎙️ Live Speech-to-Text (Auto-Type in any language)</div>
        <button id="micBtn" onclick="toggleDictation()" style="background:#E65100; color:white; border:none; padding:8px 18px; border-radius:20px; font-weight:bold; cursor:pointer; font-size:0.85rem;">
            🎙️ Start Speaking
        </button>
        <div id="statusText" style="font-size:0.8rem; color:#888; margin-top:5px;">Click to speak (English, Hindi, Sanskrit, Telugu)</div>
    </div>
    <script>
        var recognition;
        var recognizing = false;
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognition = new SpeechRecognition();
            recognition.continuous = false;
            recognition.interimResults = false;
            recognition.lang = 'hi-IN'; // Works for Sanskrit, Hindi, and general Indic speech
            
            recognition.onstart = function() {
                recognizing = true;
                document.getElementById('micBtn').style.background = '#2E7D32';
                document.getElementById('micBtn').innerText = '🔴 Listening... (Speak now)';
                document.getElementById('statusText').innerText = 'Listening to your voice...';
            };
            recognition.onresult = function(event) {
                var transcript = event.results[0][0].transcript;
                document.getElementById('statusText').innerText = 'Recognized: ' + transcript;
                
                // Copy into Streamlit chat input or clipboard
                navigator.clipboard.writeText(transcript);
                var inputs = window.parent.document.querySelectorAll('textarea, input[type=text]');
                if(inputs.length > 0) {
                    var lastInput = inputs[inputs.length - 1];
                    lastInput.value = transcript;
                    lastInput.dispatchEvent(new Event('input', { bubbles: true }));
                }
            };
            recognition.onerror = function() {
                recognizing = false;
                document.getElementById('micBtn').style.background = '#E65100';
                document.getElementById('micBtn').innerText = '🎙️ Start Speaking';
                document.getElementById('statusText').innerText = 'Speech error. Please try again.';
            };
            recognition.onend = function() {
                recognizing = false;
                document.getElementById('micBtn').style.background = '#E65100';
                document.getElementById('micBtn').innerText = '🎙️ Start Speaking';
            };
        } else {
            document.getElementById('statusText').innerText = 'Use Chrome/Edge/Safari for live speech typing.';
        }
        function toggleDictation() {
            if (recognition) {
                if (recognizing) { recognition.stop(); } else { recognition.start(); }
            }
        }
    </script>
    """, height=95)

# --- HERO ---
st.markdown("""
<div class="header-box">
    <h2 style="margin:0; font-weight:800;">🚩 Sambhāṣaṇa AI Pro (सम्भाषण-प्रशिक्षकः)</h2>
    <p style="margin:4px 0 0 0; opacity:0.9;">High-Speed Spoken Sanskrit AI • Live Auto-Type • Inline Remarks & Feedback</p>
</div>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
u_name, u_lvl, u_strk, u_xp = get_user()

with st.sidebar:
    st.markdown("### 🎙️ **Teacher & Voice Selection**")
    selected_teacher = st.selectbox("Active Guide:", list(TEACHERS.keys()), index=0)
    t_info = TEACHERS[selected_teacher]
    
    st.markdown(f"""
    <div style="text-align:center; padding:10px; background:rgba(255,255,255,0.04); border-radius:12px; border:1px solid rgba(255,143,0,0.25);">
        <img src="{t_info['img']}" style="width:90px; height:90px; border-radius:50%; object-fit:cover; border:3px solid #FF8F00; margin-bottom:6px;"/>
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
        "Proficiency Level / स्तरः",
        ["Beginner (प्रथमा)", "Intermediate (मध्यमा)", "Advanced (उत्तमा)"],
        index=0
    )
    
    st.markdown("---")
    st.markdown("### 🏆 **Student Profile**")
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.metric("🔥 Day Streak", f"{u_strk} Days")
    with col_p2:
        st.metric("⭐ Saved XP", f"{u_xp} XP")
    
    if st.button("🔄 Reset Chat History", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.turn_count = 0
        st.rerun()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "turn_count" not in st.session_state:
    st.session_state.turn_count = 0

FAST_SYSTEM_PROMPT = f"""You are '{t_info['title']}', a fast interactive spoken Sanskrit tutor.
Student Level: {target_tier}.

CRITICAL: Keep your response short, lively, and within 2-3 spoken sentences in Sarala Samskritam. Always finish with a quick question to keep dialogue going.
Format ALWAYS:
[संस्कृतम्]: <Short Sanskrit dialogue>
[IAST]: <Transliteration>
[English]: <Meaning>
[✨ Say It Better]: <One short idiomatic upgrade>
[मार्गदर्शनम्] (Only if error made):
- 💡 Hint & rule
"""

# --- 5 FOCUSED TABS (No redundant remarks tab) ---
tab_roleplay, tab_shiksha, tab_chandas, tab_vault, tab_trans = st.tabs([
    "💬 1. Fast Oral Roleplay",
    "🎙️ 2. Śikṣā Phonetics",
    "🕉️ 3. Svara & Chandaḥ",
    "🧠 4. SRS Vault",
    "🌐 5. Universal Translator"
])

# =========================================================
# TAB 1: FAST ORAL ROLEPLAY + INLINE REMARKS
# =========================================================
with tab_roleplay:
    st.markdown("#### 💬 Live Conversation with AI Tutor (सजीव-सम्भाषणम्)")
    
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
    
    # 1. Render Messages with Complete Speech & Direct Inline Remarks Form
    for idx, msg in enumerate(st.session_state.chat_history):
        role = "assistant" if msg["role"] == "model" else "user"
        with st.chat_message(role):
            st.markdown(msg["content"])
            if role == "assistant":
                full_s = extract_complete_sanskrit_speech(msg["content"])
                if full_s:
                    render_talking_avatar(full_s, selected_teacher, auto_play=False)
                
                # --- INLINE REMARK & FEEDBACK FORM ---
                with st.expander("💬 Add Remark / Report Mistake on this Response"):
                    with st.form(key=f"remark_form_{idx}"):
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
                        fb_text = st.text_area("Write your remarks / correction:", key=f"fb_txt_{idx}", placeholder="e.g. In line 1, please use 'गच्छामि'...")
                        submitted = st.form_submit_button("💾 Save Remark (पञ्जीकरणम्)")
                        if submitted:
                            prior_user = st.session_state.chat_history[idx - 1]["content"] if idx > 0 else "N/A"
                            save_feedback(selected_teacher, prior_user, msg["content"], fb_type, fb_text)
                            st.success("✅ Remark saved successfully into the database!")

    # 2. CLIENT-SIDE LIVE SPEECH-TO-TEXT (AUTO-TYPE)
    st.write("---")
    render_live_speech_recognizer()

    # 3. FAST AUDIO RECORDING WIDGET
    user_audio = st.audio_input("Or Record Voice Question:", key=f"mic_turn_{st.session_state.turn_count}")

    # Process Audio Input
    if user_audio is not None:
        if not api_key:
            st.warning("⚠️ Enter your Gemini API key in the sidebar.")
            st.stop()

        client = genai.Client(api_key=api_key)
        audio_bytes = user_audio.getvalue()
        
        st.session_state.chat_history.append({"role": "user", "content": "🎙️ *[Oral Question Submitted]*"})
        with st.chat_message("user"):
            st.audio(user_audio, format="audio/wav")

        with st.chat_message("assistant"):
            with st.spinner("आचार्यः चिन्तयति..."):
                t_start = time.time()
                try:
                    resp = client.models.generate_content(
                        model=ACTIVE_MODEL,
                        contents=[{
                            "role": "user",
                            "parts": [
                                {"inline_data": {"mime_type": "audio/wav", "data": audio_bytes}},
                                {"text": f"{FAST_SYSTEM_PROMPT}\nScenario: {scenario}. Respond quickly in character."}
                            ]
                        }],
                        config={"temperature": 0.2, "max_output_tokens": 400}
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
                    update_xp(10)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    # Process Text Input (Direct or Auto-Typed)
    if text_input := st.chat_input("Type here or speak with the microphone above..."):
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
                        config={"system_instruction": FAST_SYSTEM_PROMPT, "temperature": 0.2, "max_output_tokens": 400}
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
                    update_xp(5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

# =========================================================
# TAB 2: ŚIKṢĀ PHONETICS
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
                    contents=[{"role": "user", "parts": [{"text": f"Perform Pingala Chandaḥ scansion on: '{verse}'. Identify metre name (Anuṣṭubh, Triṣṭubh, etc.), Laghu (।) / Guru (ऽ) syllabic mapping, Gana breakdown, and Vedic Svara rules."}]}],
                    config={"max_output_tokens": 500}
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
                    config={"temperature": 0.2, "max_output_tokens": 400}
                )
                st.markdown(resp.text)
                if "संस्कृतम्" in resp.text:
                    full_s = extract_complete_sanskrit_speech(resp.text)
                    if full_s:
                        render_talking_avatar(full_s, selected_teacher, auto_play=False)
            except Exception as e:
                st.error(f"Error: {str(e)}")
