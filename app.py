import sys
import os
import time
import io
import hashlib

# Ensure UTF-8 encoding across all runtime environments
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

# --- CSS STYLING ---
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
        height: 50px;
        border-radius: 12px 12px 0px 0px;
        font-size: 15px;
        font-weight: 700;
        padding: 8px 18px;
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        color: #475569;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1E293B !important;
        color: #FFFFFF !important;
        border-color: #1E293B !important;
    }

    /* Tab Visual Containers */
    .tab1-box { background: #EEF2FF; border: 2px solid #6366F1; border-radius: 16px; padding: 20px; margin-bottom: 16px; }
    .tab2-box { background: #FFFBEB; border: 2px solid #F59E0B; border-radius: 16px; padding: 20px; margin-bottom: 16px; }
    .tab3-box { background: #F0FDF4; border: 2px solid #22C55E; border-radius: 16px; padding: 20px; margin-bottom: 16px; }
    .tab4-box { background: #FFF1F2; border: 2px solid #F43F5E; border-radius: 16px; padding: 20px; margin-bottom: 16px; }
    .tab5-box { background: #ECFEFF; border: 2px solid #06B6D4; border-radius: 16px; padding: 20px; margin-bottom: 16px; }
    .tab6-box { background: #FFF7ED; border: 2px solid #F97316; border-radius: 16px; padding: 20px; margin-bottom: 16px; }

    /* Bubbles & Cards */
    .ai-bubble { background: #FFFFFF; border-left: 5px solid #4F46E5; border-radius: 12px; padding: 14px 18px; margin-bottom: 10px; color: #1E1B4B; }
    .user-bubble { background: #DCFCE7; border-left: 5px solid #16A34A; border-radius: 12px; padding: 14px 18px; margin-bottom: 10px; color: #14532D; }
    .result-card { background: #FFFFFF; border-radius: 12px; padding: 16px; margin-top: 12px; border: 1px solid #E2E8F0; }
    .voice-dock { background: #FFFFFF; border: 2px dashed #4F46E5; border-radius: 14px; padding: 12px 18px; margin: 12px 0px; }
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

# Robust API Caller utilizing gemini-3.6-flash with exponential backoff
def call_gemini_safe(client, contents, system_instruction=""):
    last_err = None
    for attempt in range(4):
        try:
            config = {"temperature": 0.2}
            if system_instruction:
                config["system_instruction"] = system_instruction
            resp = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=contents,
                config=config
            )
            return resp.text, None
        except Exception as e:
            last_err = str(e)
            if "429" in last_err or "RESOURCE_EXHAUSTED" in last_err:
                time.sleep(3 * (attempt + 1))
                continue
            return None, last_err
            
    return None, f"Rate limit reached. Please wait a few seconds before retrying. ({last_err})"

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

# --- SIDEBAR ---
with st.sidebar:
    st.title("🚩 संस्कृतेन सम्भाषणं कुरु")
    st.caption("AI Sanskrit Spoken Coach & Vedic Portal")
    
    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        placeholder="AIza...",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Get your key at aistudio.google.com/apikey",
    )
    
    level = st.selectbox(
        "Proficiency Level / स्तरः",
        ["A1 - Beginner (प्रथमा)", "A2 - Elementary", "B1 - Intermediate (मध्यमा)", "B2 - Upper Intermediate", "C1 - Advanced (उत्तमा)"],
        index=0
    )
    
    st.write("---")
    st.subheader("🏆 Gamification")
    c1, c2 = st.columns(2)
    c1.metric("🔥 Streak", f"{st.session_state.streak} Days")
    c2.metric("⭐ Points", f"{st.session_state.xp} XP")
    
    st.write("---")
    audio_speed = st.radio("Audio Speed", ["Normal (सामान्यम्)", "Slow (मन्दम्)"], index=0)
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
# TAB 1: संस्कृतेन सम्भाषणं कुरु
# ==============================================================================
with tab_talkpal:
    st.markdown('<div class="tab1-box">', unsafe_allow_html=True)
    st.subheader("🗣️ संस्कृतेन सम्भाषणं कुरु (Speak in Sanskrit)")
    st.caption("Voice-first interactive spoken tutor with grammar inspection.")

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
            st.markdown('<div class="ai-bubble"><strong>🤖 आचार्यः (Sanskrit AI)</strong><br>', unsafe_allow_html=True)
            st.markdown(msg["content"])
            st.markdown('</div>', unsafe_allow_html=True)
            if "[संस्कृतम्]:" in msg["content"]:
                line = msg["content"].split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                play_sanskrit_audio(line, slow_mode=is_slow)
        else:
            st.markdown('<div class="user-bubble"><strong>👤 You</strong><br>', unsafe_allow_html=True)
            st.markdown(msg["content"])
            st.markdown('</div>', unsafe_allow_html=True)

    # Permanent Voice Dock
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
                st.warning("⚠️ Enter your Gemini API key in the sidebar.")
                st.stop()
            client = genai.Client(api_key=api_key)
            st.session_state.talkpal_history.append({"role": "user", "content": "🎙️ *[Spoken Voice Response]*"})
            st.session_state.xp += 15

            with st.spinner("आचार्यः शृणोति एवं चिन्तयति..."):
                reply, err = call_gemini_safe(
                    client=client,
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
            reply, err = call_gemini_safe(client, contents, sys_talkpal)
            if reply:
                st.session_state.talkpal_history.append({"role": "model", "content": reply})
                st.rerun()
            else:
                st.error(f"⚠️ {err}")
    st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 2: AMARAKOṢA
# ==============================================================================
with tab_amara:
    st.markdown('<div class="tab2-box">', unsafe_allow_html=True)
    st.subheader("📖 नामलिङ्गानुशासनम् (अमरकोशः)")
    st.caption("Traditional Sanskrit thesaurus synonyms, gender markers, and authentic kāṇḍa verses.")

    col_am1, col_am2 = st.columns([1, 1])
    with col_am1:
        amara_query = st.text_input("Enter Word or Concept (e.g., सूर्यः, अग्निः, चन्द्रः, जलम्):", value="सूर्यः")
    with col_am2:
        kanda_choice = st.selectbox("Search Scope / काण्डम्:", ["All (सर्वम्)", "प्रथमकाण्डम्", "द्वितीयकाण्डम्", "तृतीयकाण्डम्"])

    if st.button("🔍 Explore Amarakoṣa / अन्वेषणं कुरु"):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key in sidebar.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("अमरकोश-श्लोकाः अन्विष्यन्ते..."):
            prompt_amara = (
                "You are an authentic Sanskrit scholar of Amarakoṣa (नामलिङ्गानुशासनम् by Amarasimha).\n"
                f"Query: {amara_query}\nScope: {kanda_choice}\n\n"
                "Output Format:\n"
                "### 📜 अमरकोश-मूलश्लोकः (Original Verse):\n"
                "<Quote original Amarakoṣa verse in Devanagari>\n\n"
                "### 💎 पर्यायपदानि (Synonyms & Meaning):\n"
                "- List all synonyms for the query word with gender (पुं/स्त्री/नपुं) and English meaning.\n\n"
                "### 🏷️ काण्डम् एवं वर्गः (Taxonomy):\n"
                "- State the Kāṇḍa and Varga."
            )
            resp, err = call_gemini_safe(client, [{"role": "user", "parts": [{"text": prompt_amara}]}])
            if resp:
                st.markdown('<div class="result-card">', unsafe_allow_html=True)
                st.markdown(resp)
                st.markdown('</div>', unsafe_allow_html=True)
                st.session_state.xp += 10
            else:
                st.error(f"Error: {err}")
    st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 3: ŚABDA & DHĀTURŪPA
# ==============================================================================
with tab_rupa:
    st.markdown('<div class="tab3-box">', unsafe_allow_html=True)
    st.subheader("🧩 शब्दरूपाणि एवं धातुरूपाणि (Noun & Verb Engines)")
    st.caption("8-case declension charts, 10-lakāra verb conjugation tables, and identification drills.")

    rupa_type = st.radio("Choose Engine:", ["📜 Shabdarupa (Noun Declension)", "⚡ Dhaturoopa (Verb Conjugation)", "🎯 Rupa Identification Drill"], horizontal=True)

    if rupa_type == "📜 Shabdarupa (Noun Declension)":
        shabda_in = st.text_input("Enter Noun / Prātipadika (e.g., राम, लता, फल, हरि, नदी):", value="राम")
        if st.button("Generate 8 Vibhaktis"):
            if not api_key:
                st.warning("⚠️ Enter Gemini API key.")
                st.stop()
            client = genai.Client(api_key=api_key)
            with st.spinner("Generating declension table..."):
                p = f"""Generate full 8 Vibhakti table for Sanskrit noun '{shabda_in}'.
Format as Markdown Table with columns:
| विभक्तिः (Case) | एकवचनम् (Singular) | द्विवचनम् (Dual) | बहुवचनम् (Plural) | English Meaning |"""
                resp, err = call_gemini_safe(client, [{"role": "user", "parts": [{"text": p}]}])
                if resp:
                    st.markdown('<div class="result-card">', unsafe_allow_html=True)
                    st.markdown(resp)
                    st.markdown('</div>', unsafe_allow_html=True)

    elif rupa_type == "⚡ Dhaturoopa (Verb Conjugation)":
        dhatu_in = st.text_input("Enter Root / Dhātu (e.g., गम्, भू, पठ्, कृ, स्था):", value="गम्")
        lakara_in = st.selectbox("Select Lakāra / Tense:", ["लट् (Present - वर्तमाने)", "लङ् (Past - अनद्यतने भूते)", "लृट् (Future - भविष्यति)", "लोट् (Imperative - आज्ञायाम्)", "विधिलिङ् (Optative)"])
        if st.button("Generate Lakāra Conjugation"):
            if not api_key:
                st.warning("⚠️ Enter Gemini API key.")
                st.stop()
            client = genai.Client(api_key=api_key)
            with st.spinner("Generating conjugation table..."):
                p = f"""Generate conjugation table for Dhatu '{dhatu_in}' in '{lakara_in}'.
Format as Markdown Table:
| पुरुषः (Person) | एकवचनम् | द्विवचनम् | बहुवचनम् | English Meaning |"""
                resp, err = call_gemini_safe(client, [{"role": "user", "parts": [{"text": p}]}])
                if resp:
                    st.markdown('<div class="result-card">', unsafe_allow_html=True)
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
                p = "Provide a Sanskrit form challenge (e.g. रामेभ्यः). Ask student to identify Pratipadika, Vibhakti, Vacana with 4 MCQ options and spoiler answer with Paninian explanation."
                resp, err = call_gemini_safe(client, [{"role": "user", "parts": [{"text": p}]}])
                if resp:
                    st.markdown('<div class="result-card">', unsafe_allow_html=True)
                    st.markdown(resp)
                    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 4: CHANDAḤ ŚĀSTRA
# ==============================================================================
with tab_chandas:
    st.markdown('<div class="tab4-box">', unsafe_allow_html=True)
    st.subheader("🎵 छन्दः-शास्त्र-परीक्षकः (Sanskrit Prosody & Meter Engine)")
    st.caption("Detect poetic meters with Laghu-Guru syllabic weight mapping.")

    sample_sloka = "वागर्थाविव सम्पृक्तौ वागर्थप्रतिपत्तये ।\nजगतः पितरौ वन्दे पार्वतीपरमेश्वरौ ॥"
    user_sloka = st.text_area("Paste Sanskrit Śloka or Pada:", value=sample_sloka, height=90)

    if st.button("🔬 Analyze Meter / छन्दो-विश्लेषणम्"):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Analyzing meter..."):
            prompt_chandas = (
                f"Analyze this Sanskrit verse under Pingala's Chandaḥ-śāstra:\n{user_sloka}\n\n"
                "Output:\n"
                "1. Meter Name (छन्दसो नाम)\n"
                "2. Definition rule (लक्षणम्)\n"
                "3. Laghu-Guru breakdown (ल-ग) and Gaṇa analysis for each quarter (पाद)."
            )
            resp, err = call_gemini_safe(client, [{"role": "user", "parts": [{"text": prompt_chandas}]}])
            if resp:
                st.markdown('<div class="result-card">', unsafe_allow_html=True)
                st.markdown(resp)
                st.markdown('</div>', unsafe_allow_html=True)
                st.session_state.xp += 15
            else:
                st.error(f"Error: {err}")
    st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 5: BIDIRECTIONAL TRANSLATION
# ==============================================================================
with tab_trans:
    st.markdown('<div class="tab5-box">', unsafe_allow_html=True)
    st.subheader("🌐 Universal Indian Languages ↔ Sanskrit Translation")
    st.caption("Complete sentence generation, Sandhi, and grammatical analysis.")

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
- Breakdown of every word with root and vibhakti/lakara."""
            else:
                p = f"Translate this Sanskrit into {dest_lang} and English with Sandhi splits and word-by-word meanings."

            resp, err = call_gemini_safe(client, [{"role": "user", "parts": [{"text": f"{p}\nInput: {trans_in}"}]}])
            if resp:
                st.markdown('<div class="result-card">', unsafe_allow_html=True)
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
# TAB 6: SANĀTANA & VEDIC JÑĀNA PARĪKṢĀ
# ==============================================================================
with tab_vedic:
    st.markdown('<div class="tab6-box">', unsafe_allow_html=True)
    st.subheader("🏹 सनातन-ज्ञान-परीक्षा (Vedic & Epics Knowledge Quiz)")
    st.caption("Quizzes on Vedas, Rāmāyaṇa, Mahābhārata, Upaniṣads, and Bhagavad Gītā.")

    col_q1, col_q2 = st.columns([1, 1])
    with col_q1:
        vedic_topic = st.selectbox(
            "Select Scripture / शास्त्र-विभागः:",
            ["The 4 Vedas & Samhitas", "Śrīmad Vālmīki Rāmāyaṇa", "Mahābhārata & Bhagavad Gītā", "Principal Upaniṣads", "Vedāṅgas"]
        )
    with col_q2:
        diff_tier = st.selectbox("Difficulty Tier:", ["Beginner (प्रथमा)", "Intermediate (मध्यमा)", "Advanced (उत्तमा)"])

    if st.button("⚡ Generate 3-Question Challenge / नूतन-प्रश्नावली"):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key in sidebar.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Creating questions from authentic scriptures..."):
            prompt_vedic = (
                f"Generate a 3-question MCQ quiz on '{vedic_topic}' for Level '{diff_tier}'.\n"
                "Provide Sanskrit question, 4 options (A,B,C,D), correct answer, and authentic scriptural reference."
            )
            resp, err = call_gemini_safe(client, [{"role": "user", "parts": [{"text": prompt_vedic}]}])
            if resp:
                st.session_state.active_quiz_data = resp
                st.session_state.xp += 20

    if st.session_state.active_quiz_data:
        st.markdown('<div class="result-card">', unsafe_allow_html=True)
        st.markdown(st.session_state.active_quiz_data)
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
