# Vynlo 🎵

<img align="right" width="140" height="140" alt="Vynlo Logo" src="https://github.com/user-attachments/assets/3d72a50f-9a27-447d-9688-9e63cab89a5b">   

A Discord music bot built with Python and `discord.py`.

Vynlo is focused on making music playback simple without filling a server with commands. It uses a **visual player panel with buttons** for controlling playback and an interactive queue for adding music.

Simply create a music channel dedicated to Vynlo, and enter !play [url]. Let Vynlo handle the rest through the modern UI modal.




## Features

* 🎵 Play YouTube songs & playlists
* 📋 Interactive queue
* 🎛️ Visual music player
* ⏯️ Pause / resume / skip
* ⏮️ Previous track
* 🔀 Shuffle
* 🔁 Track / queue looping
* 🖼️ Track artwork & information
* 🔊 Volume & playback state
* 💬 Traditional commands still supported

## Preview

<img width="521" height="221" alt="image" src="https://github.com/user-attachments/assets/fa201b61-fcad-4478-8f4a-154b6003a3e3" />


## Tech

* Python
* discord.py
* yt-dlp
* FFmpeg
* pytest

## Setup

```bash
pip install discord.py yt-dlp python-dotenv pytest
```

Create a `.env` file:

```env
DISCORD_TOKEN=your_token_here
```

Then run:

```bash
python bot.py
```

FFmpeg must also be installed and available in your PATH.

## Commands

```text
!join
!play <url>
!queue
!skip
!pause
!resume
!stop
!clearqueue
!leave
```

Most playback can be controlled directly through the **Vynlo player panel**, so commands aren't required for normal use.

---

Built as a personal project to learn more about Python, Discord bots and building a better music experience.
