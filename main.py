import streamlit as st
import os
import time
import warnings
import requests
import tempfile
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from yt_dlp import YoutubeDL
from deep_translator import GoogleTranslator
from langdetect import detect
from deep_translator import GoogleTranslator as Translator

# Suppress non-critical warnings
warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")

# Set page config
st.set_page_config(
    page_title="YouTube Translator",
    page_icon="🎬",
    layout="wide"
)

# Custom CSS for better appearance
st.markdown("""
<style>
    .stTextInput input {
        font-size: 18px;
    }
    .stSelectbox select {
        font-size: 18px;
    }
    .stButton button {
        width: 100%;
        padding: 10px;
        font-size: 18px;
    }
    .stProgress > div > div > div {
        background-color: #4CAF50;
    }
    .success-box {
        padding: 1rem;
        background-color: #e6f7e6;
        border-radius: 0.5rem;
        border: 1px solid #2e7d32;
    }
</style>
""", unsafe_allow_html=True)

def get_video_id(url):
    parsed_url = urlparse(url)
    if parsed_url.hostname == 'youtu.be':
        return parsed_url.path[1:]
    if parsed_url.hostname in ['www.youtube.com', 'youtube.com']:
        query = parse_qs(parsed_url.query)
        return query.get('v', [None])[0]
    return None

def check_video_status(video_url):
    try:
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'socket_timeout': 30,
            'nocheckcertificate': True,
            'ignoreerrors': False,  # Changed to False to catch errors properly
            'no_warnings': True,
            'simulate': True,
            'geo_bypass': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://www.youtube.com/',
            }
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            # Check if info is None first
            if info is None:
                return False, "Failed to retrieve video information"
            
            # Now safely check the info dictionary
            upload_date = info.get('upload_date')
            if upload_date:
                try:
                    upload_time = datetime.strptime(upload_date, '%Y%m%d')
                    age_days = (datetime.now() - upload_time).days
                    if age_days < 1:
                        return False, "Video recently uploaded, try after some time."
                except ValueError:
                    pass  # Skip date parsing if format is invalid

            if info.get('is_live') or info.get('was_live'):
                return False, "Live streams are not supported."
                
            if info.get('live_status') == 'post_live':
                return False, "Live stream recording is still being processed."

            return True, "Video is ready."

    except Exception as e:
        return False, f"Error checking video status: {str(e)}"

def fetch_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'hi'])
        return " ".join([entry['text'] for entry in transcript])
    except (TranscriptsDisabled, NoTranscriptFound):
        return None
    except Exception as e:
        st.error(f"Transcript error: {str(e)}")
        return None

def  fetch_captions_url(video_url, lang='en'):
    try:
        ydl_opts = {
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': [lang],
            'quiet': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            }
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            subs = info.get('subtitles', {}).get(lang)
            auto = info.get('automatic_captions', {}).get(lang)
            captions = subs or auto
            return captions[0]['url'] if captions else None
    except Exception as e:
        st.error(f"Captions error: {str(e)}")
        return None

def get_audio_stream_url(video_url):
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            }
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return info.get('url')
    except Exception as e:
        st.error(f"Audio stream error: {str(e)}")
        return None

def get_audio_stream_url(video_url):
    try:
        with YoutubeDL({
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True
        }) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return info.get('url')
    except Exception as e:
        st.error(f"Audio stream error: {str(e)}")
        return None

def transcribe_with_whisper(audio_url):
    try:
        import whisper
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as temp_audio:
            response = requests.get(audio_url, stream=True, timeout=30)
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=8192):
                temp_audio.write(chunk)
            temp_audio_path = temp_audio.name

        model_dir = os.path.join(os.path.expanduser("~"), ".cache", "whisper")
        os.makedirs(model_dir, exist_ok=True)

        model = whisper.load_model("base", download_root=model_dir)
        result = model.transcribe(temp_audio_path, fp16=False)

        os.unlink(temp_audio_path)
        return result["text"]

    except ImportError:
        st.error("Whisper not installed. Run: pip install openai-whisper")
        return None
    except Exception as e:
        st.error(f"Whisper error: {str(e)}")
        return None

def translate_text_dynamic_lang_detection(text, target_lang):
    def split_text(text):
        sentences = [s.strip() for s in text.split('। ') if s.strip()]
        chunks = []
        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) > 2000:
                chunks.append(current_chunk)
                current_chunk = sentence
            else:
                current_chunk += "। " + sentence if current_chunk else sentence
        if current_chunk:
            chunks.append(current_chunk)
        return chunks

    translated_chunks = []
    chunks = split_text(text)
    for i, chunk in enumerate(chunks, 1):
        for attempt in range(3):
            try:
                source_lang = detect(chunk)
                translated = GoogleTranslator(source=source_lang, target=target_lang).translate(chunk)
                translated_chunks.append(translated)
                time.sleep(5)
                break
            except Exception:
                time.sleep(10)
        else:
            translated_chunks.append(f"[Translation failed for chunk {i}]")

    return "\n\n".join(translated_chunks)

def process_video(video_url, target_lang='hi'):
    video_id = get_video_id(video_url)
    if not video_id:
        return "Invalid YouTube URL", None

    is_ready, reason = check_video_status(video_url)
    if not is_ready:
        return reason, None

    text = fetch_transcript(video_id)
    if not text:
        captions_url = fetch_captions_url(video_url)
        if captions_url:
            return f"Captions available at: {captions_url}", None

    if not text:
        audio_url = get_audio_stream_url(video_url)
        if audio_url:
            text = transcribe_with_whisper(audio_url)

    if not text:
        return "Could not retrieve transcript or captions", None

    translated = translate_text_dynamic_lang_detection(text, target_lang) if target_lang else text
    return translated, text

def main():
    st.title("🎬 YouTube Video Translator")
    st.markdown("Translate YouTube videos to multiple languages")

    with st.sidebar:
        st.header("Settings")

        # Manually defined list of supported languages for Google Translate
        lang_dict = {
    "Afrikaans": "af",
    "Albanian": "sq",
    "Amharic": "am",
    "Arabic": "ar",
    "Armenian": "hy",
    "Assamese": "as",
    "Aymara": "ay",
    "Azerbaijani": "az",
    "Bambara": "bm",
    "Basque": "eu",
    "Belarusian": "be",
    "Bengali": "bn",
    "Bhojpuri": "bho",
    "Bosnian": "bs",
    "Bulgarian": "bg",
    "Catalan": "ca",
    "Cebuano": "ceb",
    "Chichewa": "ny",
    "Chinese (Simplified)": "zh-CN",
    "Chinese (Traditional)": "zh-TW",
    "Corsican": "co",
    "Croatian": "hr",
    "Czech": "cs",
    "Danish": "da",
    "Dhivehi": "dv",
    "Dogri": "doi",
    "Dutch": "nl",
    "English": "en",
    "Esperanto": "eo",
    "Estonian": "et",
    "Ewe": "ee",
    "Filipino": "tl",
    "Finnish": "fi",
    "French": "fr",
    "Frisian": "fy",
    "Galician": "gl",
    "Georgian": "ka",
    "German": "de",
    "Greek": "el",
    "Guarani": "gn",
    "Gujarati": "gu",
    "Haitian Creole": "ht",
    "Hausa": "ha",
    "Hawaiian": "haw",
    "Hebrew": "iw",
    "Hindi": "hi",
    "Hmong": "hmn",
    "Hungarian": "hu",
    "Icelandic": "is",
    "Igbo": "ig",
    "Ilocano": "ilo",
    "Indonesian": "id",
    "Irish": "ga",
    "Italian": "it",
    "Japanese": "ja",
    "Javanese": "jw",
    "Kannada": "kn",
    "Kazakh": "kk",
    "Khmer": "km",
    "Kinyarwanda": "rw",
    "Konkani": "gom",
    "Korean": "ko",
    "Krio": "kri",
    "Kurdish (Kurmanji)": "ku",
    "Kurdish (Sorani)": "ckb",
    "Kyrgyz": "ky",
    "Lao": "lo",
    "Latin": "la",
    "Latvian": "lv",
    "Lingala": "ln",
    "Lithuanian": "lt",
    "Luganda": "lg",
    "Luxembourgish": "lb",
    "Macedonian": "mk",
    "Maithili": "mai",
    "Malagasy": "mg",
    "Malay": "ms",
    "Malayalam": "ml",
    "Maltese": "mt",
    "Maori": "mi",
    "Marathi": "mr",
    "Meiteilon (Manipuri)": "mni-Mtei",
    "Mizo": "lus",
    "Mongolian": "mn",
    "Myanmar": "my",
    "Nepali": "ne",
    "Norwegian": "no",
    "Odia (Oriya)": "or",
    "Oromo": "om",
    "Pashto": "ps",
    "Persian": "fa",
    "Polish": "pl",
    "Portuguese": "pt",
    "Punjabi": "pa",
    "Quechua": "qu",
    "Romanian": "ro",
    "Russian": "ru",
    "Samoan": "sm",
    "Sanskrit": "sa",
    "Scots Gaelic": "gd",
    "Sepedi": "nso",
    "Serbian": "sr",
    "Sesotho": "st",
    "Shona": "sn",
    "Sindhi": "sd",
    "Sinhala": "si",
    "Slovak": "sk",
    "Slovenian": "sl",
    "Somali": "so",
    "Spanish": "es",
    "Sundanese": "su",
    "Swahili": "sw",
    "Swedish": "sv",
    "Tajik": "tg",
    "Tamil": "ta",
    "Tatar": "tt",
    "Telugu": "te",
    "Thai": "th",
    "Tigrinya": "ti",
    "Tsonga": "ts",
    "Turkish": "tr",
    "Turkmen": "tk",
    "Twi": "ak",
    "Ukrainian": "uk",
    "Urdu": "ur",
    "Uyghur": "ug",
    "Uzbek": "uz",
    "Vietnamese": "vi",
    "Welsh": "cy",
    "Xhosa": "xh",
    "Yiddish": "yi",
    "Yoruba": "yo",
    "Zulu": "zu"
}

        target_lang = st.selectbox(
            "Target Language",
            options=list(lang_dict.values()),
            format_func=lambda code: [k for k, v in lang_dict.items() if v == code][0],
            index=list(lang_dict.values()).index("hi") if "hi" in lang_dict.values() else 0
        )

        retries = st.slider("Retry Attempts", 1, 5, 3)

    url = st.text_input("Enter YouTube URL:", placeholder="https://www.youtube.com/watch?v=...")

    if st.button("Translate Video"):
        if not url:
            st.error("Please enter a YouTube URL")
            return

        with st.spinner("Processing video..."):
            try:
                result, original = None, None
                for attempt in range(retries):
                    result, original = process_video(url, target_lang=target_lang)
                    if not result.startswith(("Video recently", "Live streams", "still being processed", "Error")):
                        break
                    time.sleep(5 * (attempt + 1))

                if not result:
                    st.error("Failed to process the video after retries.")
                elif original:
                    st.subheader("Original Transcript / Captions:")
                    st.text_area("Transcript", original, height=300)
                    st.subheader(f"Translated Text ({target_lang}):")
                    st.text_area("Translation", result, height=300)
                else:
                    st.info(result)
            except Exception as e:
                st.error(f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()