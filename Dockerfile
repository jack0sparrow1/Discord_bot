# Use an official Python runtime as base
FROM python:3.12-slim

# Install system dependencies for audio
RUN apt-get update && apt-get install -y \
    # Pygame & SDL2 dependencies
    libsdl2-dev \
    libsdl2-mixer-dev \
    # GStreamer for audio playback
    libgstreamer1.0-0 \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    libgstreamer-plugins-base1.0-dev \
    # ALSA & PulseAudio for microphone
    portaudio19-dev \
    libasound2-dev \
    libpulse-dev \
    # GLib for threading (fixes libgthread error)
    libglib2.0-0 \
    # Clean up to reduce image size
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (for caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the files
COPY . .

# Run the bot
CMD ["python", "bot.py"]