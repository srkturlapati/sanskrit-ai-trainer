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

st.set_page_config(
    page_title="Sambhāṣaṇa AI - Spoken Sanskrit Master",
    page_icon="🚩",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.title("🚩 Sambhāṣaṇa AI (सम्भाषण-प्रशिक्षकः)")
st.caption("AI-Powered Spoken Sanskrit Academy • Fluency • Phonetics • Roleplay")

# --- SESSION STATE: Gamification & Vocabulary Vault ---
if "practice_streak" not in st.session_state:
    st.session_state.practice_streak = 1
if "vocab_vault" not in st.session_state:
    st.session_state.vocab_vault = [
        {"word": "अस्तु", "meaning": "Alright / Let it be", "level": "Beginner"},
        {"word": "धन्यवादः", "meaning": "Thank you", "level": "Beginner"},
        {"word": "पुनर्मिलामः", "meaning": "See you again", "level": "Beginner"}
    ]
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_quiz" not in st.session_state:
    st.session_state.current_quiz = None

# Helper: Sanskrit TTS Audio
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

# --- SIDEBAR: Settings & Gamification Profile ---
with st.sidebar:
    st.header("⚙️ Settings & Profile")
    api_key = st.text_input(
        "Google Gemini API Key",
        type="password",
        placeholder="AIza...",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Get your free key at aistudio.google.com/apikey",
    )
    
    level = st.selectbox(
        "Student Level / स्तरः",
        [
            "Beginner (प्रथमा - Daily Phrases & Basic Verbs)",
            "Intermediate (मध्यमा - Tenses, Participles & Flow)",
            "Advanced (उत्तमा - Shastric & Literary Sanskrit)"
        ],
        index=0,
    )
    
    st.write("---")
    st.subheader("🏆 Your Progress")
    st.metric(label="🔥 Daily Speaking Streak", value=f"{st.session_state.practice_streak} Days")
    st.metric(label="📚 Words in Vault", value=f"{len(st.session_state.vocab_vault)} Words")
    
    if st.button("🔄 Reset Chat / Clear Session"):
        st.session_state.messages = []
        st.session_state.current_quiz = None
        st.rerun()

# --- TOP NAVIGATION TABS ---
tab_roleplay, tab_shiksha, tab_translate, tab_grammar, tab_vault = st.tabs([
    "💬 1. Roleplay & Tutor",
    "🎙️ 2. Śikṣā (Pronunciation)",
    "🌐 3. Translation",
    "🧩 4. Vyākaraṇa",
    "🏆 5. Vault & Parīkṣā"
])


# =========================================================
# TAB 1: SITUATIONAL ROLEPLAY & CONVERSATION
# =========================================================
with tab_roleplay:
    st.subheader("💬 सम्भाषण-प्रसङ्गाः (Speaking Scenarios)")
    
    scenario = st.selectbox(
        "Choose Conversation Scenario / प्रसङ्गः",
        [
            "General Conversation with Ācārya (मुक्त-सम्भाषणम्)",
            "At the Market / Vegetables (विपणिः - शाकक्रयणम्)",
            "At School / Gurukula (पाठशाला - गुरुकुलम्)",
            "Travel & Directions (यात्रा - मार्गनिर्देशनम्)",
            "Welcoming a Guest (अतिथि-सत्कारः)",
            "Storyteller Mode with Animals (पञ्चतन्त्र-कथा: गजः, शुकः, मयूरः)"
        ]
    )

    SYSTEM_ROLEPLAY = f"""You are a dynamic Sanskrit Spoken Coach in the scenario: '{scenario}'.
Target Student Level: {level}.

Rules:
1. Converse naturally in spoken Sarala Samskritam according to the scenario.
2. If the student makes an error (Vibhakti, Lakara, Purusha), gently point it out.
3. Provide a '✨ Say It Better' suggestion (a more natural/idiomatic Sanskrit expression).
4. Keep the roleplay engaging and ask a relevant question back.

Format:
[संस्कृतम्]: <Devanagari Dialogue>
[IAST]: <Romanized transliteration>
[English]: <English meaning>
[✨ Say It Better]: <Alternative idiomatic phrase in Sanskrit with meaning>
[मार्गदर्शनम्] (Only if student made an error):
- 🔍 रूपम्: <Incorrect word>
- 💡 सङ्केतः: <Correction & Rule>
"""

    # Display dialogue history
    for msg in st.session_state.messages:
        role = "assistant" if msg["role"] == "model" else "user"
        with st.chat_message(role):
            st.markdown(msg["content"])
            if role == "assistant" and "[संस्कृतम्]:" in msg["content"]:
                line = msg["content"].split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                play_sanskrit_audio(line)

    # Voice Input inside Roleplay
    st.write("🎙️ **Speak your reply (वदतु):**")
    role_audio = st.audio_input("Record voice for roleplay:")
    
    if role_audio is not None:
        if not api_key:
            st.warning("⚠️ Please enter your Gemini API key in the sidebar.")
            st.stop()
        
        client = genai.Client(api_key=api_key)
        audio_bytes = role_audio.getvalue()
        
        st.session_state.messages.append({"role": "user", "content": "🎙️ *[Spoken Audio Response Submitted]*"})
        with st.chat_message("user"):
            st.audio(role_audio, format="audio/wav")
        
        with st.chat_message("assistant"):
            with st.spinner("आचार्यः शृणोति..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": audio_bytes}},
                            {"text": f"{SYSTEM_ROLEPLAY}\nRespond to the student's spoken audio within the scenario."}
                        ]
                    }],
                )
                st.markdown(resp.text)
                if "[संस्कृतम्]:" in resp.text:
                    line = resp.text.split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                    play_sanskrit_audio(line)
                st.session_state.messages.append({"role": "model", "content": resp.text})

    # Text Input inside Roleplay
    if text_msg := st.chat_input("Or type here (e.g. mama nama, katham asti...):"):
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

        st.session_state.messages.append({"role": "user", "content": user_display})
        with st.chat_message("user"):
            st.markdown(user_display)

        contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": str(m["content"])}]} for m in st.session_state.messages]

        with st.chat_message("assistant"):
            with st.spinner("आचार्यः चिन्तयति..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=contents,
                    config={"system_instruction": SYSTEM_ROLEPLAY, "temperature": 0.2},
                )
                st.markdown(resp.text)
                if "[संस्कृतम्]:" in resp.text:
                    line = resp.text.split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                    play_sanskrit_audio(line)
                st.session_state.messages.append({"role": "model", "content": resp.text})


# =========================================================
# TAB 2: PRONUNCIATION & SHADOWING (ŚIKṢĀ COACH)
# =========================================================
with tab_shiksha:
    st.subheader("🎙️ पाणिनीय-शिक्षा एवं उच्चारण-परीक्षकः (Phonetic Coach)")
    st.caption("Practice Sanskrit pronunciation with real-time articulation feedback (0–100% score).")
    
    drill_sentences = [
        "सत्यं वद, धर्मं चर। (Speak truth, walk in righteousness)",
        "विद्या ददाति विनयं विनयाद्याति पात्रताम्। (Knowledge gives humility)",
        "वृक्षात् फलानि भूमौ पतन्ति। (Fruits fall from tree to ground - check Mahāprāṇa 'ph')",
        "अहं प्रतिदिनं प्रातः पञ्चवादने उत्तिष्ठामि। (I wake up at 5 AM daily - check retroflex 'ṣṭh')"
    ]
    
    target_sentence = st.selectbox("Select Target Sentence to Shadow / अनुवाचनम्:", drill_sentences)
    
    st.write("🔊 **Listen to Master Pronunciation:**")
    play_sanskrit_audio(target_sentence.split('(')[0].strip())
    
    st.write("🎙️ **Now Record Your Voice Repeating It:**")
    shadow_audio = st.audio_input("Repeat the sentence clearly:")
    
    if shadow_audio is not None:
        if not api_key:
            st.warning("⚠️ Please enter your Gemini API key in the sidebar.")
            st.stop()
            
        client = genai.Client(api_key=api_key)
        with st.spinner("Evaluating pronunciation against Pāṇinīya Śikṣā rules..."):
            PROMPT_SHIKSHA = f"""You are an expert Vedic/Pāṇinian phonetician (पाणिनीय-शिक्षाविद्).
Target Sentence to Pronounce: "{target_sentence}"

Analyze the student's audio recording and evaluate:
1. Pronunciation Accuracy Score: Out of 100% (based on vowel length hrasva/dīrgha, visarga aspiration, and consonant articulation points).
2. Articulation Points Analysis (उच्चारण-स्थानम्):
   - Dental vs Retroflex (दन्त्य vs मूर्धन्य - e.g., त् vs ट्)
   - Mahāprāṇa aspiration (महाप्राणः - e.g., ख्, घ्, थ्, फ्)
   - Anusvāra & Visarga precision
3. Specific Coaching Tip: Practical advice on where to place the tongue or release air.

Format cleanly with markdown:
### 🎯 उच्चारण-मूल्याङ्कनम् (Pronunciation Score): [XX / 100]
**शुद्धता-स्तरः (Clarity):** [Excellent / Good / Needs Practice]

---
### 🔍 वर्णोच्चारण-विश्लेषणम् (Phonetic Breakdown):
- **उच्चारण-स्थानानि**: <Feedback on articulation points>
- **प्राण-प्रयत्नः (Aspiration)**: <Feedback on Alpaprāṇa vs Mahāprāṇa>
- **स्वर-दीर्घता (Vowel Timing)**: <Feedback on short vs long vowels>

---
### 💡 सुधार-सङ्केताः (How to Improve):
<Concrete tongue placement and breath control tip>
"""
            try:
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": shadow_audio.getvalue()}},
                            {"text": PROMPT_SHIKSHA}
                        ]
                    }]
                )
                st.markdown(resp.text)
            except Exception as e:
                st.error(f"Error evaluating audio: {str(e)}")


# =========================================================
# TAB 3: UNIVERSAL TRANSLATOR
# =========================================================
with tab_translate:
    st.subheader("🌐 सर्वभाषा-संस्कृत-अनुवादकः (Universal Translator)")
    
    trans_dir = st.radio("Direction", ["Any Language ➔ Sanskrit", "Sanskrit ➔ Any Language"], horizontal=True)
    
    if trans_dir == "Sanskrit ➔ Any Language":
        t_lang = st.selectbox("Target Language", ["Telugu (తెలుగు)", "Hindi (हिन्दी)", "English", "Tamil (தமிழ்)", "Kannada (ಕನ್ನಡ)", "Marathi (मराठी)"])
    
    in_text = st.text_area("Enter text to translate:", height=80)
    
    if st.button("Translate / अनुवादं कुरु"):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        if not in_text.strip():
            st.warning("Enter text first.")
            st.stop()
            
        client = genai.Client(api_key=api_key)
        if trans_dir == "Any Language ➔ Sanskrit":
            PROMPT_T = f"""Translate into Sanskrit for level {level}.
MANDATORY:
### 🪶 पूर्णवाक्यम्:
**संस्कृतम् (Devanagari):** <FULL TRANSLATED SENTENCE>
**IAST:** <Sentence in IAST>
**English:** <English meaning>

---
### 🔍 व्याकरणम्:
- Padaccheda and Vibhakti breakdown
"""
        else:
            PROMPT_T = f"""Translate this Sanskrit into {t_lang} and English with word-by-word meaning and sandhi splits."""
            
        with st.spinner("Translating..."):
            resp = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=[{"role": "user", "parts": [{"text": f"{PROMPT_T}\nInput: {in_text}"}]}],
            )
            st.markdown(resp.text)
            if "संस्कृतम् (Devanagari):" in resp.text:
                line = resp.text.split("संस्कृतम् (Devanagari):")[1].split("\n")[0].strip()
                st.write("🔊 **उच्चारणम्:**")
                play_sanskrit_audio(line)


# =========================================================
# TAB 4: VYĀKARAṆA ENGINE
# =========================================================
with tab_grammar:
    st.subheader("🧩 पाणिनीय-व्याकरण-उपकरणम् (Grammar Engine)")
    
    tool = st.selectbox("Tool", [
        "Sandhi Splitter & Rules (सन्धि-विच्छेदः)",
        "Shabdarupa Tables (शब्दरूपाणि - 8 Vibhaktis)",
        "Dhaturoopa Conjugator (धातुरूपाणि - 10 Lakaras)",
        "Samasa & Vigraha (समास-विग्रहः)"
    ])
    g_input = st.text_input("Enter Word / Root (e.g. राम, गम्, देवेन्द्रः):")
    
    if st.button("Generate Grammar Analysis"):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Analyzing..."):
            resp = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=[{"role": "user", "parts": [{"text": f"Generate Ashtadhyayi Paninian analysis for tool: {tool}, input: {g_input}"}]}],
            )
            st.markdown(resp.text)


# =========================================================
# TAB 5: VOCABULARY VAULT & PARĪKṢĀ
# =========================================================
with tab_vault:
    st.subheader("🏆 शब्दकोशः एवं परीक्षा (Vault & Quizzes)")
    
    col1, col2 = st.columns(2)
    with col1:
        st.write("### 📚 Saved Vocabulary Vault")
        for item in st.session_state.vocab_vault:
            st.markdown(f"- **{item['word']}**: {item['meaning']} *({item['level']})*")
            
        with st.expander("➕ Add New Word to Vault"):
            nw = st.text_input("Sanskrit Word (पदम्):")
            nm = st.text_input("Meaning (अर्थः):")
            if st.button("Save Word"):
                if nw and nm:
                    st.session_state.vocab_vault.append({"word": nw, "meaning": nm, "level": "Learner"})
                    st.success("Word added to vault!")
                    st.rerun()

    with col2:
        st.write("### 📝 Quick Quiz (परीक्षा)")
        quiz_type = st.selectbox("Topic", ["Vibhakti Drill", "Verb Conjugation", "Spoken Sanskrit Expressions"])
        if st.button("⚡ Generate Quiz"):
            if not api_key:
                st.warning("⚠️ Enter Gemini API key.")
                st.stop()
            client = genai.Client(api_key=api_key)
            with st.spinner("Generating quiz..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{"role": "user", "parts": [{"text": f"Generate 3-question MCQ quiz on {quiz_type} with correct answer and Paninian explanation."}]}],
                )
                st.session_state.current_quiz = resp.text
                
        if st.session_state.current_quiz:
            st.markdown(st.session_state.current_quiz)
