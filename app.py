import sys
import os
import time

# Ensure UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from google import genai
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate
import streamlit as st

st.set_page_config(
    page_title="Universal Sanskrit AI Platform",
    page_icon="🚩",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.title("🚩 Sanskrit AI Platform (सम्भाषणम् & उभय-अनुवादकः)")
st.caption("Bidirectional Sanskrit Translator & Pedagogical Conversational Tutor")

# --- SIDEBAR: Configuration ---
with st.sidebar:
    st.header("⚙️ Configuration / विन्यासः")
    api_key = st.text_input(
        "Google Gemini API Key",
        type="password",
        placeholder="AIza...",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Get your free key at aistudio.google.com/apikey",
    )
    
    app_mode = st.radio(
        "Select Mode / कार्यपद्धतिः",
        [
            "🌐 Any Language ➔ Sanskrit (अन्यभाषा ➔ संस्कृतम्)",
            "📖 Sanskrit ➔ Any Language (संस्कृतम् ➔ अन्यभाषा)",
            "💬 Conversational Tutor (सम्भाषणम्)"
        ],
        index=0
    )
    
    level = st.selectbox(
        "Proficiency Level / स्तरः",
        [
            "Beginner (प्रथमा - Simple & Direct)",
            "Intermediate (मध्यमा - Tenses & Participles)",
            "Advanced (उत्तमा - Classical, Sandhi & Samasa)"
        ],
        index=0,
    )
    
    if "Sanskrit ➔ Any Language" in app_mode:
        target_lang = st.selectbox(
            "Translate Sanskrit Into / लक्ष्यभाषा",
            ["Telugu (తెలుగు)", "Hindi (हिन्दी)", "English", "Tamil (தமிழ்)", "Kannada (ಕನ್ನಡ)", "Marathi (मराठी)", "Malayalam (മലയാളം)", "Bengali (বাংলা)", "Gujarati (ગુજરાતી)"],
            index=0
        )
    
    if st.button("🔄 Reset Session / पुनरारम्भः"):
        st.session_state.messages = []
        st.rerun()

# --- SYSTEM PROMPT GENERATION ---
if "Any Language ➔ Sanskrit" in app_mode:
    SYSTEM_PROMPT = f"""You are "Acharya Anuvadaka" (अनुवादकः), an expert translator converting Indian and world languages into Sanskrit.
Target Level: {level}.

CRITICAL INSTRUCTIONS:
1. Output the FULL translated Sanskrit sentence first in both Devanagari and IAST.
2. Provide a clear word-by-word grammatical breakdown.

Output Format:
### 🪶 पूर्णवाक्यम् (Complete Sanskrit Sentence):
**संस्कृतम् (Devanagari):** <FULL TRANSLATED SENTENCE>
**IAST Transliteration:** <Sentence in IAST>
**English Meaning:** <Complete English translation>

---
### 🔍 व्याकरणम् एवं पदच्छेदः (Word-by-Word Analysis):
- **<Word>**: <Pratipadika/Dhatu> + <Vibhakti/Pratyaya> — <Meaning>
- **विशेष-नियमः (Key Rule applied)**: <Brief grammar note>
"""

elif "Sanskrit ➔ Any Language" in app_mode:
    SYSTEM_PROMPT = f"""You are "Acharya Vyakhyata" (व्याख्याता), an expert scholar translating and analyzing Sanskrit text into {target_lang}.

Target Explanation Level: {level}.

CRITICAL INSTRUCTIONS:
1. Accept Sanskrit input in Devanagari or Roman transliteration.
2. Perform Sandhi-viccheda (word splitting) if words are fused.
3. Provide the full, fluent translation in {target_lang} as well as in English.
4. Give a word-by-word Pratipadartha (प्रतिपदार्थः) table or list.

Output Format:
### 🎯 अनुवादः (Translation in {target_lang}):
**{target_lang}:** <Accurate, natural translation in {target_lang}>
**English:** <Fluent English translation>

---
### 📜 पदच्छेदः एवं प्रतिपदार्थः (Word-by-Word Breakdown):
- **<Sanskrit Word (पदम्)>**: <Meaning in {target_lang}> (<Grammar/Vibhakti tag>)
- **अन्वयः / तात्पर्यार्थः (Core Essence & Context)**: <Brief summary>
"""

else:
    SYSTEM_PROMPT = f"""You are "Acharya AI" (आचार्यः), a pedagogical Sanskrit tutor specializing in Sarala Samskritam.
Current Student Level: {level}.

Rules:
1. Converse naturally in simple Sanskrit suited to the level.
2. If student makes a grammatical error (Vibhakti, Lakara, Purusha, Sandhi):
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

# --- INITIALIZE MESSAGES ---
if "messages" not in st.session_state or len(st.session_state.messages) == 0:
    if "Any Language ➔ Sanskrit" in app_mode:
        init_text = "🚩 **अन्यभाषा ➔ संस्कृतम्**\nEnter any sentence in **Telugu, Hindi, English, Tamil, etc.** to get the complete Sanskrit translation and grammatical breakdown."
    elif "Sanskrit ➔ Any Language" in app_mode:
        init_text = f"🚩 **संस्कृतम् ➔ {target_lang}**\nEnter any Sanskrit sentence, śloka, or phrase to get its full translation in **{target_lang}** with word-by-word analysis."
    else:
        init_text = "[संस्कृतम्]: हरिः ॐ! भवतः/भवत्याः नाम किम्?\n[IAST]: Harih Om! Bhavatah/Bhavatyah nama kim?\n[English]: Hello! What is your name?",
    
    st.session_state.messages = [{"role": "model", "content": init_text}]

# Display chat history
for msg in st.session_state.messages:
    role = "assistant" if msg["role"] == "model" else "user"
    with st.chat_message(role):
        st.markdown(msg["content"])

# --- USER INPUT ---
if "Any Language ➔ Sanskrit" in app_mode:
    input_placeholder = "Type in Telugu, Hindi, English, etc. (e.g. నేను చదువుతున్నాను)..."
elif "Sanskrit ➔ Any Language" in app_mode:
    input_placeholder = "Type or paste Sanskrit text (e.g. सत्यमेव जयते नानृतम् / aham pathami)..."
else:
    input_placeholder = "Type in Sanskrit / English..."

if user_input := st.chat_input(input_placeholder):
    if not api_key:
        st.warning("⚠️ Please open the sidebar and enter your Gemini API key.")
        st.stop()

    client = genai.Client(api_key=api_key)

    # Transliterate for conversation mode
    if app_mode.startswith("💬"):
        is_devanagari = any("\u0900" <= char <= "\u097f" for char in user_input)
        if not is_devanagari:
            try:
                converted_dev = transliterate(user_input, sanscript.ITRANS, sanscript.DEVANAGARI)
                display_text = f"{user_input} ({converted_dev})"
            except Exception:
                display_text = user_input
        else:
            display_text = user_input
    else:
        display_text = user_input

    st.session_state.messages.append({"role": "user", "content": display_text})
    with st.chat_message("user"):
        st.markdown(display_text)

    # Prepare chat payload
    contents = []
    for m in st.session_state.messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": str(m["content"])}]})

    with st.chat_message("assistant"):
        with st.spinner("प्रक्रिया प्रचलति... (Processing...)"):
            reply = None
            last_err = None

            for attempt in range(3):
                try:
                    response = client.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=contents,
                        config={
                            "system_instruction": SYSTEM_PROMPT,
                            "temperature": 0.2,
                        },
                    )
                    reply = response.text
                    break
                except Exception as e:
                    last_err = e
                    time.sleep(1.5)

            if reply:
                st.markdown(reply)
                st.session_state.messages.append({"role": "model", "content": reply})
            else:
                st.error(f"Error: {str(last_err)}")
