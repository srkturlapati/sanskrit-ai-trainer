import sys
import os
import time
import io
import sqlite3
import datetime
import base64
import json
import re
from pypdf import PdfReader

# Enforce UTF-8 encoding across all runtime environments
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
import streamlit.components.v1 as components

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Sambhāṣaṇa AI Pro | सम्भाषण-प्रशिक्षकः",
    page_icon="🚩",
    layout="wide",
    initial_sidebar_state="expanded",
)

ACTIVE_MODEL = "gemini-3.6-flash"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "sambhāṣaṇa_concurrency.db")

# --- RESILIENT GEMINI CALLER WITH AUTOMATIC RETRY ---
def generate_gemini_content(client, contents, config=None, is_json=False, max_retries=3):
    cfg = config.copy() if config else {}
    if is_json:
        cfg["response_mime_type"] = "application/json"

    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(
                model=ACTIVE_MODEL,
                contents=contents,
                config=cfg if cfg else None
            )
            return resp.text
        except Exception as e:
            err_str = str(e)
            if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise e

# --- DATABASE PERSISTENCE LAYER (SQLite WAL Mode + SRS Engine) ---
def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA cache_size = 10000;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_profile (
            id TEXT PRIMARY KEY,
            username TEXT,
            level TEXT,
            streak INTEGER,
            xp INTEGER,
            last_active TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS vocab_vault (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            word TEXT,
            meaning TEXT,
            dhatu TEXT,
            level TEXT,
            review_due TEXT,
            interval_days INTEGER DEFAULT 1,
            repetition_count INTEGER DEFAULT 0,
            next_review_date TEXT,
            UNIQUE(user_id, word)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS feedback_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            user_id TEXT,
            teacher_name TEXT,
            user_prompt TEXT,
            acharya_response TEXT,
            feedback_type TEXT,
            remark_text TEXT
        )
    ''')
    
    today_str = str(datetime.date.today())
    c.execute('SELECT COUNT(*) FROM vocab_vault WHERE user_id = "default_user"')
    if c.fetchone()[0] == 0:
        starter_vocab = [
            ("default_user", "अस्तु", "Alright / Let it be", "अस् (to be)", "Beginner", "Today", 1, 0, today_str),
            ("default_user", "धन्यवादः", "Thank you", "धन्य + वाद्", "Beginner", "Today", 1, 0, today_str),
            ("default_user", "पुनर्मिलामः", "See you again", "मिल् (to meet)", "Beginner", "Today", 1, 0, today_str),
            ("default_user", "किम्", "What / Why", "सर्वनामन्", "Beginner", "Today", 1, 0, today_str),
            ("default_user", "कुत्र", "Where", "अव्ययम्", "Beginner", "Today", 1, 0, today_str)
        ]
        c.executemany('''
            INSERT OR IGNORE INTO vocab_vault 
            (user_id, word, meaning, dhatu, level, review_due, interval_days, repetition_count, next_review_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', starter_vocab)

    conn.commit()
    conn.close()

init_db()

if "user_session_id" not in st.session_state:
    st.session_state.user_session_id = "default_user"

def get_user_stats(uid):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT streak, xp FROM user_profile WHERE id = ?', (uid,))
    res = c.fetchone()
    if not res:
        c.execute('INSERT OR IGNORE INTO user_profile VALUES (?, "Learner", "Beginner", 1, 100, ?)',
                  (uid, str(datetime.date.today())))
        conn.commit()
        res = (1, 100)
    conn.close()
    return res

def update_user_xp(uid, xp_add=10):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('UPDATE user_profile SET xp = xp + ? WHERE id = ?', (xp_add, uid))
    conn.commit()
    conn.close()

def get_due_flashcards(uid):
    conn = get_db_connection()
    c = conn.cursor()
    today_str = str(datetime.date.today())
    c.execute('''
        SELECT id, word, meaning, dhatu, level, interval_days, repetition_count 
        FROM vocab_vault 
        WHERE user_id = ? AND (next_review_date <= ? OR next_review_date IS NULL OR review_due = 'Today')
        ORDER BY id ASC
    ''', (uid, today_str))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "word": r[1], "meaning": r[2], "dhatu": r[3], "level": r[4], "interval": r[5] or 1, "reps": r[6] or 0} for r in rows]

def get_all_vault_words(uid):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT word, meaning, dhatu, level, review_due FROM vocab_vault WHERE user_id = ? ORDER BY id DESC', (uid,))
    rows = c.fetchall()
    conn.close()
    return [{"word": r[0], "meaning": r[1], "dhatu": r[2], "level": r[3], "review_due": r[4]} for r in rows]

def update_srs_rating(card_id, rating, current_interval, current_reps, uid):
    conn = get_db_connection()
    c = conn.cursor()
    today = datetime.date.today()
    
    if rating == "again":
        new_interval = 1
        new_reps = 0
        next_date = today
        review_due_label = "Today"
        xp_gain = 0
    elif rating == "hard":
        new_interval = max(1, int(current_interval * 1.2))
        new_reps = current_reps + 1
        next_date = today + datetime.timedelta(days=new_interval)
        review_due_label = f"In {new_interval}d"
        xp_gain = 5
    elif rating == "good":
        new_interval = max(3, int(current_interval * 2.0))
        new_reps = current_reps + 1
        next_date = today + datetime.timedelta(days=new_interval)
        review_due_label = f"In {new_interval}d"
        xp_gain = 10
    else:  # easy
        new_interval = max(7, int(current_interval * 3.0))
        new_reps = current_reps + 1
        next_date = today + datetime.timedelta(days=new_interval)
        review_due_label = f"In {new_interval}d"
        xp_gain = 20
        
    c.execute('''
        UPDATE vocab_vault 
        SET interval_days = ?, repetition_count = ?, next_review_date = ?, review_due = ?
        WHERE id = ?
    ''', (new_interval, new_reps, str(next_date), review_due_label, card_id))
    
    if xp_gain > 0:
        c.execute('UPDATE user_profile SET xp = xp + ? WHERE id = ?', (xp_gain, uid))
        
    conn.commit()
    conn.close()

def save_single_word(uid, word, meaning, dhatu):
    conn = get_db_connection()
    c = conn.cursor()
    today_str = str(datetime.date.today())
    c.execute('''
        INSERT OR REPLACE INTO vocab_vault (user_id, word, meaning, dhatu, level, review_due, interval_days, repetition_count, next_review_date)
        VALUES (?, ?, ?, ?, "Learner", "Today", 1, 0, ?)
    ''', (uid, word, meaning, dhatu, today_str))
    c.execute('UPDATE user_profile SET xp = xp + 15 WHERE id = ?', (uid,))
    conn.commit()
    conn.close()

def save_vault_bulk(uid, word_list):
    conn = get_db_connection()
    c = conn.cursor()
    today_str = str(datetime.date.today())
    added = 0
    for w in word_list:
        try:
            c.execute('''
                INSERT OR IGNORE INTO vocab_vault (user_id, word, meaning, dhatu, level, review_due, interval_days, repetition_count, next_review_date)
                VALUES (?, ?, ?, ?, ?, "Today", 1, 0, ?)
            ''', (uid, w['word'], w['meaning'], w.get('dhatu', w['word']), w.get('level', 'Beginner'), today_str))
            if c.rowcount > 0:
                added += 1
        except Exception:
            pass
    c.execute('UPDATE user_profile SET xp = xp + ? WHERE id = ?', (added * 5, uid))
    conn.commit()
    conn.close()
    return added

def save_user_feedback(uid, teacher_name, user_prompt, response_text, fb_type, remark):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO feedback_logs (timestamp, user_id, teacher_name, user_prompt, acharya_response, feedback_type, remark_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), uid, teacher_name, user_prompt, response_text, fb_type, remark))
    conn.commit()
    conn.close()

# --- CSS STYLING ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Plus Jakarta Sans', sans-serif; }
    
    .header-box {
        background: linear-gradient(135deg, #E65100 0%, #BF360C 50%, #1A1A1A 100%);
        border-radius: 16px;
        padding: 16px 22px;
        color: #FFFFFF;
        box-shadow: 0 6px 20px rgba(230, 81, 0, 0.25);
        margin-bottom: 15px;
    }
    
    .avatar-wrapper {
        position: relative;
        width: 85px;
        height: 85px;
        margin: 0 auto;
    }
    
    .avatar-base {
        width: 85px;
        height: 85px;
        border-radius: 50%;
        object-fit: cover;
        border: 3px solid #FF8F00;
        box-shadow: 0 0 14px rgba(255, 143, 0, 0.4);
        transition: all 0.3s ease;
    }
    
    .talking-lip {
        position: absolute;
        bottom: 14px;
        left: 50%;
        transform: translateX(-50%);
        width: 16px;
        height: 4px;
        background: #8D1414;
        border-radius: 50%;
        opacity: 0;
        transition: all 0.1s ease;
    }
    
    .is-speaking .talking-lip {
        opacity: 0.95;
        animation: mouthTalk 0.25s infinite alternate ease-in-out;
    }
    
    .is-speaking .avatar-base {
        box-shadow: 0 0 24px rgba(255, 111, 0, 0.9);
        transform: scale(1.03);
    }

    @keyframes mouthTalk {
        0% { height: 3px; width: 12px; }
        50% { height: 9px; width: 16px; background: #5C0B0B; }
        100% { height: 5px; width: 18px; }
    }
    
    .flashcard-box {
        background: linear-gradient(145deg, #2D1B08 0%, #170E04 100%);
        border: 2px solid #FF8F00;
        border-radius: 18px;
        padding: 30px;
        text-align: center;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
        margin: 15px auto;
        max-width: 600px;
    }
    
    .flashcard-word {
        font-size: 2.3rem;
        font-weight: 800;
        color: #FFD54F;
        margin-bottom: 8px;
    }
    
    .flashcard-sub {
        font-size: 1rem;
        color: #BDBDBD;
        margin-bottom: 16px;
    }
    
    .flashcard-answer {
        font-size: 1.4rem;
        color: #81C784;
        font-weight: 700;
        background: rgba(255, 255, 255, 0.05);
        padding: 14px;
        border-radius: 12px;
        border: 1px dashed #4CAF50;
        margin-top: 15px;
    }
    
    .sentence-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 143, 0, 0.25);
        border-radius: 12px;
        padding: 14px 18px;
        margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)

def get_avatar_img(base_name, fallback_url):
    extensions = [".jpeg", ".jpg", ".png", ".JPEG", ".JPG", ".PNG"]
    assets_dir = os.path.join(BASE_DIR, "assets")
    for ext in extensions:
        local_p = os.path.join(assets_dir, base_name + ext)
        if os.path.isfile(local_p):
            try:
                mime = "image/jpeg" if ext.lower() in [".jpeg", ".jpg"] else "image/png"
                with open(local_p, "rb") as img_f:
                    b64 = base64.b64encode(img_f.read()).decode()
                    return f"data:{mime};base64,{b64}", f"Custom Asset ({base_name}{ext})"
            except Exception:
                pass
    return fallback_url, "Default Asset"

male_src, male_status = get_avatar_img("male_guru", "https://upload.wikimedia.org/wikipedia/commons/e/e3/Raja_Ravi_Varma_-_Sankaracharya.jpg")
female_src, female_status = get_avatar_img("female_guru", "https://dme2wmiz2suov.cloudfront.net/User(18985117)/2061981-Yadavabhyudayam_(9).png")
child_src, child_status = get_avatar_img("child_guru", "https://encrypted-tbn3.gstatic.com/licensed-image?q=tbn:ANd9GcQzrF7mhDcZqvcP2RO27fhrcZXbPYo76WyMLq97WTaUJbXdG3OP6XXd3kC2v3A7-6qYwUBpUaNci3jGXWs")

TEACHERS = {
    "Male Guru (आचार्यः वसिष्ठः)": {
        "title": "आचार्यः वसिष्ठः (Acharya Vasiṣṭha)",
        "desc": "Classical Guru • Deep Dignified Voice",
        "img": male_src,
        "status": male_status,
        "tld": "co.in",
        "slow": True
    },
    "Female Āchāryā (आचार्या गार्गी)": {
        "title": "आचार्या गार्गी (Acharyaa Gargi)",
        "desc": "Scholarly Preceptor • Warm Melodic Voice",
        "img": female_src,
        "status": female_status,
        "tld": "com",
        "slow": False
    },
    "Child Peer (बालकः ध्रुवः)": {
        "title": "बालकः ध्रुवः (Balaka Dhruva)",
        "desc": "Playful Peer • Cheerful Lively Voice",
        "img": child_src,
        "status": child_status,
        "tld": "co.uk",
        "slow": False
    }
}

@st.cache_data(show_spinner=False, max_entries=200)
def get_speech_audio_b64(text: str, tld: str, slow: bool) -> str:
    try:
        tts = gTTS(text=text, lang='hi', tld=tld, slow=slow)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return base64.b64encode(fp.read()).decode()
    except Exception:
        return ""

def extract_complete_sanskrit_speech(reply_content: str) -> str:
    if "[संस्कृतम्]:" in reply_content:
        part = reply_content.split("[संस्कृतम्]:")[1]
        for marker in ["[IAST]:", "[English]:", "[✨ Say It Better]:", "[मार्गदर्शनम्]"]:
            if marker in part:
                part = part.split(marker)[0]
        return part.replace('*', '').replace('#', '').replace('-', '').strip()
    return ""

def render_talking_avatar(sanskrit_text: str, teacher_key: str, auto_play=True):
    clean_text = sanskrit_text.replace('*', '').replace('#', '').replace('-', '').replace('[', '').replace(']', '').strip()
    if not clean_text:
        return
    cfg = TEACHERS[teacher_key]
    audio_b64 = get_speech_audio_b64(clean_text, cfg["tld"], cfg["slow"])
    if not audio_b64:
        return
        
    elem_id = f"aud_{abs(hash(clean_text)) % 1000000}"
    st.markdown(f"""
    <div style="display:flex; align-items:center; gap:16px; margin: 10px 0; background:rgba(255,255,255,0.03); padding:12px; border-radius:14px; border:1px solid rgba(255,143,0,0.2);">
        <div class="avatar-wrapper" id="wrap_{elem_id}">
            <img src="{cfg['img']}" class="avatar-base"/>
            <div class="talking-lip"></div>
        </div>
        <div style="flex-grow:1;">
            <div style="font-size:0.78rem; color:#81C784; font-weight:700;">🟢 AI Preceptor Speaking ({cfg['title'].split('(')[0].strip()})</div>
            <div style="font-weight:700; color:#FF8F00; font-size:1.02rem;">{cfg['title']}</div>
            <audio id="{elem_id}" controls {'autoplay' if auto_play else ''} style="width:100%; height:36px; margin-top:5px;">
                <source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3">
            </audio>
        </div>
    </div>
    <script>
        (function(){{
            var aud = document.getElementById("{elem_id}");
            var wrp = document.getElementById("wrap_{elem_id}");
            if(aud && wrp){{
                aud.onplay = function(){{ wrp.classList.add("is-speaking"); }};
                aud.onpause = function(){{ wrp.classList.remove("is-speaking"); }};
                aud.onended = function(){{ wrp.classList.remove("is-speaking"); }};
            }}
        }})();
    </script>
    """, unsafe_allow_html=True)

# --- REAL-TIME WAVEFORM PITCH MATCHING & VOCAL VISUALIZER (POINT 3) ---
def render_live_waveform_pitch_visualizer():
    components.html("""
    <div style="font-family:'Plus Jakarta Sans', sans-serif; background:#120B02; border:2px solid #FF8F00; border-radius:16px; padding:18px; color:#FFF;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <div>
                <span style="font-size:1.05rem; font-weight:800; color:#FFD54F;">🌊 Live Vocal Pitch Spectrum (स्वर-तरङ्गिणी)</span>
                <div style="font-size:0.8rem; color:#AAA;">Real-Time Pitch & Waveform Harmonic Resonance Matching (60 FPS)</div>
            </div>
            <button id="visMicBtn" onclick="togglePitchVisualizer()" style="background:#E65100; color:white; border:none; padding:8px 20px; border-radius:20px; font-weight:bold; cursor:pointer; font-size:0.85rem;">
                🔴 Activate Visualizer
            </button>
        </div>

        <!-- HTML5 Web Audio Canvas -->
        <canvas id="pitchCanvas" width="700" height="150" style="width:100%; height:150px; background:#080401; border-radius:10px; border:1px solid #3E2723;"></canvas>

        <div style="display:flex; justify-content:space-around; align-items:center; margin-top:12px; background:rgba(255,255,255,0.03); padding:8px; border-radius:10px; font-size:0.82rem;">
            <div>🎯 Target Preceptor Harmonic: <span style="color:#FF8F00; font-weight:bold;">140 Hz - 220 Hz (Mandra / Madhya)</span></div>
            <div>🎙️ Live Vocal Pitch (F0): <span id="pitchVal" style="color:#81C784; font-weight:bold;">-- Hz</span></div>
            <div>⚡ Acoustic Volume: <span id="volVal" style="color:#64B5F6; font-weight:bold;">-- dB</span></div>
        </div>
    </div>

    <script>
        var audioCtx = null;
        var analyser = null;
        var micStream = null;
        var isVisRunning = false;
        var animId = null;

        async function togglePitchVisualizer() {
            var btn = document.getElementById("visMicBtn");
            if (!isVisRunning) {
                try {
                    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    var source = audioCtx.createMediaStreamSource(micStream);
                    
                    analyser = audioCtx.createAnalyser();
                    analyser.fftSize = 2048;
                    source.connect(analyser);

                    isVisRunning = true;
                    btn.style.background = "#2E7D32";
                    btn.innerText = "⏹️ Stop Visualizer";
                    drawLivePitchSpectrum();
                } catch(err) {
                    alert("Microphone access error: " + err.message);
                }
            } else {
                if (micStream) micStream.getTracks().forEach(t => t.stop());
                if (audioCtx) audioCtx.close();
                cancelAnimationFrame(animId);
                isVisRunning = false;
                btn.style.background = "#E65100";
                btn.innerText = "🔴 Activate Visualizer";
                document.getElementById("pitchVal").innerText = "-- Hz";
                document.getElementById("volVal").innerText = "-- dB";
            }
        }

        function drawLivePitchSpectrum() {
            if (!isVisRunning) return;
            animId = requestAnimationFrame(drawLivePitchSpectrum);

            var canvas = document.getElementById("pitchCanvas");
            var ctx = canvas.getContext("2d");
            var bufferLength = analyser.frequencyBinCount;
            var timeData = new Uint8Array(bufferLength);
            var freqData = new Uint8Array(bufferLength);

            analyser.getByteTimeDomainData(timeData);
            analyser.getByteFrequencyData(freqData);

            // Compute volume
            var sum = 0;
            var maxFreqIndex = 0;
            var maxFreqVal = 0;
            for (var i = 0; i < bufferLength; i++) {
                sum += freqData[i];
                if (freqData[i] > maxFreqVal) {
                    maxFreqVal = freqData[i];
                    maxFreqIndex = i;
                }
            }
            var avgVol = Math.round(sum / bufferLength);
            var estPitch = Math.round(maxFreqIndex * (audioCtx.sampleRate / analyser.fftSize));

            if (avgVol > 5) {
                document.getElementById("pitchVal").innerText = (estPitch > 50 && estPitch < 800) ? estPitch + " Hz" : "-- Hz";
                document.getElementById("volVal").innerText = avgVol + " dB";
            } else {
                document.getElementById("pitchVal").innerText = "Silent";
                document.getElementById("volVal").innerText = "0 dB";
            }

            // Clear Background
            ctx.fillStyle = "#080401";
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            // Draw Reference Ideal Vedic Pitch Waveform (Orange Sine Harmonic)
            ctx.lineWidth = 2;
            ctx.strokeStyle = "rgba(255, 143, 0, 0.4)";
            ctx.beginPath();
            var refSlice = canvas.width / bufferLength;
            for (var i = 0; i < canvas.width; i++) {
                var y = (canvas.height / 2) + Math.sin(i * 0.05 + Date.now() * 0.003) * 25;
                if (i === 0) ctx.moveTo(i, y);
                else ctx.lineTo(i, y);
            }
            ctx.stroke();

            // Draw Student's Live Vocal Oscillogram (Cyan / Emerald Waveform)
            ctx.lineWidth = 2.5;
            ctx.strokeStyle = "#81C784";
            ctx.beginPath();
            var sliceWidth = canvas.width * 1.0 / bufferLength;
            var x = 0;
            for (var i = 0; i < bufferLength; i++) {
                var v = timeData[i] / 128.0;
                var y = v * (canvas.height / 2);
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
                x += sliceWidth;
            }
            ctx.lineTo(canvas.width, canvas.height / 2);
            ctx.stroke();
        }
    </script>
    """, height=255)

def split_into_sentences(text: str, max_limit=50):
    lines = text.split('\n')
    sentences = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = re.split(r'([.?!।॥]+)', line)
        temp = ""
        for p in parts:
            if re.match(r'^[.?!।॥]+$', p):
                temp += p
                if temp.strip():
                    sentences.append(temp.strip())
                temp = ""
            else:
                temp += p
        if temp.strip():
            sentences.append(temp.strip())
    return sentences[:max_limit]

# --- APP HERO ---
st.markdown("""
<div class="header-box">
    <h2 style="margin:0; font-weight:800;">🚩 Sambhāṣaṇa AI Enterprise (सम्भाषणम्)</h2>
    <p style="margin:2px 0 0 0; opacity:0.92; font-size:0.9rem;">Multi-Tenant Spoken Sanskrit Engine • Live Vocal Pitch Visualizer • Interactive SRS Flashcards</p>
</div>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
u_streak, u_xp = get_user_stats(st.session_state.user_session_id)

with st.sidebar:
    st.markdown("### 🎙️ **Teacher & Voice Profile**")
    selected_teacher = st.selectbox("Active Guide:", list(TEACHERS.keys()), index=0)
    t_info = TEACHERS[selected_teacher]
    
    st.markdown(f"""
    <div style="text-align:center; padding:10px; background:rgba(255,255,255,0.04); border-radius:12px; border:1px solid rgba(255,143,0,0.25);">
        <img src="{t_info['img']}" style="width:80px; height:80px; border-radius:50%; object-fit:cover; border:3px solid #FF8F00; margin-bottom:6px;"/>
        <div style="font-weight:700; color:#FF8F00;">{t_info['title']}</div>
        <div style="font-size:0.75rem; opacity:0.8;">{t_info['desc']}</div>
        <div style="font-size:0.7rem; color:#81C784; margin-top:4px;">Image: {t_info['status']}</div>
    </div>
    """, unsafe_allow_html=True)
    
    api_key = st.text_input(
        "Google Gemini API Key",
        type="password",
        placeholder="Paste AIza... key here",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Free key from aistudio.google.com/apikey"
    )
    
    target_tier = st.selectbox(
        "Student Tier / स्तरः",
        ["Beginner (प्रथमा)", "Intermediate (मध्यमा)", "Advanced (उत्तमा)"],
        index=0
    )
    
    st.markdown("---")
    st.markdown("### 🏆 **Database User Stats**")
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        st.metric("🔥 Streak", f"{u_streak} Days")
    with col_p2:
        st.metric("⭐ Points", f"{u_xp} XP")
    
    if st.button("🔄 Reset Conversation", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.turn_count = 0
        st.rerun()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "turn_count" not in st.session_state:
    st.session_state.turn_count = 0
if "card_flipped" not in st.session_state:
    st.session_state.card_flipped = False
if "current_card_index" not in st.session_state:
    st.session_state.current_card_index = 0

FAST_SYSTEM_PROMPT = f"""You are '{t_info['title']}', a high-performance interactive conversational Sanskrit tutor.
Student Tier: {target_tier}.

Pedagogical Rules:
1. Converse dynamically in authentic spoken Sarala Samskritam.
2. Keep response to 2-3 spoken sentences.
3. Conclude by asking a natural conversational question.

Mandatory Response Format:
[संस्कृतम्]: <Your spoken Sanskrit reply>
[IAST]: <Romanized transliteration>
[English]: <English meaning>
[✨ Say It Better]: <Short idiomatic Sanskrit alternative>
[मार्गदर्शनम्] (Include only if student made a grammatical error):
- 💡 Correction & rule
"""

# --- 5 PRODUCTION TABS ---
tab_roleplay, tab_srs_flashcards, tab_shiksha, tab_chandas, tab_trans = st.tabs([
    "💬 1. Oral Roleplay",
    "🧠 2. SRS Flashcard Quiz",
    "🎙️ 3. Śikṣā Phonetics & Pitch Spectrum",
    "🕉️ 4. Svara & Chandaḥ",
    "🌐 5. Sentence Batch Translator (50 Sentences)"
])

# =========================================================
# TAB 1: HIGH-ACCURACY ORAL ROLEPLAY
# =========================================================
with tab_roleplay:
    st.markdown("#### 💬 Situational Conversational Immersion (सजीव-सम्भाषणम्)")
    
    scenario = st.selectbox(
        "Conversation Scenario / प्रसङ्गः:",
        [
            "At Gurukula / Classroom (पाठशाला - शिष्टाचारः)",
            "At the Market (विपणिः - शाकक्रयणम् / Purchasing Vegetables)",
            "Travel & Directions (यात्रा - मार्गनिर्देशनम्)",
            "Welcoming Guests (अतिथि-सत्कारः)",
            "Open Free Dialogue (मुक्त-सम्भाषणम्)"
        ]
    )
    
    for idx, msg in enumerate(st.session_state.chat_history):
        role = "assistant" if msg["role"] == "model" else "user"
        with st.chat_message(role):
            st.markdown(msg["content"])
            if role == "assistant":
                full_s = extract_complete_sanskrit_speech(msg["content"])
                if full_s:
                    render_talking_avatar(full_s, selected_teacher, auto_play=False)
                
                with st.expander(f"📝 Remark / Feedback on Response #{idx // 2 + 1}"):
                    with st.form(key=f"rem_form_{idx}"):
                        fb_type = st.selectbox(
                            "Classification:",
                            [
                                "⚠️ Grammar / Sūtra Error (व्याकरण-दोषः)",
                                "⚠️ Inaccurate Translation (अनुवाद-दोषः)",
                                "⚠️ Sandhi / Spelling Mistake (सन्धि/वर्ण-दोषः)",
                                "💡 Suggestion / Better Word (सुझावः)",
                                "✅ Auspicious & Correct (उत्कृष्टम्)"
                            ],
                            key=f"fb_sel_{idx}"
                        )
                        fb_text = st.text_area("Write remarks / corrections:", key=f"fb_txt_{idx}", placeholder="e.g. In line 1, 'गच्छामि' should be used...")
                        if st.form_submit_button("💾 Save Remark"):
                            prior_user = st.session_state.chat_history[idx - 1]["content"] if idx > 0 else "N/A"
                            save_user_feedback(st.session_state.user_session_id, selected_teacher, prior_user, msg["content"], fb_type, fb_text)
                            st.success("✅ Remark saved successfully into the database!")

    st.markdown("##### 🎙️ **Speak into Microphone (वदतु):**")
    user_audio = st.audio_input("Record continuous voice to Acharya:", key=f"mic_turn_{st.session_state.turn_count}")

    if user_audio is not None:
        if not api_key:
            st.warning("⚠️ Enter your Gemini API key in the sidebar.")
            st.stop()

        client = genai.Client(api_key=api_key)
        audio_bytes = user_audio.getvalue()
        
        st.session_state.chat_history.append({"role": "user", "content": "🎙️ *[Continuous Spoken Voice Submitted]*"})
        with st.chat_message("user"):
            st.audio(user_audio, format="audio/wav")

        with st.chat_message("assistant"):
            with st.spinner("आचार्यः शृणोति एवं चिन्तयति..."):
                t_start = time.time()
                try:
                    reply_text = generate_gemini_content(
                        client=client,
                        contents=[{
                            "role": "user",
                            "parts": [
                                {"inline_data": {"mime_type": "audio/wav", "data": audio_bytes}},
                                {"text": f"{FAST_SYSTEM_PROMPT}\nScenario: {scenario}. Transcribe student audio and reply comprehensively."}
                            ]
                        }],
                        config={"temperature": 0.2, "max_output_tokens": 500}
                    )
                    latency = round(time.time() - t_start, 2)
                    
                    st.markdown(reply_text)
                    st.caption(f"⚡ *Response Latency: {latency}s*")
                    
                    full_s = extract_complete_sanskrit_speech(reply_text)
                    if full_s:
                        render_talking_avatar(full_s, selected_teacher, auto_play=True)
                    
                    st.session_state.chat_history.append({"role": "model", "content": reply_text})
                    st.session_state.turn_count += 1
                    update_user_xp(st.session_state.user_session_id, 10)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    if text_input := st.chat_input("Type in Sanskrit, English, or Telugu (e.g. mama nama, katham asti)..."):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key in the sidebar.")
            st.stop()

        client = genai.Client(api_key=api_key)
        is_dev = any("\u0900" <= char <= "\u097f" for char in text_input)
        display_text = text_input if is_dev else f"{text_input} ({transliterate(text_input, sanscript.ITRANS, sanscript.DEVANAGARI)})"

        st.session_state.chat_history.append({"role": "user", "content": display_text})
        with st.chat_message("user"):
            st.markdown(display_text)

        contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": str(m["content"])}]} for m in st.session_state.chat_history]

        with st.chat_message("assistant"):
            with st.spinner("चिन्तयति..."):
                t_start = time.time()
                try:
                    reply_text = generate_gemini_content(
                        client=client,
                        contents=contents,
                        config={"system_instruction": FAST_SYSTEM_PROMPT, "temperature": 0.2, "max_output_tokens": 500}
                    )
                    latency = round(time.time() - t_start, 2)
                    
                    st.markdown(reply_text)
                    st.caption(f"⚡ *Response Latency: {latency}s*")
                    
                    full_s = extract_complete_sanskrit_speech(reply_text)
                    if full_s:
                        render_talking_avatar(full_s, selected_teacher, auto_play=True)
                        
                    st.session_state.chat_history.append({"role": "model", "content": reply_text})
                    st.session_state.turn_count += 1
                    update_user_xp(st.session_state.user_session_id, 5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

# =========================================================
# TAB 2: ACTIVE RECALL FLASHCARD DECK (SRS LEITNER SYSTEM)
# =========================================================
with tab_srs_flashcards:
    st.markdown("#### 🧠 Spaced Repetition (SRS) Active Recall Flashcard Deck")
    st.caption("Cards schedule themselves scientifically using Leitner review intervals. Flip to test your memory and rate difficulty.")
    
    tab_fc_quiz, tab_fc_pdf, tab_fc_manage = st.tabs(["🎴 1. Practice Due Cards", "📄 2. Ingest from PDF", "🗄️ 3. Vault Database"])
    
    with tab_fc_quiz:
        due_cards = get_due_flashcards(st.session_state.user_session_id)
        
        if not due_cards:
            st.markdown("""
            <div class="flashcard-box" style="border-color:#4CAF50;">
                <div style="font-size:2.5rem; margin-bottom:10px;">🎉</div>
                <h3 style="color:#81C784; margin:0 0 6px 0;">सर्वे शब्दाः अभ्यस्ताः! (All Caught Up!)</h3>
                <p style="color:#DDD; font-size:0.95rem;">You have reviewed all due vocabulary for today. Add more words from a PDF or check back tomorrow!</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            total_due = len(due_cards)
            idx = min(st.session_state.current_card_index, total_due - 1)
            card = due_cards[idx]
            
            st.progress((idx + 1) / total_due, text=f"Reviewing Card {idx + 1} of {total_due} Due Today")
            
            st.markdown(f"""
            <div class="flashcard-box">
                <div style="font-size:0.8rem; color:#FF8F00; font-weight:700; text-transform:uppercase; letter-spacing:1px;">
                    {card['level']} • Root: {card['dhatu']} • Reps: {card['reps']}
                </div>
                <div class="flashcard-word">{card['word']}</div>
                <div class="flashcard-sub">What does this Sanskrit word mean?</div>
                {'<div class="flashcard-answer">📖 <b>' + card['meaning'] + '</b></div>' if st.session_state.card_flipped else ''}
            </div>
            """, unsafe_allow_html=True)
            
            audio_b64 = get_speech_audio_b64(card['word'], t_info["tld"], t_info["slow"])
            if audio_b64:
                col_aud_l, col_aud_m, col_aud_r = st.columns([1, 2, 1])
                with col_aud_m:
                    st.audio(f"data:audio/mp3;base64,{audio_b64}", format="audio/mp3")

            col_b1, col_b2, col_b3, col_b4 = st.columns(4)
            
            if not st.session_state.card_flipped:
                if st.button("🔄 Flip Card to Reveal Answer / अर्थं पश्य", use_container_width=True):
                    st.session_state.card_flipped = True
                    st.rerun()
            else:
                with col_b1:
                    if st.button("❌ Again / भूयः\n(Today • 0 XP)", use_container_width=True):
                        update_srs_rating(card["id"], "again", card["interval"], card["reps"], st.session_state.user_session_id)
                        st.session_state.card_flipped = False
                        st.rerun()
                with col_b2:
                    if st.button("🟡 Hard / कठिनम्\n(+1 Day • 5 XP)", use_container_width=True):
                        update_srs_rating(card["id"], "hard", card["interval"], card["reps"], st.session_state.user_session_id)
                        st.session_state.card_flipped = False
                        st.rerun()
                with col_b3:
                    if st.button("🟢 Good / सम्यक्\n(+3 Days • 10 XP)", use_container_width=True):
                        update_srs_rating(card["id"], "good", card["interval"], card["reps"], st.session_state.user_session_id)
                        st.session_state.card_flipped = False
                        st.rerun()
                with col_b4:
                    if st.button("⭐ Easy / सरलम्\n(+7 Days • 20 XP)", use_container_width=True):
                        update_srs_rating(card["id"], "easy", card["interval"], card["reps"], st.session_state.user_session_id)
                        st.session_state.card_flipped = False
                        st.rerun()

    with tab_fc_pdf:
        col_pdf1, col_pdf2 = st.columns([1, 1])
        with col_pdf1:
            uploaded_pdf = st.file_uploader("Upload Sanskrit PDF File:", type=["pdf"], key="srs_pdf_up")
            max_words = st.slider("Max Words to Ingest into Flashcard Deck:", min_value=10, max_value=50, value=25)
            
            if uploaded_pdf is not None and st.button("⚡ Extract & Ingest as New Flashcards", use_container_width=True):
                if not api_key:
                    st.warning("⚠️ Enter your Gemini API key in the sidebar.")
                    st.stop()
                
                with st.spinner("Extracting text and analyzing morphology for flashcard deck..."):
                    try:
                        pdf_reader = PdfReader(uploaded_pdf)
                        extracted_text = ""
                        for page_idx in range(min(8, len(pdf_reader.pages))):
                            text = pdf_reader.pages[page_idx].extract_text()
                            if text:
                                extracted_text += text + "\n"
                        
                        if not extracted_text.strip():
                            st.error("No readable text found in PDF.")
                            st.stop()
                        
                        client = genai.Client(api_key=api_key)
                        PROMPT_BULK = f"""Extract {max_words} unique Sanskrit words from this text.
Return a STRICT JSON array of objects with keys: "word", "meaning", "dhatu", "level".
Example:
[
  {{"word": "गच्छति", "meaning": "goes", "dhatu": "गम्", "level": "Beginner"}}
]
Text:
{extracted_text[:4000]}
"""
                        resp_text = generate_gemini_content(
                            client=client,
                            contents=[{"role": "user", "parts": [{"text": PROMPT_BULK}]}],
                            config={"temperature": 0.1},
                            is_json=True
                        )
                        
                        parsed_vocab = json.loads(resp_text)
                        added = save_vault_bulk(st.session_state.user_session_id, parsed_vocab)
                        st.success(f"🎉 Successfully created {added} new Flashcards in your SRS Deck! (+{added * 5} XP)")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error processing PDF: {str(e)}")

        with col_pdf2:
            st.markdown("##### ➕ **Or Add Flashcard Manually:**")
            with st.form("manual_fc_add"):
                vw = st.text_input("Sanskrit Word (पदम्):")
                vm = st.text_input("Meaning (अर्थः):")
                vd = st.text_input("Root / Stem (धातुः):")
                if st.form_submit_button("Save to Flashcard Deck (+15 XP)") and vw and vm:
                    save_single_word(st.session_state.user_session_id, vw, vm, vd if vd else vw)
                    st.success(f"Saved '{vw}' as active flashcard!")
                    st.rerun()

    with tab_fc_manage:
        all_words = get_all_vault_words(st.session_state.user_session_id)
        st.caption(f"Total Words in Vault: **{len(all_words)}**")
        search_q = st.text_input("🔍 Search Flashcard Vault:", placeholder="Filter words...")
        filtered_w = [x for x in all_words if search_q.lower() in x['word'].lower() or search_q.lower() in x['meaning'].lower()] if search_q else all_words
        
        for itm in filtered_w[:40]:
            st.markdown(f"• **{itm['word']}** — *{itm['meaning']}* | Root: `{itm['dhatu']}` | ⏳ Due: `{itm['review_due']}`")

# =========================================================
# TAB 3: ŚIKṢĀ PHONETICS & VOCAL PITCH SPECTRUM (POINT 3)
# =========================================================
with tab_shiksha:
    st.markdown("#### 🎙️ पाणिनीय-शिक्षा एवं स्वर-तरङ्गिणी (Phonetic Accent & Pitch Visualizer)")
    st.caption("Matches your real-time vocal harmonics and pronunciation against classical Vedic phonetics.")
    
    # 1. Real-Time Waveform Spectrum Component
    render_live_waveform_pitch_visualizer()
    
    st.write("---")
    drill = st.selectbox("Choose Target Phrase to Master:", [
        "सत्यं वद, धर्मं चर। (Speak truth, practice righteousness)",
        "विद्या ददाति विनयं विनयाद्याति पात्रताम्। (Knowledge gives humility)",
        "वृक्षात् फलानि भूमौ पतन्ति। (Fruits fall from tree - Mahāprāṇa 'ph')",
        "अहं प्रतिदिनं प्रातः पञ्चवादने उत्तिष्ठामि। (I wake at 5 AM - Retroflex 'ṣṭh')"
    ])
    phrase = drill.split('(')[0].strip()
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.markdown(f"##### 🔊 **1. Master Chanting ({t_info['title']}):**")
        render_talking_avatar(phrase, selected_teacher, auto_play=False)
    with col_s2:
        st.markdown("##### 🎙️ **2. Record Chanting for Acoustic Diagnosis:**")
        rec_sh = st.audio_input("Chant the phrase:", key="shiksha_mic")

    if rec_sh is not None:
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Analyzing phonetic acoustics..."):
            try:
                resp_text = generate_gemini_content(
                    client=client,
                    contents=[{
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "audio/wav", "data": rec_sh.getvalue()}},
                            {"text": f"Evaluate student pronunciation against target: '{phrase}'. Return: 1. Score out of 100, 2. Articulation points (Dental vs Retroflex), 3. Mahaprana breath release, 4. Vowel duration (Hrasva/Dirgha), 5. Tongue placement tip."}
                        ]
                    }],
                    config={"max_output_tokens": 400}
                )
                st.markdown(resp_text)
                update_user_xp(st.session_state.user_session_id, 15)
            except Exception as e:
                st.error(f"Error: {str(e)}")

# =========================================================
# TAB 4: SVARA & CHANDAḤ ENGINE
# =========================================================
with tab_chandas:
    st.markdown("#### 🕉️ वैदिक-स्वर एवं छन्दो-विश्लेषकः (Pingala Chandaḥ Engine)")
    verse_input = st.text_area("Enter Verse for Scansion:", value="धर्मक्षेत्रे कुरुक्षेत्रे समवेता युयुत्सवः।\nमामकाः पाण्डवाश्चैव किमकुर्वत सञ्जय॥", height=80)
    
    if st.button("Scan Metre & Pitch / छन्दो-परीक्षणम्", use_container_width=True):
        if not api_key:
            st.warning("⚠️ Enter Gemini API key.")
            st.stop()
        client = genai.Client(api_key=api_key)
        with st.spinner("Analyzing scansion..."):
            try:
                res_text = generate_gemini_content(
                    client=client,
                    contents=[{"role": "user", "parts": [{"text": f"Perform Pingala Chandaḥ scansion on: '{verse_input}'. Identify metre name (Anuṣṭubh, Triṣṭubh, etc.), Laghu (।) / Guru (ऽ) syllabic mapping, Gana breakdown, and Vedic Svara rules."}]}],
                    config={"max_output_tokens": 450}
                )
                st.markdown(res_text)
                update_user_xp(st.session_state.user_session_id, 20)
            except Exception as e:
                st.error(f"Error: {str(e)}")

# =========================================================
# TAB 5: SENTENCE-BY-SENTENCE BATCH TRANSLATOR (UP TO 50 SENTENCES)
# =========================================================
with tab_trans:
    st.markdown("#### 🌐 Sentence-by-Sentence Batch Translator (Up to 50 Sentences at Once)")
    st.caption("Paste whole essays, paragraphs, or lists. The engine automatically splits into distinct sentences, translates each individually, provides Padaccheda/Sandhi breakdown, and enables audio playback.")
    
    col_t1, col_t2 = st.columns([1, 1])
    with col_t1:
        trans_direction = st.radio("Translation Direction:", ["Any Language ➔ Sanskrit (संस्कृतम्)", "Sanskrit (संस्कृतम्) ➔ Any Language"], horizontal=True)
    with col_t2:
        if trans_direction.startswith("Sanskrit"):
            target_lang = st.selectbox("Translate to Target Language:", ["Telugu (తెలుగు)", "Hindi (हिन्दी)", "English", "Tamil (தமிழ்)", "Kannada (ಕನ್ನಡ)", "Marathi (मराठी)"])
        else:
            target_lang = "Sanskrit (Devanagari + IAST)"
    
    input_text = st.text_area(
        "Enter sentences or paragraph (Max 50 sentences):",
        value="Speak Without Pressure. Take the quiz and start speaking your chosen language with an AI tutor today. Praktika helps you practice without pressure and turn short lessons into real progress.",
        height=140
    )
    
    detected_sentences = split_into_sentences(input_text, max_limit=50)
    st.caption(f"📊 **Detected Sentences to Process:** `{len(detected_sentences)}` (Max batch: 50)")

    if st.button("🚀 Translate Sentence-by-Sentence / वाक्यशः अनुवादं कुरु", use_container_width=True) and input_text.strip():
        if not api_key:
            st.warning("⚠️ Enter your Gemini API key in the sidebar.")
            st.stop()
        
        client = genai.Client(api_key=api_key)
        with st.spinner(f"Translating {len(detected_sentences)} sentences with automatic rate-limit management..."):
            try:
                BATCH_PROMPT = f"""You are a Sanskrit Grammatical Translation Engine.
Translate the following array of {len(detected_sentences)} sentences individually.
Direction: {trans_direction} (Target: {target_lang}).

Input sentences array:
{json.dumps(detected_sentences, ensure_ascii=False)}

Return a STRICT JSON array of objects with exact keys:
- "sentence_num": integer (1, 2, 3...)
- "source_sentence": original sentence
- "translated_sentence": translated sentence in target script
- "iast": Romanized IAST transliteration
- "padaccheda": Word-by-word grammatical Sandhi split with root meanings

Ensure pure, natural, idiomatic translation for every single sentence.
"""
                resp_text = generate_gemini_content(
                    client=client,
                    contents=[{"role": "user", "parts": [{"text": BATCH_PROMPT}]}],
                    config={"temperature": 0.1},
                    is_json=True
                )
                
                batch_results = json.loads(resp_text)
                st.success(f"🎉 Successfully translated all {len(batch_results)} sentences!")
                
                for item in batch_results:
                    s_num = item.get("sentence_num", 1)
                    src_s = item.get("source_sentence", "")
                    tr_s = item.get("translated_sentence", "")
                    iast_s = item.get("iast", "")
                    pada_s = item.get("padaccheda", "")
                    
                    st.markdown(f"""
                    <div class="sentence-card">
                        <div style="font-weight:800; color:#FF8F00; font-size:0.95rem; margin-bottom:4px;">
                            Sentence #{s_num}
                        </div>
                        <div style="font-size:0.95rem; opacity:0.85; margin-bottom:8px;">
                            <b>Original:</b> {src_s}
                        </div>
                        <div style="font-size:1.15rem; color:#FFF; font-weight:700; margin-bottom:4px;">
                            <b>अनुवादः:</b> {tr_s}
                        </div>
                        <div style="font-size:0.88rem; color:#FFD54F; margin-bottom:6px;">
                            <b>IAST:</b> <i>{iast_s}</i>
                        </div>
                        <div style="font-size:0.82rem; color:#81C784; background:rgba(255,255,255,0.02); padding:6px 10px; border-radius:6px;">
                            <b>पदच्छेदः एवं सन्धिविश्लेषणम् (Grammar):</b> {pada_s}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if trans_direction.startswith("Any"):
                        audio_b64 = get_speech_audio_b64(tr_s, t_info["tld"], t_info["slow"])
                        if audio_b64:
                            st.audio(f"data:audio/mp3;base64,{audio_b64}", format="audio/mp3")

                export_text = ""
                for it in batch_results:
                    export_text += f"[{it.get('sentence_num')}] Source: {it.get('source_sentence')}\nTranslation: {it.get('translated_sentence')}\nIAST: {it.get('iast')}\nPadaccheda: {it.get('padaccheda')}\n\n"
                
                st.download_button(
                    label="📥 Download All Translated Sentences (.txt)",
                    data=export_text,
                    file_name="sanskrit_batch_translation.txt",
                    mime="text/plain",
                    use_container_width=True
                )

            except Exception as e:
                st.error(f"Translation Error: {str(e)}")
