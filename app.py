import sys
import os
import time
import io
import hashlib

# Enforce UTF-8 encoding across environments
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
    page_title="संस्कृतेन सम्भाषणं कुरु • Sambhāṣaṇa AI",
    page_icon="🚩",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom UI Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        border-bottom: 2px solid #E2E8F0;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        border-radius: 12px 12px 0px 0px;
        font-size: 15px;
        font-weight: 700;
        padding: 8px 20px;
    }
    .talkpal-bubble-ai {
        background: linear-gradient(135deg, #F8FAFC 0%, #EFF6FF 100%);
        border: 1px solid #DBEAFE;
        border-left: 5px solid #4F46E5;
        border-radius: 16px;
        padding: 16px 20px;
        margin-bottom: 12px;
    }
    .talkpal-bubble-user {
        background: #F0FDF4;
        border: 1px solid #DCFCE7;
        border-left: 5px solid #16A34A;
        border-radius: 16px;
        padding: 14px 18px;
        margin-bottom: 12px;
    }
    .voice-dock {
        background: #FFFFFF;
        border: 2px solid #6366F1;
        border-radius: 16px;
        padding: 14px 20px;
        margin: 12px 0px;
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

# Helper: Sanskrit Audio Player (TTS)
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
def call_gemini_safe(client, model, contents, system_instruction=""):
    for attempt in range(4):
        try:
            config = {"temperature": 0.2}
            if system_instruction:
                config["system_instruction"] = system_instruction
            resp = client.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )
            return resp.text, None
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                time.sleep(3 * (attempt + 1))
                continue
            return None, err_str
    return None, "Rate limit reached. Please wait 15 seconds before trying again."

# --- SESSION STATES ---
if "xp" not in st.session_state:
    st.session_state.xp = 350
if "streak" not in st.session_state:
    st.session_state.streak = 7
if "talkpal_history" not in st.session_state:
    st.session_state.talkpal_history = []
if "tp_mode" not in st.session_state:
    st.session_state.tp_mode = "💬 Free Chat"
if "last_audio_hash" not in st.session_state:
    st.session_state.last_audio_hash = ""
if "active_quiz_data" not in st.session_state:
    st.session_state.active_quiz_data = None

# --- SIDEBAR: Profile & Controls ---
with st.sidebar:
    st.title("🚩 संस्कृतेन सम्भाषणं कुरु")
    st.caption("AI Sanskrit Spoken Coach & Vedic Knowledge Portal")
    
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
    st.subheader("🏆 Gamification Stats")
    c1, c2 = st.columns(2)
    c1.metric("🔥 Streak", f"{st.session_state.streak} Days")
    c2.metric("⭐ Points", f"{st.session_state.xp} XP")
    st.caption("🎖️ Level: **साधकः (Seeker)** • Next Rank: **विद्वान् (Scholar)** at 500 XP")
    
    st.write("---")
    audio_speed = st.radio("Sanskrit Pronunciation Speed", ["Normal (सामान्यम्)", "Slow (मन्दम्)"], index=0)
    is_slow = audio_speed.startswith("Slow")
    
    if st.button("🔄 Reset Active Chat"):
        st.session_state.talkpal_history = []
        st.session_state.last_audio_hash = ""
        st.rerun()

# --- MASTER TOP TABS ---
tab_talkpal, tab_amara, tab_rupa, tab_chandas, tab_trans, tab_vedic = st.tabs([
    "🗣️ 1. संस्कृतेन सम्भाषणं कुरु",
    "📖 2. Amarakoṣa",
    "🧩 3. Śabda & Dhātu",
    "🎵 4. Chandaḥ Śāstra",
    "🌐 5. Translation",
    "🏹 6. Vedic & Itihāsa Quiz"
])


# ==============================================================================
# TAB 1: संस्कृतेन सम्भाषणं कुरु (SPOKEN SANSKRIT ENGINE)
# ==============================================================================
with tab_talkpal:
    st.subheader("🗣️ संस्कृतेन सम्भाषणं कुरु (Speak in Sanskrit)")
    st.caption("Oral-first speaking tutor with automatic correction and feedback.")

    tp_mode = st.radio(
        "Select Mode",
        ["💬 Free Chat", "🎭 Situational Roleplay", "🔥 Debate Club", "📸 Photo Mode", "🧩 Custom Mode"],
        horizontal=True
    )
    
    if tp_mode != st.session_state.tp_mode:
        st.session_state.talkpal_history = []
        st.session_state.last_audio_hash = ""
        st.session_state.tp_mode = tp_mode
        st.rerun()

    sys_talkpal = f"""You are the 'संस्कृतेन सम्भाषणं कुरु' AI Sanskrit Tutor (आचार्यः). Student Level: {level}.
Always format output strictly as:
[संस्कृतम्]: <Conversational Sanskrit reply>
[IAST]: <Romanized transliteration>
[English]: <English meaning>
[💡 सम्भाषण-मार्गदर्शनम् (Feedback)]:
- 🔍 रूपम् / दोषः: <Error note or 'निर्दोषम् (Perfect!)'>
- ✨ वरतर-प्रयोगः (Better Way to Say): <Idiomatic alternative>
- 📖 मुख्यशब्दाः (Key Vocabulary): <1-2 words with meaning>
"""

    if len(st.session_state.talkpal_history) == 0:
        st.session_state.talkpal_history = [{
            "role": "model",
            "content": "[संस्कृतम्]: हरिः ॐ! संस्कृतेन सम्भाषणं कुरु। अद्य भवान्/भवती कीदृशं विषयम् अधिकृत्य सम्भाषणं कर्तुम् इच्छति?\n[IAST]: Hariḥ Om! Saṁskṛtena sambhāṣaṇaṁ kuru. Adya bhavān/bhavatī kīdṛśaṁ viṣayam adhikṛtya sambhāṣaṇaṁ kartum icchati?\n[English]: Hello! Speak in Sanskrit. What topic would you like to speak about today?\n[💡 सम्भाषण-मार्गदर्शनम् (Feedback)]:\n- 🔍 रूपम् / दोषः: निर्दोषम् (Ready!)\n- ✨ वरतर-प्रयोगः: शुभ-आरम्भः भवतु!\n- 📖 मुख्यशब्दाः: सम्भाषणम् (conversation)"
        }]

    for msg in st.session_state.talkpal_history:
        if msg["role"] == "model":
            st.markdown('<div class="talkpal-bubble-ai"><span style="font-weight:700; color:#4F46E5;">🤖 आचार्यः (Sanskrit AI)</span>', unsafe_allow_html=True)
            st.markdown(msg["content"])
            st.markdown('</div>', unsafe_allow_html=True)
            if "[संस्कृतम्]:" in msg["content"]:
                line = msg["content"].split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                play_sanskrit_audio(line, slow_mode=is_slow)
        else:
            st.markdown('<div class="talkpal-bubble-user"><span style="font-weight:700; color:#15803D;">👤 You</span>', unsafe_allow_html=True)
            st.markdown(msg["content"])
            st.markdown('</div>', unsafe_allow_html=True)

    # Permanent Voice Recording Dock
    st.markdown('<div class="voice-dock">', unsafe_allow_html=True)
    st.markdown("🎙️ **Tap the Mic to Speak / वदतु (संस्कृतेन वदतु):**")
    audio_reply = st.audio_input("Record voice reply:", key=f"tp_rec_{len(st.session_state.talkpal_history)}")
    st.markdown('</div>', unsafe_allow_html=True)

    if audio_reply is not None:
        audio_bytes = audio_reply.getvalue()
        audio_hash = hashlib.md5(audio_bytes).hexdigest()

        if audio_hash != st.session_state.last_audio_hash:
            st.session_state.last_audio_hash = audio_hash
            if not api_key:
                st.warning("⚠️ Enter your Gemini API key in the sidebar.")
                st.stop()
            client = genai.Client(api_key=api_key)
            st.session_state.talkpal_history.append({"role": "user", "content": "🎙️ *[Spoken Voice Response]*"})
            st.session_state.xp += 15

            with st.spinner("आचार्यः शृणोति एवं चिन्तयति..."):
                reply, err = call_gemini_safe(
                    client=client,
                    model="gemini-3.6-flash",
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": audio_bytes}},
                            {"text": f"{sys_talkpal}\nTranscribe spoken audio, reply in Sanskrit with translation and feedback."}
                        ]
                    }],
                    system_instruction=sys_talkpal
                )
                if reply:
                    st.session_state.talkpal_history.append({"role": "model", "content": reply})
                    st.rerun()
                else:
                    st.error(f"⚠️ {err}")

    if text_input := st.chat_input("Or type in Sanskrit / English (e.g. mama nama, aham pathami...)..."):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key in the sidebar.")
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

        with st.spinner("आचार्यः लिखति..."):
            reply, err = call_gemini_safe(client, "gemini-3.6-flash", contents, sys_talkpal)
            if reply:
                st.session_state.talkpal_history.append({"role": "model", "content": reply})
                st.rerun()
            else:
                st.error(f"⚠️ {err}")


# ==============================================================================
# TAB 2: AMARAKOṢA EXPLORER
# ==============================================================================
with tab_amara:
    st.subheader("📖 नामलिङ्गानुशासनम् (अमरकोशः)")
    st.caption("Explore traditional Sanskrit thesaurus synonyms, gender markers, and authentic kāṇḍa verses.")

    col_am1, col_am2 = st.columns([1, 1])
    with col_am1:
        amara_query = st.text_input("Enter Word or Concept (e.g., सूर्यः, अग्निः, चन्द्रः, जलम्, अश्वः):", value="सूर्यः")
    with col_am2:
        kanda_choice = st.selectbox("Search Scope / काण्डम्:", ["All (सर्वम्)", "प्रथमकाण्डम् (Heaven, Time, Devas)", "द्वितीयकाण्डम् (Earth, Cities, Forests)", "तृतीयकाण्डम् (General, Synonyms, Genders)"])

    if st.button("🔍 Explore Amarakoṣa / अन्वेषणं कुरु"):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key in sidebar.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("अमरकोश-श्लोकाः अन्विष्यन्ते..."):
            PROMPT_AMARA = f"""You are an authentic Sanskrit scholar of Amarakoṣa (नामलिङ्गानुशासनम् by Amarasimha).
Query: {amara_query}
Scope: {kanda_choice}

Output Format:
### 📜 अमरकोश-मूलश्लोकः (Original Verse):
```sanskrit
<Original Amarakoṣa Devanagari in verse>
