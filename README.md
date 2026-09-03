# Vynlo 🎵

<img align="right" width="125" height="125" alt="Vynlo Logo" src="https://github.com/user-attachments/assets/fcdaa802-4f4f-4a52-ad1c-b997994782a0">

**A clean, UI-first Discord music bot built with Python.**

Vynlo turns Discord into a simple music player — no command clutter, just buttons.

## 🎵 How It Works

Vynlo automatically creates a **#VynloMusic🎵** channel with the player ready to use.

**1.** 🔊 Join a voice channel
**2.** 🎵 Open **#VynloMusic🎵**
**3.** ➕ Click **Add to Queue**
**4.** 🔗 Paste a YouTube link

Vynlo connects to your voice channel and starts playing.

## 🎛️ Player

* ⏮️ Previous
* ⏸️ Pause / Resume
* ⏭️ Skip
* 🔀 Shuffle
* 🔁 Loop
* 📋 Queue
* ⏹️ Stop

The queue has its own clean interface for viewing and managing upcoming tracks.

## ✨ Features

* YouTube songs & playlists
* Interactive Discord UI
* Queue management
* Track & queue looping
* Shuffle & previous track
* Track artwork & metadata
* Automatic voice-channel connection
* Automatic Vynlo channel creation
* Temporary playback notifications

## 🖼️ Preview

<img width="330" height="421" alt="Vynlo Music Player" src="https://github.com/user-attachments/assets/7e2f66f2-618f-47d3-9194-bba4bee4eed7"/> 


## 🛠️ Built With

**Python · discord.py · yt-dlp · FFmpeg · python-dotenv**

## 🚀 Setup

```bash
pip install discord.py yt-dlp python-dotenv pytest
```

Create a `.env` file:

```env
DISCORD_TOKEN=your_token_here
```

Make sure FFmpeg is installed and available in your `PATH`.

Run Vynlo:

```bash
python bot.py
```

## 💬 Command

Vynlo is designed to be controlled through its UI.

```text
!info
```

Legacy playback commands are still available as fallbacks.

---

### Vynlo 🎵

**No commands. Just music.**
