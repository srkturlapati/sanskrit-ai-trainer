import sys
import os
import time
import io
import hashlib

# Enforce UTF-8 across all runtime environments
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

# Setup page layout
st.set_page_config(
    page_title="Sambhāṣaṇa AI • TalkPal & Sanskrit Guru",
    page_icon="🚩",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling for TalkPal & Guru UI
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    
    /* Master Navigation Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
        border-bottom: 2px solid #E2E8F0;
    }
    .stTabs [data-baseweb="tab"] {
        height: 52px;
        white-space: pre-wrap;
        border-radius: 12px 12px 0px 0px;
        font-size: 16px;
        font-weight: 700;
        padding: 10px 24px;
    }
    
    /* TalkPal Bubble Styling */
    .talkpal-bubble-ai {
        background: linear-gradient(135deg, #F8FAFC 0%, #EFF6FF 100%);
        border: 1px solid #DBEAFE;
        border-left: 5px solid #4F46E5;
        border-radius: 16px;
        padding: 16px 20px;
        margin-bottom: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.04);
    }
    .talkpal-bubble-user {
        background: #F0FDF4;
        border: 1px solid #DCFCE7;
        border-left: 5px solid #16A34A;
        border-radius: 16px;
        padding: 14px 18px;
        margin-bottom: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    .talkpal-pill {
        display: inline-block;
        background: #EEF2FF;
        color: #4F46E5;
        font-size: 12px;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 20px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 8px;
    }
    .voice-dock {
        background: #FFFFFF;
        border: 2px solid #6366F1;
        border-radius: 16px;
        padding: 14px 20px;
        margin-top: 14px;
        margin-bottom: 14px;
        box-shadow: 0 10px 15px -3px rgba(99, 102, 241, 0.1);
    }
    .suggestion-chip {
        background-color: #F1F5F9;
        border: 1px solid #CBD5E1;
        border-radius: 20px;
        padding: 4px 12px;
        font-size: 13px;
        font-weight: 600;
        color: #334155;
        display: inline-block;
        margin: 4px 4px;
    }
</style>
""", unsafe_allow_html=True)

# Helper: Sanskrit TTS Audio with Pitch/Speed adjustment
def play_sanskrit_audio(text_to_speak: str, slow_mode: bool = False):
    try:
        clean = text_to_speak.replace('*', '').replace('#', '').replace('-', '').replace('[', '').replace(']', '').strip()
        if not clean:
            return
        tts = gTTS(text=clean, lang='hi', slow=slow_mode)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        st.audio(fp, format="audio/mp3")
    except Exception:
        pass

# Rate-limit resilient API caller
def call_gemini_safe(client, model, contents, system_instruction):
    for attempt in range(4):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=contents,
                config={"system_instruction": system_instruction, "temperature": 0.2}
            )
            return resp.text, None
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                sleep_time = 3 * (attempt + 1)
                time.sleep(sleep_time)
                continue
            return None, err_str
    return None, "Rate limit reached. Please wait 15 seconds before trying again."

# --- SESSION STATES ---
if "xp" not in st.session_state:
    st.session_state.xp = 240
if "streak" not in st.session_state:
    st.session_state.streak = 5
if "talkpal_history" not in st.session_state:
    st.session_state.talkpal_history = []
if "tp_mode" not in st.session_state:
    st.session_state.tp_mode = "💬 Free Chat"
if "last_audio_hash" not in st.session_state:
    st.session_state.last_audio_hash = ""
if "guru_quiz" not in st.session_state:
    st.session_state.guru_quiz = None
if "vocab_vault" not in st.session_state:
    st.session_state.vocab_vault = [
        {"word": "अस्तु", "meaning": "Alright / Let it be", "dhatu": "अस्", "due": "Today"},
        {"word": "धन्यवादः", "meaning": "Thank you", "dhatu": "धन्य + वाद्", "due": "Tomorrow"},
        {"word": "पुनर्मिलामः", "meaning": "See you again", "dhatu": "मिल्", "due": "In 3 Days"}
    ]

# --- SIDEBAR: Configuration & Gamification ---
with st.sidebar:
    st.title("🚩 Sambhāṣaṇa AI")
    st.caption("TalkPal Spoken Clone & Pāṇinian Guru")
    
    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        placeholder="AIza...",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Get free key at aistudio.google.com",
    )
    
    level = st.selectbox(
        "Proficiency Level / स्तरः",
        ["A1 - Beginner (प्रथमा)", "A2 - Elementary", "B1 - Intermediate (मध्यमा)", "B2 - Upper Intermediate", "C1 - Advanced (उत्तमा)"],
        index=0
    )
    
    st.write("---")
    st.subheader("🎙️ Voice & Persona Settings")
    audio_speed = st.radio("Pacing", ["Normal (सामान्यम्)", "Slow (मन्दम्)"], index=0)
    is_slow = audio_speed.startswith("Slow")
    tutor_voice = st.selectbox("Tutor Tone", ["Acharya (Wise & Supportive)", "Mitram (Friendly Peer)", "Pandita (Grammatical Purist)"])
    
    st.write("---")
    st.subheader("🏆 Daily Quests & Progress")
    c1, c2 = st.columns(2)
    c1.metric("🔥 Streak", f"{st.session_state.streak} Days")
    c2.metric("⭐ Points", f"{st.session_state.xp} XP")
    st.progress(0.75, text="Daily Quest: 75% Complete")
    st.caption("🎯 Goal: Complete 1 voice conversation & 1 grammar drill today.")
    
    st.write("---")
    if st.button("🔄 Reset Current Session"):
        st.session_state.talkpal_history = []
        st.session_state.last_audio_hash = ""
        st.session_state.guru_quiz = None
        st.rerun()

# --- MASTER TOP TABS ---
master_tab1, master_tab2 = st.tabs([
    "🗣️ TAB 1: TALKPAL SANSKRIT MASTER",
    "🚩 TAB 2: SANSKRIT AI GURU (ACADEMIC ENGINES)"
])


# ==============================================================================
# MASTER TAB 1: TALKPAL SANSKRIT MASTER
# ==============================================================================
with master_tab1:
    st.subheader("🗣️ TalkPal Interactive Spoken Suite")
    st.caption("Real-Time Spoken Practice with Speech Recognition, Word Inspector & Smart Suggestions.")

    # 5 TalkPal Modes selector
    tp_mode = st.radio(
        "TalkPal Learning Mode",
        ["💬 Free Chat", "🎭 Situational Roleplay", "🔥 Debate Club", "📸 Photo Mode", "🧩 Custom Scenario"],
        horizontal=True,
        label_visibility="collapsed"
    )

    if tp_mode != st.session_state.tp_mode:
        st.session_state.talkpal_history = []
        st.session_state.last_audio_hash = ""
        st.session_state.tp_mode = tp_mode
        st.rerun()

    # Configure Mode Prompts & Suggestions
    if tp_mode == "💬 Free Chat":
        mode_header = "💬 Free Chat with TalkPal AI"
        suggestions = ["मम नाम ... अस्ति। (My name is...)", "अहं संस्कृतं पठामि। (I study Sanskrit)", "भवान् कुत्र वसति? (Where do you live?)"]
        sys_prompt = f"""You are the TalkPal AI Sanskrit Tutor ({tutor_voice}). Student Level: {level}.
Always format output strictly as:
[संस्कृतम्]: <Conversational spoken Sanskrit reply>
[IAST]: <Transliteration>
[English]: <Translation>
[💡 TalkPal Feedback]:
- 🔍 Grammatical Correction: <Error correction or 'निर्दोषम् (Perfect!)'>
- ✨ Better Way to Say: <Idiomatic alternative expression>
- 📖 Key Vocabulary: <1-2 words from the reply with root/meaning>
"""
        greeting = "[संस्कृतम्]: हरिः ॐ! अद्य भवान्/भवती कीदृशं विषयम् अधिकृत्य सम्भाषणं कर्तुम् इच्छति?\n[IAST]: Hariḥ Om! Adya bhavān/bhavatī kīdṛśaṁ viṣayam adhikṛtya sambhāṣaṇaṁ kartum icchati?\n[English]: Hello! What topic would you like to talk about today?\n[💡 TalkPal Feedback]:\n- 🔍 Grammatical Correction: निर्दोषम् (Ready!)\n- ✨ Better Way to Say: Welcome to TalkPal Chat!\n- 📖 Key Vocabulary: विषयम् (viṣayam - topic)"

    elif tp_mode == "🎭 Situational Roleplay":
        mode_header = "🎭 Situational Roleplay Mission"
        scenario = st.selectbox("Roleplay Setting:", ["Vegetable Market (शाकक्रयणम्)", "Gurukula / School (पाठशाला)", "Train Station (रेलस्थानकम्)", "Hotel Check-In (अतिथि-गृहम्)"])
        suggestions = ["अस्य मूल्यं किम्? (How much is this?)", "किञ्चित् न्यूनं करोतु। (Please reduce the price)", "जलम् आवश्यकम्। (I need water)"]
        sys_prompt = f"""You are an AI character in roleplay: '{scenario}'. Level: {level}.
Format:
[संस्कृतम्]: <In-character dialogue>
[IAST]: <Transliteration>
[English]: <Translation>
[🎯 Mission Objective]: <Clear prompt on what the user should respond next>
"""
        greeting = f"[संस्कृतम्]: नमस्ते! {scenario} प्रति स्वागतम्। कथं साहाय्यं करवाणि?\n[IAST]: Namaste! Svāgatam. Kathaṁ sāhāyyaṁ karavāṇi?\n[English]: Welcome! How may I assist you?\n[🎯 Mission Objective]: Introduce yourself and state what you need."

    elif tp_mode == "🔥 Debate Club":
        mode_header = "🔥 TalkPal Debate Club (शास्त्रार्थः)"
        debate_topic = st.selectbox("Debate Topic:", ["Gurukula vs Modern Schools", "Grammar First vs Speaking First", "AI: Boon or Curse?"])
        suggestions = ["मम मतम् अस्ति यत्... (My opinion is that...)", "एतत् न उचितम्, यतः... (This is not right, because...)", "अहं सहमतः अस्मि। (I agree)"]
        sys_prompt = f"""You are a master Sanskrit debater challenging the student on: '{debate_topic}'. Level: {level}.
Politely challenge their points using logic. Format:
[संस्कृतम्]: <Debate rebuttal>
[IAST]: <Transliteration>
[English]: <Translation>
[🔥 Counter Challenge]: <Sharp counter-question>
"""
        greeting = f"[संस्कृतम्]: शास्त्रार्थे स्वागतम्! विषये '{debate_topic}' भवतः किं मतम्?\n[IAST]: Śāstrārthe svāgatam! Bhavataḥ kiṁ matam?\n[English]: Welcome to the debate! What is your argument?\n[🔥 Counter Challenge]: State your stance clearly."

    elif tp_mode == "📸 Photo Mode":
        mode_header = "📸 Photo Mode (चित्रवर्णनम्)"
        scene_desc = st.selectbox("Scene to describe:", ["Ashrama in Himalayas with deer and trees", "Village fair with temple and sweet stalls", "Classroom with students writing on palm leaves"])
        suggestions = ["अस्मिन् चित्रे ... दृश्यते। (In this picture ... is seen)", "अत्र बहवः जनाः सन्ति। (Here are many people)", "वृक्षात् फलानि पतन्ति। (Fruits fall from tree)"]
        sys_prompt = f"""Assess student's spoken description of scene: '{scene_desc}'. Level: {level}.
Score descriptive richness (0-100%) and case agreements. Provide a model description.
"""
        greeting = f"[संस्कृतम्]: एतत् चित्रं पश्यतु ({scene_desc})। चित्रे किं किं अस्ति इति वदतु।\n[IAST]: Etat citraṁ paśyatu. Citre kiṁ kiṁ asti iti vadatu.\n[English]: Look at this scene. Describe what you see in 3-4 sentences."

    else:
        mode_header = "🧩 Custom Persona Simulation"
        custom_char = st.text_input("Who is the AI?", value="Chanakya")
        suggestions = ["प्रणामः आचार्य! (Salutations Acharya)", "एकं संशयं प्रष्टुम् इच्छामि। (I wish to ask a doubt)", "उपदेशं ददातु। (Give counsel)"]
        sys_prompt = f"""Roleplay as {custom_char}. Level: {level}. Converse in character in Sanskrit with IAST & English."""
        greeting = f"[संस्कृतम्]: हरिः ॐ! अहं {custom_char} अस्मि। किं वक्तुम् इच्छति भवान्?\n[IAST]: Hariḥ Om! Ahaṁ {custom_char} asmi. Kiṁ vaktum icchati bhavān?\n[English]: Hello! I am {custom_char}. What do you wish to speak about?"

    st.markdown(f"#### {mode_header}")

    # Initialize greeting
    if len(st.session_state.talkpal_history) == 0:
        st.session_state.talkpal_history = [{"role": "model", "content": greeting}]

    # Render Dialogue History
    for msg in st.session_state.talkpal_history:
        if msg["role"] == "model":
            st.markdown('<div class="talkpal-bubble-ai"><span class="talkpal-pill">🤖 TalkPal AI</span>', unsafe_allow_html=True)
            st.markdown(msg["content"])
            st.markdown('</div>', unsafe_allow_html=True)
            if "[संस्कृतम्]:" in msg["content"]:
                line = msg["content"].split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                play_sanskrit_audio(line, slow_mode=is_slow)
        else:
            st.markdown('<div class="talkpal-bubble-user"><span class="talkpal-pill" style="background:#DCFCE7; color:#15803D;">👤 You</span>', unsafe_allow_html=True)
            st.markdown(msg["content"])
            st.markdown('</div>', unsafe_allow_html=True)

    # Smart Suggestion Chips
    st.write("💡 **TalkPal Smart Reply Suggestions:**")
    cols_sug = st.columns(len(suggestions))
    for i, sug in enumerate(suggestions):
        with cols_sug[i]:
            st.markdown(f'<span class="suggestion-chip">{sug}</span>', unsafe_allow_html=True)

    # Word-by-Word Tap Inspector
    with st.expander("🔍 Tap to Inspect Any Word (Word-by-Word Breakdown)"):
        inspect_word = st.text_input("Enter any Sanskrit word from above to inspect:", placeholder="e.g. गच्छामि, पुस्तकस्य, पठित्वा")
        if st.button("Inspect Word"):
            if api_key and inspect_word:
                client = genai.Client(api_key=api_key)
                with st.spinner("Analyzing root and morphology..."):
                    resp = client.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=[{"role": "user", "parts": [{"text": f"Analyze Sanskrit word '{inspect_word}'. Output: Root/Pratipadika, Vibhakti/Pratyaya/Lakara/Purusha, English meaning, and Telugu/Hindi meaning."}]}],
                    )
                    st.info(resp.text)

    # Dedicated Voice Recording Dock
    st.markdown('<div class="voice-dock">', unsafe_allow_html=True)
    st.markdown("🎙️ **Tap to Speak / वदतु (Voice Reply):**")
    audio_reply = st.audio_input("Record voice reply:", key=f"tp_rec_{len(st.session_state.talkpal_history)}")
    st.markdown('</div>', unsafe_allow_html=True)

    if audio_reply is not None:
        audio_bytes = audio_reply.getvalue()
        audio_hash = hashlib.md5(audio_bytes).hexdigest()

        if audio_hash != st.session_state.last_audio_hash:
            st.session_state.last_audio_hash = audio_hash
            if not api_key:
                st.warning("⚠️ Enter Gemini API key in sidebar.")
                st.stop()

            client = genai.Client(api_key=api_key)
            st.session_state.talkpal_history.append({"role": "user", "content": "🎙️ *[Spoken Voice Response]*"})
            st.session_state.xp += 15

            with st.spinner("TalkPal is listening and evaluating..."):
                reply, err = call_gemini_safe(
                    client=client,
                    model="gemini-3.6-flash",
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": audio_bytes}},
                            {"text": f"{sys_prompt}\nTranscribe spoken audio, reply in Sanskrit with translation and feedback."}
                        ]
                    }],
                    system_instruction=sys_prompt
                )
                if reply:
                    st.session_state.talkpal_history.append({"role": "model", "content": reply})
                    st.rerun()
                else:
                    st.error(f"⚠️ {err}")

    # Fallback Text Input
    if text_input := st.chat_input("Or type in Sanskrit / English (e.g. mama nama, aham pathami...)..."):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key in sidebar.")
            st.stop()

        client = genai.Client(api_key=api_key)
        is_dev = any("\u0900" <= char <= "\u097f" for char in text_input)
        if not is_dev:
            try:
                converted = transliterate(text_input, sanscript.ITRANS, sanscript.DEVANAGARI)
                user_text = f"{text_input} ({converted})"
            except Exception:
                user_text = text_input
        else:
            user_text = text_input

        st.session_state.talkpal_history.append({"role": "user", "content": user_text})
        st.session_state.xp += 5

        contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": str(m["content"])}]} for m in st.session_state.talkpal_history]

        with st.spinner("TalkPal is typing..."):
            reply, err = call_gemini_safe(client, "gemini-3.6-flash", contents, sys_prompt)
            if reply:
                st.session_state.talkpal_history.append({"role": "model", "content": reply})
                st.rerun()
            else:
                st.error(f"⚠️ {err}")


# ==============================================================================
# MASTER TAB 2: SANSKRIT AI GURU (ACADEMIC & PEDAGOGICAL ENGINES)
# ==============================================================================
with master_tab2:
    st.subheader("🚩 Sanskrit AI Guru Academic Suite")
    st.caption("Pāṇinian Grammar • Universal Translation • Śikṣā Shadowing • Parīkṣā Engine")

    guru_subtab = st.selectbox(
        "Select Guru Engine",
        [
            "🌐 Universal Translation Engine (उभय-अनुवादकः)",
            "🧩 Pāṇinian Vyākaraṇa Tool (पाणिनीय-व्याकरणम्)",
            "🎙️ Phonetic Śikṣā & Pronunciation Coach (शिक्षा-परीक्षकः)",
            "📝 Interactive Parīkṣā & Assessment (परीक्षा)",
            "🧠 SRS Vocabulary Vault (शब्दकोशः)"
        ]
    )

    # 1. UNIVERSAL TRANSLATOR
    if "Universal Translation" in guru_subtab:
        st.markdown("### 🌐 Universal Bidirectional Translation")
        t_dir = st.radio("Direction", ["Any Language ➔ Sanskrit", "Sanskrit ➔ Any Language"], horizontal=True)
        if t_dir == "Sanskrit ➔ Any Language":
            t_lang = st.selectbox("Target Language", ["Telugu (తెలుగు)", "Hindi (हिन्दी)", "English", "Tamil (தமிழ்)", "Kannada (ಕನ್ನಡ)", "Marathi (मराठी)"])

        t_text = st.text_area("Enter sentence to translate:", height=80)
        st.write("🎙️ *Or speak the sentence:*")
        t_voice = st.audio_input("Speak to translate:", key="guru_trans_voice")

        if st.button("Translate / अनुवादं कुरु") or (t_voice is not None):
            if not api_key:
                st.warning("⚠️ Enter Gemini API key.")
                st.stop()
            client = genai.Client(api_key=api_key)
            with st.spinner("Translating..."):
                if t_dir == "Any Language ➔ Sanskrit":
                    p = f"""Translate into Sanskrit for level {level}.
MANDATORY:
### 🪶 पूर्णवाक्यम्:
**संस्कृतम् (Devanagari):** <FULL SENTENCE>
**IAST:** <IAST>
**English:** <English>
---
### 🔍 व्याकरणम्:
- Padaccheda and Vibhakti breakdown
"""
                else:
                    p = f"""Translate this Sanskrit into {t_lang} and English with Sandhi splits and word-by-word meanings."""

                payload = [{"inline_data": {"mime_type": "audio/wav", "data": t_voice.getvalue()}}, {"text": p}] if t_voice else [{"text": f"{p}\nInput: {t_text}"}]
                resp = client.models.generate_content(model="gemini-3.6-flash", contents=[{"role": "user", "parts": payload}])
                st.markdown(resp.text)
                if "संस्कृतम् (Devanagari):" in resp.text:
                    line = resp.text.split("संस्कृतम् (Devanagari):")[1].split("\n")[0].strip()
                    st.write("🔊 **उच्चारणम्:**")
                    play_sanskrit_audio(line)

    # 2. PĀṆINIAN VYĀKARAṆA ENGINE
    elif "Pāṇinian Vyākaraṇa" in guru_subtab:
        st.markdown("### 🧩 Pāṇinian Computational Grammar Engine")
        g_tool = st.selectbox(
            "Grammar Tool:",
            [
                "Sandhi Splitter & Sūtras (सन्धि-विच्छेदः)",
                "Shabdarūpa Declension Tables (शब्दरूपाणि - 8 Vibhaktis)",
                "Dhāturūpa Conjugation (धातुरूपाणि - 10 Lakāras)",
                "Samāsa Vigraha (समास-विग्रहः)"
            ]
        )
        g_term = st.text_input("Enter Term (e.g. राम, भू, गम्, देवेन्द्रः):")
        if st.button("Analyze Grammar"):
            if not api_key or not g_term:
                st.warning("Enter API key and term.")
                st.stop()
            client = genai.Client(api_key=api_key)
            with st.spinner("Executing grammatical derivations..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{"role": "user", "parts": [{"text": f"Provide comprehensive Paninian analysis for tool: {g_tool}, input: {g_term}. Include Astadhyayi sutras, clear markdown tables, and IAST."}]}]
                )
                st.markdown(resp.text)

    # 3. PHONETIC ŚIKṢĀ COACH
    elif "Phonetic Śikṣā" in guru_subtab:
        st.markdown("### 🎙️ Pāṇinīya Śikṣā Phonetic Evaluator")
        drill_phrase = st.selectbox(
            "Target Phrase to Shadow:",
            [
                "सत्यं वद, धर्मं चर। (Speak truth, walk in righteousness)",
                "विद्या ददाति विनयं विनयाद्याति पात्रताम्। (Knowledge gives humility)",
                "वृक्षात् फलानि भूमौ पतन्ति। (Fruits fall - check Mahāprāṇa 'ph')",
                "अहं प्रतिदिनं प्रातः पञ्चवादने उत्तिष्ठामि। (Retroflex 'ṣṭh' check)"
            ]
        )
        clean_target = drill_phrase.split('(')[0].strip()
        st.write("🔊 **Master Audio:**")
        play_sanskrit_audio(clean_target)
        
        sh_audio = st.audio_input("Record chanting:", key="shiksha_voice")
        if sh_audio is not None:
            if not api_key:
                st.warning("Enter API key.")
                st.stop()
            client = genai.Client(api_key=api_key)
            with st.spinner("Analyzing phonetic acoustics..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": sh_audio.getvalue()}},
                            {"text": f"Evaluate student's pronunciation against target: '{clean_target}'. Provide 0-100% score, articulation point breakdown (Dantya/Murdhanya), Mahaprana aspiration, and practical tongue placement tip."}
                        ]
                    }]
                )
                st.markdown(resp.text)

    # 4. INTERACTIVE PARĪKṢĀ
    elif "Interactive Parīkṣā" in guru_subtab:
        st.markdown("### 📝 Daily Sanskrit Parīkṣā (Exam Engine)")
        q_topic = st.selectbox("Topic", ["Vibhakti Agreement", "Verb Conjugation", "Sandhi Rules", "Spoken Sanskrit Translation"])
        if st.button("⚡ Generate New Test"):
            if not api_key:
                st.warning("Enter API key.")
                st.stop()
            client = genai.Client(api_key=api_key)
            with st.spinner("Creating test..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{"role": "user", "parts": [{"text": f"Generate a 3-question MCQ quiz on '{q_topic}' for Level: {level}. For each question: provide Devanagari, IAST, 4 options (A,B,C,D), correct answer, and Pāṇinian explanation."}]}]
                )
                st.session_state.guru_quiz = resp.text
        if st.session_state.guru_quiz:
            st.markdown(st.session_state.guru_quiz)

    # 5. SRS VOCABULARY VAULT
    elif "SRS Vocabulary" in guru_subtab:
        st.markdown("### 🧠 Spaced Repetition (SRS) Vocabulary Vault")
        for item in st.session_state.vocab_vault:
            st.markdown(f"- **{item['word']}** : {item['meaning']} | *Root:* `{item['dhatu']}` | ⏳ *Due:* `{item['due']}`")
        with st.expander("➕ Add Word to Vault"):
            nw = st.text_input("Sanskrit Word:")
            nm = st.text_input("Meaning:")
            nd = st.text_input("Root / Dhātu:")
            if st.button("Save Word"):
                if nw and nm:
                    st.session_state.vocab_vault.append({"word": nw, "meaning": nm, "dhatu": nd if nd else nw, "due": "Tomorrow"})
                    st.success("Word added to vault!")
                    st.rerun()
