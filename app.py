import sys
import os
import time
import io

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
    page_title="Sanskrit AI Platform",
    page_icon="🚩",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.title("🚩 Sanskrit AI Platform")
st.caption("सम्भाषणम् • अनुवादकः • व्याकरणम् • परीक्षा | Voice-Enabled Sanskrit Ecosystem")

# --- SIDEBAR: Settings & Navigation ---
with st.sidebar:
    st.header("⚙️ Settings & Modules / विन्यासः")
    api_key = st.text_input(
        "Google Gemini API Key",
        type="password",
        placeholder="AIza...",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Get your free key at aistudio.google.com/apikey",
    )
    
    app_module = st.radio(
        "Select Active Module / विभागः",
        [
            "💬 Module 1: Sambhashanam (सम्भाषणम्)",
            "🌐 Module 1: Universal Translation (अनुवादकः)",
            "🧩 Module 2: Vyakarana Engine (व्याकरणम्)",
            "📝 Module 3: Pariksha & Drills (परीक्षा)"
        ],
        index=0
    )
    
    level = st.selectbox(
        "Proficiency Tier / स्तरः",
        [
            "Beginner (प्रथमा - Basic)",
            "Intermediate (मध्यमा - Moderate)",
            "Advanced (उत्तमा - Classical/Shastric)"
        ],
        index=0,
    )
    
    if "Universal Translation" in app_module:
        trans_direction = st.selectbox(
            "Translation Mode",
            ["Any Language ➔ Sanskrit", "Sanskrit ➔ Any Language"]
        )
        if trans_direction == "Sanskrit ➔ Any Language":
            target_lang = st.selectbox(
                "Target Language / लक्ष्यभाषा",
                ["Telugu (తెలుగు)", "Hindi (हिन्दी)", "English", "Tamil (தமிழ்)", "Kannada (ಕನ್ನಡ)", "Marathi (मराठी)", "Malayalam (മലയാളം)", "Bengali (বাংলা)", "Gujarati (ગુજરાતી)"]
            )
    
    if st.button("🔄 Reset Module Session"):
        st.session_state.messages = []
        st.session_state.current_quiz = None
        st.rerun()

# Helper function for Sanskrit Audio Playback (TTS)
def play_sanskrit_audio(text_to_speak: str):
    try:
        clean_text = text_to_speak.replace('*', '').replace('#', '').replace('-', '').strip()
        if not clean_text:
            return
        tts = gTTS(text=clean_text, lang='hi', slow=False)
        audio_fp = io.BytesIO()
        tts.write_to_fp(audio_fp)
        audio_fp.seek(0)
        st.audio(audio_fp, format="audio/mp3")
    except Exception:
        pass


# =========================================================
# MODULE 1: SAMBHASHANAM (Conversational Tutor + Voice)
# =========================================================
if "Sambhashanam" in app_module:
    SYSTEM_PROMPT = f"""You are "Acharya AI" (आचार्यः), a pedagogical Sanskrit tutor specializing in Sarala Samskritam.
Current Student Level: {level}.

Rules:
1. Converse naturally in simple Sanskrit suited to the level.
2. If student speaks/writes with an error (Vibhakti, Lakara, Purusha, Sandhi):
   - Highlight the error gently.
   - Provide a Socratic hint or question so they can self-correct.
3. Always format your output cleanly as:
[संस्कृतम्]: <Devanagari text>
[IAST]: <IAST transliteration>
[English]: <English meaning>
[मार्गदर्शनम्] (Include ONLY if error is present):
- Error: <Student mistake>
- Hint: <Guiding hint or rule>
"""

    if "messages" not in st.session_state or len(st.session_state.messages) == 0:
        st.session_state.messages = [
            {
                "role": "model",
                "content": "[संस्कृतम्]: हरिः ॐ! भवतः/भवत्याः नाम किम्?\n[IAST]: Harih Om! Bhavatah/Bhavatyah nama kim?\n[English]: Hello! What is your name?",
            }
        ]

    for msg in st.session_state.messages:
        role = "assistant" if msg["role"] == "model" else "user"
        with st.chat_message(role):
            st.markdown(msg["content"])
            if role == "assistant":
                lines = [line.replace("[संस्कृतम्]:", "").strip() for line in msg["content"].split("\n") if "[संस्कृतम्]:" in line]
                if lines:
                    play_sanskrit_audio(lines[0])

    # 🎙️ In-App Microphone Recording Widget
    st.write("---")
    st.write("🎙️ **Oral / Voice Question (वदतु):**")
    audio_data = st.audio_input("Record your voice / स्वध्वनिं मुद्रयतु:")

    # Handle Audio Voice Input
    if audio_data is not None:
        if not api_key:
            st.warning("⚠️ Please enter your Gemini API key in the sidebar.")
            st.stop()

        client = genai.Client(api_key=api_key)
        audio_bytes = audio_data.getvalue()

        st.session_state.messages.append({"role": "user", "content": "🎙️ [Oral Voice Input Submitted]"})
        with st.chat_message("user"):
            st.audio(audio_data, format="audio/wav")
            st.caption("🎙️ Oral Question Submitted")

        with st.chat_message("assistant"):
            with st.spinner("आचार्यः शृणोति एवं चिन्तयति... (Listening & Thinking)"):
                try:
                    response = client.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=[
                            {
                                "role": "user",
                                "parts": [
                                    {"inline_data": {"mime_type": "audio/wav", "data": audio_bytes}},
                                    {"text": f"{SYSTEM_PROMPT}\nListen to this student's spoken audio. Transcribe what they said, provide the Acharya response in simple Sanskrit, and add guidance if needed."}
                                ]
                            }
                        ],
                    )
                    reply = response.text
                    st.markdown(reply)
                    lines = [line.replace("[संस्कृतम्]:", "").strip() for line in reply.split("\n") if "[संस्कृतम्]:" in line]
                    if lines:
                        play_sanskrit_audio(lines[0])
                    st.session_state.messages.append({"role": "model", "content": reply})
                except Exception as e:
                    st.error(f"Error processing audio: {str(e)}")

    # Handle Text Input
    if user_input := st.chat_input("Type in Sanskrit or English (e.g. mama nama...)..."):
        if not api_key:
            st.warning("⚠️ Please enter your Gemini API key in the sidebar.")
            st.stop()

        client = genai.Client(api_key=api_key)
        is_devanagari = any("\u0900" <= char <= "\u097f" for char in user_input)
        if not is_devanagari:
            try:
                converted_dev = transliterate(user_input, sanscript.ITRANS, sanscript.DEVANAGARI)
                display_text = f"{user_input} ({converted_dev})"
            except Exception:
                display_text = user_input
        else:
            display_text = user_input

        st.session_state.messages.append({"role": "user", "content": display_text})
        with st.chat_message("user"):
            st.markdown(display_text)

        contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": str(m["content"])}]} for m in st.session_state.messages]

        with st.chat_message("assistant"):
            with st.spinner("आचार्यः चिन्तयति..."):
                reply = None
                for _ in range(3):
                    try:
                        resp = client.models.generate_content(
                            model="gemini-3.6-flash",
                            contents=contents,
                            config={"system_instruction": SYSTEM_PROMPT, "temperature": 0.2},
                        )
                        reply = resp.text
                        break
                    except Exception:
                        time.sleep(1.5)

                if reply:
                    st.markdown(reply)
                    lines = [line.replace("[संस्कृतम्]:", "").strip() for line in reply.split("\n") if "[संस्कृतम्]:" in line]
                    if lines:
                        play_sanskrit_audio(lines[0])
                    st.session_state.messages.append({"role": "model", "content": reply})


# =========================================================
# MODULE 1: UNIVERSAL TRANSLATION ENGINE
# =========================================================
elif "Universal Translation" in app_module:
    if trans_direction == "Any Language ➔ Sanskrit":
        SYSTEM_PROMPT = f"""You are "Acharya Anuvadaka" (अनुवादकः). Translate input into Sanskrit.
Target Level: {level}.

MANDATORY OUTPUT FORMAT:
### 🪶 पूर्णवाक्यम् (Complete Sanskrit Sentence):
**संस्कृतम् (Devanagari):** <FULL TRANSLATED SENTENCE>
**IAST Transliteration:** <Sentence in IAST>
**English Meaning:** <Complete English translation>

---
### 🔍 व्याकरणम् एवं पदच्छेदः (Word-by-Word Analysis):
- **<Word>**: <Pratipadika/Dhatu> + <Vibhakti/Pratyaya> — <Meaning>
- **विशेष-नियमः (Key Rule applied)**: <Brief grammar note>
"""
    else:
        SYSTEM_PROMPT = f"""You are "Acharya Vyakhyata" (व्याख्याता). Translate Sanskrit into {target_lang}.
Target Level: {level}.

Output Format:
### 🎯 अनुवादः (Translation in {target_lang}):
**{target_lang}:** <Accurate translation>
**English:** <Fluent English translation>

---
### 📜 पदच्छेदः एवं प्रतिपदार्थः (Word-by-Word Breakdown):
- **<Sanskrit Word>**: <Meaning in {target_lang}> (<Grammar tag>)
"""

    st.subheader(f"🌐 {trans_direction}")
    
    # Text translation input
    user_query = st.text_area("Enter text to translate (or record oral voice below):", height=90)
    
    # Oral Voice for Translation
    st.write("🎙️ **Or speak to translate:**")
    trans_audio = st.audio_input("Speak sentence to translate:")
    
    if st.button("Translate / अनुवादं कुरु") or (trans_audio is not None):
        if not api_key:
            st.warning("⚠️ Please enter your Gemini API key in the sidebar.")
            st.stop()

        client = genai.Client(api_key=api_key)
        with st.spinner("Translating..."):
            try:
                if trans_audio is not None:
                    payload = [
                        {"inline_data": {"mime_type": "audio/wav", "data": trans_audio.getvalue()}},
                        {"text": f"{SYSTEM_PROMPT}\nListen to this speech and execute the translation."}
                    ]
                else:
                    if not user_query.strip():
                        st.warning("Please enter text or record audio.")
                        st.stop()
                    payload = [{"text": user_query}]

                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{"role": "user", "parts": payload}],
                    config={"system_instruction": SYSTEM_PROMPT, "temperature": 0.2},
                )
                st.markdown(resp.text)
                
                # Audio playback for translated Sanskrit sentence
                if "संस्कृतम् (Devanagari):" in resp.text:
                    s_text = resp.text.split("संस्कृतम् (Devanagari):")[1].split("\n")[0].strip()
                    st.write("🔊 **उच्चारणम् (Pronunciation Audio):**")
                    play_sanskrit_audio(s_text)
            except Exception as e:
                st.error(f"Error: {str(e)}")


# =========================================================
# MODULE 2: VYAKARANA ENGINE (Grammar, Sandhi, Shabda/Dhatu)
# =========================================================
elif "Vyakarana Engine" in app_module:
    st.subheader("🧩 व्याकरण-विश्लेषकः (Sanskrit Grammar Engine)")
    
    vyakarana_tool = st.selectbox(
        "Select Tool / उपकरणम्",
        [
            "Sandhi Splitter & Joiner (सन्धि-विच्छेदः / सन्धि-कार्यम्)",
            "Shabdarupa Tables (शब्दरूपाणि - 8 Vibhaktis)",
            "Dhaturupa Conjugator (धातुरूपाणि - 10 Lakaras)",
            "Samasa & Vigraha Vakya (समास-विग्रहः)"
        ]
    )
    
    vyak_input = st.text_input("Enter Word / Root / Sentence (e.g. देवेशः / राम / गम् / पीताम्बरः):")
    
    if st.button("Analyze / विश्लेषणं कुरु"):
        if not api_key:
            st.warning("⚠️ Please enter your Gemini API key in the sidebar.")
            st.stop()
        if not vyak_input.strip():
            st.warning("Please enter a term to analyze.")
            st.stop()

        SYSTEM_PROMPT_VYAK = f"""You are "Panini AI", an expert computational Sanskrit grammarian.
Tool Selected: {vyakarana_tool}.
Proficiency Level: {level}.

Provide an exact, structured breakdown adhering to Paninian Ashtadhyayi rules:
1. Provide Sanskrit Sutra references (e.g. आद्गुणः ६.१.८७, इको यणचि ६.१.७७, etc.).
2. Use clear Markdown tables for 8 Vibhaktis (Prathama to Sambodhana in Ekavacana, Dvivacana, Bahuvacana) or Lakaras (Prathama, Madhyama, Uttama Purusha).
3. Provide IAST transliteration and English meanings for each form.
"""
        client = genai.Client(api_key=api_key)
        with st.spinner("व्याकरण-विश्लेषणं प्रचलति..."):
            try:
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{"role": "user", "parts": [{"text": f"Tool: {vyakarana_tool}\nInput: {vyak_input}"}]}],
                    config={"system_instruction": SYSTEM_PROMPT_VYAK, "temperature": 0.1},
                )
                st.markdown(resp.text)
            except Exception as e:
                st.error(f"Error: {str(e)}")


# =========================================================
# MODULE 3: PARIKSHA & DRILLS ENGINE (Quizzes & Tests)
# =========================================================
elif "Pariksha & Drills" in app_module:
    st.subheader("📝 संस्कृत-परीक्षा एवं अभ्यासः (Assessment Engine)")
    
    quiz_topic = st.selectbox(
        "Quiz Topic / विषयः",
        [
            "Vibhakti & Karaka Agreement (विभक्ति-अभ्यासः)",
            "Dhaturoopa & Lakara Tense Conjugation (धातुरूप-अभ्यासः)",
            "Sandhi Identification & Splitting (सन्धि-परीक्षा)",
            "Sentence Translation Challenges (अनुवाद-परीक्षा)"
        ]
    )
    
    if "current_quiz" not in st.session_state:
        st.session_state.current_quiz = None

    if st.button("⚡ Generate New Quiz / नूतन-प्रश्नावली"):
        if not api_key:
            st.warning("⚠️ Please enter your Gemini API key in the sidebar.")
            st.stop()

        SYSTEM_PROMPT_QUIZ = f"""You are "Acharya Parikshaka".
Generate an interactive Sanskrit quiz for Level: {level}.
Topic: {quiz_topic}.

Create 3 distinct questions.
For each question:
1. State the Question clearly in Devanagari, IAST, and English.
2. Provide 4 options (A, B, C, D).
3. Clearly mark the Correct Answer and provide a detailed grammatical explanation (Prakriti + Pratyaya / Sutra).

Format:
### प्रश्नः १: <Question>
- A) <Option 1>
- B) <Option 2>
- C) <Option 3>
- D) <Option 4>

**उत्तरम् (Correct Answer):** <Option Letter & Answer>
**स्पष्टीकरणम् (Explanation):** <Grammar explanation>
---
"""
        client = genai.Client(api_key=api_key)
        with st.spinner("प्रश्नावली निर्मीयते..."):
            try:
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{"role": "user", "parts": [{"text": f"Generate a 3-question test on {quiz_topic}"}]}],
                    config={"system_instruction": SYSTEM_PROMPT_QUIZ, "temperature": 0.3},
                )
                st.session_state.current_quiz = resp.text
            except Exception as e:
                st.error(f"Error: {str(e)}")

    if st.session_state.current_quiz:
        st.markdown(st.session_state.current_quiz)
