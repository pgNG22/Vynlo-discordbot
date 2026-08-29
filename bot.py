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


# this is an event that is triggered when the bot is ready to start working, he will print the bot's username in the console
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# this is where we can add commands for the bot, in this case we are adding a command called hello that will respond with "Hello!" when the user types !hello
@bot.command()
async def hello(ctx):
    await ctx.send("Hello!")

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
        f"Joined {channel}!\n\n"
        "Functions:\n"
        "!leave - Disconnects the bot from the voice channel.\n"
        "!play <url> - Plays audio from the given URL in the voice channel.\n"
        "!stop - Stops playing audio.\n"
        "!pause - Pauses the currently playing audio.\n"
        "!resume - Resumes the paused audio."
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

    ydl_opts = {
        "format": "bestaudio",
        "noplaylist": True,
    }

    await ctx.send("Finding audio...")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = await asyncio.to_thread(
            ydl.extract_info,
            url,
            download=False
        )

    title = info["title"]
    audio_url = info["url"]

    await ctx.send(f"Playing **{title}** 🎵")

    # stops the audio from dropping out, attempts to retry the connection if it drops out, and sets a maximum delay for reconnecting.
    source = FFmpegPCMAudio(
    audio_url,
    before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    options="-vn"
)

    ctx.voice_client.play(source)

@bot.command()
async def stop(ctx):
    if ctx.voice_client is None:
        await ctx.send("I am not in a voice channel!")
        return

    ctx.voice_client.stop()
    await ctx.send("Stopped playing audio.")

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
bot.run(os.getenv("DISCORD_TOKEN"))