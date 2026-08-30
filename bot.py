import os
import random
from urllib.parse import parse_qs, urlparse
from dotenv import load_dotenv

# here, we are telling the bot to use the discord.py library and the commands extension
# here we are telling the bot to use the commands extension from discord.py
#ffmpeg library which is used to convert audio fles to a format for a voice channel
import discord
from discord.ext import commands
from discord import FFmpegPCMAudio

import yt_dlp
import asyncio

# "Look for a .env file and load the variables inside it."
load_dotenv()

intents = discord.Intents.default()

# this line is saying we want the bot to be able to read the content of messages, this is necessary for the bot to be able to respond to commands
intents.message_content = True

# use ! as the command prefix for the bot
bot = commands.Bot(command_prefix="!", intents=intents)


queues = {}
player_panels = {}
player_state = {}


def get_server_queue(guild_id):
    return queues.setdefault(guild_id, [])


def get_now_playing_track(guild_id):
    state = get_player_state(guild_id)
    current_track = state.get("current_track")
    if isinstance(current_track, dict) and current_track.get("title"):
        return current_track

    queue = get_server_queue(guild_id)
    return queue[0] if queue else None


def get_player_state(guild_id):
    state = player_state.setdefault(guild_id, {
        "volume": 100,
        "loop": "off",
        "shuffle": False,
        "history": [],
        "current_track": None,
    })
    state.setdefault("volume", 100)
    state.setdefault("loop", "off")
    state.setdefault("shuffle", False)
    state.setdefault("history", [])
    state.setdefault("current_track", None)
    return state


def cycle_loop_mode(guild_id):
    state = get_player_state(guild_id)
    order = ["off", "track", "queue"]
    current = state.get("loop", "off")
    next_mode = order[(order.index(current) + 1) % len(order)] if current in order else "off"
    state["loop"] = next_mode
    return next_mode


def get_loop_label(guild_id):
    loop_mode = get_player_state(guild_id).get("loop", "off")
    return {"off": "Off", "track": "Track", "queue": "Queue"}.get(loop_mode, "Off")


def get_volume_percent(guild_id):
    return get_player_state(guild_id).get("volume", 100)


def apply_volume_to_voice_client(guild_id):
    guild = bot.get_guild(guild_id)
    if not guild or guild.voice_client is None:
        return

    source = guild.voice_client.source
    if hasattr(source, "volume"):
        source.volume = get_volume_percent(guild_id) / 100.0


def shuffle_queue(guild_id):
    queue = get_server_queue(guild_id)
    state = get_player_state(guild_id)
    if len(queue) < 2:
        return False

    if state.get("shuffle"):
        original_order = state.get("original_queue")
        if original_order:
            queue[:] = original_order
            state["shuffle"] = False
            state["original_queue"] = None
            return True

    state["original_queue"] = list(queue)
    random.shuffle(queue)
    state["shuffle"] = True
    return True


def get_pause_resume_label(voice_client):
    if voice_client is None:
        return "Pause"

    try:
        if voice_client.is_paused():
            return "Resume"
    except Exception:
        pass

    return "Pause"


async def send_temporary_message(ctx, message, *, delete_after=10):
    await ctx.send(message, delete_after=delete_after)


async def cleanup_user_command_message(ctx):
    try:
        if ctx.message is not None:
            await ctx.message.delete()
    except Exception:
        pass


def format_duration(value):
    if value is None:
        return "Unknown"

    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return str(value)

    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 24)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def build_queue_embed(guild_id):
    queue = queues.get(guild_id, [])
    embed = discord.Embed(
        title="📋 LIVE QUEUE",
        description="━━━━━━━━━━━━━━━━━━━━",
        color=discord.Color.from_rgb(160, 120, 255),
    )
    embed.set_author(name="VYNLO", icon_url="https://images.unsplash.com/photo-1516280440614-37939bbacd81?auto=format&fit=crop&w=80&q=80")

    if not queue:
        embed.description = "The queue is empty."
        embed.set_footer(text="No tracks queued")
        return embed

    visible_queue = queue[:8]
    lines = []
    for index, item in enumerate(visible_queue, start=1):
        title = item.get("title", "Unknown title") if isinstance(item, dict) else str(item)
        lines.append(f"{index}. {title}")

    if len(queue) > len(visible_queue):
        lines.append(f"... +{len(queue) - len(visible_queue)} more")

    embed.add_field(name="Upcoming", value="\n".join(lines), inline=False)
    embed.set_footer(text=f"{len(queue)} tracks in queue")
    return embed


def build_player_embed(guild_id):
    guild = bot.get_guild(guild_id)
    voice_client = guild.voice_client if guild else None
    queue = queues.get(guild_id, [])
    current_track = get_now_playing_track(guild_id)
    volume_percent = get_volume_percent(guild_id)
    loop_label = get_loop_label(guild_id)

    if current_track:
        title = current_track.get("title", "Unknown title")
        artist = current_track.get("artist") or current_track.get("uploader") or "Unknown artist"
        duration = current_track.get("duration")
        duration_text = format_duration(duration)
        description = (
            "🎶 Now Playing\n"
            f"**{title}**\n\n"
            f"Artist: **{artist}**\n"
            f"Duration: **{duration_text}**"
        )
    else:
        description = (
            "🎶 Now Playing\n"
            "**Nothing is playing right now**"
        )

    embed = discord.Embed(
        title="🎵 VYNLO                                               \n",
        description=description,
        color=discord.Color.from_rgb(180, 98, 255),
    )   

    if current_track and current_track.get("thumbnail"):
        embed.set_thumbnail(url=current_track["thumbnail"])

    if voice_client is not None:
        if voice_client.is_paused():
            playback_state = "Paused"
        elif voice_client.is_playing():
            playback_state = "Playing"
        else:
            playback_state = "Idle"
    else:
        playback_state = "Disconnected"

    embed.add_field(name="Artist", value=current_track.get("artist") or current_track.get("uploader") or "Unknown artist" if current_track else "N/A", inline=True)
    embed.add_field(name="Queue", value=f"{len(queue)} track(s)", inline=True)
    embed.add_field(name="State", value=playback_state, inline=True)
    embed.set_footer(text=f"Volume: {volume_percent}% • Loop: {loop_label}")
    return embed


async def create_or_update_player_panel(ctx):
    guild_id = ctx.guild.id
    channel_id = ctx.channel.id
    key = (guild_id, channel_id)

    guild = bot.get_guild(guild_id)
    if guild is None:
        return

    channel = guild.get_channel(channel_id)
    if channel is None:
        return

    embed = build_player_embed(guild_id)
    view = MusicPlayerView(guild_id, channel_id)

    existing_message_id = player_panels.get(key)
    if existing_message_id:
        try:
            message = await channel.fetch_message(existing_message_id)
            await message.edit(embed=embed, view=view)
            return message
        except discord.NotFound:
            player_panels.pop(key, None)

    message = await channel.send(embed=embed, view=view)
    player_panels[key] = message.id
    return message


async def update_player_panel(guild_id, channel_id=None):
    if channel_id is None:
        matches = [(key, value) for key, value in player_panels.items() if key[0] == guild_id]
        if not matches:
            return
        channel_id = matches[0][0][1]

    key = (guild_id, channel_id)
    guild = bot.get_guild(guild_id)
    if guild is None:
        return

    channel = guild.get_channel(channel_id)
    if channel is None:
        return

    message_id = player_panels.get(key)
    if not message_id:
        message = await channel.send(embed=build_player_embed(guild_id), view=MusicPlayerView(guild_id, channel_id))
        player_panels[key] = message.id
        return

    try:
        message = await channel.fetch_message(message_id)
    except discord.NotFound:
        player_panels.pop(key, None)
        message = await channel.send(embed=build_player_embed(guild_id), view=MusicPlayerView(guild_id, channel_id))
        player_panels[key] = message.id
        return

    view = MusicPlayerView(guild_id, channel_id)
    try:
        await message.edit(embed=build_player_embed(guild_id), view=view)
    except discord.HTTPException:
        pass


class QueueAddModal(discord.ui.Modal):
    def __init__(self, guild_id, channel_id=None):
        super().__init__(title="Add to Queue")
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.url_input = discord.ui.TextInput(
            label="Song or playlist URL",
            placeholder="Paste a YouTube link...",
            required=True,
            style=discord.TextStyle.short,
            max_length=500,
        )
        self.add_item(self.url_input)

    async def on_submit(self, interaction):
        url = (self.url_input.value or "").strip()
        if not url:
            await interaction.response.send_message("Please enter a valid URL.", ephemeral=True)
            return

        if interaction.user.voice is None:
            await interaction.response.send_message("You need to be in a voice channel to add music.", ephemeral=True)
            return

        if interaction.guild.voice_client is None:
            await interaction.user.voice.channel.connect()

        guild_queue = get_server_queue(interaction.guild.id)

        try:
            if is_playlist_url(url):
                tracks = await extract_playlist_tracks(url)
                if not tracks:
                    await interaction.response.send_message("I could not find any playable tracks in that playlist.", ephemeral=True)
                    return

                if interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused() or guild_queue:
                    guild_queue.extend(tracks)
                    await interaction.response.send_message(f"Added **{len(tracks)} tracks** from the playlist to the queue.", ephemeral=True)
                    await update_player_panel(interaction.guild.id, interaction.channel.id)
                    return

                first_track = await resolve_track_audio(tracks[0])
                if len(tracks) > 1:
                    guild_queue.extend([await resolve_track_audio(track) for track in tracks[1:]])

                get_player_state(interaction.guild.id)["current_track"] = first_track
                source = FFmpegPCMAudio(
                    first_track["stream_url"],
                    before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                    options="-vn",
                )

                def after_play(error):
                    if error:
                        print(f"Playback error: {error}")
                        return
                    if interaction.guild.id in queues and queues[interaction.guild.id]:
                        asyncio.run_coroutine_threadsafe(play_next_in_queue(interaction), bot.loop)

                interaction.guild.voice_client.play(source, after=after_play)
                await interaction.response.send_message(f"Playing **{first_track['title']}** 🎵", ephemeral=True)
                await update_player_panel(interaction.guild.id, interaction.channel.id)
                return

            info = await extract_audio_info(url)
        except Exception:
            await interaction.response.send_message("I could not find audio for that URL. Please try another one.", ephemeral=True)
            return

        track = {
            "title": info.get("title", "Unknown title"),
            "source_url": info.get("webpage_url") or info.get("url") or url,
            "url": info.get("webpage_url") or info.get("url") or url,
            "stream_url": info.get("url") or url,
        }

        if interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused() or guild_queue:
            guild_queue.append(track)
            await interaction.response.send_message(f"Added **{track['title']}** to the queue.", ephemeral=True)
            await update_player_panel(interaction.guild.id, interaction.channel.id)
            return

        get_player_state(interaction.guild.id)["current_track"] = track
        source = FFmpegPCMAudio(
            track["stream_url"],
            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            options="-vn",
        )

        def after_play(error):
            if error:
                print(f"Playback error: {error}")
                return
            if interaction.guild.id in queues and queues[interaction.guild.id]:
                asyncio.run_coroutine_threadsafe(play_next_in_queue(interaction), bot.loop)

        interaction.guild.voice_client.play(source, after=after_play)
        await interaction.response.send_message(f"Playing **{track['title']}** 🎵", ephemeral=True)
        await update_player_panel(interaction.guild.id, interaction.channel.id)


class MusicPlayerView(discord.ui.View):
    def __init__(self, guild_id, channel_id=None, *, timeout=180):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.channel_id = channel_id

        self.shuffle_button = discord.ui.Button(emoji="🔀", label="\u200b", custom_id=f"player_shuffle_{guild_id}", style=discord.ButtonStyle.secondary)
        self.shuffle_button.callback = self.shuffle_callback
        self.shuffle_button.row = 0
        self.add_item(self.shuffle_button)

        self.previous_button = discord.ui.Button(emoji="⏮️", label="\u200b", custom_id=f"player_previous_{guild_id}", style=discord.ButtonStyle.secondary)
        self.previous_button.callback = self.previous_callback
        self.previous_button.row = 0
        self.add_item(self.previous_button)

        self.pause_button = discord.ui.Button(emoji="⏸️", label="\u200b", custom_id=f"player_pause_{guild_id}", style=discord.ButtonStyle.primary)
        self.pause_button.callback = self.pause_resume_callback
        self.pause_button.row = 0
        self.add_item(self.pause_button)

        self.skip_button = discord.ui.Button(emoji="⏭️", label="\u200b", custom_id=f"player_skip_{guild_id}", style=discord.ButtonStyle.secondary)
        self.skip_button.callback = self.skip_callback
        self.skip_button.row = 0
        self.add_item(self.skip_button)

        self.queue_button = discord.ui.Button(emoji="📋", label="\u200b", custom_id=f"player_queue_{guild_id}", style=discord.ButtonStyle.secondary)
        self.queue_button.callback = self.queue_callback
        self.queue_button.row = 0
        self.add_item(self.queue_button)

        self.loop_button = discord.ui.Button(emoji="🔁", label="\u200b", custom_id=f"player_loop_{guild_id}", style=discord.ButtonStyle.secondary)
        self.loop_button.callback = self.loop_callback
        self.loop_button.row = 1
        self.add_item(self.loop_button)

        self.stop_button = discord.ui.Button(emoji="⏹️", label="\u200b", custom_id=f"player_stop_{guild_id}", style=discord.ButtonStyle.danger)
        self.stop_button.callback = self.stop_callback
        self.stop_button.row = 1
        self.add_item(self.stop_button)

        self.refresh_state()

    def refresh_state(self):
        guild = bot.get_guild(self.guild_id)
        voice_client = guild.voice_client if guild else None
        state = get_player_state(self.guild_id)
        if voice_client is None:
            self.previous_button.disabled = True
            self.pause_button.emoji = "⏸️"
            self.pause_button.label = "\u200b"
            self.pause_button.disabled = True
            self.skip_button.disabled = True
            self.shuffle_button.disabled = True
            self.loop_button.emoji = "🔁"
            self.loop_button.label = "\u200b"
            self.loop_button.disabled = False
            self.queue_button.disabled = False
            self.stop_button.disabled = True
            self.shuffle_button.style = discord.ButtonStyle.secondary
            self.loop_button.style = discord.ButtonStyle.secondary
            return

        self.previous_button.disabled = not bool(state.get("history"))
        self.pause_button.emoji = "⏸️" if voice_client.is_paused() else "▶️"
        self.pause_button.label = "\u200b"
        self.pause_button.disabled = not (voice_client.is_playing() or voice_client.is_paused())
        self.pause_button.style = discord.ButtonStyle.green if voice_client.is_playing() or voice_client.is_paused() else discord.ButtonStyle.primary
        self.skip_button.disabled = not (voice_client.is_playing() or voice_client.is_paused())
        self.shuffle_button.disabled = len(get_server_queue(self.guild_id)) < 2
        self.shuffle_button.style = discord.ButtonStyle.green if state.get("shuffle") else discord.ButtonStyle.secondary
        self.loop_button.emoji = "🔁"
        self.loop_button.label = "\u200b"
        self.loop_button.style = discord.ButtonStyle.green if state.get("loop") != "off" else discord.ButtonStyle.secondary
        self.loop_button.disabled = False
        self.queue_button.disabled = False
        self.stop_button.disabled = False

    async def _ensure_voice_control(self, interaction):
        if interaction.guild is None:
            await interaction.response.send_message("This panel can only be used in a server voice channel.", ephemeral=True)
            return False

        voice_client = interaction.guild.voice_client
        if voice_client is None:
            await interaction.response.send_message("Vynlo is not connected to a voice channel.", ephemeral=True)
            return False

        if interaction.user.voice is None:
            await interaction.response.send_message("You need to be in a voice channel to control Vynlo.", ephemeral=True)
            return False

        if interaction.user.voice.channel != voice_client.channel:
            await interaction.response.send_message("You need to be in the same voice channel as Vynlo.", ephemeral=True)
            return False

        return True

    async def pause_resume_callback(self, interaction):
        if not await self._ensure_voice_control(interaction):
            return

        voice_client = interaction.guild.voice_client
        if voice_client.is_paused():
            voice_client.resume()
        elif voice_client.is_playing():
            voice_client.pause()
        else:
            await interaction.response.send_message("There is no audio to pause or resume.", ephemeral=True)
            return

        await interaction.response.defer()
        await update_player_panel(interaction.guild.id, interaction.channel.id)

    async def previous_callback(self, interaction):
        if not await self._ensure_voice_control(interaction):
            return

        history = get_player_state(interaction.guild.id).get("history", [])
        if not history:
            await interaction.response.send_message("There is no previous track in history.", ephemeral=True)
            return

        previous_track = history.pop()
        queue = get_server_queue(interaction.guild.id)
        queue.insert(0, previous_track)
        interaction.guild.voice_client.stop()
        await interaction.response.defer()
        await update_player_panel(interaction.guild.id, interaction.channel.id)

    async def skip_callback(self, interaction):
        if not await self._ensure_voice_control(interaction):
            return

        voice_client = interaction.guild.voice_client
        if not (voice_client.is_playing() or voice_client.is_paused()):
            await interaction.response.send_message("There is nothing playing to skip.", ephemeral=True)
            return

        voice_client.stop()
        await interaction.response.defer()
        await update_player_panel(interaction.guild.id, interaction.channel.id)

    async def stop_callback(self, interaction):
        if not await self._ensure_voice_control(interaction):
            return

        get_server_queue(interaction.guild.id).clear()
        interaction.guild.voice_client.stop()
        await interaction.response.defer()
        await update_player_panel(interaction.guild.id, interaction.channel.id)

    async def shuffle_callback(self, interaction):
        if not await self._ensure_voice_control(interaction):
            return

        state = get_player_state(interaction.guild.id)
        queue = get_server_queue(interaction.guild.id)
        if len(queue) < 2:
            await interaction.response.send_message("There are not enough tracks to shuffle.", ephemeral=True)
            return

        if state.get("shuffle"):
            original_order = state.get("original_queue")
            if original_order:
                queue[:] = original_order
                state["shuffle"] = False
                state["original_queue"] = None
            else:
                state["shuffle"] = False
        else:
            state["original_queue"] = list(queue)
            random.shuffle(queue)
            state["shuffle"] = True

        await interaction.response.defer()
        await update_player_panel(interaction.guild.id, interaction.channel.id)

    async def loop_callback(self, interaction):
        if not await self._ensure_voice_control(interaction):
            return

        cycle_loop_mode(interaction.guild.id)
        await interaction.response.defer()
        await update_player_panel(interaction.guild.id, interaction.channel.id)

    async def queue_callback(self, interaction):
        await interaction.response.send_modal(QueueAddModal(interaction.guild.id, interaction.channel.id))


def is_playlist_url(url):
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    query = parse_qs(parsed.query)

    is_youtube_host = any(domain in host for domain in ("youtube.com", "youtu.be", "music.youtube.com"))
    if not is_youtube_host:
        return False

    if parsed.path.startswith("/playlist"):
        return True

    return "list" in query or "listType" in query


def get_playlist_start_index(url):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    index_values = query.get("index")
    if not index_values:
        return 0

    try:
        return max(int(index_values[0]) - 1, 0)
    except (TypeError, ValueError):
        return 0


def get_playlist_url(url):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    playlist_id = (query.get("list") or [None])[0]
    if not playlist_id:
        return url

    return f"https://www.youtube.com/playlist?list={playlist_id}"


def build_playlist_track_url(entry, fallback_url):
    if not isinstance(entry, dict):
        return fallback_url

    direct_url = entry.get("webpage_url") or entry.get("url")
    if direct_url:
        return direct_url

    video_id = entry.get("id")
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"

    return fallback_url


def build_queue_message(guild_id):
    queue = queues.get(guild_id, [])
    if not queue:
        return "The queue is empty."

    visible_queue = queue[:10]
    lines = ["Now queued:"]
    for index, item in enumerate(visible_queue, start=1):
        title = item.get("title", "Unknown title") if isinstance(item, dict) else str(item)
        lines.append(f"{index}. {title}")

    if len(queue) > len(visible_queue):
        lines.append(f"... and {len(queue) - len(visible_queue)} more")

    return "\n".join(lines)


async def extract_audio_info(url):
    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {
            "youtube": [
                "player_client=android",
                "player_client=web",
                "player_client=tv_embedded",
            ]
        },
    }
    if not is_playlist_url(url):
        ydl_opts["noplaylist"] = True

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = await asyncio.to_thread(
            ydl.extract_info,
            url,
            download=False,
        )

    if info is None:
        raise ValueError("Could not find audio for the provided URL.")

    if "entries" in info and info["entries"]:
        info = info["entries"][0]

    return info


async def extract_playlist_tracks(url):
    if not is_playlist_url(url):
        info = await extract_audio_info(url)
        return [{
            "title": info.get("title", "Unknown title"),
            "source_url": info.get("webpage_url") or info.get("url") or url,
            "url": info.get("webpage_url") or info.get("url") or url,
            "stream_url": info.get("url") or info.get("webpage_url") or url,
        }]

    ydl_opts = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {
            "youtube": [
                "player_client=android",
                "player_client=web",
                "player_client=tv_embedded",
            ]
        },
    }

    playlist_url = get_playlist_url(url)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = await asyncio.to_thread(
            ydl.extract_info,
            playlist_url,
            download=False,
        )

    if info is None:
        raise ValueError("Could not find playlist audio for the provided URL.")

    entries = info.get("entries") or []
    if not entries:
        return []

    start_index = get_playlist_start_index(url)
    selected_entries = entries[start_index:]

    tracks = []
    for entry in selected_entries:
        if not entry:
            continue
        track_url = build_playlist_track_url(entry, url)
        tracks.append({
            "title": entry.get("title", "Unknown title"),
            "source_url": track_url,
            "url": track_url,
            "stream_url": None,
        })

    return tracks


async def resolve_track_audio(track):
    queue_url = track.get("source_url") or track.get("url") or track.get("stream_url")
    if not queue_url:
        return track

    info = await extract_audio_info(queue_url)
    title = info.get("title") or track.get("title") or "Unknown title"
    artist = info.get("artist") or info.get("uploader") or track.get("artist") or "Unknown artist"
    duration = info.get("duration") or track.get("duration")
    audio_url = info.get("url") or track.get("stream_url") or queue_url
    thumbnail = info.get("thumbnail") or info.get("thumbnails", [{}])[-1].get("url") if isinstance(info.get("thumbnails"), list) else None

    track["title"] = title
    track["artist"] = artist
    track["duration"] = duration
    track["thumbnail"] = thumbnail or track.get("thumbnail")
    track["stream_url"] = audio_url
    return track


async def play_next_in_queue(ctx):
    guild_queue = queues.get(ctx.guild.id, [])
    if not guild_queue:
        state = get_player_state(ctx.guild.id)
        state["current_track"] = None
        return

    current_state = get_player_state(ctx.guild.id)
    current_track = current_state.get("current_track")
    if current_track and isinstance(current_track, dict):
        current_state.setdefault("history", []).append(current_track)

    next_track = guild_queue.pop(0)
    next_track = await resolve_track_audio(next_track)
    current_state["current_track"] = next_track
    title = next_track.get("title", "Unknown title")
    audio_url = next_track.get("stream_url") or next_track.get("source_url") or next_track.get("url")

    if not audio_url:
        await ctx.send(f"Skipping **{title}** because no valid audio stream was found.")
        if ctx.guild.id in queues and queues[ctx.guild.id]:
            asyncio.run_coroutine_threadsafe(play_next_in_queue(ctx), bot.loop)
        return

    source = FFmpegPCMAudio(
        audio_url,
        before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        options="-vn",
    )

    def after_play(error):
        if error:
            print(f"Playback error: {error}")
            return

        if ctx.guild.id in queues and queues[ctx.guild.id]:
            asyncio.run_coroutine_threadsafe(play_next_in_queue(ctx), bot.loop)

    ctx.voice_client.play(source, after=after_play)
    await send_temporary_message(ctx, f"Playing **{title}** 🎵")
    if getattr(ctx, "channel", None) is not None:
        await update_player_panel(ctx.guild.id, ctx.channel.id)


# this is an event that is triggered when the bot is ready to start working, he will print the bot's username in the console
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# here we are adding another ! command, this one would be !join
@bot.command()
async def join(ctx):
    # if statement/condition to actually see if we are inside a voice channel. None comes from the discord.py library, it is a way to check if the user is in a voice channel or not. If the user is not in a voice channel, the bot will send a message saying "You are not in a voice channel!" and return from the function.
    if ctx.author.voice is None:
        await ctx.send("You are not in a voice channel!")
        return
    # We're storing the voice channel in a variable called channel. So this looks where my user is.
    channel = ctx.author.voice.channel
    # then we are telling the bot to connect to the voice channel that the user is in. This is done by using the connect() method from the discord.py library. This method is asynchronous, so we need to use the await keyword before it.
    await channel.connect()
    await create_or_update_player_panel(ctx)
    await send_temporary_message(
        ctx,
        f"✅ Joined {channel}!\n\n"
        "**Vynlo music controls**\n"
        "• `!play <url>` — play a song or playlist\n"
        "• `!queue` — see the current queue\n"
        "• `!skip` — skip the current track\n"
        "• `!clearqueue` — clear the queue\n"
        "• `!leave` — disconnect the bot\n\n"
        "**Playback controls**\n"
        "• `!pause` — pause the music\n"
        "• `!resume` — resume playback\n"
        "• `!stop` — stop and clear everything\n",
    )


@bot.command()
async def panel(ctx):
    await create_or_update_player_panel(ctx)
    await send_temporary_message(ctx, "🎵 Player panel ready. Use the buttons below to control the music.")


@bot.command()
async def start(ctx):
    await create_or_update_player_panel(ctx)
    await send_temporary_message(ctx, "🎵 Vynlo is live and ready to control.")

@bot.command()
async def info(ctx):
    await send_temporary_message(
        ctx,
        "🎵 **Vynlo music bot**\n\n"
        "**What I can do**\n"
        "• `!play <url>` — play a single track or a whole playlist\n"
        "• `!queue` — show what’s queued up next\n"
        "• `!skip` — skip the currently playing track\n"
        "• `!clearqueue` — remove everything from the queue\n"
        "• `!leave` — disconnect the bot from the voice channel\n\n"
        "**Playback controls**\n"
        "• `!pause` — pause the current track\n"
        "• `!resume` — continue where you left off\n"
        "• `!stop` — stop playback and clear the queue\n\n"
        "**Tip**: You can paste a YouTube song link or playlist link directly after `!play`.",
    )


@bot.command()
async def leave(ctx):
    if ctx.voice_client is None:
        await ctx.send("I am not in a voice channel!")
        return

    guild_queue = get_server_queue(ctx.guild.id)
    guild_queue.clear()
    connectedchannel = ctx.voice_client
    await connectedchannel.disconnect()
    await send_temporary_message(ctx, "Disconnected from the voice channel and cleared the queue.")

# this is for the bot to be able to play audio in a voice channel, this is done by using the FFmpeg library, which is a library that can be used to convert audio and video files. In this case, we are using it to convert an mp3 file to a format that can be played in a voice channel.
@bot.command()
async def play(ctx, url):
    await cleanup_user_command_message(ctx)

    if ctx.author.voice is None:
        await send_temporary_message(ctx, "You are not in a voice channel!")
        return

    if ctx.voice_client is None:
        await ctx.author.voice.channel.connect()

    guild_queue = get_server_queue(ctx.guild.id)

    try:
        if is_playlist_url(url):
            await send_temporary_message(ctx, "Playlist detected — building the rest of the playlist and starting playback...")
            tracks = await extract_playlist_tracks(url)
            if not tracks:
                await send_temporary_message(ctx, "I could not find any playable tracks in that playlist.")
                return

            if ctx.voice_client.is_playing() or ctx.voice_client.is_paused() or guild_queue:
                guild_queue.extend(tracks)
                await send_temporary_message(ctx, f"Added **{len(tracks)} tracks** from the playlist to the queue.")
                return

            first_track = await resolve_track_audio(tracks[0])
            if len(tracks) > 1:
                guild_queue.extend([await resolve_track_audio(track) for track in tracks[1:]])

            get_player_state(ctx.guild.id)["current_track"] = first_track
            await send_temporary_message(ctx, f"Playing **{first_track['title']}** 🎵")

            source = FFmpegPCMAudio(
                first_track["stream_url"],
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn",
            )

            def after_play(error):
                if error:
                    print(f"Playback error: {error}")
                    return

                if ctx.guild.id in queues and queues[ctx.guild.id]:
                    asyncio.run_coroutine_threadsafe(play_next_in_queue(ctx), bot.loop)

            ctx.voice_client.play(source, after=after_play)
            asyncio.run_coroutine_threadsafe(update_player_panel(ctx.guild.id, ctx.channel.id), bot.loop)
            return

        info = await extract_audio_info(url)
    except Exception:
        await send_temporary_message(ctx, "I could not find audio for that URL. Please try another one.")
        return

    track = {
        "title": info.get("title", "Unknown title"),
        "source_url": info.get("webpage_url") or info.get("url") or url,
        "url": info.get("webpage_url") or info.get("url") or url,
        "stream_url": info.get("url") or url,
    }

    if ctx.voice_client.is_playing() or ctx.voice_client.is_paused() or guild_queue:
        guild_queue.append(track)
        await send_temporary_message(ctx, f"Added **{track['title']}** to the queue. Position: {len(guild_queue)}")
        await update_player_panel(ctx.guild.id, ctx.channel.id)
        return

    get_player_state(ctx.guild.id)["current_track"] = track
    await send_temporary_message(ctx, f"Playing **{track['title']}** 🎵")

    source = FFmpegPCMAudio(
        track["stream_url"],
        before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        options="-vn",
    )

    def after_play(error):
        if error:
            print(f"Playback error: {error}")
            return

        if ctx.guild.id in queues and queues[ctx.guild.id]:
            asyncio.run_coroutine_threadsafe(play_next_in_queue(ctx), bot.loop)

    ctx.voice_client.play(source, after=after_play)
    await update_player_panel(ctx.guild.id, ctx.channel.id)


@bot.command()
async def queue(ctx):
    await send_temporary_message(ctx, build_queue_message(ctx.guild.id))
    await update_player_panel(ctx.guild.id, ctx.channel.id)


@bot.command()
async def skip(ctx):
    if ctx.voice_client is None:
        await send_temporary_message(ctx, "I am not in a voice channel!")
        return

    if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
        await send_temporary_message(ctx, "There is nothing playing to skip.")
        return

    ctx.voice_client.stop()
    await send_temporary_message(ctx, "Skipped the current track.")
    await update_player_panel(ctx.guild.id, ctx.channel.id)


@bot.command(aliases=['clear', 'cq'])
async def clearqueue(ctx):
    get_server_queue(ctx.guild.id).clear()
    await send_temporary_message(ctx, "The queue has been cleared.")
    await update_player_panel(ctx.guild.id, ctx.channel.id)

@bot.command()
async def stop(ctx):
    if ctx.voice_client is None:
        await send_temporary_message(ctx, "I am not in a voice channel!")
        return

    get_server_queue(ctx.guild.id).clear()
    get_player_state(ctx.guild.id)["current_track"] = None
    ctx.voice_client.stop()
    await send_temporary_message(ctx, "Stopped playing audio and cleared the queue.")
    await update_player_panel(ctx.guild.id, ctx.channel.id)

@bot.command()
async def pause(ctx):
    if ctx.voice_client is None:
        await send_temporary_message(ctx, "I am not in a voice channel!")
        return

    if not ctx.voice_client.is_playing():
        await send_temporary_message(ctx, "No audio is currently playing.")
        return

    ctx.voice_client.pause()
    await send_temporary_message(ctx, "Paused audio.")
    await update_player_panel(ctx.guild.id, ctx.channel.id)

@bot.command()
async def resume(ctx):
    if ctx.voice_client is None:
        await send_temporary_message(ctx, "I am not in a voice channel!")
        return

    if not ctx.voice_client.is_paused():
        await send_temporary_message(ctx, "Audio is not paused. You may have cancelled the audio with !stop or the audio has finished playing.")
        return

    ctx.voice_client.resume()
    await send_temporary_message(ctx, "Resumed audio.")
    await update_player_panel(ctx.guild.id, ctx.channel.id)

# this now grabs the token from the .env file instead of publicly putting it on git.
if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))