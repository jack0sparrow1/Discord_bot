import os
if os.environ.get('RENDER') == 'true':
    print("Running on Render, skipping audio initialization.")
    pygame = None
else:
    import pygame
    pygame.mixer.init()

import discord
from discord.ext import commands
import speech_recognition as sr
import tempfile
from gtts import gTTS
import asyncio
import time
import requests
from discord.ui import View, Button 
from deep_translator import GoogleTranslator
import textwrap
from dotenv import load_dotenv

# ======================
# Configuration
# ======================
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

# ======================
# Views
# ======================
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

# ======================
# Helpers
# ======================
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
    system_prompt = f"""
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

async def play_audio(audio_file):
    if pygame:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(audio_file)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)
        finally:
            pygame.mixer.quit()
            try:
                os.remove(audio_file)
            except:
                pass
    else:
        print("Audio skipped (running on Render).")

# ======================
# Events
# ======================
@bot.event
async def on_ready():
    print(f"✅ Bot is now online as {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

async def start_voice_interaction(interaction):
    user = interaction.user
    if not user.voice or not user.voice.channel:
        return await interaction.followup.send("❗ Join a voice channel first!", ephemeral=True)

    voice_client = await user.voice.channel.connect()

    await interaction.followup.send("🌐 Available Languages:\n" + "\n".join([f"{k} - {v}" for k, v in LANGUAGES.items()]))
    await interaction.followup.send("💬 Type your preferred language code (e.g., en, te):")

    def check(m):
        return m.author == user and m.channel == interaction.channel and m.content.lower() in LANGUAGES

    try:
        lang_msg = await bot.wait_for('message', timeout=30.0, check=check)
        user_lang = lang_msg.content.lower()
    except asyncio.TimeoutError:
        await voice_client.disconnect()
        return await interaction.followup.send("⌛ You took too long to reply.")

    await interaction.followup.send("🎙️ Speak now...")

    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=1)
        try:
            audio = recognizer.listen(source, phrase_time_limit=10)
            recognized_text = recognizer.recognize_google(audio)
            await interaction.followup.send(f"📝 You said: {recognized_text}")
        except sr.UnknownValueError:
            await voice_client.disconnect()
            return await interaction.followup.send("❌ Could not understand audio.")
        except Exception as e:
            await voice_client.disconnect()
            return await interaction.followup.send(f"❌ Error: {e}")

    english_text = translate_text(recognized_text, 'en')
    groq_response_en = get_groq_response(english_text)
    final_response = translate_text(groq_response_en, user_lang)

    chunks = textwrap.wrap(final_response, width=1900, break_long_words=False)
    for chunk in chunks:
        await interaction.followup.send(f"🤖 AidBot:\n```\n{chunk}\n```")

    temp_file = os.path.join(tempfile.gettempdir(), f"response_{int(time.time())}.mp3")
    try:
        tts = gTTS(text=final_response, lang=user_lang)
        tts.save(temp_file)
        await play_audio(temp_file)
    except Exception as e:
        await interaction.followup.send(f"🔊 Audio playback error: {e}")

    await voice_client.disconnect()
    await send_listen_button(interaction.channel, user)

# ======================
# Run
# ======================
bot.run(TOKEN)
