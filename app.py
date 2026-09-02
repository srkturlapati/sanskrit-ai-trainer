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
import json
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

# --- SESSION STATES INITIALIZATION ---
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
if "selected_tab" not in st.session_state:
    st.session_state.selected_tab = "🗣️ 1. सम्भाषणम्"

# Button Output Caches
if "amara_result" not in st.session_state:
    st.session_state.amara_result = None
if "shabda_result" not in st.session_state:
    st.session_state.shabda_result = None
if "dhatu_result" not in st.session_state:
    st.session_state.dhatu_result = None
if "rupa_drill_result" not in st.session_state:
    st.session_state.rupa_drill_result = None
if "chandas_result" not in st.session_state:
    st.session_state.chandas_result = None
if "trans_result" not in st.session_state:
    st.session_state.trans_result = None

# Interactive Quiz States
if "interactive_quiz_questions" not in st.session_state:
    st.session_state.interactive_quiz_questions = None
if "quiz_submitted" not in st.session_state:
    st.session_state.quiz_submitted = False
if "quiz_score" not in st.session_state:
    st.session_state.quiz_score = 0

# --- SIDEBAR: Profile & Settings ---
with st.sidebar:
    st.title("🚩 संस्कृतेन सम्भाषणं कुरु")
    st.caption("AI Sanskrit Spoken Coach & Vedic Knowledge Portal")
    
    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        placeholder="AIza...",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Get your key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)",
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
    st.caption("🎖️ Rank: **साधकः (Seeker)** • Next Rank at 500 XP")
    
    st.write("---")
    audio_speed = st.radio("Pronunciation Speed", ["Normal (सामान्यम्)", "Slow (मन्दम्)"], index=0)
    is_slow = audio_speed.startswith("Slow")
    
    if st.button("🔄 Reset All Caches & Chat", key="btn_reset_all"):
        st.session_state.talkpal_history = []
        st.session_state.last_audio_hash = ""
        st.session_state.amara_result = None
        st.session_state.shabda_result = None
        st.session_state.dhatu_result = None
        st.session_state.rupa_drill_result = None
        st.session_state.chandas_result = None
        st.session_state.trans_result = None
        st.session_state.interactive_quiz_questions = None
        st.session_state.quiz_submitted = False
        st.session_state.quiz_score = 0
        st.rerun()

# --- TOP NAVIGATION BAR ---
tab_options = [
    "🗣️ 1. सम्भाषणम्",
    "📖 2. अमरकोशः",
    "🧩 3. शब्द-धातुरूपाणि",
    "🎵 4. छन्दःशास्त्रम्",
    "🌐 5. सर्वभाषा-अनुवादकः",
    "🏹 6. ज्ञान-परीक्षा"
]

selected_tab = st.radio(
    "Navigation",
    tab_options,
    index=tab_options.index(st.session_state.selected_tab) if st.session_state.selected_tab in tab_options else 0,
    horizontal=True,
    label_visibility="collapsed",
    key="master_nav_tab"
)
st.session_state.selected_tab = selected_tab

# --- FULL-BODY DYNAMIC PALETTES PER TAB ---
if "सम्भाषणम्" in selected_tab:
    bg_gradient = "linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 50%, #C7D2FE 100%)"
    theme_accent = "#4F46E5"
    theme_dark = "#1E1B4B"
    theme_header = "#312E81"
    border_accent = "#6366F1"
elif "अमरकोशः" in selected_tab:
    bg_gradient = "linear-gradient(135deg, #FFFBEB 0%, #FEF3C7 50%, #FDE68A 100%)"
    theme_accent = "#D97706"
    theme_dark = "#451A03"
    theme_header = "#78350F"
    border_accent = "#F59E0B"
elif "शब्द-धातुरूपाणि" in selected_tab:
    bg_gradient = "linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 50%, #BBF7D0 100%)"
    theme_accent = "#059669"
    theme_dark = "#064E3B"
    theme_header = "#064E3B"
    border_accent = "#10B981"
elif "छन्दःशास्त्रम्" in selected_tab:
    bg_gradient = "linear-gradient(135deg, #FFF1F2 0%, #FFE4E6 50%, #FECDD3 100%)"
    theme_accent = "#E11D48"
    theme_dark = "#881337"
    theme_header = "#881337"
    border_accent = "#F43F5E"
elif "सर्वभाषा-अनुवादकः" in selected_tab:
    bg_gradient = "linear-gradient(135deg, #ECFEFF 0%, #CFFAFE 50%, #A5F3FC 100%)"
    theme_accent = "#0891B2"
    theme_dark = "#164E63"
    theme_header = "#164E63"
    border_accent = "#06B6D4"
else:
    bg_gradient = "linear-gradient(135deg, #FFF7ED 0%, #FFEDD5 50%, #FED7AA 100%)"
    theme_accent = "#EA580C"
    theme_dark = "#7C2D12"
    theme_header = "#7C2D12"
    border_accent = "#F97316"

st.markdown(f"""
<style>
    @import url('[https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&family=Noto+Sans+Devanagari:wght@400;600;700&display=swap](https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&family=Noto+Sans+Devanagari:wght@400;600;700&display=swap)');
    
    html, body, [class*="css"] {{
        font-family: 'Plus Jakarta Sans', 'Noto Sans Devanagari', sans-serif;
    }}

    .stApp {{
        background: {bg_gradient} !important;
        background-attachment: fixed !important;
    }}
    
    .main .block-container {{
        background: transparent !important;
        padding-top: 1.5rem !important;
        padding-bottom: 3rem !important;
        max-width: 1100px !important;
    }}

    .stRadio [role="radiogroup"] {{
        background: rgba(255, 255, 255, 0.85);
        backdrop-filter: blur(10px);
        padding: 8px 12px;
        border-radius: 20px;
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        border: 2px solid {border_accent};
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.08);
        margin-bottom: 20px;
    }}
    .stRadio [role="radiogroup"] label {{
        background: #FFFFFF;
        border-radius: 12px;
        padding: 8px 16px;
        font-weight: 700;
        color: {theme_dark} !important;
        border: 1px solid rgba(0, 0, 0, 0.08);
        transition: all 0.2s ease-in-out;
    }}
    .stRadio [role="radiogroup"] label[data-checked="true"] {{
        background: {theme_accent} !important;
        color: #FFFFFF !important;
        border-color: {theme_accent} !important;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15);
    }}

    h1, h2, h3, h4 {{
        color: {theme_header} !important;
        font-weight: 800 !important;
    }}
    p, span, label {{
        color: {theme_dark} !important;
    }}

    .content-box {{
        background: #FFFFFF !important;
        border-left: 6px solid {theme_accent} !important;
        border-radius: 18px;
        padding: 22px 26px;
        margin-top: 14px;
        margin-bottom: 16px;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.08);
        border-top: 1px solid rgba(0,0,0,0.05);
        border-right: 1px solid rgba(0,0,0,0.05);
        border-bottom: 1px solid rgba(0,0,0,0.05);
    }}

    .quiz-card {{
        background: #FFFFFF !important;
        border: 1px solid rgba(0,0,0,0.08);
        border-radius: 16px;
        padding: 18px 20px;
        margin-bottom: 18px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
    }}
    .quiz-correct {{
        background: #ECFDF5 !important;
        border-left: 6px solid #10B981 !important;
        border-radius: 12px;
        padding: 14px 16px;
        margin-top: 10px;
        color: #065F46 !important;
    }}
    .quiz-wrong {{
        background: #FEF2F2 !important;
        border-left: 6px solid #EF4444 !important;
        border-radius: 12px;
        padding: 14px 16px;
        margin-top: 10px;
        color: #991B1B !important;
    }}

    .card-ai {{
        background: #FFFFFF !important;
        border-left: 6px solid #4F46E5 !important;
        border-radius: 16px;
        padding: 16px 20px;
        margin-bottom: 12px;
        box-shadow: 0 4px 12px rgba(79, 70, 229, 0.08);
    }}
    .card-user {{
        background: #DCFCE7 !important;
        border-left: 6px solid #16A34A !important;
        border-radius: 16px;
        padding: 14px 18px;
        margin-bottom: 12px;
        color: #14532D !important;
    }}
    .voice-panel {{
        background: #FFFFFF !important;
        border: 2px dashed {theme_accent} !important;
        border-radius: 18px;
        padding: 16px 22px;
        margin: 16px 0px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
    }}
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

# Robust API Caller with types.Part and Unicode encoding safety
def call_gemini_safe(client, contents, system_instruction=""):
    last_err = None
    
    # Ensure contents is converted to official types.Part structures to prevent ASCII codec crashes
    if isinstance(contents, str):
        payload = [types.Part.from_text(text=contents)]
    elif isinstance(contents, list):
        payload = []
        for item in contents:
            if isinstance(item, str):
                payload.append(types.Part.from_text(text=item))
            else:
                payload.append(item)
    else:
        payload = contents

    for attempt in range(4):
        try:
            config = types.GenerateContentConfig(
                temperature=0.2,
                system_instruction=system_instruction if system_instruction else None
            )
            resp = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=payload,
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

# Fallback Scriptural Question Bank for Tab 6
FALLBACK_QUESTIONS = {
    "The 4 Vedas & Samhitas": [
        {
            "question": "कति वेदाः सन्ति? तेषां नामानि कानि? (How many Vedas are there?)",
            "options": ["A) त्रयः (3 Vedas)", "B) चत्वारः - ऋक्, यजुस्, साम, अथर्व (4 Vedas)", "C) पञ्च (5 Vedas)", "D) षट् (6 Vedas)"],
            "correct_idx": 1,
            "ref": "वेदाः चत्वारः भवन्ति - ऋग्वेदः, यजुर्वेदः, सामवेदः, अथर्ववेदः चेति।"
        },
        {
            "question": "ऋग्वेदस्य प्रमुखः देवता कः? (Who is the most frequently addressed deity in Rigveda?)",
            "options": ["A) इन्द्रः (Indra)", "B) सूर्यः (Surya)", "C) वरुणः (Varuna)", "D) सोमः (Soma)"],
            "correct_idx": 0,
            "ref": "ऋग्वेदे इन्द्रस्य स्तुतयः सर्वाधिकेषु सूक्तेषु (प्रायः २५० सूक्तेषु) प्राप्यन्ते।"
        },
        {
            "question": "गायत्रीमन्त्रः कस्मिन् वेदे वर्तते? (In which Veda is the Gayatri Mantra found?)",
            "options": ["A) सामवेदे", "B) यजुर्वेदे", "C) ऋग्वेदे (तृतीयमण्डले)", "D) अथर्ववेदे"],
            "correct_idx": 2,
            "ref": "गायत्रीमन्त्रः ऋग्वेदस्य तृतीयमण्डलस्य ६२ तमे सूक्ते (३.६२.१०) वर्तते।"
        }
    ],
    "Śrīmad Vālmīki Rāmāyaṇa": [
        {
            "question": "वाल्मीकि-रामायणे कति काण्डानि सन्ति? (How many Kandas in Valmiki Ramayana?)",
            "options": ["A) ५ काण्डानि", "B) ६ काण्डानि", "C) ७ काण्डानि (बाल, अयोध्या, आरण्य, किष्किन्धा, सुन्दर, युद्ध, उत्तर)", "D) ८ काण्डानि"],
            "correct_idx": 2,
            "ref": "वाल्मीकिरामायणे बालकाण्डादारभ्य उत्तरकाण्डपर्यन्तं सप्त काण्डानि सन्ति।"
