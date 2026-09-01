import sys
import os
import time
import io
import sqlite3
import datetime
import base64

# Enforce UTF-8 encoding across environments
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

# --- DATABASE PERSISTENCE LAYER (SQLite) ---
DB_FILE = "sambhāṣaṇa_master.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Profile & Gamification
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
    # Vocabulary Vault (SRS)
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
    # Analytics & Session Log
    c.execute('''
        CREATE TABLE IF NOT EXISTS session_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_date TEXT,
            words_spoken INTEGER,
            accuracy_score INTEGER
        )
    ''')
    
    # Initialize default user
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

# --- COMMERCIAL THEME & ANIMATED LIP-SYNC CSS ---
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
    
    /* AVATAR TALKING & LIP-SYNC ANIMATION */
    .avatar-wrapper {
        position: relative;
        width: 130px;
        height: 130px;
        margin: 0 auto 10px auto;
    }
    
    .avatar-base {
        width: 130px;
        height: 130px;
        border-radius: 50%;
        object-fit: cover;
        border: 4px solid #FF8F00;
        box-shadow: 0 0 20px rgba(255, 143, 0, 0.4);
    }
    
    .talking-lip {
        position: absolute;
        bottom: 24px;
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
        opacity: 0.9;
        animation: mouthTalk 0.28s infinite alternate ease-in-out;
    }
    
    .is-speaking .avatar-base {
        box-shadow: 0 0 28px rgba(255, 111, 0, 0.85);
        transform: scale(1.02);
    }

    @keyframes mouthTalk {
        0% { height: 4px; width: 18px; border-radius: 50%; }
        50% { height: 14px; width: 22px; border-radius: 40%; background: #5C0B0B; }
        100% { height: 8px; width: 24px; border-radius: 50%; }
    }

    .metric-pill {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 143, 0, 0.25);
        border-radius: 12px;
        padding: 10px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# Helper: Load .jpeg, .jpg, or .png automatically from assets/
def get_avatar_img(base_name, fallback_url):
    extensions = [".jpeg", ".jpg", ".png", ".JPEG", ".JPG", ".PNG"]
    for ext in extensions:
        local_p = os.path.join("assets", base_name + ext)
        if os.path.exists(local_p):
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
        "desc": "Traditional Classical Guru • Deep Pāṇinian Master",
        "img": male_src,
        "status": male_status,
        "tld": "co.in",
        "is_slow": True
    },
    "Female Āchāryā (आचार्या गार्गी)": {
        "title": "आचार्या गार्गी (Acharyaa Gargi)",
        "desc": "Scholarly Preceptor • Warm Socratic Mentor",
        "img": female_src,
        "status": female_status,
        "tld": "com",
        "is_slow": False
    },
    "Child Peer (बालकः ध्रुवः)": {
        "title": "बालकः ध्रुवः (Balaka Dhruva)",
        "desc": "Playful Young Peer • Fast & Cheerful Cadence",
        "img": child_src,
        "status": child_status,
        "tld": "co.uk",
        "is_slow": False
    }
}

# Synchronized speech playback + Lip-Sync trigger
def render_talking_avatar(text_to_speak: str, teacher_key: str, auto_play=True):
    clean_text = text_to_speak.replace('*', '').replace('#', '').replace('-', '').replace('[', '').replace(']', '').strip()
    if not clean_text:
        return
    cfg = TEACHERS[teacher_key]
    try:
        tts = gTTS(text=clean_text, lang='hi', tld=cfg["tld"], slow=cfg["is_slow"])
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        audio_b64 = base64.b64encode(fp.read()).decode()
        
        elem_id = f"audio_{int(time.time()*1000)}"
        st.markdown(f"""
        <div style="display:flex; align-items:center; gap:16px; margin: 12px 0;">
            <div class="avatar-wrapper" id="wrap_{elem_id}">
                <img src="{cfg['img']}" class="avatar-base"/>
                <div class="talking-lip"></div>
            </div>
            <div style="flex-grow:1;">
                <div style="font-weight:700; color:#FF8F00; font-size:1rem;">{cfg['title']} Speaking...</div>
                <audio id="{elem_id}" controls {'autoplay' if auto_play else ''} style="width:100%; height:38px; margin-top:6px;">
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
    <p style="margin:4px 0 0 0; opacity:0.9;">Commercial Spoken Sanskrit Engine • Ultra-Low Latency • Talking Lip-Sync Avatars</p>
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
    st.markdown("### 🏆 **Student Database Profile**")
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.markdown(f"""<div class="metric-pill"><div style="font-size:1.3rem; font-weight:700; color:#FF8F00;">🔥 {u_strk}</div><div style="font-size:0.7rem;">DAY STREAK</div></div>""", unsafe_allow_html=True)
    with col_p2:
        st.markdown(f"""<div class="metric-pill"><div style="font-size:1.3rem; font-weight:700; color:#FF8F00;">⭐ {u_xp}</div><div style="font-size:0.7rem;">SAVED XP</div></div>""", unsafe_allow_html=True)
    
    if st.button("🔄 Reset Conversation History", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

FAST_SYSTEM_PROMPT = f"""You are '{t_info['title']}', an instant Sanskrit dialogue tutor.
Student Tier: {target_tier}.

CRITICAL: Respond concisely within 3-4 sentences maximum for ultra-fast oral conversation.
Format ALWAYS:
[संस्कृतम्]: <Simple Sanskrit dialogue>
[IAST]: <Romanized transliteration>
[English]: <English meaning>
[✨ Say It Better]: <One short idiomatic Sanskrit upgrade>
[मार्गदर्शनम्] (Only if error occurred):
- 💡 Correction & rule
"""

tab_roleplay, tab_shiksha, tab_chandas, tab_vault, tab_trans = st.tabs([
    "💬 1. Ultra-Fast Oral Roleplay",
    "🎙️ 2. Śikṣā Phonetic Coach",
    "🕉️ 3. Svara & Chandaḥ Metre",
    "🧠 4. Persistent SRS Vault",
    "🌐 5. Universal Translator"
])

# =========================================================
# TAB 1: LOW-LATENCY ORAL ROLEPLAY
# =========================================================
with tab_roleplay:
    st.markdown("#### 💬 Situational Real-Life Immersion (सजीव-सम्भाषणम्)")
    
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
    
    for msg in st.session_state.chat_history:
        role = "assistant" if msg["role"] == "model" else "user"
        with st.chat_message(role):
            st.markdown(msg["content"])
            if role == "assistant" and "[संस्कृतम्]:" in msg["content"]:
                sanskrit_text = msg["content"].split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                render_talking_avatar(sanskrit_text, selected_teacher, auto_play=False)

    st.markdown("##### 🎙️ **Speak to Acharya (Oral Microphone):**")
    user_audio = st.audio_input("Record voice:")

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
                                {"text": f"{FAST_SYSTEM_PROMPT}\nScenario: {scenario}. Listen to student audio and reply immediately."}
                            ]
                        }],
                        config={"temperature": 0.2, "max_output_tokens": 500}
                    )
                    reply_text = resp.text
                    latency = round(time.time() - t_start, 2)
                    
                    st.markdown(reply_text)
                    st.caption(f"⚡ *Response Latency: {latency}s*")
                    
                    if "[संस्कृतम्]:" in reply_text:
                        sanskrit_text = reply_text.split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                        render_talking_avatar(sanskrit_text, selected_teacher, auto_play=True)
                    
                    st.session_state.chat_history.append({"role": "model", "content": reply_text})
                    update_xp(10)
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    if text_input := st.chat_input("Or type (e.g. mama nama, katham asti...):"):
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
                    
                    if "[संस्कृतम्]:" in reply_text:
                        sanskrit_text = reply_text.split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                        render_talking_avatar(sanskrit_text, selected_teacher, auto_play=True)
                        
                    st.session_state.chat_history.append({"role": "model", "content": reply_text})
                    update_xp(5)
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
        rec_sh = st.audio_input("Chant the phrase:")

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
                    s_line = resp.text.split("संस्कृतम्")[1].split("\n")[0].replace(':', '').replace('(Devanagari)', '').strip()
                    render_talking_avatar(s_line, selected_teacher, auto_play=False)
            except Exception as e:
                st.error(f"Error: {str(e)}")
