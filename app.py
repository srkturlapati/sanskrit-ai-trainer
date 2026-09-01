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

# --- ADVANCED DEDICATED COLOR PALETTES FOR EACH TAB ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&family=Noto+Sans+Devanagari:wght@400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', 'Noto Sans Devanagari', sans-serif;
    }

    /* Master Tabs Navigation Bar */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 2px solid #CBD5E1;
        padding-bottom: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 52px;
        border-radius: 12px 12px 0px 0px;
        font-size: 15px;
        font-weight: 700;
        padding: 8px 18px;
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        color: #475569;
        transition: all 0.2s ease-in-out;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1E293B !important;
        color: #FFFFFF !important;
        border-color: #1E293B !important;
    }

    /* TAB 1: ROYAL INDIGO (Spoken Engine) */
    .tab1-container {
        background: linear-gradient(180deg, #EEF2FF 0%, #E0E7FF 100%);
        border: 2px solid #6366F1;
        border-radius: 20px;
        padding: 24px;
        margin-bottom: 20px;
        color: #1E1B4B;
    }
    .tab1-bubble-ai {
        background: #FFFFFF;
        border-left: 6px solid #4F46E5;
        border-radius: 14px;
        padding: 16px 20px;
        margin-bottom: 12px;
        box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.08);
        color: #1E1B4B;
    }
    .tab1-bubble-user {
        background: #DCFCE7;
        border-left: 6px solid #16A34A;
        border-radius: 14px;
        padding: 14px 18px;
        margin-bottom: 12px;
        color: #14532D;
    }
    .tab1-voice-dock {
        background: #FFFFFF;
        border: 2px dashed #4F46E5;
        border-radius: 16px;
        padding: 16px 20px;
        margin-top: 14px;
        margin-bottom: 14px;
    }

    /* TAB 2: VEDIC SAFFRON & AMBER (Amarakoṣa) */
    .tab2-container {
        background: linear-gradient(180deg, #FFFBEB 0%, #FEF3C7 100%);
        border: 2px solid #F59E0B;
        border-radius: 20px;
        padding: 24px;
        margin-bottom: 20px;
        color: #78350F;
    }
    .tab2-card {
        background: #FFFFFF;
        border-left: 6px solid #D97706;
        border-radius: 14px;
        padding: 18px 22px;
        margin-top: 14px;
        box-shadow: 0 4px 6px -1px rgba(217, 119, 6, 0.08);
        color: #451A03;
    }

    /* TAB 3: EMERALD SAGE (Śabda & Dhātu) */
    .tab3-container {
        background: linear-gradient(180deg, #F0FDF4 0%, #DCFCE7 100%);
        border: 2px solid #22C55E;
        border-radius: 20px;
        padding: 24px;
        margin-bottom: 20px;
        color: #064E3B;
    }
    .tab3-card {
        background: #FFFFFF;
        border-left: 6px solid #16A34A;
        border-radius: 14px;
        padding: 18px 22px;
        margin-top: 14px;
        box-shadow: 0 4px 6px -1px rgba(22, 163, 74, 0.08);
        color: #064E3B;
    }

    /* TAB 4: LOTUS ROSE (Chandaḥ Śāstra) */
    .tab4-container {
        background: linear-gradient(180deg, #FFF1F2 0%, #FFE4E6 100%);
        border: 2px solid #F43F5E;
        border-radius: 20px;
        padding: 24px;
        margin-bottom: 20px;
        color: #881337;
    }
    .tab4-card {
        background: #FFFFFF;
        border-left: 6px solid #E11D48;
        border-radius: 14px;
        padding: 18px 22px;
        margin-top: 14px;
        box-shadow: 0 4px 6px -1px rgba(225, 29, 72, 0.08);
        color: #881337;
    }

    /* TAB 5: OCEAN CYAN (Universal Translation) */
    .tab5-container {
        background: linear-gradient(180deg, #ECFEFF 0%, #CFFAFE 100%);
        border: 2px solid #06B6D4;
        border-radius: 20px;
        padding: 24px;
        margin-bottom: 20px;
        color: #164E63;
    }
    .tab5-card {
        background: #FFFFFF;
        border-left: 6px solid #0891B2;
        border-radius: 14px;
        padding: 18px 22px;
        margin-top: 14px;
        box-shadow: 0 4px 6px -1px rgba(8, 145, 178, 0.08);
        color: #164E63;
    }

    /* TAB 6: SACRED GOLDEN ORANGE (Vedic & Epics Quiz) */
    .tab6-container {
        background: linear-gradient(180deg, #FFF7ED 0%, #FFEDD5 100%);
        border: 2px solid #F97316;
        border-radius: 20px;
        padding: 24px;
        margin-bottom: 20px;
        color: #7C2D12;
    }
    .tab6-card {
        background: #FFFFFF;
        border-left: 6px solid #EA580C;
        border-radius: 14px;
        padding: 18px 22px;
        margin-top: 14px;
        box-shadow: 0 4px 6px -1px rgba(234, 88, 12, 0.08);
        color: #7C2D12;
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

# Safe API caller with exponential backoff
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
    audio_speed = st.radio("Pronunciation Speed", ["Normal (सामान्यम्)", "Slow (मन्दम्)"], index=0)
    is_slow = audio_speed.startswith("Slow")
    
    if st.button("🔄 Reset Active Chat"):
        st.session_state.talkpal_history = []
        st.session_state.last_audio_hash = ""
        st.rerun()

# --- TOP MASTER NAVIGATION TABS ---
tab_talkpal, tab_amara, tab_rupa, tab_chandas, tab_trans, tab_vedic = st.tabs([
    "🗣️ 1. संस्कृतेन सम्भाषणं कुरु",
    "📖 2. Amarakoṣa",
    "🧩 3. Śabda & Dhātu",
    "🎵 4. Chandaḥ Śāstra",
    "🌐 5. Translation",
    "🏹 6. Vedic & Itihāsa Quiz"
])


# ==============================================================================
# TAB 1: संस्कृतेन सम्भाषणं कुरु (ROYAL INDIGO THEME)
# ==============================================================================
with tab_talkpal:
    st.markdown('<div class="tab1-container">', unsafe_allow_html=True)
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
            st.markdown('<div class="tab1-bubble-ai"><span style="font-weight:700; color:#4F46E5;">🤖 आचार्यः (Sanskrit AI)</span>', unsafe_allow_html=True)
            st.markdown(msg["content"])
            st.markdown('</div>', unsafe_allow_html=True)
            if "[संस्कृतम्]:" in msg["content"]:
                line = msg["content"].split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                play_sanskrit_audio(line, slow_mode=is_slow)
        else:
            st.markdown('<div class="tab1-bubble-user"><span style="font-weight:700; color:#15803D;">👤 You</span>', unsafe_allow_html=True)
            st.markdown(msg["content"])
            st.markdown('</div>', unsafe_allow_html=True)

    # Permanent Voice Recording Dock
    st.markdown('<div class="tab1-voice-dock">', unsafe_allow_html=True)
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
    st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 2: AMARAKOṢA (VEDIC SAFFRON THEME)
# ==============================================================================
with tab_amara:
    st.markdown('<div class="tab2-container">', unsafe_allow_html=True)
    st.subheader("📖 नामलिङ्गानुशासनम् (अमरकोशः)")
    st.caption("Traditional Sanskrit thesaurus synonyms, gender markers, and authentic kāṇḍa verses.")

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
            prompt_amara = (
                "You are an authentic Sanskrit scholar of Amarakoṣa (नामलिङ्गानुशासनम् by Amarasimha).\n"
                f"Query: {amara_query}\n"
                f"Scope: {kanda_choice}\n\n"
                "Output Format:\n"
                "### 📜 अमरकोश-मूलश्लोकः (Original Verse):\n"
                "<Quote the authentic Amarakoṣa verse in Devanagari>\n\n"
                "### 💎 पर्यायपदानि (Synonyms & Meaning):\n"
                "- List all synonyms for the query word.\n"
                "- For each word provide: Devanagari, IAST, Gender (पुंल्लिङ्ग / स्त्रीलिङ्ग / नपुंसकलिङ्ग), and English meaning.\n\n"
                "### 🏷️ काण्डम् एवं वर्गः (Taxonomy):\n"
                "- State the Kāṇḍa and Varga (e.g., स्वर्गवर्गः, दिग्वर्गः, भूमिवर्गः)."
            )
            resp, err = call_gemini_safe(client, "gemini-3.6-flash", [{"role": "user", "parts": [{"text": prompt_amara}]}])
            if resp:
                st.markdown('<div class="tab2-card">', unsafe_allow_html=True)
                st.markdown(resp)
                st.markdown('</div>', unsafe_allow_html=True)
                st.session_state.xp += 10
            else:
                st.error(f"Error: {err}")
    st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 3: ŚABDA & DHĀTURŪPA (EMERALD SAGE THEME)
# ==============================================================================
with tab_rupa:
    st.markdown('<div class="tab3-container">', unsafe_allow_html=True)
    st.subheader("🧩 शब्दरूपाणि एवं धातुरूपाणि (Noun & Verb Engines)")
    st.caption("Complete 8-case declension charts, 10-lakāra verb conjugation tables, and identification drills.")

    rupa_type = st.radio("Choose Engine:", ["📜 Shabdarupa (Noun Declension)", "⚡ Dhaturoopa (Verb Conjugation)", "🎯 Rupa Identification Drill"], horizontal=True)

    if rupa_type == "📜 Shabdarupa (Noun Declension)":
        shabda_in = st.text_input("Enter Noun / Prātipadika (e.g., राम, लता, फल, हरि, नदी, मति, पितृ):", value="राम")
        if st.button("Generate 8 Vibhaktis"):
            if not api_key:
                st.warning("⚠️ Enter Gemini API key.")
                st.stop()
            client = genai.Client(api_key=api_key)
            with st.spinner("Generating declension table..."):
                p = f"""Generate full 8 Vibhakti table for Sanskrit noun '{shabda_in}'.
Format as Markdown Table with columns:
| विभक्तिः (Case) | एकवचनम् (Singular) | द्विवचनम् (Dual) | बहुवचनम् (Plural) | English Meaning |
State the Pratipadika, Gender, and Ending vowel (e.g., अकारान्त-पुंल्लिङ्गः)."""
                resp, err = call_gemini_safe(client, "gemini-3.6-flash", [{"role": "user", "parts": [{"text": p}]}])
                if resp:
                    st.markdown('<div class="tab3-card">', unsafe_allow_html=True)
                    st.markdown(resp)
                    st.markdown('</div>', unsafe_allow_html=True)

    elif rupa_type == "⚡ Dhaturoopa (Verb Conjugation)":
        dhatu_in = st.text_input("Enter Root / Dhātu (e.g., गम्, भू, पठ्, कृ, स्था, दृश्):", value="गम्")
        lakara_in = st.selectbox("Select Lakāra / Tense:", ["लट् (Present - वर्तमाने)", "लङ् (Past - अनद्यतने भूते)", "लृट् (Future - भविष्यति)", "लोट् (Imperative - आज्ञायाम्)", "विधिलिङ् (Optative - सम्भाषणे)"])
        if st.button("Generate Lakāra Conjugation"):
            if not api_key:
                st.warning("⚠️ Enter Gemini API key.")
                st.stop()
            client = genai.Client(api_key=api_key)
            with st.spinner("Generating conjugation table..."):
                p = f"""Generate conjugation table for Dhatu '{dhatu_in}' in '{lakara_in}'.
Provide:
1. Gana, Pada (Parasmaipada/Atmanepada), Root meaning.
2. Markdown Table with columns:
| पुरुषः (Person) | एकवचनम् | द्विवचनम् | बहुवचनम् | English Meaning |
(प्रथमपुरुषः, मध्यमपुरुषः, उत्तमपुरुषः)"""
                resp, err = call_gemini_safe(client, "gemini-3.6-flash", [{"role": "user", "parts": [{"text": p}]}])
                if resp:
                    st.markdown('<div class="tab3-card">', unsafe_allow_html=True)
                    st.markdown(resp)
                    st.markdown('</div>', unsafe_allow_html=True)

    else:
        st.write("🎯 **Test Your Form Identification Skills:**")
        if st.button("⚡ Generate New Identification Challenge"):
            if not api_key:
                st.warning("⚠️ Enter Gemini API key.")
                st.stop()
            client = genai.Client(api_key=api_key)
            with st.spinner("Generating challenge..."):
                p = """Give a single Sanskrit word form (e.g., 'रामेभ्यः' or 'अभवन्'). Ask the student to identify:
1. Base root/pratipadika
2. Vibhakti + Vacana OR Lakara + Purusha + Vacana
Provide 4 multiple-choice options (A, B, C, D) followed by an expandable spoiler with the correct answer and Paninian explanation."""
                resp, err = call_gemini_safe(client, "gemini-3.6-flash", [{"role": "user", "parts": [{"text": p}]}])
                if resp:
                    st.markdown('<div class="tab3-card">', unsafe_allow_html=True)
                    st.markdown(resp)
                    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 4: CHANDAḤ ŚĀSTRA (LOTUS ROSE THEME)
# ==============================================================================
with tab_chandas:
    st.markdown('<div class="tab4-container">', unsafe_allow_html=True)
    st.subheader("🎵 छन्दः-शास्त्र-परीक्षकः (Sanskrit Prosody & Meter Engine)")
    st.caption("Detect Vedic & Classical poetic meters (Anuṣṭubh, Upajāti, Indravajrā, Vasantatilakā, etc.) with Laghu-Guru mapping.")

    sample_sloka = "वागर्थाविव सम्पृक्तौ वागर्थप्रतिपत्तये ।\nजगतः पितरौ वन्दे पार्वतीपरमेश्वरौ ॥"
    user_sloka = st.text_area("Paste Sanskrit Śloka or Pada:", value=sample_sloka, height=100)

    if st.button("🔬 Analyze Meter / छन्दो-विश्लेषणम्"):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Calculating Laghu-Guru syllabic weights and Gaṇas..."):
            prompt_chandas = (
                "You are an authority on Pingala's Chandaḥ-śāstra (छन्दःशास्त्रम्).\n"
                f"Analyze this Sanskrit verse:\n{user_sloka}\n\n"
                "Output Format:\n"
                "### 🎯 छन्दसो नाम (Meter Identified):\n"
                "**[Name of the Meter]** (e.g. अनुष्टुप्, उपजातिः, इन्द्रवज्रा, वसन्ततिलका, शिखरिणी, मन्दाक्रान्ता)\n\n"
                "### 📏 लक्षणम् (Metrical Rule):\n"
                "<Classical Sanskrit definition śloka from Vṛttaratnākara with English meaning>\n\n"
                "### 🔍 पाद-लघु-गुरु-व्यवस्था (Syllable Breakdown per Quarter):\n"
                "Break down each pāda with:\n"
                "- Syllable representation with ल (Laghu, 1 mātrā) and ग (Guru, 2 mātrās) notation (l-g).\n"
                "- Gaṇa classification (य, म, त, र, ज, भ, न, स).\n"
                "- Matra/Akshara count."
            )
            resp, err = call_gemini_safe(client, "gemini-3.6-flash", [{"role": "user", "parts": [{"text": prompt_chandas}]}])
            if resp:
                st.markdown('<div class="tab4-card">', unsafe_allow_html=True)
                st.markdown(resp)
                st.markdown('</div>', unsafe_allow_html=True)
                st.session_state.xp += 15
            else:
                st.error(f"Error: {err}")
    st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 5: BIDIRECTIONAL TRANSLATION (OCEAN CYAN THEME)
# ==============================================================================
with tab_trans:
    st.markdown('<div class="tab5-container">', unsafe_allow_html=True)
    st.subheader("🌐 Universal Indian Languages ↔ Sanskrit Translation")
    st.caption("Translate with complete sentence generation, Sandhi, and grammatical analysis.")

    t_dir = st.radio("Direction", ["Indian Language / English ➔ Sanskrit", "Sanskrit ➔ Indian Language / English"], horizontal=True)
    
    if "Sanskrit ➔" in t_dir:
        dest_lang = st.selectbox("Select Target Language:", ["Telugu (తెలుగు)", "Hindi (हिन्दी)", "English", "Tamil (தமிழ்)", "Kannada (ಕನ್ನಡ)", "Marathi (मराठी)"])

    trans_in = st.text_area("Enter sentence to translate:", height=80, placeholder="Type in Telugu, Hindi, English or Sanskrit...")

    if st.button("Execute Translation / अनुवादं कुरु"):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key in sidebar.")
            st.stop()
        if not trans_in.strip():
            st.warning("Please enter text to translate.")
            st.stop()

        client = genai.Client(api_key=api_key)
        with st.spinner("Translating..."):
            if "➔ Sanskrit" in t_dir:
                p = f"""Translate into Sanskrit for student level: {level}.
MANDATORY FORMAT:
### 🪶 पूर्णवाक्यम् (Complete Sanskrit Sentence):
**संस्कृतम् (Devanagari):** <FULL SANSKRIT SENTENCE>
**IAST:** <Full sentence in IAST>
**English Meaning:** <Complete translation>

---
### 🔍 पदच्छेदः एवं व्याकरणम्:
- Breakdown of every word with its root/pratipadika and vibhakti/lakara.
"""
            else:
                p = f"""Translate this Sanskrit into {dest_lang} and English with Sandhi splits and word-by-word meanings."""

            resp, err = call_gemini_safe(client, "gemini-3.6-flash", [{"role": "user", "parts": [{"text": f"{p}\nInput: {trans_in}"}]}])
            if resp:
                st.markdown('<div class="tab5-card">', unsafe_allow_html=True)
                st.markdown(resp)
                st.markdown('</div>', unsafe_allow_html=True)
                st.session_state.xp += 10
                if "संस्कृतम् (Devanagari):" in resp:
                    line = resp.split("संस्कृतम् (Devanagari):")[1].split("\n")[0].strip()
                    st.write("🔊 **उच्चारणम् (Pronunciation):**")
                    play_sanskrit_audio(line, slow_mode=is_slow)
            else:
                st.error(f"Error: {err}")
    st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 6: SANĀTANA & VEDIC JÑĀNA PARĪKṢĀ (SACRED GOLDEN ORANGE THEME)
# ==============================================================================
with tab_vedic:
    st.markdown('<div class="tab6-container">', unsafe_allow_html=True)
    st.subheader("🏹 सनातन-ज्ञान-परीक्षा (Vedic & Epics Knowledge Quiz)")
    st.caption("Interactive gamified quizzes on the Vedas, Rāmāyaṇa, Mahābhārata, Upaniṣads, and Bhagavad Gītā.")

    col_q1, col_q2 = st.columns([1, 1])
    with col_q1:
        vedic_topic = st.selectbox(
            "Select Scripture / शास्त्र-विभागः:",
            [
                "The 4 Vedas & Samhitas (ऋक्, यजुस्, साम, अथर्व)",
                "Śrīmad Vālmīki Rāmāyaṇa (बाल, अयोध्या, आरण्य, किष्किन्धा, सुन्दर, युद्ध)",
                "Mahābhārata & Bhagavad Gītā (१८ पर्वाणि, १८ अध्यायाः)",
                "Principal Upaniṣads (ईश, केन, कठ, प्रश्न, मुण्डक, माण्डूक्य, etc.)",
                "Vedāṅgas (शिक्षा, कल्प, व्याकरण, निरुक्त, छन्दस्, ज्योतिष)"
            ]
        )
    with col_q2:
        diff_tier = st.selectbox("Difficulty Tier:", ["Beginner (प्रथमा - Famous Stories & Names)", "Intermediate (मध्यमा - Philosophy, Ślokas & Characters)", "Advanced (उत्तमा - Shastric Concepts & Mantras)"])

    if st.button("⚡ Generate 3-Question Challenge / नूतन-प्रश्नावली"):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key in sidebar.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Creating questions from authentic scriptures..."):
            prompt_vedic = (
                "You are an Acharya of Sanātana Dharma and Vedic literature.\n"
                "Generate an engaging 3-question MCQ quiz.\n"
                f"Topic: {vedic_topic}\n"
                f"Difficulty: {diff_tier}\n\n"
                "For each question:\n"
                "1. Provide the Question clearly in both Devanagari Sanskrit and English.\n"
                "2. Provide 4 distinct options (A, B, C, D).\n"
                "3. Provide the Correct Answer in bold.\n"
                "4. Provide the Authentic Reference (e.g. Rāmāyaṇa Sundarakāṇḍa, Bhagavad Gītā, or Upaniṣad verse).\n\n"
                "Format:\n"
                "### प्रश्नः १: <Question in Sanskrit & English>\n"
                "- A) <Option 1>\n"
                "- B) <Option 2>\n"
                "- C) <Option 3>\n"
                "- D) <Option 4>\n\n"
                "**उत्तरम् (Correct Answer):** <Option Letter and Answer>\n"
                "**प्रमाणम् (Scriptural Reference & Context):** <Explanation>\n"
                "---"
            )
            resp, err = call_gemini_safe(client, "gemini-3.6-flash", [{"role": "user", "parts": [{"text": prompt_vedic}]}])
            if resp:
                st.session_state.active_quiz_data = resp
                st.session_state.xp += 20

    if st.session_state.active_quiz_data:
        st.markdown('<div class="tab6-card">', unsafe_allow_html=True)
        st.markdown(st.session_state.active_quiz_data)
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
