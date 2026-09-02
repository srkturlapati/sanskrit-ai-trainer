import sys
import os

# 1. Enforce strict UTF-8 environment globally
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["LANG"] = "C.UTF-8"
os.environ["LC_ALL"] = "C.UTF-8"

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import time
import io
import hashlib

from google import genai
from google.genai import types
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

# --- MODERN GLASSMORPHISM & DEDICATED TAB COLOR THEMES ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&family=Noto+Sans+Devanagari:wght@400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', 'Noto Sans Devanagari', sans-serif;
    }

    /* Master Tabs Top Navigation */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        border-bottom: 2px solid #E2E8F0;
        padding-bottom: 6px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 52px;
        border-radius: 14px 14px 0px 0px;
        font-size: 15px;
        font-weight: 700;
        padding: 10px 20px;
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        color: #475569;
        transition: all 0.25s ease-in-out;
    }
    .stTabs [aria-selected="true"] {
        background-color: #0F172A !important;
        color: #FFFFFF !important;
        border-color: #0F172A !important;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.2);
    }

    /* ==========================================================================
       TAB 1: ROYAL INDIGO & VIOLET (Spoken Engine)
       ========================================================================== */
    .theme-tab1 {
        background: linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 100%);
        border: 2px solid #6366F1;
        border-radius: 24px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 10px 25px -5px rgba(99, 102, 241, 0.15);
    }
    .theme-tab1 .tab-header {
        color: #312E81;
        font-size: 24px;
        font-weight: 800;
        margin-bottom: 4px;
    }
    .theme-tab1 .tab-subtitle {
        color: #4338CA;
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 16px;
    }
    .theme-tab1 .card-ai {
        background: #FFFFFF;
        border-left: 6px solid #4F46E5;
        border-radius: 16px;
        padding: 16px 20px;
        margin-bottom: 14px;
        box-shadow: 0 4px 12px rgba(79, 70, 229, 0.08);
        color: #1E1B4B;
    }
    .theme-tab1 .card-user {
        background: #DCFCE7;
        border-left: 6px solid #16A34A;
        border-radius: 16px;
        padding: 14px 18px;
        margin-bottom: 14px;
        color: #14532D;
    }
    .theme-tab1 .voice-panel {
        background: #FFFFFF;
        border: 2px dashed #4F46E5;
        border-radius: 18px;
        padding: 16px 22px;
        margin: 16px 0px;
    }

    /* ==========================================================================
       TAB 2: VEDIC SAFFRON & ROYAL AMBER (Amarakoṣa)
       ========================================================================== */
    .theme-tab2 {
        background: linear-gradient(135deg, #FFFBEB 0%, #FEF3C7 100%);
        border: 2px solid #F59E0B;
        border-radius: 24px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 10px 25px -5px rgba(245, 158, 11, 0.15);
    }
    .theme-tab2 .tab-header {
        color: #78350F;
        font-size: 24px;
        font-weight: 800;
        margin-bottom: 4px;
    }
    .theme-tab2 .tab-subtitle {
        color: #B45309;
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 16px;
    }
    .theme-tab2 .card-result {
        background: #FFFFFF;
        border-left: 6px solid #D97706;
        border-radius: 16px;
        padding: 20px 24px;
        margin-top: 16px;
        box-shadow: 0 4px 12px rgba(217, 119, 6, 0.08);
        color: #451A03;
    }

    /* ==========================================================================
       TAB 3: EMERALD FOREST & JADE (Śabda & Dhātu)
       ========================================================================== */
    .theme-tab3 {
        background: linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%);
        border: 2px solid #10B981;
        border-radius: 24px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 10px 25px -5px rgba(16, 185, 129, 0.15);
    }
    .theme-tab3 .tab-header {
        color: #064E3B;
        font-size: 24px;
        font-weight: 800;
        margin-bottom: 4px;
    }
    .theme-tab3 .tab-subtitle {
        color: #047857;
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 16px;
    }
    .theme-tab3 .card-result {
        background: #FFFFFF;
        border-left: 6px solid #059669;
        border-radius: 16px;
        padding: 20px 24px;
        margin-top: 16px;
        box-shadow: 0 4px 12px rgba(5, 150, 105, 0.08);
        color: #064E3B;
    }

    /* ==========================================================================
       TAB 4: LOTUS RUBY & CRIMSON ROSE (Chandaḥ Śāstra)
       ========================================================================== */
    .theme-tab4 {
        background: linear-gradient(135deg, #FFF1F2 0%, #FFE4E6 100%);
        border: 2px solid #F43F5E;
        border-radius: 24px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 10px 25px -5px rgba(244, 63, 94, 0.15);
    }
    .theme-tab4 .tab-header {
        color: #881337;
        font-size: 24px;
        font-weight: 800;
        margin-bottom: 4px;
    }
    .theme-tab4 .tab-subtitle {
        color: #BE123C;
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 16px;
    }
    .theme-tab4 .card-result {
        background: #FFFFFF;
        border-left: 6px solid #E11D48;
        border-radius: 16px;
        padding: 20px 24px;
        margin-top: 16px;
        box-shadow: 0 4px 12px rgba(225, 29, 72, 0.08);
        color: #881337;
    }

    /* ==========================================================================
       TAB 5: DEEP OCEAN & CYAN AZURE (Universal Translation)
       ========================================================================== */
    .theme-tab5 {
        background: linear-gradient(135deg, #ECFEFF 0%, #CFFAFE 100%);
        border: 2px solid #06B6D4;
        border-radius: 24px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 10px 25px -5px rgba(6, 182, 212, 0.15);
    }
    .theme-tab5 .tab-header {
        color: #164E63;
        font-size: 24px;
        font-weight: 800;
        margin-bottom: 4px;
    }
    .theme-tab5 .tab-subtitle {
        color: #0E7490;
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 16px;
    }
    .theme-tab5 .card-result {
        background: #FFFFFF;
        border-left: 6px solid #0891B2;
        border-radius: 16px;
        padding: 20px 24px;
        margin-top: 16px;
        box-shadow: 0 4px 12px rgba(8, 145, 178, 0.08);
        color: #164E63;
    }

    /* ==========================================================================
       TAB 6: SURYA SUNSET & SACRED ORANGE (Vedic & Epics Quiz)
       ========================================================================== */
    .theme-tab6 {
        background: linear-gradient(135deg, #FFF7ED 0%, #FFEDD5 100%);
        border: 2px solid #F97316;
        border-radius: 24px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 10px 25px -5px rgba(249, 115, 22, 0.15);
    }
    .theme-tab6 .tab-header {
        color: #7C2D12;
        font-size: 24px;
        font-weight: 800;
        margin-bottom: 4px;
    }
    .theme-tab6 .tab-subtitle {
        color: #C2410C;
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 16px;
    }
    .theme-tab6 .card-result {
        background: #FFFFFF;
        border-left: 6px solid #EA580C;
        border-radius: 16px;
        padding: 20px 24px;
        margin-top: 16px;
        box-shadow: 0 4px 12px rgba(234, 88, 12, 0.08);
        color: #7C2D12;
    }

    /* Badges & Accent Chips */
    .badge-pill {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 700;
        margin-bottom: 8px;
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

# Robust API Caller with types.GenerateContentConfig
def call_gemini_safe(client, contents, system_instruction=""):
    last_err = None
    for attempt in range(4):
        try:
            config = types.GenerateContentConfig(
                temperature=0.2,
                system_instruction=system_instruction if system_instruction else None
            )
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
            
    return None, f"Rate limit reached. Please wait a few moments before retrying. ({last_err})"

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

# --- SIDEBAR: Profile & Settings ---
with st.sidebar:
    st.title("🚩 संस्कृतेन सम्भाषणं कुरु")
    st.caption("AI Sanskrit Spoken Coach & Vedic Knowledge Portal")
    
    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        placeholder="AIza...",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Get your key at aistudio.google.com/apikey",
    )
    
    level = st.selectbox(
        "Proficiency Tier / स्तरः",
        ["A1 - Beginner (प्रथमा)", "A2 - Elementary", "B1 - Intermediate (मध्यमा)", "B2 - Upper Intermediate", "C1 - Advanced (उत्तमा)"],
        index=0
    )
    
    st.write("---")
    st.subheader("🏆 Your Gamification Stats")
    c1, c2 = st.columns(2)
    c1.metric("🔥 Streak", f"{st.session_state.streak} Days")
    c2.metric("⭐ Points", f"{st.session_state.xp} XP")
    st.caption("🎖️ Status: **साधकः (Seeker)** • Next Rank at 500 XP")
    
    st.write("---")
    audio_speed = st.radio("Pronunciation Speed", ["Normal (सामान्यम्)", "Slow (मन्दम्)"], index=0)
    is_slow = audio_speed.startswith("Slow")
    
    if st.button("🔄 Reset Active Session"):
        st.session_state.talkpal_history = []
        st.session_state.last_audio_hash = ""
        st.session_state.active_quiz_data = None
        st.rerun()

# --- MASTER TOP TABS ---
tab_talkpal, tab_amara, tab_rupa, tab_chandas, tab_trans, tab_vedic = st.tabs([
    "🗣️ 1. सम्भाषणम्",
    "📖 2. अमरकोशः",
    "🧩 3. शब्द-धातुरूपाणि",
    "🎵 4. छन्दःशास्त्रम्",
    "🌐 5. सर्वभाषा-अनुवादकः",
    "🏹 6. ज्ञान-परीक्षा"
])


# ==============================================================================
# TAB 1: संस्कृतेन सम्भाषणं कुरु (ROYAL INDIGO & VIOLET)
# ==============================================================================
with tab_talkpal:
    st.markdown("""
    <div class="theme-tab1">
        <div class="tab-header">🗣️ संस्कृतेन सम्भाषणं कुरु (Spoken Sanskrit AI)</div>
        <div class="tab-subtitle">Oral-first interactive conversational tutor with instantaneous phonetic & grammatical guidance.</div>
    """, unsafe_allow_html=True)

    tp_mode = st.radio(
        "Conversation Mode",
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
            st.markdown('<div class="card-ai"><span class="badge-pill" style="background:#EEF2FF; color:#4F46E5;">🤖 आचार्यः (Sanskrit AI)</span><br>', unsafe_allow_html=True)
            st.markdown(msg["content"])
            st.markdown('</div>', unsafe_allow_html=True)
            if "[संस्कृतम्]:" in msg["content"]:
                line = msg["content"].split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                play_sanskrit_audio(line, slow_mode=is_slow)
        else:
            st.markdown('<div class="card-user"><span class="badge-pill" style="background:#DCFCE7; color:#15803D;">👤 You</span><br>', unsafe_allow_html=True)
            st.markdown(msg["content"])
            st.markdown('</div>', unsafe_allow_html=True)

    # Permanent Voice Dock
    st.markdown('<div class="voice-panel">', unsafe_allow_html=True)
    st.markdown("🎙️ **Tap the Mic to Speak / वदतु (Oral Reply):**")
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
                audio_part = types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")
                prompt_part = types.Part.from_text(text="Listen to this spoken Sanskrit, transcribe what was said, reply in Sanskrit with translation, and provide grammatical feedback.")
                
                reply, err = call_gemini_safe(
                    client=client,
                    contents=[audio_part, prompt_part],
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
        
        chat_contents = [f"{m['role'].upper()}: {m['content']}" for m in st.session_state.talkpal_history]
        chat_contents.append(f"USER: {user_text}")

        with st.spinner("आचार्यः लिखति..."):
            reply, err = call_gemini_safe(client, "\n\n".join(chat_contents), sys_talkpal)
            if reply:
                st.session_state.talkpal_history.append({"role": "model", "content": reply})
                st.rerun()
            else:
                st.error(f"⚠️ {err}")
    st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 2: AMARAKOṢA (VEDIC SAFFRON & AMBER)
# ==============================================================================
with tab_amara:
    st.markdown("""
    <div class="theme-tab2">
        <div class="tab-header">📖 नामलिङ्गानुशासनम् (अमरकोशः)</div>
        <div class="tab-subtitle">Authentic traditional Sanskrit thesaurus synonyms, gender markers, and original verses.</div>
    """, unsafe_allow_html=True)

    col_am1, col_am2 = st.columns([1, 1])
    with col_am1:
        amara_query = st.text_input("Enter Word or Concept (e.g., सूर्यः, अग्निः, चन्द्रः, जलम्):", value="सूर्यः")
    with col_am2:
        kanda_choice = st.selectbox("Search Scope / काण्डम्:", ["All (सर्वम्)", "प्रथमकाण्डम् (Heaven, Time, Devas)", "द्वितीयकाण्डम् (Earth, Cities, Forests)", "तृतीयकाण्डम् (General, Synonyms, Genders)"])

    if st.button("🔍 Explore Amarakoṣa / अन्वेषणं कुरु"):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key in sidebar.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("अमरकोश-श्लोकाः अन्विष्यन्ते..."):
            prompt_amara = f"""You are an authentic Sanskrit scholar of Amarakoṣa (नामलिङ्गानुशासनम् by Amarasimha).
Search Query: {amara_query}
Scope: {kanda_choice}

Output Format:
### 📜 अमरकोश-मूलश्लोकः (Original Verse):
<Quote authentic Amarakoṣa verse in Devanagari>

### 💎 पर्यायपदानि (Synonyms & Meaning):
- List all synonyms for the query word with gender (पुं/स्त्री/नपुं) and English meaning.

### 🏷️ काण्डम् एवं वर्गः (Taxonomy):
- State the Kāṇḍa and Varga.
"""
            resp, err = call_gemini_safe(client, prompt_amara)
            if resp:
                st.markdown('<div class="card-result">', unsafe_allow_html=True)
                st.markdown(resp)
                st.markdown('</div>', unsafe_allow_html=True)
                st.session_state.xp += 10
            else:
                st.error(f"Error: {err}")
    st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 3: ŚABDA & DHĀTURŪPA (EMERALD FOREST & JADE)
# ==============================================================================
with tab_rupa:
    st.markdown("""
    <div class="theme-tab3">
        <div class="tab-header">🧩 शब्दरूपाणि एवं धातुरूपाणि (Morphology Engine)</div>
        <div class="tab-subtitle">Complete 8-case declension charts, 10-lakāra verb conjugation tables, and identification drills.</div>
    """, unsafe_allow_html=True)

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
                resp, err = call_gemini_safe(client, p)
                if resp:
                    st.markdown('<div class="card-result">', unsafe_allow_html=True)
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
                resp, err = call_gemini_safe(client, p)
                if resp:
                    st.markdown('<div class="card-result">', unsafe_allow_html=True)
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
                resp, err = call_gemini_safe(client, p)
                if resp:
                    st.markdown('<div class="card-result">', unsafe_allow_html=True)
                    st.markdown(resp)
                    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 4: CHANDAḤ ŚĀSTRA (LOTUS RUBY & CRIMSON ROSE)
# ==============================================================================
with tab_chandas:
    st.markdown("""
    <div class="theme-tab4">
        <div class="tab-header">🎵 छन्दः-शास्त्र-परीक्षकः (Sanskrit Prosody & Meter)</div>
        <div class="tab-subtitle">Detect Classical & Vedic poetic meters with Laghu-Guru syllabic weight mapping.</div>
    """, unsafe_allow_html=True)

    sample_sloka = "वागर्थाविव सम्पृक्तौ वागर्थप्रतिपत्तये ।\nजगतः पितरौ वन्दे पार्वतीपरमेश्वरौ ॥"
    user_sloka = st.text_area("Paste Sanskrit Śloka or Pada:", value=sample_sloka, height=90)

    if st.button("🔬 Analyze Meter / छन्दो-विश्लेषणम्"):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Analyzing meter..."):
            prompt_chandas = f"""Analyze this Sanskrit verse under Pingala's Chandaḥ-śāstra:
{user_sloka}

Output:
1. Meter Name (छन्दसो नाम)
2. Definition rule (लक्षणम्)
3. Laghu-Guru breakdown (ल-ग) and Gaṇa analysis for each quarter (पाद).
"""
            resp, err = call_gemini_safe(client, prompt_chandas)
            if resp:
                st.markdown('<div class="card-result">', unsafe_allow_html=True)
                st.markdown(resp)
                st.markdown('</div>', unsafe_allow_html=True)
                st.session_state.xp += 15
            else:
                st.error(f"Error: {err}")
    st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 5: BIDIRECTIONAL TRANSLATION (DEEP OCEAN & CYAN AZURE)
# ==============================================================================
with tab_trans:
    st.markdown("""
    <div class="theme-tab5">
        <div class="tab-header">🌐 सर्वभाषा-संस्कृत-अनुवादकः (Universal Translator)</div>
        <div class="tab-subtitle">Complete bidirectional translation across Indian languages & Sanskrit with full Padaccheda.</div>
    """, unsafe_allow_html=True)

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
- Breakdown of every word with root and vibhakti/lakara.

Input Sentence: {trans_in}"""
            else:
                p = f"Translate this Sanskrit into {dest_lang} and English with Sandhi splits and word-by-word meanings.\n\nInput: {trans_in}"

            resp, err = call_gemini_safe(client, p)
            if resp:
                st.markdown('<div class="card-result">', unsafe_allow_html=True)
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
# TAB 6: SANĀTANA & VEDIC JÑĀNA PARĪKṢĀ (SURYA SUNSET & ORANGE)
# ==============================================================================
with tab_vedic:
    st.markdown("""
    <div class="theme-tab6">
        <div class="tab-header">🏹 सनातन-ज्ञान-परीक्षा (Vedic & Epics Quiz)</div>
        <div class="tab-subtitle">Interactive gamified challenges on the Vedas, Rāmāyaṇa, Mahābhārata, Upaniṣads, and Bhagavad Gītā.</div>
    """, unsafe_allow_html=True)

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
            prompt_vedic = f"""Generate a 3-question MCQ quiz on '{vedic_topic}' for Level '{diff_tier}'.
Provide Sanskrit question, 4 options (A,B,C,D), correct answer, and authentic scriptural reference."""
            resp, err = call_gemini_safe(client, prompt_vedic)
            if resp:
                st.session_state.active_quiz_data = resp
                st.session_state.xp += 20

    if st.session_state.active_quiz_data:
        st.markdown('<div class="card-result">', unsafe_allow_html=True)
        st.markdown(st.session_state.active_quiz_data)
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
