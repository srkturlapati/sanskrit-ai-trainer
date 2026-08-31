import sys
import os

# Enforce UTF-8 encoding across the environment
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from google import genai
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate
import streamlit as st

# Mobile-friendly screen configuration
st.set_page_config(
    page_title="Sambhashana AI",
    page_icon="🚩",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.title("🚩 Sambhashanam AI (सम्भाषणम्)")
st.caption("Sarala Samskritam AI Tutor | सरल-संस्कृत-सम्भाषण-प्रशिक्षकः")

# Sidebar for settings
with st.sidebar:
    st.header("Settings / विन्यासः")
    api_key = st.text_input(
        "Google Gemini API Key",
        type="password",
        placeholder="AIza...",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Get your free key at aistudio.google.com/apikey",
    )
    level = st.selectbox(
        "Proficiency Level / स्तरः",
        ["Beginner (Prathama)", "Intermediate (Madhyama)", "Advanced (Uttama)"],
        index=0,
    )
    if st.button("Reset Chat / पुनरारम्भः"):
        st.session_state.messages = []
        st.rerun()

SYSTEM_PROMPT = f"""You are "Acharya AI" (आचार्यः), an expert, pedagogical Sanskrit tutor specializing in Sarala Samskritam (सरल-संस्कृतम्).
Current Student Level: {level}.

Rules:
1. Converse naturally in simple Sanskrit suited to the level.
2. If the student makes a grammatical mistake (Vibhakti, Lakara, Purusha mismatch, Sandhi):
   - Never dismiss them abruptly.
   - Highlight the incorrect word gently.
   - Provide a Socratic hint or guiding question so they can self-correct.
3. Always format your output cleanly as:
[Sanskrit]: <Devanagari text>
[IAST]: <IAST transliteration>
[English]: <English meaning>
[Margadarshanam] (Include ONLY if the student made an error):
- Error: <Incorrect student word>
- Hint: <Guiding hint or rule>
"""

# Initial greeting
if "messages" not in st.session_state or len(st.session_state.messages) == 0:
    st.session_state.messages = [
        {
            "role": "model",
            "content": "[Sanskrit]: हरिः ॐ! भवतः/भवत्याः नाम किम्?\n[IAST]: Harih Om! Bhavatah/Bhavatyah nama kim?\n[English]: Hello! What is your name?",
        }
    ]

# Display chat history
for msg in st.session_state.messages:
    role = "assistant" if msg["role"] == "model" else "user"
    with st.chat_message(role):
        st.markdown(msg["content"])

# User input handling
if user_input := st.chat_input("Type in Devanagari or English (e.g., mama nama...)..."):
    if not api_key:
        st.warning("⚠️ Please open the sidebar (top-left arrow) and enter your Gemini API key.")
        st.stop()

    client = genai.Client(api_key=api_key)

    # Convert Latin input to Devanagari if needed
    is_devanagari = any("\u0900" <= char <= "\u097f" for char in user_input)
    if not is_devanagari:
        try:
            converted_dev = transliterate(
                user_input, sanscript.ITRANS, sanscript.DEVANAGARI
            )
            display_text = f"{user_input} ({converted_dev})"
        except Exception:
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
        with st.spinner("Acharya is thinking..."):
            candidate_models = ["gemini-2.5-flash", "gemini-3.1-pro-preview"]
            reply = None
            last_error = None

            for model_name in candidate_models:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config={
                            "system_instruction": SYSTEM_PROMPT,
                            "temperature": 0.3,
                        },
                    )
                    reply = response.text
                    break
                except Exception as e:
                    last_error = e
                    continue

            if reply:
                st.markdown(reply)
                st.session_state.messages.append(
                    {"role": "model", "content": reply}
                )
            else:
                st.error(f"Error: {str(last_error)}")
