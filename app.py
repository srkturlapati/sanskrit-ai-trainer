import os
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate
from openai import OpenAI
import streamlit as st

# Mobile-friendly screen configuration
st.set_page_config(
    page_title="Sambhāṣaṇa AI",
    page_icon="🚩",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.title("🚩 सम्भाषणम् AI")
st.caption("सरल-संस्कृत-सम्भाषण-प्रशिक्षकः | Sanskrit AI Tutor")

# --- SIDEBAR: Settings & Keys ---
with st.sidebar:
    st.header("⚙️ Settings / विन्यासः")
    api_key = st.text_input(
        "OpenAI API Key",
        type="password",
        placeholder="sk-...",
        value=os.getenv("OPENAI_API_KEY", ""),
        help="Paste your OpenAI API key here to start chatting.",
    )
    level = st.selectbox(
        "Proficiency Level / स्तरः",
        ["Beginner (प्रथमा)", "Intermediate (मध्यमा)", "Advanced (उत्तमा)"],
        index=0,
    )
    if st.button("🔄 Reset Chat / पुनरारम्भः"):
        st.session_state.messages = []
        st.rerun()

# --- PEDAGOGICAL SYSTEM PROMPT ---
SYSTEM_PROMPT = f"""You are "Acharya AI" (आचार्यः), a pedagogical Sanskrit tutor specializing in Sarala Samskritam (सरल-संस्कृतम्).
Current Student Level: {level}.

Rules:
1. Converse naturally in simple Sanskrit suited to the level.
2. If the student makes a grammatical mistake (Vibhakti, Lakāra, Puruṣa mismatch, Sandhi):
   - Do NOT just hand over the answer.
   - Highlight the incorrect word gently.
   - Provide a Socratic hint or guiding question so they can self-correct.
3. Always format your output cleanly as:
[संस्कृतम्]: <Devanagari text>
[IAST]: <IAST transliteration>
[English]: <English meaning>
[मार्गदर्शनम्] (Include ONLY if the student made an error):
- 🔍 रूपम्: <Incorrect student word>
- 💡 सङ्केतः: <Guiding hint or rule>
"""

# --- CHAT SESSION INITIALIZATION ---
if "messages" not in st.session_state or len(st.session_state.messages) == 0:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "[संस्कृतम्]: हरिः ॐ! भवतः/भवत्याः नाम किम्?\n[IAST]: Hariḥ Om! Bhavataḥ/Bhavatyāḥ nāma kim?\n[English]: Hello! What is your name?",
        }
    ]

# Display conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- USER INPUT & SCRIPT TRANSLITERATION ---
if user_input := st.chat_input("Type in Devanagari or English (e.g., mama nama...)..."):
    if not api_key:
        st.warning("⚠️ Please open the sidebar (top-left arrow) and enter your OpenAI API key.")
        st.stop()

    client = OpenAI(api_key=api_key)

    # Convert Latin English/ITRANS input to Devanagari if not already in Devanagari
    is_devanagari = any("\u0900" <= char <= "\u097f" for char in user_input)
    if not is_devanagari:
        try:
            converted_dev = transliterate(user_input, sanscript.ITRANS, sanscript.DEVANAGARI)
            display_text = f"{user_input} ({converted_dev})"
        except Exception:
            display_text = user_input
    else:
        display_text = user_input

    # Add user message to UI
    st.session_state.messages.append({"role": "user", "content": display_text})
    with st.chat_message("user"):
        st.markdown(display_text)

    # Build payload for OpenAI
    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + [
        {"role": m["role"], "content": m["content"]} for m in st.session_state.messages
    ]

    # Generate response
    with st.chat_message("assistant"):
        with st.spinner("आचार्यः चिन्तयति..."):
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=api_messages,
                    temperature=0.3,
                )
                reply = response.choices[0].message.content
                st.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})
            except Exception as e:
                st.error(f"Error: {str(e)}")