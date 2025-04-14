import os
import discord
from discord.ext import commands
import tempfile
from gtts import gTTS
import asyncio
import time
import requests
from discord.ui import View, Button
from deep_translator import GoogleTranslator
import textwrap
from dotenv import load_dotenv
import vosk
import wave
import json

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "te": "Telugu",
    "ta": "Tamil",
    "ml": "Malayalam",
    "kn": "Kannada",
    "pa": "Punjabi",
    "mr": "Marathi"
}

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

async def generate_tts(text, lang, filename):
    def _save_tts():
        tts = gTTS(text=text, lang=lang)
        tts.save(filename)
    await asyncio.to_thread(_save_tts)

# Views
class ListenView(View):
    def __init__(self, user):
        super().__init__(timeout=None)
        self.user = user

    @discord.ui.button(label="🎙️ Start Talking", style=discord.ButtonStyle.primary)
    async def listen_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ You can't use this button.", ephemeral=True)
            return
        await interaction.response.defer()
        await start_voice_interaction(interaction)

# Helpers
@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel is None and after.channel is not None and not member.bot:
        text_channels = [c for c in after.channel.guild.text_channels if c.permissions_for(member).send_messages]
        if text_channels:
            await send_listen_button(text_channels[0], member)

async def send_listen_button(channel, user):
    view = ListenView(user)
    await channel.send("Click below to talk to AidBot 👇", view=view)

def translate_text(text, target_lang='en'):
    try:
        return GoogleTranslator(source='auto', target=target_lang).translate(text)
    except Exception as e:
        print(f"Translation Error: {e}")
        return text

def get_groq_response(prompt, lang="en"):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    system_prompt = """
    You are AidBot, a multilingual disaster relief assistant.
    Your goal is to explain disaster-related news and topics clearly in less than 1990 characters.
    """
    data = {
        "model": "llama3-70b-8192",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 2000
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        return f"Error getting AI response: {e}"

# Voice recording callback
async def recording_callback(sink, interaction):
    temp_wav = os.path.join(tempfile.gettempdir(), f"temp_{int(time.time())}.wav")
    user = interaction.user
    try:
        with wave.open(temp_wav, 'wb') as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(48000)
            audio_data = sink.audio_data.get(user.id)
            if audio_data:
                wf.writeframes(audio_data.get('audio'))
        return temp_wav
    except Exception as e:
        print(f"Recording error: {e}")
        return None

# Events
@bot.event
async def on_ready():
    print(f"✅ Bot is now online as {bot.user}")
    print(f"Guilds: {[g.name for g in bot.guilds]}")

async def start_voice_interaction(interaction):
    print(f"Starting voice interaction for user {interaction.user}")
    user = interaction.user
    if not user.voice or not user.voice.channel:
        print("User not in voice channel")
        return await interaction.followup.send("❗ Join a voice channel first!", ephemeral=True)

    try:
        voice_client = await user.voice.channel.connect()
        print(f"Connected to voice channel: {user.voice.channel.name}")
    except Exception as e:
        print(f"Voice connection failed: {e}")
        return await interaction.followup.send(f"❌ Failed to join voice channel: {e}")

    await interaction.followup.send("🌐 Available Languages:\n" + "\n".join([f"{k} - {v}" for k, v in LANGUAGES.items()]))
    await interaction.followup.send("💬 Type your preferred language code (e.g., en, te):")

    def check(m):
        return m.author == user and m.channel == interaction.channel and m.content.lower() in LANGUAGES

    try:
        lang_msg = await bot.wait_for('message', timeout=30.0, check=check)
        user_lang = lang_msg.content.lower()
        print(f"User selected language: {user_lang}")
    except asyncio.TimeoutError:
        await voice_client.disconnect()
        print("Language selection timed out")
        return await interaction.followup.send("⌛ You took too long to reply.")

    await interaction.followup.send("🎙️ Speak now...")

    # Record audio from voice channel
    try:
        sink = discord.sinks.WaveSink()
        print("Initialized WaveSink")
    except Exception as e:
        await voice_client.disconnect()
        print(f"WaveSink error: {e}")
        return await interaction.followup.send(f"❌ Voice recording not supported: {e}")

    voice_client.start_recording(sink, recording_callback, interaction)
    print("Started recording")
    await asyncio.sleep(10)  # Record for 10 seconds
    voice_client.stop_recording()
    print("Stopped recording")

    # Process recorded audio
    temp_wav = await recording_callback(sink, interaction)
    if not temp_wav:
        await voice_client.disconnect()
        print("No audio recorded")
        return await interaction.followup.send("❌ Failed to record audio.")

    # Process audio with Vosk
    try:
        model = vosk.Model("models/vosk-model-small-en-us-0.15")
        wf = wave.open(temp_wav, "rb")
        recognizer = vosk.KaldiRecognizer(model, wf.getframerate())
        print("Initialized Vosk model")
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if recognizer.AcceptWaveform(data):
                result = recognizer.Result()
                recognized_text = json.loads(result).get("text", "")
                print(f"Recognized text: {recognized_text}")
                break
        wf.close()
    except Exception as e:
        await voice_client.disconnect()
        os.remove(temp_wav)
        print(f"Vosk error: {e}")
        return await interaction.followup.send(f"❌ Voice recognition failed: {e}")

    os.remove(temp_wav)
    if not recognized_text:
        await voice_client.disconnect()
        print("No text recognized")
        return await interaction.followup.send("❌ Could not understand audio.")

    await interaction.followup.send(f"📝 You said: {recognized_text}")

    # Process with translation and Groq
    english_text = translate_text(recognized_text, 'en')
    groq_response_en = get_groq_response(english_text)
    final_response = translate_text(groq_response_en, user_lang)

    chunks = textwrap.wrap(final_response, width=1900, break_long_words=False)
    for chunk in chunks:
        await interaction.followup.send(f"🤖 AidBot:\n```\n{chunk}\n```")

    # Generate and send TTS
    temp_file = os.path.join(tempfile.gettempdir(), f"response_{int(time.time())}.mp3")
    try:
        await generate_tts(final_response, user_lang, temp_file)
        await interaction.followup.send(file=discord.File(temp_file))
        os.remove(temp_file)
        print("Sent TTS audio")
    except Exception as e:
        await interaction.followup.send(f"🔊 Audio generation failed: {e}")
        print(f"TTS error: {e}")

    await voice_client.disconnect()
    print("Disconnected from voice channel")
    await send_listen_button(interaction.channel, user)

# Run
bot.run(TOKEN)