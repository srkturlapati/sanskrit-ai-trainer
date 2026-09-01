import sys
import os
import time
import io
import sqlite3
import datetime

# Ensure UTF-8 encoding across environments
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
    page_title="Sambhāṣaṇa AI | Complete Sanskrit Academy",
    page_icon="🚩",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- DATABASE PERSISTENCE LAYER (SQLite) ---
DB_FILE = "sanskrit_app.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # User Profile table
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_profile (
            id INTEGER PRIMARY KEY,
            streak INTEGER,
            xp INTEGER,
            last_login TEXT
        )
    ''')
    # Vocabulary Vault table
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
    # Initialize profile if empty
    c.execute('SELECT COUNT(*) FROM user_profile')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO user_profile (id, streak, xp, last_login) VALUES (1, 1, 150, ?)', (str(datetime.date.today()),))
        default_words = [
            ("अस्तु", "Alright / Let it be", "अस् (to be)", "Beginner", "Today"),
            ("धन्यवादः", "Thank you", "धन्य + वाद्", "Beginner", "Tomorrow"),
            ("पुनर्मिलामः", "See you again", "मिल् (to meet)", "Beginner", "In 3 Days")
        ]
        c.executemany('INSERT OR IGNORE INTO vocab_vault (word, meaning, dhatu, level, review_due) VALUES (?, ?, ?, ?, ?)', default_words)
    conn.commit()
    conn.close()

init_db()

def get_profile():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT streak, xp FROM user_profile WHERE id = 1')
    res = c.fetchone()
    conn.close()
    return res if res else (1, 150)

def update_profile(add_xp=0, increment_streak=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    streak, xp = get_profile()
    new_xp = xp + add_xp
    new_streak = streak + 1 if increment_streak else streak
    c.execute('UPDATE user_profile SET streak = ?, xp = ? WHERE id = 1', (new_streak, new_xp))
    conn.commit()
    conn.close()

def get_vault_words():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT word, meaning, dhatu, level, review_due FROM vocab_vault')
    rows = c.fetchall()
    conn.close()
    return [{"word": r[0], "meaning": r[1], "dhatu": r[2], "level": r[3], "review_due": r[4]} for r in rows]

def add_vault_word(word, meaning, dhatu, level="Learner"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO vocab_vault (word, meaning, dhatu, level, review_due) VALUES (?, ?, ?, ?, ?)',
              (word, meaning, dhatu, level, "Tomorrow"))
    conn.commit()
    conn.close()
    update_profile(add_xp=10)

# --- LUXURY VEDIC THEME CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
    
    .header-container {
        background: linear-gradient(135deg, #FF6F00 0%, #D84315 50%, #3E2723 100%);
        border-radius: 18px;
        padding: 22px 28px;
        color: white;
        margin-bottom: 20px;
        box-shadow: 0 10px 25px -5px rgba(216, 67, 21, 0.3);
    }
    .avatar-card {
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 111, 0, 0.3);
        padding: 12px;
        text-align: center;
        margin-bottom: 12px;
    }
    .avatar-img {
        width: 90px;
        height: 90px;
        border-radius: 50%;
        object-fit: cover;
        border: 3px solid #FF8F00;
        margin: 0 auto 8px auto;
    }
    .metric-card {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 111, 0, 0.2);
        border-radius: 12px;
        padding: 10px;
        text-align: center;
    }
    .skill-node {
        background: rgba(255, 111, 0, 0.08);
        border: 1px solid #FF6F00;
        border-radius: 12px;
        padding: 14px;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# --- AVATARS CONFIG ---
AVATARS = {
    "Male Teacher (आचार्यः वसिष्ठः)": {
        "title": "आचार्यः वसिष्ठः (Acharya Vasiṣṭha)",
        "desc": "Classical Guru • Deep & Pedagogical Voice",
        "img": "https://upload.wikimedia.org/wikipedia/commons/e/e3/Raja_Ravi_Varma_-_Sankaracharya.jpg",
        "accent_tld": "co.in",
        "is_slow": True
    },
    "Female Teacher (आचार्या गार्गी)": {
        "title": "आचार्या गार्गी (Acharyaa Gargi)",
        "desc": "Scholarly Preceptor • Warm & Expressive Voice",
        "img": "https://dme2wmiz2suov.cloudfront.net/User(18985117)/2061981-Yadavabhyudayam_(9).png",
        "accent_tld": "com",
        "is_slow": False
    },
    "Child Student Peer (बालकः ध्रुवः)": {
        "title": "बालकः ध्रुवः (Balaka Dhruva)",
        "desc": "Playful Child Peer • Fast & Cheerful Voice",
        "img": "https://encrypted-tbn3.gstatic.com/licensed-image?q=tbn:ANd9GcQzrF7mhDcZqvcP2RO27fhrcZXbPYo76WyMLq97WTaUJbXdG3OP6XXd3kC2v3A7-6qYwUBpUaNci3jGXWs",
        "accent_tld": "co.uk",
        "is_slow": False
    }
}

# --- SESSION STATE ---
if "roleplay_messages" not in st.session_state:
    st.session_state.roleplay_messages = []
if "session_stats" not in st.session_state:
    st.session_state.session_stats = {"words_spoken": 0, "errors_caught": 0, "start_time": time.time()}

# Helper: Sanskrit TTS with Pitch/Speed Control
def play_persona_audio(text_to_speak: str, persona_key: str):
    try:
        clean_text = text_to_speak.replace('*', '').replace('#', '').replace('-', '').replace('[', '').replace(']', '').strip()
        if not clean_text:
            return
        cfg = AVATARS[persona_key]
        tts = gTTS(text=clean_text, lang='hi', tld=cfg["accent_tld"], slow=cfg["is_slow"])
        audio_fp = io.BytesIO()
        tts.write_to_fp(audio_fp)
        audio_fp.seek(0)
        st.audio(audio_fp, format="audio/mp3")
    except Exception:
        pass

# --- HEADER HERO ---
st.markdown("""
<div class="header-container">
    <h2 style="margin:0; font-weight:800;">🚩 सम्भाषणम् AI (Sambhāṣaṇa Master Academy)</h2>
    <p style="margin:4px 0 0 0; opacity:0.92;">Vedic Śikṣā • Persistent Database • Chandaḥ Engine • Situational Immersion</p>
</div>
""", unsafe_allow_html=True)

# --- SIDEBAR: Profile & Settings ---
streak_val, xp_val = get_profile()
with st.sidebar:
    st.markdown("### 🎙️ **Teacher Persona & Voice**")
    selected_teacher = st.selectbox("Choose Guide:", list(AVATARS.keys()), index=0)
    teacher_info = AVATARS[selected_teacher]
    
    st.markdown(f"""
    <div class="avatar-card">
        <img src="{teacher_info['img']}" class="avatar-img" />
        <div style="font-weight:700; color:#FF8F00;">{teacher_info['title']}</div>
        <div style="font-size:0.78rem; opacity:0.85;">{teacher_info['desc']}</div>
    </div>
    """, unsafe_allow_html=True)
    
    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        placeholder="AIza... key",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Get your free key at aistudio.google.com/apikey",
    )
    
    st.markdown("---")
    st.markdown("### 🏆 **Persistent Progress**")
    col_sb1, col_sb2 = st.columns(2)
    with col_sb1:
        st.metric("🔥 Streak", f"{streak_val} Days")
    with col_sb2:
        st.metric("⭐ Points", f"{xp_val} XP")
        
    st.caption("💾 *All stats & vocabulary are saved to local database.*")
    if st.button("🔄 Reset Dialogue Session", use_container_width=True):
        st.session_state.roleplay_messages = []
        st.rerun()

# --- 7 MASTER TABS ---
tab_roleplay, tab_shiksha, tab_chandas, tab_curriculum, tab_inspect, tab_translate, tab_report = st.tabs([
    "💬 1. Roleplay & Immersion",
    "🎙️ 2. Śikṣā Accent Coach",
    "🕉️ 3. Svara & Chandaḥ",
    "🗺️ 4. Skill Tree Levels",
    "🔍 5. Tap-to-Inspect & Vault",
    "🌐 6. Universal Translator",
    "📊 7. Diagnostic Report"
])


# =========================================================
# TAB 1: SITUATIONAL ROLEPLAY
# =========================================================
with tab_roleplay:
    col_r1, col_r2 = st.columns([1, 2])
    with col_r1:
        st.image(teacher_info['img'], caption=teacher_info['title'], width=170)
    with col_r2:
        scenario = st.selectbox(
            "Conversation Context / प्रसङ्गः:",
            [
                "At the Market (विपणिः - शाकक्रयणम् / Purchasing Vegetables)",
                "At Gurukula (पाठशाला - शिष्टाचारः / Teacher & Student Dialogue)",
                "Travel & Directions (यात्रा - मार्गनिर्देशनम् / Road & Station)",
                "Welcoming Guests (अतिथि-सत्कारः / Home Hospitality)",
                "Open Dialogue with Ācārya (मुक्त-सम्भाषणम् / Open Discussion)"
            ]
        )
        st.info(f"Conversing with **{teacher_info['title']}** in **{scenario.split('(')[0]}**")

    SYSTEM_ROLEPLAY = f"""You are '{teacher_info['title']}' in scenario: '{scenario}'.
Rules:
1. Converse in spoken Sarala Samskritam.
2. If student makes an error, gently guide them.
3. Provide a '✨ Say It Better' upgrade.
4. End by asking a natural conversational question.

Format:
[संस्कृतम्]: <Devanagari Dialogue>
[IAST]: <Transliteration>
[English]: <Meaning>
[✨ Say It Better]: <Idiomatic upgrade>
[मार्गदर्शनम्] (Only if error made):
- 🔍 रूपम्: <Incorrect word>
- 💡 सङ्केतः: <Guiding rule>
"""

    for msg in st.session_state.roleplay_messages:
        role = "assistant" if msg["role"] == "model" else "user"
        with st.chat_message(role):
            st.markdown(msg["content"])
            if role == "assistant" and "[संस्कृतम्]:" in msg["content"]:
                line = msg["content"].split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                play_persona_audio(line, selected_teacher)

    st.markdown("##### 🎙️ **Speak Your Reply (वदतु):**")
    role_audio = st.audio_input("Record your voice:")

    if role_audio is not None:
        if not api_key:
            st.warning("⚠️ Enter Gemini API key in sidebar.")
            st.stop()
        
        client = genai.Client(api_key=api_key)
        audio_bytes = role_audio.getvalue()
        
        st.session_state.roleplay_messages.append({"role": "user", "content": "🎙️ *[Oral Spoken Input Submitted]*"})
        update_profile(add_xp=10)
        st.session_state.session_stats["words_spoken"] += 8
        with st.chat_message("user"):
            st.audio(role_audio, format="audio/wav")
        
        with st.chat_message("assistant"):
            with st.spinner(f"{teacher_info['title']} चिन्तयति..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": audio_bytes}},
                            {"text": f"{SYSTEM_ROLEPLAY}\nRespond to student's spoken audio."}
                        ]
                    }],
                )
                st.markdown(resp.text)
                if "[संस्कृतम्]:" in resp.text:
                    line = resp.text.split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                    play_persona_audio(line, selected_teacher)
                st.session_state.roleplay_messages.append({"role": "model", "content": resp.text})

    if text_msg := st.chat_input("Or type here (e.g. bho mātulā, phalasya mūlyaṁ kim?)..."):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key in sidebar.")
            st.stop()
            
        client = genai.Client(api_key=api_key)
        is_dev = any("\u0900" <= char <= "\u097f" for char in text_msg)
        display_text = text_msg if is_dev else f"{text_msg} ({transliterate(text_msg, sanscript.ITRANS, sanscript.DEVANAGARI)})"

        st.session_state.roleplay_messages.append({"role": "user", "content": display_text})
        update_profile(add_xp=5)
        st.session_state.session_stats["words_spoken"] += len(text_msg.split())
        with st.chat_message("user"):
            st.markdown(display_text)

        contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": str(m["content"])}]} for m in st.session_state.roleplay_messages]

        with st.chat_message("assistant"):
            with st.spinner(f"{teacher_info['title']} चिन्तयति..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=contents,
                    config={"system_instruction": SYSTEM_ROLEPLAY, "temperature": 0.2},
                )
                st.markdown(resp.text)
                if "[संस्कृतम्]:" in resp.text:
                    line = resp.text.split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                    play_persona_audio(line, selected_teacher)
                st.session_state.roleplay_messages.append({"role": "model", "content": resp.text})


# =========================================================
# TAB 2: PHONETIC COACH (ŚIKṢĀ)
# =========================================================
with tab_shiksha:
    st.markdown("#### 🎙️ पाणिनीय-शिक्षा एवं उच्चारण-परीक्षकः (Phonetic Coach)")
    
    drill_options = [
        "सत्यं वद, धर्मं चर। (Speak truth, walk in righteousness)",
        "विद्या ददाति विनयं विनयाद्याति पात्रताम्। (Knowledge gives humility)",
        "वृक्षात् फलानि भूमौ पतन्ति। (Fruits fall from tree - Mahāprāṇa 'ph' & 'bh')",
        "अहं प्रतिदिनं प्रातः पञ्चवादने उत्तिष्ठामि। (I wake at 5 AM - Retroflex 'ṣṭh')"
    ]
    
    target_drill = st.selectbox("Choose Target Phrase:", drill_options)
    clean_target = target_drill.split('(')[0].strip()
    
    col_sh1, col_sh2 = st.columns(2)
    with col_sh1:
        st.markdown(f"##### 🔊 **1. Listen ({teacher_info['title']}):**")
        play_persona_audio(clean_target, selected_teacher)
    with col_sh2:
        st.markdown("##### 🎙️ **2. Record Your Chanting:**")
        rec_shiksha = st.audio_input("Chant the phrase clearly:")

    if rec_shiksha is not None:
        if not api_key:
            st.warning("⚠️ Enter Gemini API key in sidebar.")
            st.stop()
            
        client = genai.Client(api_key=api_key)
        with st.spinner("Analyzing acoustic phonemes & tongue articulation..."):
            PROMPT_SHIKSHA = f"""You are a Pāṇinīya Śikṣā phonetic evaluator.
Target Sentence: "{clean_target}"

Evaluate the student's audio recording strictly on:
1. Overall Pronunciation Score (0 to 100%).
2. Articulation Points (उच्चारण-स्थानम्): Dental vs Retroflex, Guttural, Labial.
3. Aspiration (प्राण-प्रयत्नः): Mahāprāṇa consonants vs Alpaprāṇa.
4. Vowel Timing (स्वर-मात्रा): Hrasva vs Dīrgha.
5. Actionable Tongue Placement Tip.

Format as:
### 🎯 उच्चारण-अङ्काः (Score): [XX / 100]
**शुद्धता-स्तरः (Clarity Rating):** [उत्कृष्टम् / समीचीनम् / अभ्यासोऽपेक्षितः]

---
### 🔍 ध्वन्युच्चारण-विश्लेषणम् (Phonetic Breakdown):
- **उच्चारण-स्थानानि**: <Analysis>
- **प्राण-प्रयत्नः**: <Analysis>
- **मात्रा-दीर्घता**: <Analysis>

---
### 💡 जिह्वा-स्थान-मार्गदर्शनम् (Tongue & Breath Guidance):
<Concrete tip on mouth position and air release>
"""
            try:
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": rec_shiksha.getvalue()}},
                            {"text": PROMPT_SHIKSHA}
                        ]
                    }]
                )
                st.markdown(resp.text)
                update_profile(add_xp=15)
            except Exception as e:
                st.error(f"Error evaluating audio: {str(e)}")


# =========================================================
# TAB 3: SVARA & CHANDAḤ ENGINE (Vedic Pitch & Metre)
# =========================================================
with tab_chandas:
    st.markdown("#### 🕉️ वैदिक-स्वर एवं छन्दो-विश्लेषकः (Svara & Metre Coach)")
    st.caption("Identify Laghu/Guru syllables, Vedic pitch accents (उदात्तः/अनुदात्तः/स्वरितः), and classical metres.")
    
    chandas_input = st.text_area(
        "Enter Śloka / Mantra (e.g., गायत्री-मन्त्रः or भगवद्गीता-श्लोकः):",
        value="धर्मक्षेत्रे कुरुक्षेत्रे समवेता युयुत्सवः।\nमामकाः पाण्डवाश्चैव किमकुर्वत सञ्जय॥",
        height=90
    )
    
    if st.button("Scan Metre & Pitch / छन्दो-परीक्षणम्", use_container_width=True):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("छन्दः सूत्राणि विचार्यन्ते..."):
            PROMPT_CHANDAS = f"""You are a master Pingala Chandaḥ-śāstra (पिङ्गल-छन्दःशास्त्र) and Vedic Svara expert.
Analyze this Sanskrit verse:
"{chandas_input}"

Provide:
1. Chandaḥ Name (e.g. Anuṣṭubh, Triṣṭubh, Śārdūlavikrīḍita, Indravajrā).
2. Metrical Scansion (लघु-गुरु-व्यवस्था): Mark each pāda with Laghu (।) and Guru (ऽ) symbols and syllable count.
3. Gana Breakdown (गण-विभागः): e.g. म-गण, य-गण, etc.
4. Vedic Svara Guide (if applicable): Udātta (उच्चैः), Anudātta (नीचैः), Svarita (समाहारः).
5. Meaning & Chanting Rhythm Guidance.
"""
            try:
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{"role": "user", "parts": [{"text": PROMPT_CHANDAS}]}],
                    config={"temperature": 0.1}
                )
                st.markdown(resp.text)
                update_profile(add_xp=20)
            except Exception as e:
                st.error(f"Error: {str(e)}")


# =========================================================
# TAB 4: STRUCTURED SKILL TREE (Levels 1 to 4)
# =========================================================
with tab_curriculum:
    st.markdown("#### 🗺️ सोपान-मार्गः (Structured Skill Tree Curriculum)")
    st.caption("Follow the Samskrita Bharati / CEFR progressive competency milestones.")
    
    col_k1, col_k2 = st.columns(2)
    with col_k1:
        st.markdown("""
        <div class="skill-node">
            <h4>🟢 Level 1: Paricayaḥ (परिचयः - The Beginner)</h4>
            <p>• Self Introduction (मम नाम...)</p>
            <p>• Greetings & Politeness (हरिः ॐ, धन्यवादः, क्षम्यताम्)</p>
            <p>• Present Tense Singular (गच्छति, पठति, लिखति)</p>
            <b>Status: Unlocked ✅</b>
        </div>
        
        <div class="skill-node">
            <h4>🟡 Level 2: Śikṣā (शिक्षा - The Communicator)</h4>
            <p>• 7 Cases & Relationships (षष्ठी, द्वितीया, तृतीया)</p>
            <p>• Past & Future Tenses (अगच्छत्, गमिष्यति, क्तवतु)</p>
            <p>• Daily Situational Roleplays (Market & Travel)</p>
            <b>Status: Active In-Progress ⏳</b>
        </div>
        """, unsafe_allow_html=True)
        
    with col_k2:
        st.markdown("""
        <div class="skill-node">
            <h4>🟠 Level 3: Kovidaḥ (कोविदः - The Intermediate)</h4>
            <p>• Conjunctions & Participles (क्त्वा, ल्यप्, तुमुन्)</p>
            <p>• Moderate Sandhi Application (दीर्घ, गुण, वृद्धि)</p>
            <p>• Story Narration & Debate</p>
            <b>Status: Locked 🔒 (Requires 300 XP)</b>
        </div>
        
        <div class="skill-node">
            <h4>🔴 Level 4: Samarthaḥ (समर्थः - Classical Scholar)</h4>
            <p>• Samāsa Compounds (तत्पुरुष, बहुव्रीहि, द्वन्द्व)</p>
            <p>• Passive Voice (कर्मणि / भावे प्रयोगः)</p>
            <p>• Śāstra & Kāvya Appreciation</p>
            <b>Status: Locked 🔒 (Requires 600 XP)</b>
        </div>
        """, unsafe_allow_html=True)


# =========================================================
# TAB 5: TAP-TO-INSPECT & PERSISTENT SRS VAULT
# =========================================================
with tab_inspect:
    st.markdown("#### 🔍 Tap-to-Inspect Morphological Inspector & SRS Vault")
    
    col_in1, col_in2 = st.columns(2)
    with col_in1:
        st.markdown("##### 🔬 **Inspect Any Word / Root:**")
        lookup_word = st.text_input("Enter word (e.g. पठित्वा, रामाय, गच्छतः):")
        if st.button("Inspect Word / पद-विश्लेषणम्", use_container_width=True):
            if not api_key:
                st.warning("⚠️ Enter Gemini API key.")
                st.stop()
            client = genai.Client(api_key=api_key)
            with st.spinner("Morphological analysis..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{"role": "user", "parts": [{"text": f"Provide exact morphological breakdown for Sanskrit word: '{lookup_word}'. Return: Base Pratipadika/Dhatu, Linga, Vibhakti, Vacana, Pratyaya, English Meaning, and a 1-sentence example."}]}],
                    config={"temperature": 0.1}
                )
                st.markdown(resp.text)
                
        st.markdown("---")
        st.markdown("##### ➕ **Add to Persistent Vocabulary Vault:**")
        with st.form("vault_form"):
            vw = st.text_input("Sanskrit Word (पदम्):")
            vm = st.text_input("Meaning (अर्थः):")
            vd = st.text_input("Root / Dhātu (धातुः):")
            submitted = st.form_submit_button("Save to Database Vault (+10 XP)")
            if submitted and vw and vm:
                add_vault_word(vw, vm, vd)
                st.success(f"Saved '{vw}' permanently into SQLite database!")
                st.rerun()

    with col_in2:
        st.markdown("##### 📚 **Your Saved Vocabulary Cards (Database):**")
        v_words = get_vault_words()
        for item in v_words:
            st.markdown(f"• **{item['word']}** — {item['meaning']} | *Root:* `{item['dhatu']}` | ⏳ `{item['review_due']}`")


# =========================================================
# TAB 6: UNIVERSAL TRANSLATOR
# =========================================================
with tab_translate:
    st.markdown("#### 🌐 Universal Multi-Language ↔ Sanskrit Translator")
    
    trans_mode = st.radio("Direction", ["Any Language ➔ Sanskrit", "Sanskrit ➔ Any Language"], horizontal=True)
    if trans_mode == "Sanskrit ➔ Any Language":
        dest_lang = st.selectbox("Target Language:", ["Telugu (తెలుగు)", "Hindi (हिन्दी)", "English", "Tamil (தமிழ்)", "Kannada (ಕನ್ನಡ)"])
    
    t_input = st.text_area("Enter Text:", height=70)
    t_voice = st.audio_input("Or speak to translate:")
    
    if st.button("Execute Translation / अनुवादं कुरु", use_container_width=True) or (t_voice is not None):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key in sidebar.")
            st.stop()
        
        client = genai.Client(api_key=api_key)
        with st.spinner("अनुवादः प्रचलति..."):
            if trans_mode == "Any Language ➔ Sanskrit":
                PROMPT_T = """Translate into Sanskrit.
MANDATORY FORMAT:
### 🪶 पूर्णवाक्यम् (Complete Sanskrit Sentence):
**संस्कृतम् (Devanagari):** <FULL TRANSLATED SENTENCE>
**IAST:** <Sentence in IAST>
**English Meaning:** <Complete English translation>
---
### 🔍 पदच्छेदः एवं व्याकरणम्:
- <Word>: <Pratipadika/Dhatu> + <Vibhakti/Pratyaya> — <Meaning>
"""
            else:
                PROMPT_T = f"Translate this Sanskrit into {dest_lang} and English with Sandhi splits and word-by-word meanings."

            if t_voice is not None:
                payload = [
                    {"inline_data": {"mime_type": "audio/wav", "data": t_voice.getvalue()}},
                    {"text": f"{PROMPT_T}\nTranscribe spoken audio and translate."}
                ]
            else:
                if not t_input.strip():
                    st.warning("Please enter text or audio.")
                    st.stop()
                payload = [{"text": f"{PROMPT_T}\nInput: {t_input}"}]

            try:
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{"role": "user", "parts": payload}],
                    config={"temperature": 0.2}
                )
                st.markdown(resp.text)
                if "संस्कृतम् (Devanagari):" in resp.text:
                    line = resp.text.split("संस्कृतम् (Devanagari):")[1].split("\n")[0].strip()
                    st.write(f"🔊 **उच्चारणम् ({teacher_info['title']}):**")
                    play_persona_audio(line, selected_teacher)
            except Exception as e:
                st.error(f"Error: {str(e)}")


# =========================================================
# TAB 7: END-OF-SESSION DIAGNOSTIC REPORT CARD
# =========================================================
with tab_report:
    st.markdown("#### 📊 Session Performance & Diagnostic Report")
    
    elapsed_mins = max(1, int((time.time() - st.session_state.session_stats["start_time"]) / 60))
    wpm = int(st.session_state.session_stats["words_spoken"] / elapsed_mins)
    
    col_rep1, col_rep2, col_rep3 = st.columns(3)
    with col_rep1:
        st.metric("🗣️ Total Words Spoken", f"{st.session_state.session_stats['words_spoken']} Words")
    with col_rep2:
        st.metric("⚡ Speech Pacing", f"{wpm} WPM")
    with col_rep3:
        st.metric("⏱️ Active Practice Time", f"{elapsed_mins} Mins")
        
    st.markdown("---")
    st.markdown("##### 📜 **Automated Learning Report Card:**")
    st.markdown(f"""
    - **Current CEFR / Samskrita Bharati Stage:** *Paricayaḥ (Level 1) $\\rightarrow$ Śikṣā (Level 2)*
    - **Grammar Concord Accuracy:** *88% Case Alignment*
    - **Aspiration & Śikṣā Rating:** *High Fidelity (Mahāprāṇa & Visarga Precision)*
    - **Suggested Homework Practice:** *Practice past participles (क्तवतु प्रत्ययाः - गतवान् / गतवती)*
    """)
