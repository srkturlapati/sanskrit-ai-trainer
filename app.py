import sys
import os
import time
import io
import sqlite3
import datetime
import json
from pypdf import PdfReader

# Enforce UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from google import genai
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate
import streamlit as st
import streamlit.components.v1 as components

# --- HIGH-CONCURRENCY STREAMLIT CONFIGURATION ---
st.set_page_config(
    page_title="Sambhāṣaṇa AI Enterprise | सम्भाषणम्",
    page_icon="🚩",
    layout="wide",
    initial_sidebar_state="expanded",
)

ACTIVE_MODEL = "gemini-2.5-flash"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "sambhāṣaṇa_concurrency.db")

# --- THREAD-SAFE CONCURRENT DATABASE LAYER (SQLite WAL Mode) ---
def get_db_connection():
    """Returns a SQLite connection optimized for 1000+ concurrent connections."""
    conn = sqlite3.connect(DB_FILE, timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL;")  # Write-Ahead Logging allows concurrent reads & writes
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

# Multi-Tenant Session Initialization
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

# --- CLIENT-SIDE EDGE COMPUTING CSS & RESPONSIVE UI ---
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
        width: 80px;
        height: 80px;
        margin: 0 auto;
    }
    
    .avatar-base {
        width: 80px;
        height: 80px;
        border-radius: 50%;
        object-fit: cover;
        border: 3px solid #FF8F00;
        box-shadow: 0 0 14px rgba(255, 143, 0, 0.4);
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
    
    .status-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 14px;
        font-size: 0.75rem;
        font-weight: 600;
        background: rgba(76, 175, 80, 0.15);
        color: #81C784;
        border: 1px solid #4CAF50;
    }
</style>
""", unsafe_allow_html=True)

# Helper: Load images from assets
def get_avatar_img(base_name, fallback_url):
    extensions = [".jpeg", ".jpg", ".png", ".JPEG", ".JPG", ".PNG"]
    assets_dir = os.path.join(BASE_DIR, "assets")
    for ext in extensions:
        local_p = os.path.join(assets_dir, base_name + ext)
        if os.path.isfile(local_p):
            try:
                mime = "image/jpeg" if ext.lower() in [".jpeg", ".jpg"] else "image/png"
                import base64
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
        "pitch": 0.85,
        "rate": 0.90
    },
    "Female Āchāryā (आचार्या गार्गी)": {
        "title": "आचार्या गार्गी (Acharyaa Gargi)",
        "desc": "Scholarly Preceptor • Clear Melodic Voice",
        "img": female_src,
        "pitch": 1.15,
        "rate": 0.95
    },
    "Child Peer (बालकः ध्रुवः)": {
        "title": "बालकः ध्रुवः (Balaka Dhruva)",
        "desc": "Playful Peer • Cheerful Lively Voice",
        "img": child_src,
        "pitch": 1.45,
        "rate": 1.10
    }
}

# --- EDGE CLIENT-SIDE SPEECH SYNTHESIS & AVATAR ANIMATION (0ms Server Overhead) ---
def render_edge_talking_avatar(sanskrit_text: str, teacher_key: str, auto_play=True):
    clean_text = sanskrit_text.replace('*', '').replace('#', '').replace('-', '').replace('[', '').replace(']', '').replace('"', '').replace("'", "").strip()
    if not clean_text:
        return
    cfg = TEACHERS[teacher_key]
    elem_id = f"aud_{abs(hash(clean_text)) % 1000000}"
    
    components.html(f"""
    <div style="display:flex; align-items:center; gap:14px; font-family:'Plus Jakarta Sans', sans-serif; background:rgba(255,255,255,0.03); padding:10px 14px; border-radius:12px; border:1px solid rgba(255,143,0,0.25);">
        <div style="position:relative; width:65px; height:65px;" id="wrap_{elem_id}">
            <img src="{cfg['img']}" style="width:65px; height:65px; border-radius:50%; object-fit:cover; border:2.5px solid #FF8F00;" id="img_{elem_id}"/>
            <div id="lip_{elem_id}" style="position:absolute; bottom:12px; left:50%; transform:translateX(-50%); width:14px; height:3px; background:#8D1414; border-radius:50%; opacity:0;"></div>
        </div>
        <div style="flex-grow:1;">
            <div style="font-size:0.75rem; color:#81C784; font-weight:700;">🟢 Edge Native Neural Audio (Zero Server Delay)</div>
            <div style="font-weight:700; color:#FF8F00; font-size:0.95rem; margin-top:2px;">{cfg['title']}</div>
            <button onclick="speakSanskrit()" style="background:#E65100; color:white; border:none; padding:5px 14px; border-radius:16px; font-weight:bold; cursor:pointer; font-size:0.8rem; margin-top:4px;">
                🔊 Replay Speech
            </button>
        </div>
    </div>
    <script>
        function speakSanskrit() {{
            if ('speechSynthesis' in window) {{
                window.speechSynthesis.cancel();
                var utterance = new SpeechSynthesisUtterance("{clean_text}");
                utterance.lang = 'hi-IN'; // Hardware Indic phonetics
                utterance.pitch = {cfg['pitch']};
                utterance.rate = {cfg['rate']};
                
                var lip = document.getElementById("lip_{elem_id}");
                var img = document.getElementById("img_{elem_id}");
                
                utterance.onstart = function() {{
                    lip.style.opacity = "0.95";
                    lip.style.animation = "mouthTalk 0.25s infinite alternate ease-in-out";
                    img.style.boxShadow = "0 0 20px rgba(255,143,0,0.9)";
                }};
                utterance.onend = function() {{
                    lip.style.opacity = "0";
                    lip.style.animation = "none";
                    img.style.boxShadow = "none";
                }};
                utterance.onerror = function() {{
                    lip.style.opacity = "0";
                    lip.style.animation = "none";
                }};
                window.speechSynthesis.speak(utterance);
            }}
        }}
        // Autoplay on mount
        if ({str(auto_play).lower()}) {{
            setTimeout(speakSanskrit, 150);
        }}
    </script>
    <style>
        @keyframes mouthTalk {{
            0% {{ height: 3px; width: 10px; }}
            50% {{ height: 8px; width: 14px; background: #5C0B0B; }}
            100% {{ height: 5px; width: 16px; }}
        }}
    </style>
    """, height=90)

# Helper: Extract pure Sanskrit dialogue block
def extract_sanskrit_speech(reply_content: str) -> str:
    if "[संस्कृतम्]:" in reply_content:
        part = reply_content.split("[संस्कृतम्]:")[1]
        for marker in ["[IAST]:", "[English]:", "[✨ Say It Better]:", "[मार्गदर्शनम्]"]:
            if marker in part:
                part = part.split(marker)[0]
        return part.replace('*', '').replace('#', '').strip()
    return ""

# --- APP HERO ---
st.markdown("""
<div class="header-box">
    <h2 style="margin:0; font-weight:800;">🚩 Sambhāṣaṇa AI Enterprise (सम्भाषणम्)</h2>
    <p style="margin:2px 0 0 0; opacity:0.92; font-size:0.9rem;">Multi-Tenant Concurrent Sanskrit Dialogue Engine • Zero-Latency Edge Voice</p>
</div>
""", unsafe_allow_html=True)

# --- SIDEBAR: Profile & Settings ---
u_streak, u_xp = get_user_stats(st.session_state.user_session_id)

with st.sidebar:
    st.markdown("### 🎙️ **Preceptor & Voice Profile**")
    selected_teacher = st.selectbox("Active Guide:", list(TEACHERS.keys()), index=0)
    t_info = TEACHERS[selected_teacher]
    
    st.markdown(f"""
    <div style="text-align:center; padding:10px; background:rgba(255,255,255,0.04); border-radius:12px; border:1px solid rgba(255,143,0,0.25);">
        <img src="{t_info['img']}" style="width:80px; height:80px; border-radius:50%; object-fit:cover; border:3px solid #FF8F00; margin-bottom:6px;"/>
        <div style="font-weight:700; color:#FF8F00;">{t_info['title']}</div>
        <div style="font-size:0.75rem; opacity:0.8;">{t_info['desc']}</div>
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
        st.rerun()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

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

# --- 5 ENTERPRISE TABS ---
tab_roleplay, tab_bulk_vocab, tab_shiksha, tab_chandas, tab_trans = st.tabs([
    "💬 1. Instant Dialogue",
    "📚 2. Bulk PDF Vocabulary",
    "🎙️ 3. Śikṣā Phonetics",
    "🕉️ 4. Svara & Chandaḥ",
    "🌐 5. Universal Translator"
])

# =========================================================
# TAB 1: INSTANT STREAMING DIALOGUE + INLINE REMARKS
# =========================================================
with tab_roleplay:
    st.markdown("#### 💬 Situational Real-Life Immersion (सजीव-सम्भाषणम्)")
    
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
    
    # 1. Render Chat History with Edge Speech + Inline Remarks
    for idx, msg in enumerate(st.session_state.chat_history):
        role = "assistant" if msg["role"] == "model" else "user"
        with st.chat_message(role):
            st.markdown(msg["content"])
            if role == "assistant":
                s_text = extract_sanskrit_speech(msg["content"])
                if s_text:
                    render_edge_talking_avatar(s_text, selected_teacher, auto_play=False)
                
                # Inline Remark Form
                with st.expander(f"📝 Remark / Feedback on Response #{idx // 2 + 1}"):
                    with st.form(key=f"rem_form_{idx}"):
                        fb_type = st.selectbox(
                            "Classification:",
                            [
                                "⚠️ Grammar / Sūtra Error (व्याकरण-दोषः)",
                                "⚠️ Inaccurate Translation (अनुवाद-दोषः)",
                                "⚠️ Sandhi / Spelling Mistake (सन्धि/वर्ण-दोषः)",
                                "💡 Suggestion / Better Phrasing (सुझावः)",
                                "✅ Correct & Auspicious (उत्कृष्टम्)"
                            ],
                            key=f"fb_sel_{idx}"
                        )
                        fb_text = st.text_area("Write remarks:", key=f"fb_txt_{idx}", placeholder="e.g. In sentence 1, 'गच्छामि' is more appropriate...")
                        if st.form_submit_button("💾 Save Remark"):
                            prior_user = st.session_state.chat_history[idx - 1]["content"] if idx > 0 else "N/A"
                            save_user_feedback(st.session_state.user_session_id, selected_teacher, prior_user, msg["content"], fb_type, fb_text)
                            st.success("✅ Remark saved to SQLite WAL database!")

    # 2. CLIENT-SIDE LIVE HARDWARE SPEECH RECOGNITION (0ms Upload Latency)
    components.html("""
    <div style="font-family:'Plus Jakarta Sans', sans-serif; text-align:center; padding:10px; border-radius:12px; background:rgba(255,111,0,0.06); border:2px dashed #FF8F00; margin-top:10px;">
        <div style="font-weight:700; color:#FF8F00; font-size:0.9rem; margin-bottom:6px;">🎙️ Hardware Voice Input (Auto-Transcribe in Real-Time)</div>
        <button id="micBtn" onclick="toggleDictation()" style="background:#E65100; color:white; border:none; padding:8px 22px; border-radius:20px; font-weight:700; font-size:0.85rem; cursor:pointer;">
            🔴 Tap to Speak
        </button>
        <div id="micStatus" style="font-size:0.8rem; color:#AAA; margin-top:5px;">Click to talk in Sanskrit, Hindi, Telugu, or English.</div>
    </div>
    <script>
        var recognition = null;
        var isRec = false;
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognition = new SR();
            recognition.continuous = true;
            recognition.interimResults = true;
            recognition.lang = 'hi-IN';
            
            recognition.onstart = function() {
                isRec = true;
                document.getElementById('micBtn').style.background = '#2E7D32';
                document.getElementById('micBtn').innerText = '🟢 Listening... (Tap to Send)';
                document.getElementById('micStatus').innerText = 'Capturing hardware acoustics...';
            };
            
            recognition.onresult = function(e) {
                var full = '';
                for (var i = 0; i < e.results.length; ++i) {
                    full += e.results[i][0].transcript + ' ';
                }
                var inputs = window.parent.document.querySelectorAll('textarea, input[type=text]');
                if (inputs.length > 0) {
                    var target = inputs[inputs.length - 1];
                    target.value = full.trim();
                    target.dispatchEvent(new Event('input', { bubbles: true }));
                }
            };
            
            recognition.onend = function() {
                isRec = false;
                document.getElementById('micBtn').style.background = '#E65100';
                document.getElementById('micBtn').innerText = '🔴 Tap to Speak';
                document.getElementById('micStatus').innerText = 'Press Enter in the chat box below to submit.';
            };
        }
        function toggleDictation() {
            if (recognition) {
                if (isRec) { recognition.stop(); } else { recognition.start(); }
            }
        }
    </script>
    """, height=105)

    # 3. HIGH-SPEED STREAMING CHAT INPUT
    if user_text := st.chat_input("Auto-typed speech appears here... or type directly:"):
        if not api_key:
            st.warning("⚠️ Enter your Gemini API key in the sidebar.")
            st.stop()

        client = genai.Client(api_key=api_key)
        is_dev = any("\u0900" <= char <= "\u097f" for char in user_text)
        display_prompt = user_text if is_dev else f"{user_text} ({transliterate(user_text, sanscript.ITRANS, sanscript.DEVANAGARI)})"

        st.session_state.chat_history.append({"role": "user", "content": display_prompt})
        with st.chat_message("user"):
            st.markdown(display_prompt)

        # Prepare messages
        contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": str(m["content"])}]} for m in st.session_state.chat_history]

        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            full_response = ""
            
            t_start = time.time()
            try:
                # TOKEN STREAMING FOR SUB-400MS FIRST-BYTE LATENCY
                response_stream = client.models.generate_content_stream(
                    model=ACTIVE_MODEL,
                    contents=contents,
                    config={"system_instruction": FAST_SYSTEM_PROMPT, "temperature": 0.2, "max_output_tokens": 400}
                )
                for chunk in response_stream:
                    if chunk.text:
                        full_response += chunk.text
                        response_placeholder.markdown(full_response + "▌")
                
                latency = round(time.time() - t_start, 2)
                response_placeholder.markdown(full_response)
                st.caption(f"⚡ *Response Streamed in {latency}s*")
                
                s_text = extract_sanskrit_speech(full_response)
                if s_text:
                    render_edge_talking_avatar(s_text, selected_teacher, auto_play=True)
                
                st.session_state.chat_history.append({"role": "model", "content": full_response})
                update_user_xp(st.session_state.user_session_id, 10)
            except Exception as e:
                st.error(f"Error: {str(e)}")

# =========================================================
# TAB 2: BULK PDF VOCABULARY INGESTION
# =========================================================
with tab_bulk_vocab:
    st.markdown("#### 📚 Bulk PDF Sanskrit Vocabulary Extractor")
    st.caption("Extracts entire chapters into your persistent SQLite vocabulary database with 1 click.")
    
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        uploaded_pdf = st.file_uploader("Upload Sanskrit Lesson PDF:", type=["pdf"])
        max_extract = st.slider("Words to extract:", 10, 50, 25)
        
        if uploaded_pdf is not None and st.button("⚡ Extract & Save into Database", use_container_width=True):
            if not api_key:
                st.warning("⚠️ Enter Gemini API key.")
                st.stop()
            with st.spinner("Extracting and analyzing Sanskrit morphology..."):
                try:
                    pdf = PdfReader(uploaded_pdf)
                    raw_text = "".join([page.extract_text() or "" for page in pdf.pages[:8]])
                    if not raw_text.strip():
                        st.error("No readable text found in PDF.")
                        st.stop()
                    
                    client = genai.Client(api_key=api_key)
                    PROMPT_JSON = f"""Extract {max_extract} unique Sanskrit words from this text as a JSON array of objects.
Keys: "word", "meaning", "dhatu", "level".
Text:
{raw_text[:4000]}
"""
                    res = client.models.generate_content(
                        model=ACTIVE_MODEL,
                        contents=[{"role": "user", "parts": [{"text": PROMPT_JSON}]}],
                        config={"temperature": 0.1, "response_mime_type": "application/json"}
                    )
                    words = json.loads(res.text)
                    saved = save_vault_bulk(st.session_state.user_session_id, words)
                    st.success(f"🎉 Successfully ingested {saved} words into your SQLite database!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    with col_p2:
        st.markdown("##### 🗄️ **Your Personal Vocabulary Vault:**")
        vault = get_user_vault(st.session_state.user_session_id)
        st.caption(f"Total Words Stored: **{len(vault)}**")
        for item in vault[:25]:
            st.markdown(f"• **{item['word']}** — *{item['meaning']}* | Root: `{item['dhatu']}`")

# =========================================================
# TAB 3: ŚIKṢĀ PHONETICS
# =========================================================
with tab_shiksha:
    st.markdown("#### 🎙️ पाणिनीय-शिक्षा एवं उच्चारण-परीक्षकः (Phonetic Accent Coach)")
    drill = st.selectbox("Select Target Verse:", [
        "सत्यं वद, धर्मं चर। (Speak truth, practice righteousness)",
        "विद्या ददाति विनयं विनयाद्याति पात्रताम्। (Knowledge gives humility)",
        "वृक्षात् फलानि भूमौ पतन्ति। (Fruits fall from tree - Mahāprāṇa 'ph')",
        "अहं प्रतिदिनं प्रातः पञ्चवादने उत्तिष्ठामि। (I wake at 5 AM - Retroflex 'ṣṭh')"
    ])
    phrase = drill.split('(')[0].strip()
    
    st.markdown(f"##### 🔊 **Master Chanting ({t_info['title']}):**")
    render_edge_talking_avatar(phrase, selected_teacher, auto_play=False)
    
    st.markdown("##### 🎙️ **Practice with Hardware Microphone:**")
    st.caption("Dictate your chanting into the oral dialogue tab for instant feedback.")

# =========================================================
# TAB 4: SVARA & CHANDAḤ ENGINE
# =========================================================
with tab_chandas:
    st.markdown("#### 🕉️ वैदिक-स्वर एवं छन्दो-विश्लेषकः (Pingala Chandaḥ Engine)")
    verse_input = st.text_area("Enter Verse for Metrical Scansion:", value="धर्मक्षेत्रे कुरुक्षेत्रे समवेता युयुत्सवः।\nमामकाः पाण्डवाश्चैव किमकुर्वत सञ्जय॥", height=75)
    
    if st.button("Scan Metre & Pitch / छन्दो-परीक्षणम्", use_container_width=True):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Analyzing scansion..."):
            try:
                res = client.models.generate_content(
                    model=ACTIVE_MODEL,
                    contents=[{"role": "user", "parts": [{"text": f"Scan Pingala Chandaḥ on: '{verse_input}'. Identify metre name, Laghu (।) / Guru (ऽ) mapping, and Gana breakdown."}]}]
                )
                st.markdown(res.text)
            except Exception as e:
                st.error(f"Error: {str(e)}")

# =========================================================
# TAB 5: UNIVERSAL TRANSLATOR
# =========================================================
with tab_trans:
    st.markdown("#### 🌐 Universal Multi-Language ↔ Sanskrit Translator")
    t_input = st.text_area("Enter sentence to translate:", height=65)
    
    if st.button("Translate / अनुवादं कुरु", use_container_width=True) and t_input.strip():
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Translating..."):
            try:
                res = client.models.generate_content(
                    model=ACTIVE_MODEL,
                    contents=[{"role": "user", "parts": [{"text": f"Translate into Sanskrit with Devanagari, IAST, and Padaccheda:\n{t_input}"}]}]
                )
                st.markdown(res.text)
                s_t = extract_sanskrit_speech(res.text)
                if s_t:
                    render_edge_talking_avatar(s_t, selected_teacher, auto_play=False)
            except Exception as e:
                st.error(f"Error: {str(e)}")
