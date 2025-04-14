from flask import Flask, request, jsonify
from groq import Groq
from deep_translator import GoogleTranslator
from gtts import gTTS
import speech_recognition as sr
import tempfile
import base64
import os
import re
from dotenv import load_dotenv
import warnings

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Setup Groq client
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

# Supported languages
LANGUAGES = {
    'hi': 'Hindi', 'te': 'Telugu', 'ta': 'Tamil', 'bn': 'Bengali',
    'mr': 'Marathi', 'ml': 'Malayalam', 'kn': 'Kannada', 'en': 'English'
}

def translate_text(text: str, target_lang: str, source_lang: str = 'auto') -> str:
    """Translates input text to the target language."""
    try:
        if source_lang == target_lang:
            return text
        return GoogleTranslator(source=source_lang, target=target_lang).translate(text)
    except Exception as e:
        warnings.warn(f"Translation failed: {str(e)}")
        return text

def get_groq_response(prompt: str, model: str = "llama3-70b-8192") -> str:
    """Gets AI response in English (Groq always returns English)."""
    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        raise RuntimeError(f"Groq API error: {str(e)}")

def speak_text(text: str, lang: str = 'en') -> str:
    """Converts text to speech and returns the audio as base64."""
    try:
        tts = gTTS(text=text, lang=lang)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            temp_path = fp.name
        tts.save(temp_path)
        with open(temp_path, "rb") as audio_file:
            encoded_string = base64.b64encode(audio_file.read()).decode('utf-8')
        os.remove(temp_path)
        return encoded_string
    except Exception as e:
        return f"TTS generation failed: {e}"

@app.route("/languages", methods=["GET"])
def get_languages():
    """Returns the available languages."""
    return jsonify(LANGUAGES)

@app.route("/chat", methods=["POST"])
def chat():
    """Handles user input text and returns AI response in the target language."""
    data = request.get_json()
    user_input = data.get("input")
    lang_code = data.get("lang_code", "en")

    if not user_input:
        return jsonify({"error": "Missing input text"}), 400

    # Translate user input to English
    english_input = translate_text(user_input, 'en', lang_code)
    
    # If input is too short, add context
    if len(english_input.strip().split()) < 3:
        english_input = f"This is a disaster-related question: {english_input}"

    # Get Groq response in English
    response_text = get_groq_response(english_input)

    # Translate the response to the target language
    translated_response = translate_text(response_text, lang_code, 'en')

    # Clean the response for text-to-speech
    cleaned_response = re.sub(r"[•*+→\-\–\—▶️🌐🎙️📝🚨🔈💡❗✅🔁📍📢🔥]", "", translated_response)

    return jsonify({
        "response": cleaned_response.strip()
    })

@app.route("/speak", methods=["POST"])
def speak():
    """Generates and returns the speech for given text."""
    data = request.get_json()
    text = data.get("text")
    lang = data.get("lang", "en")

    if not text:
        return jsonify({"error": "Missing text to speak"}), 400

    audio_base64 = speak_text(text, lang)
    return jsonify({"audio_base64": audio_base64})

@app.route("/voice", methods=["POST"])
def voice():
    """Handles voice input and returns AI response as audio output."""
    lang_code = request.args.get("lang_code", "en")
    recognizer = sr.Recognizer()
    
    with sr.Microphone() as source:
        try:
            recognizer.adjust_for_ambient_noise(source, duration=1.5)
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)
            user_input = recognizer.recognize_google(audio, language=f"{lang_code}-IN")
            
            # Step 1: Translate user input to English
            english_input = translate_text(user_input, 'en', lang_code)
            if len(english_input.strip().split()) < 3:
                english_input = f"This is a disaster-related question: {english_input}"

            # Step 2: Get AI response in English from Groq
            response_text = get_groq_response(english_input)

            # Step 3: Translate response to the user’s language
            translated_response = translate_text(response_text, lang_code, 'en')

            # Step 4: Convert translated response to audio
            audio_base64 = speak_text(translated_response, lang_code)

            return jsonify({"audio_base64": audio_base64})

        except Exception as e:
            return jsonify({"error": f"Voice input failed: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True)
