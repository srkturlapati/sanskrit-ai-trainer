import sys
import os
import time
import io
import datetime

# Ensure UTF-8 encoding across all runtime environments
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

# --- CUSTOM CSS: LUXURY VEDIC SAFFRON & GOLD UI ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Yatra+One&display=swap');

    /* Global Typography & Background Elements */
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    
    /* Header Banner Styling */
    .header-container {
        background: linear-gradient(135deg, #FF6F00 0%, #D84315 50%, #4E342E 100%);
        border-radius: 20px;
        padding: 24px 30px;
        color: white;
        margin-bottom: 24px;
        box-shadow: 0 10px 25px -5px rgba(216, 67, 21, 0.3);
        border: 1px solid rgba(255, 255, 255, 0.15);
    }
    
    .header-title {
        font-size: 2.2rem;
        font-weight: 800;
        letter-spacing: -0.5px;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    
    .header-subtitle {
        font-size: 0.98rem;
        opacity: 0.92;
        margin-top: 6px;
        font-weight: 400;
    }

    /* Custom Metric Cards */
    .metric-card {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 111, 0, 0.2);
        border-radius: 14px;
        padding: 14px 18px;
        text-align: center;
        transition: transform 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        border-color: #FF6F00;
    }
    .metric-val {
        font-size: 1.4rem;
        font-weight: 700;
        color: #FF8F00;
    }
    .metric-lbl {
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        opacity: 0.8;
    }

    /* Output Card / Section Wrapper */
    .output-card {
        background: rgba(255, 255, 255, 0.03);
        border-left: 4px solid #FF6F00;
        border-radius: 12px;
        padding: 18px;
        margin: 15px 0;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
    }

    /* Primary Accent Button Styling */
    .stButton>button {
        background: linear-gradient(135deg, #FF6F00 0%, #E65100 100%);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 10px 24px;
        font-weight: 600;
        letter-spacing: 0.3px;
        box-shadow: 0 4px 12px rgba(230, 81, 0, 0.25);
        transition: all 0.2s ease;
    }
    .stButton>button:hover {
        transform: scale(1.02);
        box-shadow: 0 6px 18px rgba(230, 81, 0, 0.4);
    }

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px;
        padding: 8px 16px;
        font-weight: 600;
        font-size: 0.9rem;
    }
    .stTabs [aria-selected="true"] {
        background-color: rgba(255, 111, 0, 0.12) !important;
        color: #FF6F00 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE INITIALIZATION ---
if "xp_points" not in st.session_state:
    st.session_state.xp_points = 150
if "practice_streak" not in st.session_state:
    st.session_state.practice_streak = 3
if "roleplay_messages" not in st.session_state:
    st.session_state.roleplay_messages = []
if "vocab_vault" not in st.session_state:
    st.session_state.vocab_vault = [
        {"word": "अस्तु", "meaning": "Alright / Let it be", "dhatu": "अस् (to be)", "level": "Beginner", "review_due": "Today"},
        {"word": "धन्यवादः", "meaning": "Thank you", "dhatu": "धन्य + वाद्", "level": "Beginner", "review_due": "Tomorrow"},
        {"word": "पुनर्मिलामः", "meaning": "See you again", "dhatu": "मिल् (to meet)", "level": "Beginner", "review_due": "In 3 Days"}
    ]
if "active_quiz" not in st.session_state:
    st.session_state.active_quiz = None

# Helper: Sanskrit Text-to-Speech
def play_sanskrit_audio(text_to_speak: str):
    try:
        clean_text = text_to_speak.replace('*', '').replace('#', '').replace('-', '').replace('[', '').replace(']', '').strip()
        if not clean_text:
            return
        tts = gTTS(text=clean_text, lang='hi', slow=False)
        audio_fp = io.BytesIO()
        tts.write_to_fp(audio_fp)
        audio_fp.seek(0)
        st.audio(audio_fp, format="audio/mp3")
    except Exception:
        pass

# --- HEADER HERO BANNER ---
st.markdown("""
<div class="header-container">
    <div class="header-title">🚩 सम्भाषणम् AI (Sambhāṣaṇa)</div>
    <div class="header-subtitle">Intelligent Sanskrit Spoken Academy • Real-Time Voice Feedback • Situational Immersion</div>
</div>
""", unsafe_allow_html=True)

# --- SIDEBAR: Profile & Configuration ---
with st.sidebar:
    st.markdown("### ⚙️ **विन्यासः (Settings)**")
    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        placeholder="Paste AIza... key here",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Get your free key at aistudio.google.com/apikey",
    )
    
    level = st.selectbox(
        "Proficiency Tier / स्तरः",
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
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-val">🔥 {st.session_state.practice_streak}</div>
            <div class="metric-lbl">Day Streak</div>
        </div>
        """, unsafe_allow_html=True)
    with col_sb2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-val">⭐ {st.session_state.xp_points}</div>
            <div class="metric-lbl">Total XP</div>
        </div>
        """, unsafe_allow_html=True)
        
    st.markdown("<br>", unsafe_allow_html=True)
    st.caption("🎖️ **Active Badges:** 🗣️ Vipani Explorer • 📜 Sandhi Master")
    
    st.markdown("---")
    if st.button("🔄 Reset Active Chat", use_container_width=True):
        st.session_state.roleplay_messages = []
        st.session_state.active_quiz = None
        st.rerun()

# --- TAB NAVIGATION ---
tab_roleplay, tab_shiksha, tab_shadow, tab_translate, tab_grammar, tab_vault = st.tabs([
    "💬 Roleplay & Tutor",
    "🎙️ Śikṣā (Pronunciation)",
    "🔁 Shadowing Drills",
    "🌐 Universal Translation",
    "🧩 Vyākaraṇa Engine",
    "🧠 SRS Vault & Quiz"
])


# =========================================================
# TAB 1: CONVERSATIONAL ROLEPLAY
# =========================================================
with tab_roleplay:
    st.markdown("#### 💬 Situational Real-Life Immersion (सम्भाषण-प्रसङ्गाः)")
    
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        scenario = st.selectbox(
            "Select Scenario / प्रसङ्गः:",
            [
                "At the Market (विपणिः - शाकक्रयणम् / Buying Vegetables)",
                "At School / Gurukula (पाठशाला - शिष्टाचारः / Teacher & Student)",
                "Travel & Directions (यात्रा - मार्गनिर्देशनम् / Road & Station)",
                "Welcoming Guests (अतिथि-सत्कारः / Home Hospitality)",
                "Free Dialogue with Ācārya (मुक्त-सम्भाषणम् / Open Discussion)",
                "Animal Storyteller (पञ्चतन्त्र-कथा: गजः, शुकः, मयूरः)"
            ]
        )
    with col_r2:
        tutor_persona = st.selectbox(
            "Tutor Persona / स्वभावः:",
            [
                "Acharya AI (Patient & Socratic Guide)",
                "Mitram AI (Friendly Peer Learner)",
                "Gaja-Guru (Playful Storybook Animal for Kids)"
            ]
        )

    SYSTEM_ROLEPLAY = f"""You are '{tutor_persona}' in the scenario: '{scenario}'.
Target Level: {level}.

Rules:
1. Converse dynamically in simple spoken Sanskrit according to the scenario.
2. If student makes an error (Vibhakti, Lakara, Purusha), gently point it out.
3. Offer a '✨ Say It Better' suggestion (a more natural/idiomatic Sanskrit expression).
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

    for msg in st.session_state.roleplay_messages:
        role = "assistant" if msg["role"] == "model" else "user"
        with st.chat_message(role):
            st.markdown(msg["content"])
            if role == "assistant" and "[संस्कृतम्]:" in msg["content"]:
                line = msg["content"].split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                play_sanskrit_audio(line)

    st.markdown("##### 🎙️ **Speak Your Reply (वदतु):**")
    role_audio = st.audio_input("Record voice reply:")

    if role_audio is not None:
        if not api_key:
            st.warning("⚠️ Please enter your Gemini API key in the sidebar.")
            st.stop()
        
        client = genai.Client(api_key=api_key)
        audio_bytes = role_audio.getvalue()
        
        st.session_state.roleplay_messages.append({"role": "user", "content": "🎙️ *[Oral Spoken Input Submitted]*"})
        st.session_state.xp_points += 10
        with st.chat_message("user"):
            st.audio(role_audio, format="audio/wav")
        
        with st.chat_message("assistant"):
            with st.spinner("आचार्यः शृणोति एवं चिन्तयति..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": audio_bytes}},
                            {"text": f"{SYSTEM_ROLEPLAY}\nListen to the spoken audio and respond in character."}
                        ]
                    }],
                )
                st.markdown(resp.text)
                if "[संस्कृतम्]:" in resp.text:
                    line = resp.text.split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                    play_sanskrit_audio(line)
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
            with st.spinner("चिन्तयति..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=contents,
                    config={"system_instruction": SYSTEM_ROLEPLAY, "temperature": 0.2},
                )
                st.markdown(resp.text)
                if "[संस्कृतम्]:" in resp.text:
                    line = resp.text.split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                    play_sanskrit_audio(line)
                st.session_state.roleplay_messages.append({"role": "model", "content": resp.text})


# =========================================================
# TAB 2: PRONUNCIATION COACH (ŚIKṢĀ)
# =========================================================
with tab_shiksha:
    st.markdown("#### 🎙️ पाणिनीय-शिक्षा एवं उच्चारण-परीक्षकः (Phonetic Coach)")
    st.caption("AI evaluates mouth acoustics: Dental vs Retroflex, Mahāprāṇa aspiration, and vowel duration.")
    
    drill_options = [
        "सत्यं वद, धर्मं चर। (Speak truth, walk in righteousness)",
        "विद्या ददाति विनयं विनयाद्याति पात्रताम्। (Knowledge gives humility)",
        "वृक्षात् फलानि भूमौ पतन्ति। (Fruits fall from tree - Mahāprāṇa 'ph' & 'bh')",
        "अहं प्रतिदिनं प्रातः पञ्चवादने उत्तिष्ठामि। (I wake at 5 AM - Retroflex 'ṣṭh')",
        "अथातो ब्रह्मजिज्ञासा। (Now begins inquiry into Brahman - Aspirated 'th' & 'jh')"
    ]
    
    target_drill = st.selectbox("Choose Target Phrase to Practice:", drill_options)
    clean_target = target_drill.split('(')[0].strip()
    
    col_sh1, col_sh2 = st.columns(2)
    with col_sh1:
        st.markdown("##### 🔊 **1. Master Reference Chanting:**")
        play_sanskrit_audio(clean_target)
    with col_sh2:
        st.markdown("##### 🎙️ **2. Record Your Chanting:**")
        rec_shiksha = st.audio_input("Chant the phrase clearly:")

    if rec_shiksha is not None:
        if not api_key:
            st.warning("⚠️ Enter your Gemini API key in sidebar.")
            st.stop()
            
        client = genai.Client(api_key=api_key)
        with st.spinner("Analyzing tongue placement & acoustic frequencies..."):
            PROMPT_SHIKSHA = f"""You are a Pāṇinīya Śikṣā (पाणिनीय-शिक्षा) phonetic evaluator.
Target Sentence: "{clean_target}"

Evaluate the student's audio recording strictly on:
1. Overall Pronunciation Score (0 to 100%).
2. Articulation Points (उच्चारण-स्थानम्): Dental (दन्त्य) vs Retroflex (मूर्धन्य), Guttural (कण्ठ्य), Labial (ओष्ठ्य).
3. Aspiration (प्राण-प्रयत्नः): Mahāprāṇa consonants (ख्, घ्, थ्, ध्, फ्, भ्) vs Alpaprāṇa.
4. Vowel Timing (स्वर-मात्रा): Hrasva (1 mātrā) vs Dīrgha (2 mātrās).
5. Actionable Tongue Placement Tip.

Format cleanly:
### 🎯 उच्चारण-अङ्काः (Score): [XX / 100]
**शुद्धता-स्तरः (Clarity Rating):** [उत्कृष्टम् (Excellent) / समीचीनम् (Good) / अभ्यासोऽपेक्षितः (Needs Practice)]

---
### 🔍 ध्वन्युच्चारण-विश्लेषणम् (Phonetic Breakdown):
- **उच्चारण-स्थानानि**: <Analysis>
- **प्राण-प्रयत्नः**: <Analysis>
- **मात्रा-दीर्घता**: <Analysis>

---
### 💡 जिह्वा-स्थान-मार्गदर्शनम् (Tongue & Breath Guidance):
<Practical tip on mouth position and air release>
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
                st.error(f"Error evaluating audio: {str(e)}")


# =========================================================
# TAB 3: SHADOWING DRILLS
# =========================================================
with tab_shadow:
    st.markdown("#### 🔁 Listen & Repeat (Shadowing & Pacing Drills)")
    st.caption("Build oral muscle memory, rhythm, and conversational cadence.")
    
    shadow_list = [
        "भवतः गृहं कुत्र अस्ति? मम गृहं समीपे एव अस्ति।",
        "अद्य अहं संस्कृत-सम्भाषण-वर्गे नूतन-शब्दान् अपठम्।",
        "यथा बीजं विना वृक्षः न भवति, तथा उद्योगं विना कार्यं न सिद्ध्यति।"
    ]
    
    s_choice = st.selectbox("Select Shadowing Passage:", shadow_list)
    
    col_sw1, col_sw2 = st.columns(2)
    with col_sw1:
        st.markdown("##### 🎧 **1. Listen to Native Pacing:**")
        play_sanskrit_audio(s_choice)
    with col_sw2:
        st.markdown("##### 🎙️ **2. Shadow in One Breath:**")
        shadow_user_audio = st.audio_input("Repeat phrase:")
    
    if shadow_user_audio is not None:
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Analyzing pacing and cadence..."):
            PROMPT_SHADOW = f"""You are a Sanskrit Fluency and Speech-Rate Assessor.
Target Reference: "{s_choice}"

Analyze the student's spoken audio:
1. Cadence & Rhythm: Natural sentence flow without hesitation.
2. Estimated Words Per Minute (WPM) & Speech Pacing.
3. Native Language Stress Interference.
4. Fluency Score (0-100%).

Format:
### ⚡ गतिः एवं धाराप्रवाहः (Fluency & Pacing Analysis):
- **Fluency Score**: [XX / 100]
- **Speed & Cadence**: <Commentary>
- **Rhythm & Flow**: <Commentary>
- **Sandhi Fluency Tip**: <Tip>
"""
            try:
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": shadow_user_audio.getvalue()}},
                            {"text": PROMPT_SHADOW}
                        ]
                    }]
                )
                st.markdown(resp.text)
                st.session_state.xp_points += 15
            except Exception as e:
                st.error(f"Error: {str(e)}")


# =========================================================
# TAB 4: UNIVERSAL TRANSLATOR
# =========================================================
with tab_translate:
    st.markdown("#### 🌐 Universal Multi-Language ↔ Sanskrit Translator")
    
    trans_mode = st.radio("Translation Direction", ["Any Language ➔ Sanskrit", "Sanskrit ➔ Any Language"], horizontal=True)
    
    if trans_mode == "Sanskrit ➔ Any Language":
        dest_lang = st.selectbox("Target Language:", ["Telugu (తెలుగు)", "Hindi (हिन्दी)", "English", "Tamil (தமிழ்)", "Kannada (ಕನ್ನಡ)", "Marathi (मराठी)", "Malayalam (മലയാളം)"])
    
    t_input = st.text_area("Enter Text:", height=70, placeholder="Type sentence here...")
    t_voice = st.audio_input("Or speak input to translate:")
    
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
### 🔍 पदच्छेदः एवं व्याकरणम् (Word-by-Word Analysis):
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
                    st.write("🔊 **उच्चारणम् (Audio):**")
                    play_sanskrit_audio(line)
            except Exception as e:
                st.error(f"Error: {str(e)}")


# =========================================================
# TAB 5: VYĀKARAṆA ENGINE
# =========================================================
with tab_grammar:
    st.markdown("#### 🧩 पाणिनीय-व्याकरण-उपकरणम् (Paninian Grammar Engine)")
    
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
# TAB 6: SRS VAULT & PARĪKṢĀ
# =========================================================
with tab_vault:
    st.markdown("#### 🧠 Spaced Repetition (SRS) Vocabulary Vault & Parīkṣā")
    
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        st.markdown("##### 📚 **Personal Word Vault (शब्दकोशः)**")
        for item in st.session_state.vocab_vault:
            st.markdown(f"• **{item['word']}** — {item['meaning']} | *Root:* `{item['dhatu']}` | ⏳ Due: `{item['review_due']}`")
        
        with st.expander("➕ Add New Word to Vault"):
            nw = st.text_input("Sanskrit Word (पदम्):")
            nm = st.text_input("Meaning (अर्थः):")
            nd = st.text_input("Root / Pratipadika (मूलम्):")
            if st.button("Save Word to Vault", use_container_width=True):
                if nw and nm:
                    st.session_state.vocab_vault.append({"word": nw, "meaning": nm, "dhatu": nd if nd else nw, "level": "Learner", "review_due": "Tomorrow"})
                    st.session_state.xp_points += 5
                    st.success(f"Saved '{nw}' (+5 XP)!")
                    st.rerun()

    with col_v2:
        st.markdown("##### 📝 **Daily Interactive Parīkṣā (परीक्षा)**")
        quiz_topic = st.selectbox("Topic:", ["Vibhakti & Karaka Agreement", "Dhaturoopa & Lakara Tenses", "Sandhi Identification", "Spoken Idioms & Vocabulary"])
        
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
