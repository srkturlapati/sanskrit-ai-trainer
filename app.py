import sys
import os
import time
import io
import datetime

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
    page_title="Sambhāṣaṇa AI - Spoken Sanskrit Master",
    page_icon="🚩",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- SESSION STATE INITIALIZATION ---
if "xp_points" not in st.session_state:
    st.session_state.xp_points = 120
if "practice_streak" not in st.session_state:
    st.session_state.practice_streak = 3
if "roleplay_messages" not in st.session_state:
    st.session_state.roleplay_messages = []
if "vocab_vault" not in st.session_state:
    st.session_state.vocab_vault = [
        {"word": "अस्तु", "meaning": "Alright / Let it be", "dhatu": "अस् (to be)", "level": "Beginner", "review_due": "Today"},
        {"word": "धन्यवादः", "meaning": "Thank you", "dhatu": "धन्य + वाद्", "level": "Beginner", "review_due": "Tomorrow"},
        {"word": "पुनर्मिलामः", "meaning": "See you again", "dhatu": "मिल् (to meet)", "level": "Beginner", "review_due": "In 3 Days"}
    ]
if "active_quiz" not in st.session_state:
    st.session_state.active_quiz = None

# Helper: Sanskrit Text-to-Speech
def play_sanskrit_audio(text_to_speak: str):
    try:
        clean_text = text_to_speak.replace('*', '').replace('#', '').replace('-', '').replace('[', '').replace(']', '').strip()
        if not clean_text:
            return
        tts = gTTS(text=clean_text, lang='hi', slow=False)
        audio_fp = io.BytesIO()
        tts.write_to_fp(audio_fp)
        audio_fp.seek(0)
        st.audio(audio_fp, format="audio/mp3")
    except Exception:
        pass

# --- SIDEBAR: Profile, Settings & Gamification ---
with st.sidebar:
    st.title("🚩 Sambhāṣaṇa AI")
    st.caption("AI-Powered Spoken Sanskrit Academy")
    
    api_key = st.text_input(
        "Google Gemini API Key",
        type="password",
        placeholder="AIza...",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Get your free key at aistudio.google.com/apikey",
    )
    
    level = st.selectbox(
        "Student Tier / स्तरः",
        [
            "Beginner (प्रथमा - Daily Phrases & Basic Verbs)",
            "Intermediate (मध्यमा - Tenses, Participles & Flow)",
            "Advanced (उत्तमा - Shastric & Literary Sanskrit)"
        ],
        index=0,
    )
    
    st.write("---")
    st.subheader("🏆 Fluency & Gamification")
    col_sb1, col_sb2 = st.columns(2)
    with col_sb1:
        st.metric("🔥 Streak", f"{st.session_state.practice_streak} Days")
    with col_sb2:
        st.metric("⭐ Points", f"{st.session_state.xp_points} XP")
        
    st.write("🎖️ **Badges Earned:**")
    st.markdown("🏅 *Śikṣā Novice* &nbsp;|&nbsp; 🗣️ *Vipani Explorer* &nbsp;|&nbsp; 📜 *Sandhi Master*")
    
    st.write("---")
    if st.button("🔄 Reset Chat & Sessions"):
        st.session_state.roleplay_messages = []
        st.session_state.active_quiz = None
        st.rerun()

# --- TOP LEVEL NAVIGATION TABS ---
tab_roleplay, tab_shiksha, tab_shadow, tab_translate, tab_grammar, tab_vault = st.tabs([
    "💬 1. Roleplay & Scenarios",
    "🎙️ 2. Śikṣā Phonetic Coach",
    "🔁 3. Shadowing Drills",
    "🌐 4. Universal Translator",
    "🧩 5. Vyākaraṇa Engine",
    "🧠 6. SRS Vault & Parīkṣā"
])


# =========================================================
# TAB 1: CONVERSATIONAL ROLEPLAY & PERSONAS
# =========================================================
with tab_roleplay:
    st.subheader("💬 Situational Roleplay & Real-Life Immersion")
    
    col_r1, col_r2 = st.columns([1, 1])
    with col_r1:
        scenario = st.selectbox(
            "Select Scenario / प्रसङ्गः:",
            [
                "At the Market (विपणिः - शाकक्रयणम् / Purchasing Vegetables)",
                "At School / Gurukula (पाठशाला - शिष्टाचारः / Teacher & Student)",
                "Travel & Directions (यात्रा - मार्गनिर्देशनम् / Station & Road)",
                "Welcoming Guests (अतिथि-सत्कारः / Home Hospitality)",
                "Free Dialogue with Ācārya (मुक्त-सम्भाषणम् / Open Discussion)",
                "Animal Storyteller (पञ्चतन्त्र-कथा: गजः, शुकः, मयूरः)"
            ]
        )
    with col_r2:
        tutor_persona = st.selectbox(
            "Tutor Persona / स्वभावः:",
            [
                "Acharya AI (Patient, Pedagogical & Socratic)",
                "Mitram AI (Friendly Peer Learner / Informal)",
                "Gaja-Guru (Playful Storybook Character for Kids)"
            ]
        )

    SYSTEM_ROLEPLAY = f"""You are '{tutor_persona}' engaging the student in the scenario: '{scenario}'.
Target Proficiency Level: {level}.

Rules:
1. Converse dynamically in spoken Sarala Samskritam according to the persona and scenario.
2. If the student makes an error (Vibhakti, Lakāra, Puruṣa mismatch, Sandhi):
   - Highlight the mistake gently.
   - Provide a Socratic hint or guiding rule.
3. Offer a '✨ Say It Better' upgrade (a more idiomatic, natural Sanskrit expression for what they said).
4. Always end your turn by asking an engaging situational question.

Output Format:
[संस्कृतम्]: <Devanagari Dialogue>
[IAST]: <Romanized Transliteration>
[English]: <English Meaning>
[✨ Say It Better]: <More natural or idiomatic way to express the student's thought>
[मार्गदर्शनम्] (Include ONLY if the student made a mistake):
- 🔍 रूपम्: <Incorrect student word>
- 💡 सङ्केतः: <Guiding rule or correction>
"""

    # Display dialogue history
    for msg in st.session_state.roleplay_messages:
        role = "assistant" if msg["role"] == "model" else "user"
        with st.chat_message(role):
            st.markdown(msg["content"])
            if role == "assistant" and "[संस्कृतम्]:" in msg["content"]:
                line = msg["content"].split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                play_sanskrit_audio(line)

    # Audio Voice Input for Roleplay
    st.write("🎙️ **Speak Your Response / वदतु (Voice Input):**")
    role_audio = st.audio_input("Record voice for roleplay:")

    if role_audio is not None:
        if not api_key:
            st.warning("⚠️ Please enter your Gemini API key in the sidebar.")
            st.stop()
        
        client = genai.Client(api_key=api_key)
        audio_bytes = role_audio.getvalue()
        
        st.session_state.roleplay_messages.append({"role": "user", "content": "🎙️ *[Oral Spoken Input Submitted]*"})
        st.session_state.xp_points += 10
        with st.chat_message("user"):
            st.audio(role_audio, format="audio/wav")
        
        with st.chat_message("assistant"):
            with st.spinner("आचार्यः शृणोति एवं चिन्तयति..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": audio_bytes}},
                            {"text": f"{SYSTEM_ROLEPLAY}\nListen to the student's spoken audio, transcribe it, and reply accordingly."}
                        ]
                    }],
                )
                st.markdown(resp.text)
                if "[संस्कृतम्]:" in resp.text:
                    line = resp.text.split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                    play_sanskrit_audio(line)
                st.session_state.roleplay_messages.append({"role": "model", "content": resp.text})

    # Text Input for Roleplay
    if text_msg := st.chat_input("Or type dialogue (e.g. bho mātulā, phalasya mūlyaṁ kim?)..."):
        if not api_key:
            st.warning("⚠️ Please enter your Gemini API key in the sidebar.")
            st.stop()
            
        client = genai.Client(api_key=api_key)
        is_dev = any("\u0900" <= char <= "\u097f" for char in text_msg)
        if not is_dev:
            try:
                converted = transliterate(text_msg, sanscript.ITRANS, sanscript.DEVANAGARI)
                user_display = f"{text_msg} ({converted})"
            except Exception:
                user_display = text_msg
        else:
            user_display = text_msg

        st.session_state.roleplay_messages.append({"role": "user", "content": user_display})
        st.session_state.xp_points += 5
        with st.chat_message("user"):
            st.markdown(user_display)

        contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": str(m["content"])}]} for m in st.session_state.roleplay_messages]

        with st.chat_message("assistant"):
            with st.spinner("चिन्तयति..."):
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=contents,
                    config={"system_instruction": SYSTEM_ROLEPLAY, "temperature": 0.2},
                )
                st.markdown(resp.text)
                if "[संस्कृतम्]:" in resp.text:
                    line = resp.text.split("[संस्कृतम्]:")[1].split("\n")[0].strip()
                    play_sanskrit_audio(line)
                st.session_state.roleplay_messages.append({"role": "model", "content": resp.text})


# =========================================================
# TAB 2: PHONETIC PRONUNCIATION COACH (ŚIKṢĀ)
# =========================================================
with tab_shiksha:
    st.subheader("🎙️ पाणिनीय-शिक्षा एवं उच्चारण-परीक्षकः (Phonetic Accent Coach)")
    st.caption("AI evaluates your vocal acoustics: Articulation points (दन्त्य/मूर्धन्य), Mahāprāṇa aspiration, and vowel timing.")
    
    drill_options = [
        "सत्यं वद, धर्मं चर। (Speak truth, practice righteousness)",
        "विद्या ददाति विनयं विनयाद्याति पात्रताम्। (Knowledge confers humility)",
        "वृक्षात् फलानि भूमौ पतन्ति। (Fruits fall from tree - Mahāprāṇa 'ph' & 'bh')",
        "अहं प्रतिदिनं प्रातः पञ्चवादने उत्तिष्ठामि। (I wake at 5 AM - Retroflex 'ṣṭh')",
        "अथातो ब्रह्मजिज्ञासा। (Now begins the inquiry into Brahman - Aspirated 'th' & 'jh')"
    ]
    
    target_drill = st.selectbox("Choose Target Phrase / वाक्यम्:", drill_options)
    clean_target = target_drill.split('(')[0].strip()
    
    col_sh1, col_sh2 = st.columns([1, 1])
    with col_sh1:
        st.write("🔊 **1. Master Reference Chanting:**")
        play_sanskrit_audio(clean_target)
    with col_sh2:
        st.write("🎙️ **2. Record Your Pronunciation:**")
        rec_shiksha = st.audio_input("Record your voice chanting the sentence:")

    if rec_shiksha is not None:
        if not api_key:
            st.warning("⚠️ Please enter your Gemini API key in the sidebar.")
            st.stop()
            
        client = genai.Client(api_key=api_key)
        with st.spinner("Analyzing phoneme frequencies, tongue placement, and aspiration..."):
            PROMPT_SHIKSHA = f"""You are a Pāṇinīya Śikṣā (पाणिनीय-शिक्षा) phonetic acoustic evaluator.
Target Sentence: "{clean_target}"

Evaluate the student's audio recording strictly on:
1. Overall Pronunciation Score (0 to 100%).
2. Articulation Points (उच्चारण-स्थानम्): Dental (दन्त्य) vs Retroflex (मूर्धन्य), Guttural (कण्ठ्य), Labial (ओष्ठ्य).
3. Aspiration (प्राण-प्रयत्नः): Proper breath release on Mahāprāṇa consonants (ख्, घ्, थ्, ध्, फ्, भ्) vs Alpaprāṇa.
4. Vowel Timing (स्वर-मात्रा): Hrasva (1 mātrā) vs Dīrgha (2 mātrās) vowel duration.
5. Actionable Tongue Placement Tip: Practical tip to achieve native Sanskrit clarity.

Format as:
### 🎯 उच्चारण-अङ्काः (Score): [XX / 100]
**शुद्धता-स्तरः (Clarity Rating):** [उत्कृष्टम् (Excellent) / समीचीनम् (Good) / अभ्यासोऽपेक्षितः (Needs Practice)]

---
### 🔍 ध्वन्युच्चारण-विश्लेषणम् (Phonetic Breakdown):
- **उच्चारण-स्थानानि (Place of Articulation)**: <Analysis>
- **प्राण-प्रयत्नः (Aspiration & Breath Release)**: <Analysis>
- **मात्रा-दीर्घता (Vowel Length Precision)**: <Analysis>

---
### 💡 जिह्वा-स्थान-मार्गदर्शनम् (Tongue & Breath Guidance):
<Concrete, practical advice on mouth position and air release>
"""
            try:
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": rec_shiksha.getvalue()}},
                            {"text": PROMPT_SHIKSHA}
                        ]
                    }]
                )
                st.markdown(resp.text)
                st.session_state.xp_points += 15
            except Exception as e:
                st.error(f"Error evaluating audio: {str(e)}")


# =========================================================
# TAB 3: SHADOWING & FLUENCY PACING DRILLS
# =========================================================
with tab_shadow:
    st.subheader("🔁 Listen & Repeat (Shadowing & Pacing Drills)")
    st.caption("Build oral muscle memory and conversational cadence (Words Per Minute / WPM).")
    
    shadow_list = [
        "भवतः गृहं कुत्र अस्ति? मम गृहं समीपे एव अस्ति।",
        "अद्य अहं संस्कृत-सम्भाषण-वर्गे नूतन-शब्दान् अपठम्।",
        "यथा बीजं विना वृक्षः न भवति, तथा उद्योगं विना कार्यं न सिद्ध्यति।"
    ]
    
    s_choice = st.selectbox("Select Shadowing Passage:", shadow_list)
    
    st.write("🎧 **Step 1: Listen to Native Pacing**")
    play_sanskrit_audio(s_choice)
    
    st.write("🎙️ **Step 2: Shadow (Repeat in one continuous breath)**")
    shadow_user_audio = st.audio_input("Record your repetition:")
    
    if shadow_user_audio is not None:
        if not api_key:
            st.warning("⚠️ Please enter your Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Analyzing fluency cadence and speech pace..."):
            PROMPT_SHADOW = f"""You are a Sanskrit Fluency and Speech-Rate Assessor.
Target Reference: "{s_choice}"

Analyze the student's spoken audio:
1. Cadence & Rhythm: Natural sentence flow without unnatural pauses.
2. Estimated Words Per Minute (WPM) & Speech Pacing: [e.g. 60-80 WPM is ideal for beginners].
3. Native Language Interference: Did they apply English or mother-tongue stress patterns?
4. Fluency Score: (0-100%).

Format:
### ⚡ गतिः एवं धाराप्रवाहः (Fluency & Pacing Analysis):
- **Fluency Score**: [XX / 100]
- **Speed & Cadence**: <Speed commentary>
- **Rhythm & Anvaya Flow**: <Rhythm commentary>
- **Fluency Tip**: <How to link words smoothly with Sandhi>
"""
            try:
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": shadow_user_audio.getvalue()}},
                            {"text": PROMPT_SHADOW}
                        ]
                    }]
                )
                st.markdown(resp.text)
                st.session_state.xp_points += 15
            except Exception as e:
                st.error(f"Error: {str(e)}")


# =========================================================
# TAB 4: UNIVERSAL TRANSLATION ENGINE
# =========================================================
with tab_translate:
    st.subheader("🌐 Universal Multi-Language ↔ Sanskrit Translator")
    
    trans_mode = st.radio("Direction / दिशा", ["Any Language ➔ Sanskrit", "Sanskrit ➔ Any Language"], horizontal=True)
    
    if trans_mode == "Sanskrit ➔ Any Language":
        dest_lang = st.selectbox("Translate Into:", ["Telugu (తెలుగు)", "Hindi (हिन्दी)", "English", "Tamil (தமிழ்)", "Kannada (ಕನ್ನಡ)", "Marathi (मराठी)", "Malayalam (മലയാളം)"])
    
    t_input = st.text_area("Enter Text (or speak below):", height=80)
    t_voice = st.audio_input("Or speak input to translate:")
    
    if st.button("Execute Translation / अनुवादं कुरु") or (t_voice is not None):
        if not api_key:
            st.warning("⚠️ Please enter your Gemini API key in the sidebar.")
            st.stop()
        
        client = genai.Client(api_key=api_key)
        with st.spinner("अनुवादः प्रचलति..."):
            if trans_mode == "Any Language ➔ Sanskrit":
                PROMPT_T = f"""Translate into Sanskrit for level {level}.
MANDATORY FORMAT:
### 🪶 पूर्णवाक्यम् (Complete Sanskrit Sentence):
**संस्कृतम् (Devanagari):** <FULL TRANSLATED SENTENCE>
**IAST:** <Sentence in IAST>
**English Meaning:** <Complete English translation>

---
### 🔍 पदच्छेदः एवं व्याकरणम् (Word-by-Word Analysis):
- <Word>: <Pratipadika/Dhatu> + <Vibhakti/Pratyaya> — <Meaning>
"""
            else:
                PROMPT_T = f"""Translate this Sanskrit into {dest_lang} and English with Sandhi splits and word-by-word meanings."""

            if t_voice is not None:
                payload = [
                    {"inline_data": {"mime_type": "audio/wav", "data": t_voice.getvalue()}},
                    {"text": f"{PROMPT_T}\nTranscribe spoken audio and translate."}
                ]
            else:
                if not t_input.strip():
                    st.warning("Please enter text or audio.")
                    st.stop()
                payload = [{"text": f"{PROMPT_T}\nInput: {t_input}"}]

            try:
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{"role": "user", "parts": payload}],
                    config={"temperature": 0.2}
                )
                st.markdown(resp.text)
                if "संस्कृतम् (Devanagari):" in resp.text:
                    line = resp.text.split("संस्कृतम् (Devanagari):")[1].split("\n")[0].strip()
                    st.write("🔊 **उच्चारणम् (Audio):**")
                    play_sanskrit_audio(line)
            except Exception as e:
                st.error(f"Error: {str(e)}")


# =========================================================
# TAB 5: VYĀKARAṆA & PĀṆINIAN ENGINE
# =========================================================
with tab_grammar:
    st.subheader("🧩 पाणिनीय-व्याकरण-उपकरणम् (Paninian Grammar Engine)")
    
    g_tool = st.selectbox(
        "Select Tool / उपकरणम्:",
        [
            "Sandhi Splitter & Sūtra Rules (सन्धि-विच्छेदः)",
            "Shabdarupa Declension Tables (शब्दरूपाणि - 8 Vibhaktis)",
            "Dhaturoopa Conjugation (धातुरूपाणि - 10 Lakaras)",
            "Samāsa Analysis & Vigraha Vākya (समास-विग्रहः)"
        ]
    )
    g_query = st.text_input("Enter Word / Root / Compound (e.g. राम, भू, गम्, पीताम्बरः, देवेन्द्रः):")
    
    if st.button("Analyze Grammar / विश्लेषणं कुरु"):
        if not api_key:
            st.warning("⚠️ Please enter your Gemini API key.")
            st.stop()
        if not g_query.strip():
            st.warning("Please enter a term.")
            st.stop()
            
        client = genai.Client(api_key=api_key)
        with st.spinner("पाणिनीय-सूत्राणि अन्विष्यन्ते..."):
            try:
                resp = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[{"role": "user", "parts": [{"text": f"Provide comprehensive Paninian analysis for tool: {g_tool}, input: {g_query}. Include Astadhyayi Sutra references, markdown tables for all cases/purushas, and IAST."}]}],
                    config={"temperature": 0.1}
                )
                st.markdown(resp.text)
            except Exception as e:
                st.error(f"Error: {str(e)}")


# =========================================================
# TAB 6: SRS VOCABULARY VAULT & PARĪKṢĀ
# =========================================================
with tab_vault:
    st.subheader("🧠 Spaced Repetition (SRS) Vocabulary Vault & Parīkṣā")
    
    col_v1, col_v2 = st.columns([1, 1])
    with col_v1:
        st.write("### 📚 Personal Spaced Repetition Vault")
        st.caption("Words automatically surfaced at optimal recall intervals.")
        for item in st.session_state.vocab_vault:
            with st.container():
                st.markdown(f"**{item['word']}** — {item['meaning']} | *Root:* `{item['dhatu']}` | ⏳ Due: `{item['review_due']}`")
        
        with st.expander("➕ Manually Add Word to Vault"):
            nw = st.text_input("Sanskrit Word (पदम्):")
            nm = st.text_input("Meaning (अर्थः):")
            nd = st.text_input("Root / Pratipadika (मूलम्):")
            if st.button("Save to SRS Vault"):
                if nw and nm:
                    st.session_state.vocab_vault.append({"word": nw, "meaning": nm, "dhatu": nd if nd else nw, "level": "Learner", "review_due": "Tomorrow"})
                    st.session_state.xp_points += 5
                    st.success(f"Saved '{nw}' to your vault (+5 XP)!")
                    st.rerun()

    with col_v2:
        st.write("### 📝 Daily Interactive Parīkṣā (परीक्षा)")
        quiz_topic = st.selectbox("Drill Topic:", ["Vibhakti & Karaka Agreement", "Dhaturoopa & Lakara Tenses", "Sandhi Identification", "Spoken Idioms & Vocabulary"])
        
        if st.button("⚡ Generate Interactive Quiz"):
            if not api_key:
                st.warning("⚠️ Please enter your Gemini API key.")
                st.stop()
            client = genai.Client(api_key=api_key)
            with st.spinner("Generating 3-question MCQ quiz..."):
                try:
                    resp = client.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=[{"role": "user", "parts": [{"text": f"Generate a 3-question MCQ quiz on '{quiz_topic}' for Level: {level}. For each question: provide Devanagari, IAST, English, 4 options (A, B, C, D), the correct answer, and an Astadhyayi grammatical explanation."}]}],
                        config={"temperature": 0.2}
                    )
                    st.session_state.active_quiz = resp.text
                    st.session_state.xp_points += 10
                except Exception as e:
                    st.error(f"Error: {str(e)}")

        if st.session_state.active_quiz:
            st.markdown(st.session_state.active_quiz)
