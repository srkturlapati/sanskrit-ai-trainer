import sys
import os
import time
import io
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
    page_title="Sambhāṣaṇa AI | सम्भाषणम्",
    page_icon="🚩",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- LUXURY VEDIC THEME CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    
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
        padding: 14px;
        text-align: center;
        margin-bottom: 12px;
    }
    
    .avatar-img {
        width: 100px;
        height: 100px;
        border-radius: 50%;
        object-fit: cover;
        border: 3px solid #FF8F00;
        margin: 0 auto 8px auto;
    }
    
    .metric-card {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 111, 0, 0.2);
        border-radius: 12px;
        padding: 10px 14px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# --- AVATAR ASSETS & METADATA ---
AVATARS = {
    "Male Teacher (आचार्यः वसिष्ठः)": {
        "title": "आचार्यः वसिष्ठः (Acharya Vasiṣṭha)",
        "desc": "Traditional Classical Guru • Deep & Authoritative Voice",
        "img": "https://upload.wikimedia.org/wikipedia/commons/e/e3/Raja_Ravi_Varma_-_Sankaracharya.jpg",
        "accent_tld": "co.in",
        "voice_type": "male"
    },
    "Female Teacher (आचार्या गार्गी)": {
        "title": "आचार्या गार्गी (Acharyaa Gargi)",
        "desc": "Scholarly Female Preceptor • Warm & Expressive Voice",
        "img": "https://dme2wmiz2suov.cloudfront.net/User(18985117)/2061981-Yadavabhyudayam_(9).png",
        "accent_tld": "com",
        "voice_type": "female"
    },
    "Child Student Peer (बालकः ध्रुवः)": {
        "title": "बालकः ध्रुवः (Balaka Dhruva)",
        "desc": "Playful Child Peer • Fast & Cheerful Voice",
        "img": "https://encrypted-tbn3.gstatic.com/licensed-image?q=tbn:ANd9GcQzrF7mhDcZqvcP2RO27fhrcZXbPYo76WyMLq97WTaUJbXdG3OP6XXd3kC2v3A7-6qYwUBpUaNci3jGXWs",
        "accent_tld": "co.uk",
        "voice_type": "child"
    }
}

# --- SESSION STATE INITIALIZATION ---
if "xp_points" not in st.session_state:
    st.session_state.xp_points = 150
if "practice_streak" not in st.session_state:
    st.session_state.practice_streak = 3
if "roleplay_messages" not in st.session_state:
    st.session_state.roleplay_messages = []
if "vocab_vault" not in st.session_state:
    st.session_state.vocab_vault = [
        {"word": "अस्तु", "meaning": "Alright / Let it be", "dhatu": "अस् (to be)", "level": "Beginner"},
        {"word": "धन्यवादः", "meaning": "Thank you", "dhatu": "धन्य + वाद्", "level": "Beginner"}
    ]
if "active_quiz" not in st.session_state:
    st.session_state.active_quiz = None

# Helper: Multi-Voice Sanskrit TTS
def play_persona_audio(text_to_speak: str, persona_key: str):
    try:
        clean_text = text_to_speak.replace('*', '').replace('#', '').replace('-', '').replace('[', '').replace(']', '').strip()
        if not clean_text:
            return
        
        cfg = AVATARS[persona_key]
        # Modulate speed and tld accent based on selected voice
        is_slow = (cfg["voice_type"] == "male")
        tts = gTTS(text=clean_text, lang='hi', tld=cfg["accent_tld"], slow=is_slow)
        
        audio_fp = io.BytesIO()
        tts.write_to_fp(audio_fp)
        audio_fp.seek(0)
        st.audio(audio_fp, format="audio/mp3")
    except Exception:
        pass

# --- HERO HEADER ---
st.markdown("""
<div class="header-container">
    <h2 style="margin:0; font-weight:800;">🚩 सम्भाषणम् AI (Sambhāṣaṇa Platform)</h2>
    <p style="margin:4px 0 0 0; opacity:0.9;">Multimodal Voice & Visual Teacher Personas • Spoken Sanskrit Academy</p>
</div>
""", unsafe_allow_html=True)

# --- SIDEBAR: Configuration & Teacher Persona Selector ---
with st.sidebar:
    st.markdown("### 🎙️ **Teacher Persona & Voice (शिक्षक-चयनम्)**")
    
    selected_teacher = st.selectbox(
        "Choose AI Teacher:",
        list(AVATARS.keys()),
        index=0
    )
    
    teacher_info = AVATARS[selected_teacher]
    st.markdown(f"""
    <div class="avatar-card">
        <img src="{teacher_info['img']}" class="avatar-img" />
        <div style="font-weight:700; color:#FF8F00; font-size:1rem;">{teacher_info['title']}</div>
        <div style="font-size:0.8rem; opacity:0.85;">{teacher_info['desc']}</div>
    </div>
    """, unsafe_allow_html=True)
    
    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        placeholder="Paste AIza... key",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Get your free key at aistudio.google.com/apikey",
    )
    
    level = st.selectbox(
        "Student Tier / स्तरः",
        [
            "Beginner (प्रथमा - Daily Phrases)",
            "Intermediate (मध्यमा - Tenses & Flow)",
            "Advanced (उत्तमा - Shastric & Literary)"
        ],
        index=0,
    )
    
    st.markdown("---")
    st.markdown("### 🏆 **प्रगतिः (Progress)**")
    col_sb1, col_sb2 = st.columns(2)
    with col_sb1:
        st.metric("🔥 Streak", f"{st.session_state.practice_streak} Days")
    with col_sb2:
        st.metric("⭐ Points", f"{st.session_state.xp_points} XP")
        
    st.markdown("---")
    if st.button("🔄 Reset Active Chat", use_container_width=True):
        st.session_state.roleplay_messages = []
        st.session_state.active_quiz = None
        st.rerun()

# --- TAB NAVIGATION ---
tab_roleplay, tab_shiksha, tab_translate, tab_grammar, tab_vault = st.tabs([
    "💬 Interactive Roleplay",
    "🎙️ Śikṣā Phonetic Coach",
    "🌐 Universal Translation",
    "🧩 Vyākaraṇa Engine",
    "🧠 SRS Vault & Quiz"
])

# =========================================================
# TAB 1: VISUAL TEACHER CONVERSATION & ROLEPLAY
# =========================================================
with tab_roleplay:
    col_top1, col_top2 = st.columns([1, 2])
    with col_top1:
        st.image(teacher_info['img'], caption=f"Active Guide: {teacher_info['title']}", width=180)
    with col_top2:
        scenario = st.selectbox(
            "Select Scenario / प्रसङ्गः:",
            [
                "At School / Gurukula (पाठशाला - शिष्टाचारः / Classroom Dialogue)",
                "At the Market (विपणिः - शाकक्रयणम् / Buying Fruits & Vegetables)",
                "Travel & Directions (यात्रा - मार्गनिर्देशनम् / Road & Station)",
                "Welcoming Guests (अतिथि-सत्कारः / Home Hospitality)",
                "Open Dialogue with Teacher (मुक्त-सम्भाषणम् / Open Discussion)"
            ]
        )
        st.info(f"Speaking with **{teacher_info['title']}** in **{scenario.split('(')[0]}**")

    SYSTEM_PROMPT_CHAT = f"""You are {teacher_info['title']} in the scenario: '{scenario}'.
Target Student Level: {level}.

Persona Style:
- If Male Teacher: Traditional, dignified, patient Acharya.
- If Female Teacher: Scholarly, encouraging, clear Gargi preceptor.
- If Child Student: Playful, cheerful, eager young peer Dhruva.

Rules:
1. Converse naturally in simple Sanskrit suited to the level.
2. If student makes a grammar error, gently point it out.
3. Offer a '✨ Say It Better' suggestion (a more idiomatic Sanskrit expression).
4. Always end your turn by asking an engaging situational question.

Format:
[संस्कृतम्]: <Devanagari Dialogue>
[IAST]: <Romanized Transliteration>
[English]: <English Meaning>
[✨ Say It Better]: <More idiomatic phrasing in Sanskrit with meaning>
[मार्गदर्शनम्] (Include ONLY if error is made):
- 🔍 रूपम्: <Incorrect word>
- 💡 सङ्केतः: <Guiding rule>
"""

    # Display dialogue history
    for msg in st.session_state.roleplay_messages:
        role = "assistant" if msg["role"] == "model" else "user"
        with st.chat_message(role):
            st.markdown(msg["content"])
            if role == "assistant" and "[संस्कृतम्]:" in msg["content"]:
                line = msg["content"].split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                play_persona_audio(line, selected_teacher)

    st.markdown("##### 🎙️ **Speak Your Reply (वदतु):**")
    role_audio = st.audio_input("Record voice reply:")

    if role_audio is not None:
        if not api_key:
            st.warning("⚠️ Please enter your Gemini API key in the sidebar.")
            st.stop()
        
        client = genai.Client(api_key=api_key)
        audio_bytes = role_audio.getvalue()
        
        st.session_state.roleplay_messages.append({"role": "user", "content": "🎙️ *[Spoken Audio Response Submitted]*"})
        st.session_state.xp_points += 10
        with st.chat_message("user"):
            st.audio(role_audio, format="audio/wav")
        
        with st.chat_message("assistant"):
            with st.spinner(f"{teacher_info['title']} शृणोति एवं चिन्तयति..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": audio_bytes}},
                            {"text": f"{SYSTEM_PROMPT_CHAT}\nRespond to the student's spoken audio."}
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
            st.warning("⚠️ Please enter your Gemini API key in the sidebar.")
            st.stop()
            
        client = genai.Client(api_key=api_key)
        is_dev = any("\u0900" <= char <= "\u097f" for char in text_msg)
        if not is_dev:
            try:
                converted = transliterate(text_msg, sanscript.ITRANS, sanscript.DEVANAGARI)
                user_display = f"{text_msg} ({converted})"
            except Exception:
                user_display = text_msg
        else:
            user_display = text_msg

        st.session_state.roleplay_messages.append({"role": "user", "content": user_display})
        st.session_state.xp_points += 5
        with st.chat_message("user"):
            st.markdown(user_display)

        contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": str(m["content"])}]} for m in st.session_state.roleplay_messages]

        with st.chat_message("assistant"):
            with st.spinner(f"{teacher_info['title']} चिन्तयति..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=contents,
                    config={"system_instruction": SYSTEM_PROMPT_CHAT, "temperature": 0.2},
                )
                st.markdown(resp.text)
                if "[संस्कृतम्]:" in resp.text:
                    line = resp.text.split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                    play_persona_audio(line, selected_teacher)
                st.session_state.roleplay_messages.append({"role": "model", "content": resp.text})


# =========================================================
# TAB 2: PRONUNCIATION COACH (ŚIKṢĀ)
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
        st.markdown(f"##### 🔊 **1. Listen to {teacher_info['title']} Voice:**")
        play_persona_audio(clean_target, selected_teacher)
    with col_sh2:
        st.markdown("##### 🎙️ **2. Record Your Chanting:**")
        rec_shiksha = st.audio_input("Chant the phrase clearly:")

    if rec_shiksha is not None:
        if not api_key:
            st.warning("⚠️ Enter your Gemini API key in sidebar.")
            st.stop()
            
        client = genai.Client(api_key=api_key)
        with st.spinner("Evaluating pronunciation..."):
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
                st.session_state.xp_points += 15
            except Exception as e:
                st.error(f"Error: {str(e)}")


# =========================================================
# TAB 3: UNIVERSAL TRANSLATOR
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
                PROMPT_T = f"""Translate into Sanskrit for level {level}.
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
                PROMPT_T = f"""Translate this Sanskrit into {dest_lang} and English with Sandhi splits and word-by-word meanings."""

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
# TAB 4: VYĀKARAṆA ENGINE
# =========================================================
with tab_grammar:
    st.markdown("#### 🧩 पाणिनीय-व्याकरण-उपकरणम् (Grammar Engine)")
    
    col_g1, col_g2 = st.columns([1, 1])
    with col_g1:
        g_tool = st.selectbox(
            "Select Tool / उपकरणम्:",
            [
                "Sandhi Splitter & Sūtra Rules (सन्धि-विच्छेदः)",
                "Shabdarupa Declension Tables (शब्दरूपाणि - 8 Vibhaktis)",
                "Dhaturoopa Conjugation (धातुरूपाणि - 10 Lakaras)",
                "Samāsa Analysis & Vigraha Vākya (समास-विग्रहः)"
            ]
        )
    with col_g2:
        g_query = st.text_input("Enter Word / Root / Compound:", placeholder="e.g. राम, भू, गम्, पीताम्बरः")
    
    if st.button("Generate Paninian Analysis", use_container_width=True):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        if not g_query.strip():
            st.warning("Please enter a term.")
            st.stop()
            
        client = genai.Client(api_key=api_key)
        with st.spinner("पाणिनीय-सूत्राणि अन्विष्यन्ते..."):
            try:
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{"role": "user", "parts": [{"text": f"Provide comprehensive Paninian analysis for tool: {g_tool}, input: {g_query}. Include Astadhyayi Sutra references, markdown tables for all cases/purushas, and IAST."}]}],
                    config={"temperature": 0.1}
                )
                st.markdown(resp.text)
            except Exception as e:
                st.error(f"Error: {str(e)}")


# =========================================================
# TAB 5: SRS VAULT & PARĪKṢĀ
# =========================================================
with tab_vault:
    st.markdown("#### 🧠 Spaced Repetition (SRS) Vocabulary Vault & Parīkṣā")
    
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        st.markdown("##### 📚 **Personal Word Vault (शब्दकोशः)**")
        for item in st.session_state.vocab_vault:
            st.markdown(f"• **{item['word']}** — {item['meaning']} | *Root:* `{item['dhatu']}`")
        
        with st.expander("➕ Add New Word to Vault"):
            nw = st.text_input("Sanskrit Word (पदम्):")
            nm = st.text_input("Meaning (अर्थः):")
            nd = st.text_input("Root / Pratipadika (मूलम्):")
            if st.button("Save Word to Vault", use_container_width=True):
                if nw and nm:
                    st.session_state.vocab_vault.append({"word": nw, "meaning": nm, "dhatu": nd if nd else nw, "level": "Learner"})
                    st.session_state.xp_points += 5
                    st.success(f"Saved '{nw}' (+5 XP)!")
                    st.rerun()

    with col_v2:
        st.markdown("##### 📝 **Daily Interactive Parīkṣā (परीक्षा)**")
        quiz_topic = st.selectbox("Topic:", ["Vibhakti & Karaka Agreement", "Dhaturoopa & Lakara Tenses", "Sandhi Identification"])
        
        if st.button("⚡ Generate Interactive Quiz", use_container_width=True):
            if not api_key:
                st.warning("⚠️ Enter Gemini API key.")
                st.stop()
            client = genai.Client(api_key=api_key)
            with st.spinner("Generating 3-question MCQ quiz..."):
                try:
                    resp = client.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=[{"role": "user", "parts": [{"text": f"Generate a 3-question MCQ quiz on '{quiz_topic}' for Level: {level}. For each question: provide Devanagari, IAST, English, 4 options (A, B, C, D), the correct answer, and an Astadhyayi grammatical explanation."}]}],
                        config={"temperature": 0.2}
                    )
                    st.session_state.active_quiz = resp.text
                    st.session_state.xp_points += 10
                except Exception as e:
                    st.error(f"Error: {str(e)}")

        if st.session_state.active_quiz:
            st.markdown(st.session_state.active_quiz)
