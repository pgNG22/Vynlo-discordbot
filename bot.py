import os
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


def build_queue_message(guild_id):
    queue = queues.get(guild_id, [])
    if not queue:
        return "The queue is empty."

    lines = ["Now queued:"]
    for index, item in enumerate(queue, start=1):
        lines.append(f"{index}. {item['title']}")
    return "\n".join(lines)


async def extract_audio_info(url):
    ydl_opts = {
        "format": "bestaudio",
        "noplaylist": True,
    }

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


async def play_next_in_queue(ctx):
    guild_queue = queues.get(ctx.guild.id, [])
    if not guild_queue:
        return

    next_track = guild_queue.pop(0)
    queue_url = next_track.get("source_url") or next_track.get("url") or next_track.get("stream_url")
    info = await extract_audio_info(queue_url)
    title = info.get("title") or next_track.get("title") or "Unknown title"
    audio_url = info.get("url") or next_track.get("stream_url") or queue_url

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
async def leave(ctx):
    if ctx.voice_client is None:
        await ctx.send("I am not in a voice channel!")
        return
    connectedchannel = ctx.voice_client
    # Disconnect the bot from the voice channel
    await connectedchannel.disconnect()
    await ctx.send("Disconnected from the voice channel!")

# this is for the bot to be able to play audio in a voice channel, this is done by using the FFmpeg library, which is a library that can be used to convert audio and video files. In this case, we are using it to convert an mp3 file to a format that can be played in a voice channel.
@bot.command()
async def play(ctx, url):
    if ctx.author.voice is None:
        await ctx.send("You are not in a voice channel!")
        return

    if ctx.voice_client is None:
        await ctx.author.voice.channel.connect()

    await ctx.send("Use !info to see the full command list.")

    try:
        info = await extract_audio_info(url)
    except Exception:
        await ctx.send("I could not find audio for that URL. Please try another one.")
        return

    track = {
        "title": info.get("title", "Unknown title"),
        "source_url": url,
        "url": url,
        "stream_url": info.get("url") or url,
    }

    guild_queue = queues.setdefault(ctx.guild.id, [])

    if ctx.voice_client.is_playing() or ctx.voice_client.is_paused() or guild_queue:
        guild_queue.append(track)
        await ctx.send(f"Added **{track['title']}** to the queue. Position: {len(guild_queue)}")
        return

    await ctx.send("Finding audio...")
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


@bot.command()
async def clearqueue(ctx):
    queues[ctx.guild.id] = []
    await ctx.send("The queue has been cleared.")

@bot.command()
async def stop(ctx):
    if ctx.voice_client is None:
        await ctx.send("I am not in a voice channel!")
        return

    queues[ctx.guild.id] = []
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