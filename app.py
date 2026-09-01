import sys
import os
import time
import io
import hashlib

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

# TalkPal Mobile & Desktop Layout
st.set_page_config(
    page_title="TalkPal Sanskrit AI",
    page_icon="🗣️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- MODERN TALKPAL UI STYLING ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    
    /* Top Mode Navigation Pills */
    .stRadio [role="radiogroup"] {
        background: #F1F5F9;
        padding: 6px;
        border-radius: 16px;
        display: flex;
        gap: 8px;
        justify-content: center;
        border: 1px solid #E2E8F0;
    }
    .stRadio [role="radiogroup"] label {
        background: transparent;
        border-radius: 12px;
        padding: 6px 14px;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    
    /* TalkPal Tutor Message Bubble */
    .talkpal-bubble-ai {
        background: linear-gradient(135deg, #F8FAFC 0%, #EFF6FF 100%);
        border: 1px solid #DBEAFE;
        border-left: 5px solid #4F46E5;
        border-radius: 16px;
        padding: 16px 20px;
        margin-bottom: 14px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }
    
    /* TalkPal User Message Bubble */
    .talkpal-bubble-user {
        background: #F0FDF4;
        border: 1px solid #DCFCE7;
        border-left: 5px solid #16A34A;
        border-radius: 16px;
        padding: 14px 18px;
        margin-bottom: 14px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.03);
    }

    /* Feedback Pill Badge */
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
    
    /* Permanent Voice Recording Dock */
    .voice-dock {
        background: #FFFFFF;
        border: 2px solid #6366F1;
        border-radius: 16px;
        padding: 12px 18px;
        margin-top: 15px;
        margin-bottom: 10px;
        box-shadow: 0 10px 15px -3px rgba(99, 102, 241, 0.1);
    }
</style>
""", unsafe_allow_html=True)

# Helper: Sanskrit Audio Player (TTS) with TalkPal Slow/Normal Speed
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

# --- SESSION STATES ---
if "xp" not in st.session_state:
    st.session_state.xp = 180
if "streak" not in st.session_state:
    st.session_state.streak = 5
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "active_mode_key" not in st.session_state:
    st.session_state.active_mode_key = "💬 Chat"
if "last_processed_audio_hash" not in st.session_state:
    st.session_state.last_processed_audio_hash = ""

# --- SIDEBAR: Profile, Settings & Rate Limiter ---
with st.sidebar:
    st.title("🗣️ TalkPal Sanskrit")
    st.caption("AI Spoken Sanskrit Companion • सम्भाषणम्")
    
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
    st.subheader("⚙️ TalkPal Audio Controls")
    audio_speed = st.radio("Pronunciation Speed", ["Normal (सामान्यम्)", "Slow (मन्दम्)"], index=0)
    is_slow = audio_speed.startswith("Slow")
    
    st.write("---")
    st.markdown("### 🏆 Your Fluency Stats")
    c1, c2 = st.columns(2)
    c1.metric("🔥 Streak", f"{st.session_state.streak} Days")
    c2.metric("⭐ Points", f"{st.session_state.xp} XP")
    
    st.progress(0.70, text="Daily Speaking Goal: 70%")
    
    st.write("---")
    if st.button("🔄 Clear Active Session"):
        st.session_state.chat_history = []
        st.session_state.last_processed_audio_hash = ""
        st.rerun()

# --- TOP NAVIGATION: 5 TALKPAL MODES ---
selected_mode = st.radio(
    "Select Mode",
    ["💬 Chat", "🎭 Roleplays", "🔥 Debates", "📸 Photo Mode", "🧩 Custom Mode"],
    horizontal=True,
    label_visibility="collapsed"
)

if selected_mode != st.session_state.active_mode_key:
    st.session_state.chat_history = []
    st.session_state.last_processed_audio_hash = ""
    st.session_state.active_mode_key = selected_mode
    st.rerun()

# Safe API caller with automatic exponential backoff for 429 errors
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
                sleep_time = 4 * (attempt + 1)
                time.sleep(sleep_time)
                continue
            return None, err_str
    return None, "Rate limit reached. Please wait 15 seconds before speaking again."

# Mode system instructions
if selected_mode == "💬 Chat":
    mode_title = "💬 Free Chat with TalkPal Tutor"
    mode_caption = "Converse freely in spoken Sanskrit. TalkPal analyzes your speech, translates, and offers real-time improvements."
    system_instruction = f"""You are the TalkPal AI Sanskrit Tutor. Student Level: {level}.
Always format your response cleanly as:
[संस्कृतम्]: <Conversational Sanskrit reply>
[IAST]: <Romanized transliteration>
[English]: <English meaning>
[💡 TalkPal Feedback]:
- 🔍 Grammatical Correction: <Point out any Vibhakti/Lakara/Sandhi error, or state 'निर्दोषम् (Perfect!)'>
- ✨ Better Way to Say: <An idiomatic, native-like alternative phrase>
- 📖 Key Vocabulary: <1-2 words from the reply with root/meaning>
"""
    initial_greeting = "[संस्कृतम्]: हरिः ॐ! अद्य भवान्/भवती कीदृशं विषयम् अधिकृत्य सम्भाषणं कर्तुम् इच्छति?\n[IAST]: Hariḥ Om! Adya bhavān/bhavatī kīdṛśaṁ viṣayam adhikṛtya sambhāṣaṇaṁ kartum icchati?\n[English]: Hello! What topic would you like to talk about today?\n[💡 TalkPal Feedback]:\n- 🔍 Grammatical Correction: निर्दोषम् (Ready to converse!)\n- ✨ Better Way to Say: Welcome to TalkPal Chat!\n- 📖 Key Vocabulary: विषयम् (viṣayam - topic)"

elif selected_mode == "🎭 Roleplays":
    mode_title = "🎭 Situational Roleplay"
    mode_caption = "Practice real-life missions (Market, Hotel, Gurukula, Travel)."
    system_instruction = f"""You are an immersive situational AI character in Spoken Sanskrit. Student Level: {level}.
Keep the dialogue active and ask a question to continue the mission. Format:
[संस्कृतम्]: <In-character Sanskrit speech>
[IAST]: <Transliteration>
[English]: <Translation>
[🎯 Mission Hint]: <What to say next to advance the conversation>
"""
    initial_greeting = "[संस्कृतम्]: नमस्ते! विपणिं प्रति स्वागतम्। भवते/भवत्यै किं फलं वा शाकं रोचते?\n[IAST]: Namaste! Vipaṇiṁ prati svāgatam. Bhavate/bhavatyai kiṁ phalaṁ vā śākaṁ rocate?\n[English]: Greetings! Welcome to the market. Which fruit or vegetable would you like?\n[🎯 Mission Hint]: Ask for the price of fruits (e.g., phalasya mūlyaṁ kim?)."

elif selected_mode == "🔥 Debates":
    mode_title = "🔥 TalkPal Debate Club (शास्त्रार्थः)"
    mode_caption = "Sharpen your spoken argumentation. Defend your point in Sanskrit."
    system_instruction = f"""You are a master Sanskrit debater. Student Level: {level}.
Politely challenge the student's argument. Format:
[संस्कृतम्]: <Debate rebuttal>
[IAST]: <Transliteration>
[English]: <Translation>
[🔥 Counter Challenge]: <Question challenging their logic>
"""
    initial_greeting = "[संस्कृतम्]: अस्मिन् शास्त्रार्थे भवतः स्वागतम्। वदतु, आधुनिक-शिक्षण-पद्धतिः श्रेष्ठा वा पारम्परिकी गुरुकुल-पद्धतिः?\n[IAST]: Asmin śāstrārthe bhavataḥ svāgatam. Vadatu, ādhunika-śikṣaṇa-paddhatiḥ śreṣṭhā vā pārampārikī gurukula-paddhatiḥ?\n[English]: Welcome to the debate. Tell me, is the modern education system better or traditional Gurukula?\n[🔥 Counter Challenge]: State your position with one clear reason."

else:
    mode_title = f"{selected_mode} Simulation"
    mode_caption = "Interactive spoken Sanskrit practice."
    system_instruction = f"You are TalkPal Sanskrit Tutor for level {level}. Converse in simple Sanskrit."
    initial_greeting = "[संस्कृतम्]: हरिः ॐ! वदतु, कथम् अस्ति?\n[IAST]: Hariḥ Om! Vadatu, katham asti?\n[English]: Hello! Tell me, how are you?"

if len(st.session_state.chat_history) == 0:
    st.session_state.chat_history = [{"role": "model", "content": initial_greeting}]

st.subheader(mode_title)
st.caption(mode_caption)

# --- DISPLAY CHAT HISTORY WITH TALKPAL CARDS ---
for msg in st.session_state.chat_history:
    if msg["role"] == "model":
        st.markdown('<div class="talkpal-bubble-ai"><span class="talkpal-pill">🤖 TalkPal Tutor</span>', unsafe_allow_html=True)
        st.markdown(msg["content"])
        st.markdown('</div>', unsafe_allow_html=True)
        
        if "[संस्कृतम्]:" in msg["content"]:
            line = msg["content"].split("[संस्कृतम्]:")[1].split("\n")[0].strip()
            play_sanskrit_audio(line, slow_mode=is_slow)
    else:
        st.markdown('<div class="talkpal-bubble-user"><span class="talkpal-pill" style="background:#DCFCE7; color:#15803D;">👤 You</span>', unsafe_allow_html=True)
        st.markdown(msg["content"])
        st.markdown('</div>', unsafe_allow_html=True)

# --- PERMANENT VOICE DOCK (WITH DEBOUNCE CACHE TO STOP 429) ---
st.markdown('<div class="voice-dock">', unsafe_allow_html=True)
st.markdown("🎙️ **Tap the Mic to Speak your Reply / वदतु (Voice Reply):**")
audio_reply = st.audio_input("Record your spoken reply:", key=f"rec_dock_{len(st.session_state.chat_history)}")
st.markdown('</div>', unsafe_allow_html=True)

# Process Audio Only Once Per Recording (Prevents 429 loops)
if audio_reply is not None:
    audio_bytes = audio_reply.getvalue()
    audio_hash = hashlib.md5(audio_bytes).hexdigest()

    if audio_hash != st.session_state.last_processed_audio_hash:
        st.session_state.last_processed_audio_hash = audio_hash

        if not api_key:
            st.warning("⚠️ Please enter your Gemini API key in the sidebar.")
            st.stop()

        client = genai.Client(api_key=api_key)
        st.session_state.chat_history.append({"role": "user", "content": "🎙️ *[Spoken Voice Response]*"})
        st.session_state.xp += 15

        with st.spinner("TalkPal is listening and evaluating..."):
            reply, err = call_gemini_safe(
                client=client,
                model="gemini-3.6-flash",
                contents=[{
                    "role": "user",
                    "parts": [
                        {"inline_data": {"mime_type": "audio/wav", "data": audio_bytes}},
                        {"text": f"{system_instruction}\nListen to the student's spoken audio, transcribe what they said, reply in Sanskrit with translation, and provide grammatical feedback."}
                    ]
                }],
                system_instruction=system_instruction
            )
            if reply:
                st.session_state.chat_history.append({"role": "model", "content": reply})
                st.rerun()
            else:
                st.error(f"⚠️ {err}")

# --- TEXT INPUT (ALTERNATIVE) ---
if text_input := st.chat_input("Or type here in Sanskrit or English (e.g. mama nama, aham pathami...)..."):
    if not api_key:
        st.warning("⚠️ Please enter your Gemini API key in the sidebar.")
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

    contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": str(m["content"])}]} for m in st.session_state.chat_history]

    with st.spinner("TalkPal is typing..."):
        reply, err = call_gemini_safe(
            client=client,
            model="gemini-3.6-flash",
            contents=contents,
            system_instruction=system_instruction
        )
        if reply:
            st.session_state.chat_history.append({"role": "model", "content": reply})
            st.rerun()
        else:
            st.error(f"⚠️ {err}")
