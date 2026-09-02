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
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&family=Noto+Sans+Devanagari:wght@400;600;700&display=swap');
    
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
        },
        {
            "question": "रामायणस्य प्रथमः श्लोकः कः? (Which is the first shloka uttered by Valmiki?)",
            "options": ["A) मा निषाद प्रतिष्ठां त्वमगमः शाश्वतीः समाः...", "B) यदा यदा हि धर्मस्य...", "C) सत्यमेव जयते नानृतम्...", "D) वागर्थाविव सम्पृक्तौ..."],
            "correct_idx": 0,
            "ref": "क्रौञ्चवधदर्शनेन महर्षेः वाल्मीकेः मुखात् 'मा निषाद प्रतिष्ठां त्वमगमः...' इति श्लोकः निःसृतः।"
        },
        {
            "question": "हनूमान् सीतायाः अन्वेषणं कस्मिन् काण्डे कृतवान्? (In which Kanda does Hanuman find Sita?)",
            "options": ["A) किष्किन्धाकाण्डे", "B) सुन्दरकाण्डे", "C) युद्धकाण्डे", "D) आरण्यकाण्डे"],
            "correct_idx": 1,
            "ref": "सुन्दरकाण्डे हनूमतः समुद्रलङ्घनं तथा लङ्कायां सीतादर्शनं वर्णितम्।"
        }
    ],
    "Mahābhārata & Bhagavad Gītā": [
        {
            "question": "भगवद्गीता महाभारते कस्मिन् पर्वे वर्तते? (In which Parva of Mahabharata is Gita found?)",
            "options": ["A) वनपर्वे", "B) भीष्मपर्वे (अध्यायाः २५-४२)", "C) उद्योगपर्वे", "D) शान्तिपर्वे"],
            "correct_idx": 1,
            "ref": "श्रीमद्भगवद्गीता महाभारतस्य भीष्मपर्वणि २५ तमाध्यायात् ४२ तमाध्यायपर्यन्तं वर्तते।"
        },
        {
            "question": "भगवद्गीतायां कति अध्यायाः, कति श्लोकाः च सन्ति? (How many chapters and verses in Gita?)",
            "options": ["A) १० अध्यायाः, ५०० श्लोकाः", "B) १२ अध्यायाः, ६०० श्लोकाः", "C) १८ अध्यायाः, ७०० श्लोकाः", "D) २४ अध्यायाः, १००० श्लोकाः"],
            "correct_idx": 2,
            "ref": "भगवद्गीता अष्टादशाध्यायात्मिका (18 Chapters) सप्तशतश्लोकात्मिका (700 Slokas) च वर्तते।"
        },
        {
            "question": "'कर्मण्येवाधिकारस्ते मा फलेषु कदाचन' इति श्लोकः कस्य अध्यायस्य? (In which chapter is this verse?)",
            "options": ["A) प्रथमाध्यायस्य", "B) द्वितीयाध्यायस्य (सांख्ययोगः, श्लोकः ४७)", "C) तृतीयाध्यायस्य", "D) चतुर्थाध्यायस्य"],
            "correct_idx": 1,
            "ref": "एषः प्रसिद्धः श्लोकः गीतायाः द्वितीयाध्याये (२.४७) निष्कामकर्मयोगस्य उपदेशे वर्तते।"
        }
    ],
    "Principal Upaniṣads": [
        {
            "question": "'सत्यमेव जयते' इति महावाक्यं कस्मात् उपनिषदः उद्धृतम्? (From which Upanishad is 'Satyameva Jayate' taken?)",
            "options": ["A) ईशावास्योपनिषदः", "B) मुण्डकोपनिषदः (३.१.६)", "C) कठोपनिषदः", "D) केनोपनिषदः"],
            "correct_idx": 1,
            "ref": "'सत्यमेव जयते नानृतम्' इति मन्त्रभागः मुण्डकोपनिषदः तृतीयमुण्डके वर्तते।"
        },
        {
            "question": "नचिकेतसः यमस्य च सम्वादः कस्मिन् उपनिषदि अस्ति? (Dialogue between Nachiketa and Yama?)",
            "options": ["A) कठोपनिषदि", "B) प्रश्नोपनिषदि", "C) छान्दोग्योपनिषदि", "D) माण्डूक्योपनिषदि"],
            "correct_idx": 0,
            "ref": "कठोपनिषदि यम-नचिकेतसोः आत्मतत्त्वविषयकः सम्वादः वर्णितः अस्ति।"
        },
        {
            "question": "कति मुख्याः उपनिषदः शङ्कराचार्यैः भाष्यकृताः? (How many principal Upanishads commented by Shankara?)",
            "options": ["A) अष्टौ (8)", "B) दश (10)", "C) द्वादश (12)", "D) अष्टादश (18)"],
            "correct_idx": 1,
            "ref": "श्रीमदाद्यशङ्कराचार्यैः ईशादि-दशोपनिषत्सु प्रमुखतया भाष्यं रचितम्।"
        }
    ],
    "Vedāṅgas": [
        {
            "question": "वेदाङ्गानि कति सन्ति? (How many Vedangas are there?)",
            "options": ["A) चत्वारि (4)", "B) पञ्च (5)", "C) षट् (6 - शिक्षा, कल्प, व्याकरण, निरुक्त, छन्दस्, ज्योतिष)", "D) अष्ट (8)"],
            "correct_idx": 2,
            "ref": "वेदाङ्गानि षट् - शिक्षा, कल्पः, व्याकरणम्, निरुक्तम्, छन्दः, ज्योतिषम्।"
        },
        {
            "question": "'छन्दः पादौ तु वेदस्य...' - व्याकरणं किं स्मृतम्? (Grammar is considered what organ of Veda?)",
            "options": ["A) नेत्रम्", "B) मुखं व्याकरणं स्मृतम् (Mouth / Face)", "C) नासिका", "D) श्रोत्रम्"],
            "correct_idx": 1,
            "ref": "'मुखं व्याकरणं स्मृतम्' - पाणिनीयशिक्षायां व्याकरणं वेदपुरुषस्य मुखत्वेन प्रतिपादितम्।"
        },
        {
            "question": "वैदिकपदानां व्युत्पत्तिः अर्थनिर्वचनं च कस्मिन् अङ्गे क्रियते? (Etymology of Vedic words?)",
            "options": ["A) निरुक्ते (यास्काचार्यस्य निरुक्तम्)", "B) कल्पे", "C) ज्योतिषे", "D) शिक्षायाम्"],
            "correct_idx": 0,
            "ref": "यास्कप्रणीते निरुक्ते वैदिकपदानां निर्वचनं व्युत्पत्तिश्च प्रतिपादिता।"
        }
    ]
}


# ==============================================================================
# TAB 1: सम्भाषणम्
# ==============================================================================
if "सम्भाषणम्" in selected_tab:
    st.subheader("🗣️ संस्कृतेन सम्भाषणं कुरु (Spoken Sanskrit AI)")
    st.caption("Oral-first interactive conversational tutor with instantaneous phonetic & grammatical guidance.")

    tp_mode = st.radio(
        "Conversation Mode",
        ["💬 Free Chat", "🎭 Situational Roleplay", "🔥 Debate Club", "📸 Photo Mode", "🧩 Custom Mode"],
        horizontal=True,
        key="sub_mode_talkpal"
    )
    
    if tp_mode != st.session_state.tp_mode:
        st.session_state.talkpal_history = []
        st.session_state.last_audio_hash = ""
        st.session_state.tp_mode = tp_mode
        st.rerun()

    sys_talkpal = (
        f"You are the 'संस्कृतेन सम्भाषणं कुरु' AI Sanskrit Tutor (आचार्यः). Student Level: {level}.\n"
        "Always format output strictly as:\n"
        "[संस्कृतम्]: <Conversational Sanskrit reply>\n"
        "[IAST]: <Romanized transliteration>\n"
        "[English]: <English meaning>\n"
        "[💡 सम्भाषण-मार्गदर्शनम् (Feedback)]:\n"
        "- 🔍 रूपम् / दोषः: <Error note or 'निर्दोषम् (Perfect!)'>\n"
        "- ✨ वरतर-प्रयोगः (Better Way to Say): <Idiomatic alternative>\n"
        "- 📖 मुख्यशब्दाः (Key Vocabulary): <1-2 words with meaning>"
    )

    if len(st.session_state.talkpal_history) == 0:
        st.session_state.talkpal_history = [{
            "role": "model",
            "content": "[संस्कृतम्]: हरिः ॐ! संस्कृतेन सम्भाषणं कुरु। अद्य भवान्/भवती कीदृशं विषयम् अधिकृत्य सम्भाषणं कर्तुम् इच्छति?\n[IAST]: Hariḥ Om! Saṁskṛtena sambhāṣaṇaṁ kuru. Adya bhavān/bhavatī kīdṛśaṁ viṣayam adhikṛtya sambhāṣaṇaṁ kartum icchati?\n[English]: Hello! Speak in Sanskrit. What topic would you like to speak about today?\n[💡 सम्भाषण-मार्गदर्शनम् (Feedback)]:\n- 🔍 रूपम् / दोषः: निर्दोषम् (Ready!)\n- ✨ वरतर-प्रयोगः: शुभ-आरम्भः भवतु!\n- 📖 मुख्यशब्दाः: सम्भाषणम् (conversation)"
        }]

    for msg in st.session_state.talkpal_history:
        if msg["role"] == "model":
            st.markdown('<div class="card-ai"><span style="font-weight:700; color:#4F46E5;">🤖 आचार्यः (Sanskrit AI)</span><br>', unsafe_allow_html=True)
            st.markdown(msg["content"])
            st.markdown('</div>', unsafe_allow_html=True)
            if "[संस्कृतम्]:" in msg["content"]:
                line = msg["content"].split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                play_sanskrit_audio(line, slow_mode=is_slow)
        else:
            st.markdown('<div class="card-user"><span style="font-weight:700; color:#15803D;">👤 You</span><br>', unsafe_allow_html=True)
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
            else:
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
        else:
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


# ==============================================================================
# TAB 2: अमरकोशः (5 COMPREHENSIVE TOOLS)
# ==============================================================================
elif "अमरकोशः" in selected_tab:
    st.subheader("📖 नामलिङ्गानुशासनम् (अमरकोश-मञ्जूषा)")
    st.caption("Complete traditional Sanskrit thesaurus suite: Word-to-Śloka Search, Synonyms, MCQs, Matching, and Odd-One-Out.")

    amara_tool = st.radio(
        "Select Amarakoṣa Activity / गतिविधिः:",
        [
            "🔍 श्लोकान्वेषणम् (Find Śloka by Word)",
            "💎 पर्यायपदानि (Full Synonyms & Genders)",
            "📝 बहुविकल्प-प्रश्नाः (MCQ Quiz)",
            "🔗 युग्म-मेलनम् (Matching Challenge)",
            "🚫 विजातीयपद-चयनम् (Odd One Out)"
        ],
        horizontal=True,
        key="sel_amara_tool"
    )

    col_am1, col_am2 = st.columns([1, 1])
    with col_am1:
        amara_query = st.text_input("Enter Word or Theme (e.g. सूर्यः, अग्निः, जलम्, अश्वः, पृथ्वी, गगनम्):", value="सूर्यः", key="inp_amara_query")
    with col_am2:
        kanda_choice = st.selectbox("Search Scope / काण्डम्:", ["All (सर्वम्)", "प्रथमकाण्डम् (Heaven, Time, Devas)", "द्वितीयकाण्डम् (Earth, Cities, Forests)", "तृतीयकाण्डम् (General, Genders)"], key="sel_amara_kanda")

    btn_label = f"⚡ Execute {amara_tool.split('(')[0].strip()}"
    if st.button(btn_label, key="btn_run_amara"):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key in sidebar.")
        elif not amara_query.strip():
            st.warning("⚠️ Please enter a word to search.")
        else:
            client = genai.Client(api_key=api_key)
            with st.spinner("अमरकोशे अन्वेषणं प्रचलति..."):
                
                if "श्लोकान्वेषणम्" in amara_tool:
                    prompt_amara = (
                        "You are a master scholar of Amarasimha's Amarakoṣa (नामलिङ्गानुशासनम्).\n"
                        f"Search Word: {amara_query}\n"
                        f"Scope: {kanda_choice}\n\n"
                        f"Find the exact verse(s) where '{amara_query}' is defined.\n"
                        "Format:\n"
                        "### 📜 अमरकोश-मूलश्लोकः (Authentic Verse):\n"
                        "[Provide full Amarakoṣa Devanagari verse mentioning the query]\n\n"
                        "### 🔍 पदच्छेदः एवं काण्डनिर्देशः:\n"
                        "- काण्डम् एवं वर्गः: e.g. प्रथमकाण्डे स्वर्गवर्गे\n"
                        "- अन्वयार्थः (Meaning): Clear explanation in Sanskrit and English.\n"
                        "- समानार्थकाः शब्दाः (Words in this verse): Bullet points with genders."
                    )

                elif "पर्यायपदानि" in amara_tool:
                    prompt_amara = (
                        f"Provide the complete list of synonyms from Amarakoṣa for: '{amara_query}' (Scope: {kanda_choice}).\n"
                        "Format:\n"
                        f"### 💎 अमरकोशोक्ताः पर्यायाः (Synonyms for {amara_query}):\n"
                        "| क्र.सं. | संस्कृत-पदम् | IAST | लिङ्गम् (Gender) | आङ्ग्लार्थः (English Meaning) |\n"
                        "|---|---|---|---|---|\n"
                        "(List 6 to 10 authentic synonyms from Amarakoṣa)\n\n"
                        "### 🏷️ काण्डम् एवं वर्गनिर्देशः:\n"
                        "- State the exact Kāṇḍa and Varga where these appear."
                    )

                elif "बहुविकल्प-प्रश्नाः" in amara_tool:
                    prompt_amara = (
                        f"Generate a 3-question Multiple Choice Quiz on Amarakoṣa synonyms and definitions for: '{amara_query}'.\n"
                        "Format each question as:\n"
                        "### प्रश्नः: <Question in Sanskrit with English translation>\n"
                        "- A) <Option>\n"
                        "- B) <Option>\n"
                        "- C) <Option>\n"
                        "- D) <Option>\n\n"
                        "**उत्तरम् (Correct Answer):** <Correct letter and word>\n"
                        "**अमरकोश-प्रमाणम् (Verse reference & explanation):** <Quote the verse or rule>\n"
                        "---"
                    )

                elif "युग्म-मेलनम्" in amara_tool:
                    prompt_amara = (
                        f"Create an engaging 'Match the Following' (युग्म-मेलनम्) challenge based on Amarakoṣa synonyms related to: '{amara_query}' and related terms.\n"
                        "Format:\n"
                        "### 🔗 स्तम्भः 'क' एवं स्तम्भः 'ख' (Match Columns):\n"
                        "| स्तम्भः 'क' (Term) | स्तम्भः 'ख' (Synonym in Amarakoṣa) |\n"
                        "| 1. <Word 1> | A. <Synonym B> |\n"
                        "| 2. <Word 2> | B. <Synonym C> |\n"
                        "| 3. <Word 3> | C. <Synonym A> |\n"
                        "| 4. <Word 4> | D. <Synonym D> |\n\n"
                        "---\n"
                        "### 🎯 समीचीनं मेलनम् (Answer Key & Sloka Evidence):\n"
                        "- 1 ➔ <Letter> (<Explanation>)\n"
                        "- 2 ➔ <Letter> (<Explanation>)\n"
                        "- 3 ➔ <Letter> (<Explanation>)\n"
                        "- 4 ➔ <Letter> (<Explanation>)"
                    )

                else:
                    prompt_amara = (
                        f"Create 3 'Odd One Out' (विजातीयपद-चयनम्) challenges based on Amarakoṣa for the theme: '{amara_query}'.\n"
                        "In each question, provide 4 Sanskrit words where 3 are synonyms in the same Varga of Amarakoṣa, and 1 belongs to a completely different entity or Varga.\n\n"
                        "Format:\n"
                        "### प्रश्नः: विजातीयं पदं चिनोतु (Find the Odd One Out):\n"
                        "- A) <Word 1>\n"
                        "- B) <Word 2>\n"
                        "- C) <Word 3>\n"
                        "- D) <Word 4>\n\n"
                        "**विजातीयपदम् (Odd Word):** <Word letter and name>\n"
                        "**कारणम् (Why it is Odd):** <Explain which 3 words are synonyms and what the odd word means>\n"
                        "---"
                    )

                resp, err = call_gemini_safe(client, prompt_amara)
                if resp:
                    st.session_state.amara_result = resp
                    st.session_state.xp += 15
                else:
                    st.error(f"Error: {err}")

    if st.session_state.amara_result:
        st.markdown('<div class="content-box">', unsafe_allow_html=True)
        st.markdown(st.session_state.amara_result)
        st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 3: शब्द-धातुरूपाणि
# ==============================================================================
elif "शब्द-धातुरूपाणि" in selected_tab:
    st.subheader("🧩 शब्दरूपाणि एवं धातुरूपाणि (Morphology Engine)")
    st.caption("Complete 8-case declension charts, 10-lakāra verb conjugation tables, and identification drills.")

    rupa_type = st.radio("Choose Engine:", ["📜 Shabdarupa (Noun Declension)", "⚡ Dhaturoopa (Verb Conjugation)", "🎯 Rupa Identification Drill"], horizontal=True, key="sel_rupa_type")

    if rupa_type == "📜 Shabdarupa (Noun Declension)":
        shabda_in = st.text_input("Enter Noun / Prātipadika (e.g., राम, लता, फल, हरि, नदी):", value="राम", key="inp_shabda_noun")
        if st.button("Generate 8 Vibhaktis", key="btn_gen_shabda"):
            if not api_key:
                st.warning("⚠️ Enter Gemini API key in sidebar.")
            elif not shabda_in.strip():
                st.warning("⚠️ Please enter a noun.")
            else:
                client = genai.Client(api_key=api_key)
                with st.spinner("Generating declension table..."):
                    p = (
                        f"Generate full 8 Vibhakti table for Sanskrit noun '{shabda_in}'.\n"
                        "Format as Markdown Table with columns:\n"
                        "| विभक्तिः (Case) | एकवचनम् (Singular) | द्विवचनम् (Dual) | बहुवचनम् (Plural) | English Meaning |"
                    )
                    resp, err = call_gemini_safe(client, p)
                    if resp:
                        st.session_state.shabda_result = resp
                    else:
                        st.error(f"Error: {err}")

        if st.session_state.shabda_result:
            st.markdown('<div class="content-box">', unsafe_allow_html=True)
            st.markdown(st.session_state.shabda_result)
            st.markdown('</div>', unsafe_allow_html=True)

    elif rupa_type == "⚡ Dhaturoopa (Verb Conjugation)":
        dhatu_in = st.text_input("Enter Root / Dhātu (e.g., गम्, भू, पठ्, कृ, स्था):", value="गम्", key="inp_dhatu_root")
        lakara_in = st.selectbox("Select Lakāra / Tense:", ["लट् (Present - वर्तमाने)", "लङ् (Past - अनद्यतने भूते)", "लृट् (Future - भविष्यति)", "लोट् (Imperative - आज्ञायाम्)", "विधिलिङ् (Optative)"], key="sel_dhatu_lakara")
        
        if st.button("Generate Lakāra Conjugation", key="btn_gen_dhatu"):
            if not api_key:
                st.warning("⚠️ Enter Gemini API key in sidebar.")
            elif not dhatu_in.strip():
                st.warning("⚠️ Please enter a verb root.")
            else:
                client = genai.Client(api_key=api_key)
                with st.spinner("Generating conjugation table..."):
                    p = (
                        f"Generate conjugation table for Dhatu '{dhatu_in}' in '{lakara_in}'.\n"
                        "Format as Markdown Table:\n"
                        "| पुरुषः (Person) | एकवचनम् | द्विवचनम् | बहुवचनम् | English Meaning |"
                    )
                    resp, err = call_gemini_safe(client, p)
                    if resp:
                        st.session_state.dhatu_result = resp
                    else:
                        st.error(f"Error: {err}")

        if st.session_state.dhatu_result:
            st.markdown('<div class="content-box">', unsafe_allow_html=True)
            st.markdown(st.session_state.dhatu_result)
            st.markdown('</div>', unsafe_allow_html=True)

    else:
        st.write("🎯 **Test Your Form Identification Skills:**")
        if st.button("⚡ Generate New Identification Challenge", key="btn_gen_rupa_drill"):
            if not api_key:
                st.warning("⚠️ Enter Gemini API key in sidebar.")
            else:
                client = genai.Client(api_key=api_key)
                with st.spinner("Generating challenge..."):
                    p = "Provide a Sanskrit form challenge (e.g. रामेभ्यः). Ask student to identify Pratipadika, Vibhakti, Vacana with 4 MCQ options and spoiler answer with Paninian explanation."
                    resp, err = call_gemini_safe(client, p)
                    if resp:
                        st.session_state.rupa_drill_result = resp
                    else:
                        st.error(f"Error: {err}")

        if st.session_state.rupa_drill_result:
            st.markdown('<div class="content-box">', unsafe_allow_html=True)
            st.markdown(st.session_state.rupa_drill_result)
            st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 4: छन्दःशास्त्रम्
# ==============================================================================
elif "छन्दःशास्त्रम्" in selected_tab:
    st.subheader("🎵 छन्दः-शास्त्र-परीक्षकः (Sanskrit Prosody & Meter)")
    st.caption("Detect Classical & Vedic poetic meters with Laghu-Guru syllabic weight mapping.")

    sample_sloka = "वागर्थाविव सम्पृक्तौ वागर्थप्रतिपत्तये ।\nजगतः पितरौ वन्दे पार्वतीपरमेश्वरौ ॥"
    user_sloka = st.text_area("Paste Sanskrit Śloka or Pada:", value=sample_sloka, height=90, key="inp_chandas_sloka")

    if st.button("🔬 Analyze Meter / छन्दो-विश्लेषणम्", key="btn_analyze_chandas"):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key in sidebar.")
        elif not user_sloka.strip():
            st.warning("⚠️ Please enter a verse to analyze.")
        else:
            client = genai.Client(api_key=api_key)
            with st.spinner("Analyzing meter..."):
                prompt_chandas = (
                    f"Analyze this Sanskrit verse under Pingala's Chandaḥ-śāstra:\n{user_sloka}\n\n"
                    "Output:\n"
                    "1. Meter Name (छन्दसो नाम)\n"
                    "2. Definition rule (लक्षणम्)\n"
                    "3. Laghu-Guru breakdown (ल-ग) and Gaṇa analysis for each quarter (पाद)."
                )
                resp, err = call_gemini_safe(client, prompt_chandas)
                if resp:
                    st.session_state.chandas_result = resp
                    st.session_state.xp += 15
                else:
                    st.error(f"Error: {err}")

    if st.session_state.chandas_result:
        st.markdown('<div class="content-box">', unsafe_allow_html=True)
        st.markdown(st.session_state.chandas_result)
        st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 5: सर्वभाषा-अनुवादकः
# ==============================================================================
elif "सर्वभाषा-अनुवादकः" in selected_tab:
    st.subheader("🌐 सर्वभाषा-संस्कृत-अनुवादकः (Universal Translator)")
    st.caption("Complete bidirectional translation across Indian languages & Sanskrit with full Padaccheda.")

    t_dir = st.radio("Direction", ["Indian Language / English ➔ Sanskrit", "Sanskrit ➔ Indian Language / English"], horizontal=True, key="sel_trans_dir")
    
    dest_lang = "English"
    if "Sanskrit ➔" in t_dir:
        dest_lang = st.selectbox("Select Target Language:", ["Telugu (తెలుగు)", "Hindi (हिन्दी)", "English", "Tamil (தமிழ்)", "Kannada (ಕನ್ನಡ)", "Marathi (मराठी)"], key="sel_trans_target_lang")

    trans_in = st.text_area("Enter sentence to translate:", height=80, placeholder="Type in Telugu, Hindi, English or Sanskrit...", key="inp_trans_text")

    if st.button("Execute Translation / अनुवादं कुरु", key="btn_exec_trans"):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key in sidebar.")
        elif not trans_in.strip():
            st.warning("⚠️ Please enter text to translate.")
        else:
            client = genai.Client(api_key=api_key)
            with st.spinner("Translating..."):
                if "➔ Sanskrit" in t_dir:
                    p = (
                        f"Translate into Sanskrit for student level: {level}.\n"
                        "MANDATORY FORMAT:\n"
                        "### 🪶 पूर्णवाक्यम् (Complete Sanskrit Sentence):\n"
                        "**संस्कृतम् (Devanagari):** <FULL SANSKRIT SENTENCE>\n"
                        "**IAST:** <Full sentence in IAST>\n"
                        "**English Meaning:** <Complete translation>\n\n"
                        "---\n"
                        "### 🔍 पदच्छेदः एवं व्याकरणम्:\n"
                        "- Breakdown of every word with root and vibhakti/lakara.\n\n"
                        f"Input Sentence: {trans_in}"
                    )
                else:
                    p = f"Translate this Sanskrit into {dest_lang} and English with Sandhi splits and word-by-word meanings.\n\nInput: {trans_in}"

                resp, err = call_gemini_safe(client, p)
                if resp:
                    st.session_state.trans_result = resp
                    st.session_state.xp += 10
                else:
                    st.error(f"Error: {err}")

    if st.session_state.trans_result:
        st.markdown('<div class="content-box">', unsafe_allow_html=True)
        st.markdown(st.session_state.trans_result)
        if "संस्कृतम् (Devanagari):" in st.session_state.trans_result:
            line = st.session_state.trans_result.split("संस्कृतम् (Devanagari):")[1].split("\n")[0].strip()
            st.write("🔊 **उच्चारणम् (Pronunciation):**")
            play_sanskrit_audio(line, slow_mode=is_slow)
        st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# TAB 6: ज्ञान-परीक्षा (INTERACTIVE EVALUATION WITH PASS/FAIL MARKS)
# ==============================================================================
else:
    st.subheader("🏹 सनातन-ज्ञान-परीक्षा (Vedic & Epics Quiz)")
    st.caption("Interactive challenges on the Vedas, Rāmāyaṇa, Mahābhārata, Upaniṣads, and Bhagavad Gītā with instant grading.")

    col_q1, col_q2 = st.columns([1, 1])
    with col_q1:
        vedic_topic = st.selectbox(
            "Select Scripture / शास्त्र-विभागः:",
            ["The 4 Vedas & Samhitas", "Śrīmad Vālmīki Rāmāyaṇa", "Mahābhārata & Bhagavad Gītā", "Principal Upaniṣads", "Vedāṅgas"],
            key="sel_vedic_topic"
        )
    with col_q2:
        diff_tier = st.selectbox("Difficulty Tier:", ["Beginner (प्रथमा)", "Intermediate (मध्यमा)", "Advanced (उत्तमा)"], key="sel_vedic_tier")

    if st.button("⚡ Generate 3-Question Challenge / नूतन-प्रश्नावली", key="btn_gen_vedic_quiz"):
        st.session_state.quiz_submitted = False
        st.session_state.interactive_quiz_questions = None

        new_questions = None
        if api_key:
            client = genai.Client(api_key=api_key)
            with st.spinner("Generating fresh questions from authentic scriptures..."):
                prompt_json = (
                    "You are an authentic Vedic and Sanatana Dharma Acharya.\n"
                    f"Generate 3 challenging multiple-choice questions on '{vedic_topic}' for level '{diff_tier}'.\n\n"
                    "Return ONLY a valid JSON list of 3 objects with exact keys:\n"
                    "[\n"
                    "  {\n"
                    '    "question": "<Question in Devanagari Sanskrit with English in parentheses>",\n'
                    '    "options": ["A) <Option 1>", "B) <Option 2>", "C) <Option 3>", "D) <Option 4>"],\n'
                    '    "correct_idx": 0,\n'
                    '    "ref": "<Authentic scriptural reference and explanation in Sanskrit/English>"\n'
                    "  }\n"
                    "]\n"
                    "DO NOT wrap with markdown syntax or explanations. Output pure JSON only."
                )
                
                resp, err = call_gemini_safe(client, prompt_json)
                if resp:
                    try:
                        clean_json = resp.strip()
                        if clean_json.startswith("```"):
                            clean_json = clean_json.split("\n", 1)[1].rsplit("\n", 1)[0]
                        new_questions = json.loads(clean_json)
                    except Exception:
                        new_questions = None

        if not new_questions:
            new_questions = FALLBACK_QUESTIONS.get(vedic_topic, FALLBACK_QUESTIONS["The 4 Vedas & Samhitas"])
        
        st.session_state.interactive_quiz_questions = new_questions
        st.rerun()

    # RENDER INTERACTIVE QUIZ FORM IF QUESTIONS ARE LOADED
    if st.session_state.interactive_quiz_questions:
        st.write("---")
        st.markdown("#### 📝 **अधस्तन-प्रश्नानाम् उत्तराणि चिनोतु (Choose Your Answers):**")

        user_choices = []
        with st.form("interactive_quiz_form"):
            for i, q in enumerate(st.session_state.interactive_quiz_questions):
                st.markdown('<div class="quiz-card">', unsafe_allow_html=True)
                st.markdown(f"**प्रश्नः {i+1} : {q['question']}**")
                choice = st.radio(
                    label=f"q_{i}",
                    options=q["options"],
                    index=0,
                    key=f"user_choice_{i}",
                    label_visibility="collapsed"
                )
                user_choices.append(choice)
                st.markdown('</div>', unsafe_allow_html=True)

            submit_quiz = st.form_submit_button("🏁 Submit Answers / उत्तरं समर्पयतु")

        if submit_quiz:
            st.session_state.quiz_submitted = True
            correct_count = 0
            
            st.markdown("### 📊 परीक्षा-परिणामः (Quiz Results):")
            
            for i, q in enumerate(st.session_state.interactive_quiz_questions):
                selected_str = user_choices[i]
                correct_str = q["options"][q["correct_idx"]]
                is_correct = (selected_str == correct_str)
                
                st.markdown('<div class="quiz-card">', unsafe_allow_html=True)
                st.markdown(f"**प्रश्नः {i+1} : {q['question']}**")
                
                if is_correct:
                    correct_count += 1
                    st.markdown(f"""
                    <div class="quiz-correct">
                        ✅ <strong>सम्यक् उत्तरम्! (Correct Answer)</strong><br>
                        <strong>भवतः उत्तरम् (Your Choice):</strong> {selected_str}<br>
                        📜 <strong>प्रमाणम् (Scriptural Reference):</strong> {q['ref']}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="quiz-wrong">
                        ❌ <strong>अशुद्धम् (Incorrect)</strong><br>
                        <strong>भवतः उत्तरम् (Your Choice):</strong> {selected_str}<br>
                        🎯 <strong>शुद्धम् उत्तरम् (Correct Answer):</strong> {correct_str}<br>
                        📜 <strong>प्रमाणम् (Scriptural Reference):</strong> {q['ref']}
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

            earned_xp = correct_count * 15
            st.session_state.xp += earned_xp
            st.session_state.quiz_score = correct_count
            
            if correct_count == len(st.session_state.interactive_quiz_questions):
                st.success(f"🎉 **अतीव उत्तमम्! Full Score:** {correct_count}/3 Correct! (+{earned_xp} XP)")
                st.balloons()
            else:
                st.info(f"📈 **Score:** {correct_count}/3 Correct (+{earned_xp} XP earned). Review the explanations above!")
