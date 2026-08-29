import os
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


def get_server_queue(guild_id):
    return queues.setdefault(guild_id, [])


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
        "format": "bestaudio",
        "quiet": True,
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
    audio_url = info.get("url") or track.get("stream_url") or queue_url

    track["title"] = title
    track["stream_url"] = audio_url
    return track


async def play_next_in_queue(ctx):
    guild_queue = queues.get(ctx.guild.id, [])
    if not guild_queue:
        return

    next_track = guild_queue.pop(0)
    next_track = await resolve_track_audio(next_track)
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
    await ctx.send(f"Playing **{title}** 🎵")


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
    await ctx.send(
        f"✅ Joined {channel}!\n\n"
        "```md\n"
        "Music Bot Command Menu\n"
        "======================\n\n"
        "!play <url>    - Play a song and auto-join if needed\n"
        "!queue        - Show the current queue\n"
        "!skip         - Skip the current song\n"
        "!clearqueue   - Remove every queued song\n"
        "!leave        - Disconnect the bot\n"
        "\n"
        "Current song controls:\n"
        "!pause        - Pause the current track\n"
        "!resume       - Resume the paused track\n"
        "!stop         - Stop playback and clear the queue\n"
        "```"
    )

@bot.command()
async def info(ctx):
    await ctx.send(
        "```md\n"
        "Vynlo Command List\n"
        "==================\n\n"
        "!play <url>    - Play a song or playlist\n"
        "!queue        - Show the current queue\n"
        "!skip         - Skip the current song\n"
        "!clearqueue   - Remove every queued song\n"
        "!leave        - Disconnect the bot\n"
        "\n"
        "Current song controls:\n"
        "!pause        - Pause the current track\n"
        "!resume       - Resume the paused track\n"
        "!stop         - Stop playback and clear the queue\n"
        "```"
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
    await ctx.send("Disconnected from the voice channel and cleared the queue.")

# this is for the bot to be able to play audio in a voice channel, this is done by using the FFmpeg library, which is a library that can be used to convert audio and video files. In this case, we are using it to convert an mp3 file to a format that can be played in a voice channel.
@bot.command()
async def play(ctx, url):
    if ctx.author.voice is None:
        await ctx.send("You are not in a voice channel!")
        return

    if ctx.voice_client is None:
        await ctx.author.voice.channel.connect()

    guild_queue = get_server_queue(ctx.guild.id)

    try:
        if is_playlist_url(url):
            await ctx.send("Playlist detected — building the rest of the playlist and starting playback...")
            tracks = await extract_playlist_tracks(url)
            if not tracks:
                await ctx.send("I could not find any playable tracks in that playlist.")
                return

            if ctx.voice_client.is_playing() or ctx.voice_client.is_paused() or guild_queue:
                guild_queue.extend(tracks)
                await ctx.send(f"Added **{len(tracks)} tracks** from the playlist to the queue.")
                return

            first_track = await resolve_track_audio(tracks[0])
            if len(tracks) > 1:
                guild_queue.extend([await resolve_track_audio(track) for track in tracks[1:]])

            await ctx.send(f"Playing **{first_track['title']}** 🎵")

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
            return

        info = await extract_audio_info(url)
    except Exception:
        await ctx.send("I could not find audio for that URL. Please try another one.")
        return

    track = {
        "title": info.get("title", "Unknown title"),
        "source_url": info.get("webpage_url") or info.get("url") or url,
        "url": info.get("webpage_url") or info.get("url") or url,
        "stream_url": info.get("url") or url,
    }

    if ctx.voice_client.is_playing() or ctx.voice_client.is_paused() or guild_queue:
        guild_queue.append(track)
        await ctx.send(f"Added **{track['title']}** to the queue. Position: {len(guild_queue)}")
        return

    await ctx.send(f"Playing **{track['title']}** 🎵")

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


@bot.command()
async def queue(ctx):
    await ctx.send(build_queue_message(ctx.guild.id))


@bot.command()
async def skip(ctx):
    if ctx.voice_client is None:
        await ctx.send("I am not in a voice channel!")
        return

    if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
        await ctx.send("There is nothing playing to skip.")
        return

    ctx.voice_client.stop()
    await ctx.send("Skipped the current track.")


@bot.command(aliases=['clear', 'cq'])
async def clearqueue(ctx):
    get_server_queue(ctx.guild.id).clear()
    await ctx.send("The queue has been cleared.")

@bot.command()
async def stop(ctx):
    if ctx.voice_client is None:
        await ctx.send("I am not in a voice channel!")
        return

    get_server_queue(ctx.guild.id).clear()
    ctx.voice_client.stop()
    await ctx.send("Stopped playing audio and cleared the queue.")

@bot.command()
async def pause(ctx):
    if ctx.voice_client is None:
        await ctx.send("I am not in a voice channel!")
        return

    if not ctx.voice_client.is_playing():
        await ctx.send("No audio is currently playing.")
        return

    ctx.voice_client.pause()
    await ctx.send("Paused audio.")

@bot.command()
async def resume(ctx):
    if ctx.voice_client is None:
        await ctx.send("I am not in a voice channel!")
        return

    if not ctx.voice_client.is_paused():
        await ctx.send("Audio is not paused. You may have cancelled the audio with !stop or the audio has finished playing.")
        return

    ctx.voice_client.resume()
    await ctx.send("Resumed audio.")

@bot.command()
async def testyoutube(ctx, url):

    ydl_opts = {
        "format": "bestaudio",
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = await asyncio.to_thread(
            ydl.extract_info,
            url,
            download=False
        )

    await ctx.send(f"Title: {info['title']}")
    print(info["url"])

# this now grabs the token from the .env file instead of publicly putting it on git.
if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))