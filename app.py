import sys
import os
import time
import io

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

# TalkPal Mobile App UX Layout
st.set_page_config(
    page_title="TalkPal Sanskrit AI",
    page_icon="🗣️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling for TalkPal Modern Card UI
st.markdown("""
<style>
    .talkpal-header {
        font-size: 26px;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 2px;
    }
    .talkpal-tag {
        background-color: #EEF2FF;
        color: #4F46E5;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 13px;
        font-weight: 600;
    }
    .correction-box {
        background-color: #FEF2F2;
        border-left: 4px solid #EF4444;
        padding: 10px 14px;
        border-radius: 6px;
        margin: 8px 0px;
    }
    .upgrade-box {
        background-color: #F0FDF4;
        border-left: 4px solid #22C55E;
        padding: 10px 14px;
        border-radius: 6px;
        margin: 8px 0px;
    }
</style>
""", unsafe_allow_html=True)

# Helper: Sanskrit Audio Player (TTS)
def play_sanskrit_audio(text_to_speak: str):
    try:
        clean = text_to_speak.replace('*', '').replace('#', '').replace('-', '').replace('[', '').replace(']', '').strip()
        if not clean:
            return
        tts = gTTS(text=clean, lang='hi', slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        st.audio(fp, format="audio/mp3")
    except Exception:
        pass

# --- SESSION STATES ---
if "xp" not in st.session_state:
    st.session_state.xp = 180
if "streak" not in st.session_state:
    st.session_state.streak = 5
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "active_mode_key" not in st.session_state:
    st.session_state.active_mode_key = "💬 Chat"

# --- SIDEBAR: Profile & Settings ---
with st.sidebar:
    st.markdown('<div class="talkpal-header">🗣️ TalkPal Sanskrit</div>', unsafe_allow_html=True)
    st.caption("The #1 AI Spoken Language Tutor • सम्भाषणम्")
    
    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        placeholder="AIza...",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Get free key at aistudio.google.com",
    )
    
    level = st.selectbox(
        "Your Level (CEFR / स्तरः)",
        ["A1 - Beginner (प्रथमा)", "A2 - Elementary", "B1 - Intermediate (मध्यमा)", "B2 - Upper Intermediate", "C1 - Advanced (उत्तमा)"],
        index=0
    )
    
    st.write("---")
    st.markdown("### 🏆 Your TalkPal Stats")
    c1, c2 = st.columns(2)
    c1.metric("🔥 Streak", f"{st.session_state.streak} Days")
    c2.metric("⭐ Total XP", f"{st.session_state.xp} XP")
    
    st.progress(0.65, text="Daily Goal: 65% completed")
    
    st.write("---")
    if st.button("🔄 Clear Active Chat"):
        st.session_state.chat_history = []
        st.rerun()

# --- TOP NAVIGATION: 5 TALKPAL MODES ---
selected_mode = st.radio(
    "Select Mode",
    ["💬 Chat", "🎭 Roleplays", "🔥 Debates", "📸 Photo Mode", "🧩 Custom Mode"],
    horizontal=True,
    label_visibility="collapsed"
)

# Reset history when switching modes
if selected_mode != st.session_state.active_mode_key:
    st.session_state.chat_history = []
    st.session_state.active_mode_key = selected_mode
    st.rerun()


# =========================================================
# 1. TALKPAL CHAT MODE
# =========================================================
if selected_mode == "💬 Chat":
    st.subheader("💬 Free Chat with AI Tutor (Emma / Ācārya)")
    st.caption("Converse on any topic. TalkPal analyzes your speech, translates, and offers real-time improvements.")

    SYSTEM_PROMPT = f"""You are the TalkPal AI Sanskrit Tutor.
Student Level: {level}.

Rules:
1. Speak in natural Sarala Samskritam adapted to {level}.
2. Always structure your answer strictly as follows:
[संस्कृतम्]: <Your Sanskrit conversational reply>
[IAST]: <Romanized transliteration with diacritics>
[English]: <Accurate English translation>
[💡 TalkPal Feedback]:
- 🔍 Grammatical Correction: <Point out any Vibhakti/Lakara/Sandhi error the user made, or state 'निर्दोषम् (Perfect!)' if correct>
- ✨ Better Way to Say: <An idiomatic, native-like phrase the student could have used>
"""

    if len(st.session_state.chat_history) == 0:
        st.session_state.chat_history = [
            {
                "role": "model",
                "content": "[संस्कृतम्]: हरिः ॐ! अद्य भवान्/भवती कीदृशं विषयम् अधिकृत्य सम्भाषणं कर्तुम् इच्छति?\n[IAST]: Hariḥ Om! Adya bhavān/bhavatī kīdṛśaṁ viṣayam adhikṛtya sambhāṣaṇaṁ kartum icchati?\n[English]: Hello! What topic would you like to talk about today?\n[💡 TalkPal Feedback]:\n- 🔍 Grammatical Correction: निर्दोषम् (Ready to start!)\n- ✨ Better Way to Say: Welcome to TalkPal Chat!"
            }
        ]

    for msg in st.session_state.chat_history:
        role = "assistant" if msg["role"] == "model" else "user"
        with st.chat_message(role):
            st.markdown(msg["content"])
            if role == "assistant" and "[संस्कृतम्]:" in msg["content"]:
                sanskrit_line = msg["content"].split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                play_sanskrit_audio(sanskrit_line)

    st.write("🎙️ **Oral Voice Input (वदतु):**")
    chat_audio = st.audio_input("Record voice to chat:")

    if chat_audio is not None:
        if not api_key:
            st.warning("⚠️ Please enter your Gemini API key in the sidebar.")
            st.stop()
            
        client = genai.Client(api_key=api_key)
        audio_bytes = chat_audio.getvalue()
        
        st.session_state.chat_history.append({"role": "user", "content": "🎙️ *[Spoken Audio Response Submitted]*"})
        st.session_state.xp += 10
        with st.chat_message("user"):
            st.audio(chat_audio, format="audio/wav")
            
        with st.chat_message("assistant"):
            with st.spinner("TalkPal is listening & typing..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": audio_bytes}},
                            {"text": f"{SYSTEM_PROMPT}\nTranscribe spoken audio, reply in character, and provide feedback."}
                        ]
                    }],
                )
                st.markdown(resp.text)
                if "[संस्कृतम्]:" in resp.text:
                    line = resp.text.split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                    play_sanskrit_audio(line)
                st.session_state.chat_history.append({"role": "model", "content": resp.text})

    if text_input := st.chat_input("Or type in Sanskrit / English (e.g. mama nama, adya aham...)..."):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
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

        st.session_state.chat_history.append({"role": "user", "content": user_text})
        st.session_state.xp += 5
        with st.chat_message("user"):
            st.markdown(user_text)

        contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": str(m["content"])}]} for m in st.session_state.chat_history]

        with st.chat_message("assistant"):
            with st.spinner("TalkPal thinking..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=contents,
                    config={"system_instruction": SYSTEM_PROMPT, "temperature": 0.2},
                )
                st.markdown(resp.text)
                if "[संस्कृतम्]:" in resp.text:
                    line = resp.text.split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                    play_sanskrit_audio(line)
                st.session_state.chat_history.append({"role": "model", "content": resp.text})


# =========================================================
# 2. TALKPAL ROLEPLAY MODE
# =========================================================
elif selected_mode == "🎭 Roleplays":
    st.subheader("🎭 TalkPal Immersion Roleplays")
    st.caption("Practice real-life missions. Reach objectives by speaking with situational AI characters.")

    roleplay_scenarios = {
        "🛒 Indian Vegetable Market (विपणिः)": "You are a vegetable vendor at a bustling traditional market. The student wants to buy fresh vegetables and bargain politely.",
        "🏨 Hotel / Gurukula Check-In (अतिथि-गृहम्)": "You are the manager of an Indian traditional heritage stay/guest house. The user is checking in and asking about room facilities and food timings.",
        "💼 Sanskrit Teacher Job Interview (उपाध्याय-साक्षात्कारः)": "You are the Dean of a university interviewing the candidate for a Sanskrit teaching position.",
        "🚆 Railway Station Enquiry (रेलस्थानकम्)": "You are the enquiry officer at a railway station helping a passenger book a ticket to Varanasi."
    }

    selected_rp = st.selectbox("Choose Roleplay Scenario:", list(roleplay_scenarios.keys()))
    rp_prompt = roleplay_scenarios[selected_rp]

    SYSTEM_RP = f"""You are the AI actor in this scenario: '{selected_rp}'.
Context: {rp_prompt}
Target Student Level: {level}.

Rules:
1. Stay in character 100% of the time.
2. Format:
[संस्कृतम्]: <In-character Sanskrit speech>
[IAST]: <Transliteration>
[English]: <Translation>
[🎯 Mission Objective Hint]: <A quick tip for the student on what to say next to advance the roleplay>
"""

    if len(st.session_state.chat_history) == 0:
        st.session_state.chat_history = [
            {
                "role": "model",
                "content": f"[संस्कृतम्]: नमस्ते! स्वागतम्। अहं भवतः/भवत्याः कथं साहाय्यं कर्तुं शक्नोमि?\n[IAST]: Namaste! Svāgatam. Ahaṁ bhavataḥ/bhavatyāḥ kathaṁ sāhāyyaṁ kartuṁ śaknomi?\n[English]: Greetings! Welcome. How may I help you?\n[🎯 Mission Objective Hint]: Introduce yourself and state your purpose."
            }
        ]

    for msg in st.session_state.chat_history:
        role = "assistant" if msg["role"] == "model" else "user"
        with st.chat_message(role):
            st.markdown(msg["content"])
            if role == "assistant" and "[संस्कृतम्]:" in msg["content"]:
                line = msg["content"].split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                play_sanskrit_audio(line)

    st.write("🎙️ **Your Spoken Response (वदतु):**")
    rp_audio = st.audio_input("Record roleplay voice:")

    if rp_audio is not None:
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        
        st.session_state.chat_history.append({"role": "user", "content": "🎙️ *[Spoken Audio Reply]*"})
        st.session_state.xp += 15
        with st.chat_message("user"):
            st.audio(rp_audio, format="audio/wav")

        with st.chat_message("assistant"):
            with st.spinner("Character responding..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": rp_audio.getvalue()}},
                            {"text": f"{SYSTEM_RP}\nRespond in character to the student's spoken audio."}
                        ]
                    }]
                )
                st.markdown(resp.text)
                if "[संस्कृतम्]:" in resp.text:
                    line = resp.text.split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                    play_sanskrit_audio(line)
                st.session_state.chat_history.append({"role": "model", "content": resp.text})


# =========================================================
# 3. TALKPAL DEBATE MODE
# =========================================================
elif selected_mode == "🔥 Debates":
    st.subheader("🔥 TalkPal Debate Club (शास्त्रार्थः / वाद-विवादः)")
    st.caption("Sharpen critical thinking and fluent argumentation. The AI will challenge your arguments.")

    debate_topics = [
        "प्राचीन-गुरुकुल-पद्धतिः श्रेयस्करी वा आधुनिक-शिक्षण-पद्धतिः? (Ancient Gurukula vs Modern Education)",
        "संस्कृत-सम्भाषणाय व्याकरणं अनिवार्यं वा केवलम् अभ्यासः? (Grammar vs Spoken Immersion)",
        "कृत्रिमबुद्धिः (AI) मानवाय वरदानं वा शापः? (Is AI a boon or a curse?)"
    ]
    topic = st.selectbox("Select Debate Topic:", debate_topics)

    SYSTEM_DEBATE = f"""You are a master Sanskrit debater engaged in Śāstrārtha on topic: '{topic}'.
Target Level: {level}.

Rules:
1. Counter the student's argument logically and politely in crisp Sanskrit.
2. Push them to justify their points using Sanskrit conjunctions (यतः, अतः, यदि, तर्हि).
3. Format:
[संस्कृतम्]: <Debate rebuttal>
[IAST]: <IAST transliteration>
[English]: <English meaning>
[🔥 Counter-Argument Challenge]: <A sharp challenge question to test their reasoning>
"""

    if len(st.session_state.chat_history) == 0:
        st.session_state.chat_history = [
            {
                "role": "model",
                "content": f"[संस्कृतम्]: अस्मिन् विषये मम विचारः अस्ति यत् प्राचीन-दृष्टिकोणः एव श्रेष्ठः। भवतः/भवत्याः किं मतम्?\n[IAST]: Asmin viṣaye mama vicāraḥ asti yat prācīna-dṛṣṭikoṇaḥ eva śreṣṭhaḥ. Bhavataḥ/bhavatyāḥ kiṁ matam?\n[English]: In my view on this topic, the traditional perspective is superior. What is your argument?\n[🔥 Counter-Argument Challenge]: State your opening stance and give one strong reason why."
            }
        ]

    for msg in st.session_state.chat_history:
        role = "assistant" if msg["role"] == "model" else "user"
        with st.chat_message(role):
            st.markdown(msg["content"])
            if role == "assistant" and "[संस्कृतम्]:" in msg["content"]:
                line = msg["content"].split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                play_sanskrit_audio(line)

    st.write("🎙️ **Deliver Your Debate Argument (स्वपक्षं स्थापयतु):**")
    deb_audio = st.audio_input("Record your debate argument:")

    if deb_audio is not None:
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        st.session_state.chat_history.append({"role": "user", "content": "🎙️ *[Spoken Debate Argument]*"})
        st.session_state.xp += 20
        with st.chat_message("user"):
            st.audio(deb_audio, format="audio/wav")
        with st.chat_message("assistant"):
            with st.spinner("AI analyzing your thesis & formulating counter..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": deb_audio.getvalue()}},
                            {"text": f"{SYSTEM_DEBATE}\nRebut the student's spoken thesis in the debate."}
                        ]
                    }]
                )
                st.markdown(resp.text)
                if "[संस्कृतम्]:" in resp.text:
                    line = resp.text.split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                    play_sanskrit_audio(line)
                st.session_state.chat_history.append({"role": "model", "content": resp.text})


# =========================================================
# 4. TALKPAL PHOTO MODE (Describe Image / चित्रवर्णनम्)
# =========================================================
elif selected_mode == "📸 Photo Mode":
    st.subheader("📸 Photo Mode (चित्रवर्णनम्)")
    st.caption("TalkPal gives you a vibrant scene. Describe what you observe using your voice.")

    scenes = {
        "🌳 Forest Scene (तपोवनम्)": "A serene Himalayan hermitage (Āśrama) where an Ācārya is seated under a banyan tree with deer and peacocks listening peacefully.",
        "🎪 Indian Village Festival (ग्रामोत्सवः)": "A colorful village fair with temples, sweet vendors selling laddus, children playing with toys, and decorated cows.",
        "🏫 Classroom (पाठशाला)": "A clean classroom with students sitting on mats writing on palm leaves with a blackboard showing the Sanskrit alphabet."
    }

    photo_choice = st.selectbox("Select Visual Challenge:", list(scenes.keys()))
    st.info(f"🖼️ **Scene Description:** {scenes[photo_choice]}")

    st.write("🎙️ **Describe what you see in Sanskrit (3-5 sentences):**")
    photo_audio = st.audio_input("Record your spoken description:")

    if photo_audio is not None:
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Evaluating vocabulary, descriptive accuracy, and grammar..."):
            PROMPT_PHOTO = f"""You are the TalkPal Photo Mode Assessor.
Target Visual Scene: "{scenes[photo_choice]}"
Target Level: {level}.

Analyze student's spoken recording describing this picture:
1. Vocabulary & Descriptive Richness Score: (0-100%)
2. Grammatical Accuracy (Vibhakti of nouns, Lakāra of verbs).
3. Ideal Sample Description: Provide a beautiful 3-line Sanskrit model description of this scene with IAST & English.

Format:
### 🎯 चित्रवर्णन-मूल्याङ्कनम् (Score): [XX / 100]
- **वर्णन-गुणवत्ता (Descriptive Richness)**: <Feedback>
- **व्याकरण-शुद्धिः (Grammar Check)**: <Feedback on Case/Verb agreements>

---
### 🌟 आदर्श-वर्णनम् (Model Sanskrit Description):
[संस्कृतम्]: <Model description>
[IAST]: <IAST>
[English]: <English translation>
"""
            try:
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": photo_audio.getvalue()}},
                            {"text": PROMPT_PHOTO}
                        ]
                    }]
                )
                st.markdown(resp.text)
                st.session_state.xp += 25
                if "[संस्कृतम्]:" in resp.text:
                    line = resp.text.split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                    play_sanskrit_audio(line)
            except Exception as e:
                st.error(f"Error: {str(e)}")


# =========================================================
# 5. TALKPAL CUSTOM SCENARIOS
# =========================================================
elif selected_mode == "🧩 Custom Mode":
    st.subheader("🧩 Custom Topic or Roleplay")
    st.caption("Create any learning mission, job interview, or historical character simulation.")

    custom_character = st.text_input("Who should the AI be?", placeholder="e.g. Kalidasa, Chanakya, my Sanskrit study buddy")
    custom_setting = st.text_area("What is the situation / topic?", placeholder="e.g. We are discussing poetry in the court of King Vikramaditya.")

    if st.button("Start Custom Simulation"):
        if not custom_character or not custom_setting:
            st.warning("Please fill in both fields.")
        else:
            st.session_state.chat_history = [
                {
                    "role": "model",
                    "content": f"[संस्कृतम्]: हरिः ॐ! अहं {custom_character} अस्मि। भवतः स्वागतम्।\n[IAST]: Hariḥ Om! Ahaṁ {custom_character} asmi. Bhavataḥ svāgatam.\n[English]: Hello! I am {custom_character}. Welcome!\n[🎯 Mission]: Begin your custom conversation."
                }
            ]
            st.rerun()

    for msg in st.session_state.chat_history:
        role = "assistant" if msg["role"] == "model" else "user"
        with st.chat_message(role):
            st.markdown(msg["content"])
            if role == "assistant" and "[संस्कृतम्]:" in msg["content"]:
                line = msg["content"].split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                play_sanskrit_audio(line)

    if len(st.session_state.chat_history) > 0:
        cust_audio = st.audio_input("Speak to your custom character:")
        if cust_audio is not None:
            if not api_key:
                st.warning("⚠️ Enter Gemini API key.")
                st.stop()
            client = genai.Client(api_key=api_key)
            st.session_state.chat_history.append({"role": "user", "content": "🎙️ *[Spoken Voice Input]*"})
            with st.chat_message("user"):
                st.audio(cust_audio, format="audio/wav")
            with st.chat_message("assistant"):
                with st.spinner("AI responding..."):
                    resp = client.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=[{
                            "role": "user",
                            "parts": [
                                {"inline_data": {"mime_type": "audio/wav", "data": cust_audio.getvalue()}},
                                {"text": f"You are {custom_character} in setting: {custom_setting}. Speak in Sanskrit suited for {level}. Provide IAST, English, and guidance."}
                            ]
                        }]
                    )
                    st.markdown(resp.text)
                    if "[संस्कृतम्]:" in resp.text:
                        line = resp.text.split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                        play_sanskrit_audio(line)
                    st.session_state.chat_history.append({"role": "model", "content": resp.text})
