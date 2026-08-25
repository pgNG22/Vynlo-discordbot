import os
from dotenv import load_dotenv

# here, we are telling the bot to use the discord.py library and the commands extension
import discord
# here we are telling the bot to use the commands extension from discord.py
from discord.ext import commands

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
        "!leave - Disconnects the bot from the voice channel."
)   

@bot.command()
async def leave(ctx):
    if ctx.author.voice is None:
        await ctx.send("I am not in a voice channel!")
        return
    connectedchannel = ctx.voice_client
    # Disconnect the bot from the voice channel
    await connectedchannel.disconnect()
    await ctx.send("Disconnected from the voice channel!")

# this now grabs the token from the .env file instead of publicly putting it on git.
bot.run(os.getenv("DISCORD_TOKEN"))