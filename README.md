# Vynlo <img width="35" height="35" alt="337A39AD-C1A0-4509-BA89-B2760ED0057C" src="https://github.com/user-attachments/assets/3d72a50f-9a27-447d-9688-9e63cab89a5b" />


Vynlo is a lightweight Python Discord music bot built with discord.py. It connects to a voice channel, plays music from YouTube links, and handles queue-based playback for a smooth listening experience in your server.

This project uses Python as the bot application itself, and discord.py as the library that speaks to Discord's API. There is no separate frontend for this bot — it runs as a server-side bot process.

## Features

- Join and leave voice channels
- Play music from YouTube URLs
- Queue songs for continuous playback
- Skip the current track
- Clear the queue
- Pause and resume playback
- Stop playback and reset the queue
- Clean command menu for easy use

## Tech stack

- Python
- discord.py
- yt-dlp
- FFmpeg

## Setup

1. Install dependencies:
   ```bash
   pip install python-dotenv yt-dlp discord.py
   ```
2. Create a `.env` file with your Discord bot token:
   ```env
   DISCORD_TOKEN=your_token_here
   ```
3. Run the bot:
   ```bash
   python bot.py
   ```

## Example commands

```text
!play <youtube_url>
!queue
!skip
!pause
!resume
!stop
!clearqueue
```

## Notes

Vynlo is intentionally simple and focused: it is a Discord music bot, written in Python, with discord.py handling the Discord side and yt-dlp/FFmpeg handling the audio playback flow.
