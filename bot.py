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
MAX_HISTORY_ITEMS = 25
DEFAULT_EMBED_IMAGE = (
    "https://raw.githubusercontent.com/pgNG22/Vynlo-discordbot/main/img/thumbnail-fallback.png"
)


def trim_history(history):
    if len(history) > MAX_HISTORY_ITEMS:
        del history[:-MAX_HISTORY_ITEMS]
    return history


def record_history_entry(state, track):
    history = state.setdefault("history", [])
    history.append(track)
    state["history"] = trim_history(history)
    return state["history"]


def get_server_queue(guild_id):
    return queues.setdefault(guild_id, [])


def clear_guild_state(guild_id):
    queues.pop(guild_id, None)
    player_state.pop(guild_id, None)

    for key in list(player_panels):
        if key[0] == guild_id:
            del player_panels[key]


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
        "skip_requested": False,
    })
    state.setdefault("volume", 100)
    state.setdefault("loop", "off")
    state.setdefault("shuffle", False)
    state["history"] = trim_history(state.setdefault("history", []))
    state.setdefault("current_track", None)
    state.setdefault("skip_requested", False)
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

async def send_temporary_message_info(ctx, message, *, delete_after=30):
    await ctx.send(message, delete_after=delete_after)


async def send_temporary_interaction_message(interaction, message, *, ephemeral=True, delete_after=5):
    try:
        msg = await interaction.followup.send(message, ephemeral=ephemeral)
        # Manually delete after delay since delete_after is not supported for followup
        if not ephemeral:
            await asyncio.sleep(delete_after)
            try:
                await msg.delete()
            except Exception:
                pass
    except Exception as e:
        print(f"Failed to send temporary interaction message: {e}")


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
    current_track = get_now_playing_track(guild_id)
    thumbnail_url = (
        current_track.get("thumbnail")
        if isinstance(current_track, dict) and current_track.get("thumbnail")
        else DEFAULT_EMBED_IMAGE
    )

    embed = discord.Embed(
        title="LIVE QUEUE",
        description="\u200b",
        color=discord.Color.from_rgb(160, 120, 255),
    )
    embed.set_image(url=thumbnail_url)

    if not queue:
        embed.description = "The queue is empty."
        embed.set_footer(text="Vynlo • by pgdev")
        return embed

    visible_queue = queue[:8]
    lines = []
    for index, item in enumerate(visible_queue, start=1):
        if isinstance(item, dict):
            title = item.get("title", "Unknown title")
            requester = item.get("requested_by")
            if requester:
                lines.append(f"{index}. {title} `by {requester}`")
            else:
                lines.append(f"{index}. {title}")
        else:
            lines.append(f"{index}. {str(item)}")

    if len(queue) > len(visible_queue):
        lines.append(f"... +{len(queue) - len(visible_queue)} more")

    embed.add_field(name="Upcoming", value="\n".join(lines), inline=False)
    embed.set_footer(text=f"{len(queue)} tracks in queue • Vynlo • by pgdev")
    return embed


def build_player_embed(guild_id):
    guild = bot.get_guild(guild_id)
    voice_client = guild.voice_client if guild else None
    queue = queues.get(guild_id, [])
    current_track = get_now_playing_track(guild_id)
    volume_percent = get_volume_percent(guild_id)
    loop_label = get_loop_label(guild_id)
    fallback_thumbnail = DEFAULT_EMBED_IMAGE

    # Determine playback state
    if voice_client is None:
        playback_state = "Disconnected"
    elif voice_client.is_paused():
        playback_state = "Paused"
    elif voice_client.is_playing():
        playback_state = "Playing"
    else:
        playback_state = "Idle"

    embed = discord.Embed(
        color=discord.Color.from_rgb(180, 98, 255),
    )

    if current_track:
        title = current_track.get("title", "Unknown title")
        artist = (
            current_track.get("artist")
            or current_track.get("uploader")
            or "Unknown artist"
        )

        duration = current_track.get("duration")
        duration_text = format_duration(duration)
        requester = current_track.get("requested_by")
        requested_by_text = f"`requested by {requester}`" if requester else "`requested by Unknown`"

        # Main player information
        embed.description = (
            "🎶 ** NOW PLAYING:**\n\n"
            f"### {title}\n\n"
            f"**Artist: {artist}**\n"
            f"Duration: `{duration_text}` {requested_by_text}\n\n"
        )

        # Album artwork
        if current_track.get("thumbnail"):
            embed.set_image(url=current_track["thumbnail"])
        else:
            embed.set_image(url=fallback_thumbnail)

    else:
        embed.description = (
            "🎶 **NOW PLAYING**\n\n"
            "### Nothing is playing right now\n"
            "Add a song to the queue to get started."
        )
        embed.set_image(url=fallback_thumbnail)

    # Player information
    #embed.add_field(
    #    name="🎧 State",
   #     value=f"**{playback_state}**",
    #    inline=True,
   # )

    #embed.add_field(
    #    name="📋 Queue",
    #    value=f"**{len(queue)}** track(s)",
    #    inline=True,
    #)
    next_track = queue[0] if queue else None

    embed.add_field(
        name="\u200b",
        value="\u200b",
        inline=False,
    )

    embed.add_field(
        name="\u200b",
        value="\u200b",
        inline=False,
    )   

    embed.add_field(
        name="🔊 Queued Next:",
        value=f"**{next_track.get('title', 'Unknown track')}**" if next_track else "**Nothing queued**",
        inline=True,
    )

    # Footer
    embed.set_footer(
        text="Vynlo • by pgdev"
        )

    return embed

async def create_or_update_player_panel(guild, channel):
    guild_id = guild.id
    channel_id = channel.id
    key = (guild_id, channel_id)

    embed = build_player_embed(guild_id)
    view = MusicPlayerView(guild_id, channel_id)

    # If we already know about the player message,
    # try to update it.
    existing_message_id = player_panels.get(key)

    if existing_message_id:
        try:
            message = await channel.fetch_message(existing_message_id)
            await message.edit(embed=embed, view=view)
            return message

        except discord.NotFound:
            player_panels.pop(key, None)

    # If we don't know the message ID, look through recent
    # messages to see if Vynlo already has a player message.
    try:
        async for message in channel.history(limit=50):
            if message.author == bot.user and message.embeds:
                embed = message.embeds[0]

                if embed.description and (
                    "NOW PLAYING" in embed.description
                    or "Nothing is playing right now" in embed.description
                ):
                    player_panels[key] = message.id

                    await message.edit(
                        embed=build_player_embed(guild_id),
                        view=MusicPlayerView(guild_id, channel_id)
                    )

                    return message

    except discord.Forbidden:
        print(f"Vynlo does not have permission to read {channel.name}")

    # No existing player found, so create one.
    message = await channel.send(
        embed=build_player_embed(guild_id),
        view=MusicPlayerView(guild_id, channel_id)
    )

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
    except discord.HTTPException as e:
        print(f"Player panel update failed: {e}")



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
        # Acknowledge the interaction immediately.
        # This prevents Discord's 3-second interaction timeout.
        await interaction.response.defer(ephemeral=True)

        url = (self.url_input.value or "").strip()

        if not url:
            await send_temporary_interaction_message(
                interaction,
                "Please enter a valid URL.",
                ephemeral=False,
                delete_after=3
            )
            return

        # Validate URL format
        if not url.startswith(("http://", "https://")):
            await send_temporary_interaction_message(
                interaction,
                "That doesn't look like a valid URL. Make sure it starts with http:// or https://",
                ephemeral=False,
                delete_after=3
            )
            return

        if interaction.user.voice is None:
            await send_temporary_interaction_message(
                interaction,
                "You need to be in a voice channel to add music.",
                ephemeral=False,
                delete_after=3
            )
            return

        # Connect to the user's voice channel if needed
        if interaction.guild.voice_client is None:
            await interaction.user.voice.channel.connect()

        guild_queue = get_server_queue(interaction.guild.id)

        try:
            # ---------------------------------------------------------
            # PLAYLIST
            # ---------------------------------------------------------
            if is_playlist_url(url):
                await send_temporary_interaction_message(
                    interaction,
                    "Playlist detected. Vynlo is building the queue... This may take a moment.",
                    ephemeral=False,
                    delete_after=3
                )
                
                tracks = await extract_playlist_tracks(url)

                if not tracks:
                    await send_temporary_interaction_message(
                        interaction,
                        "I could not find any playable tracks in that playlist.",
                        ephemeral=False,
                        delete_after=3
                    )
                    return

                tracks = [compact_track(track) for track in tracks]

                voice_client = interaction.guild.voice_client

                # If something is already playing/paused, or there is
                # already something in the queue, add everything.
                if (
                    voice_client.is_playing()
                    or voice_client.is_paused()
                    or guild_queue
                ):
                    guild_queue.extend(tracks)

                    await send_temporary_interaction_message(
                        interaction,
                        f"Added **{len(tracks)} tracks** from the playlist to the queue."
                    )

                    await update_player_panel(
                        interaction.guild.id,
                        interaction.channel.id
                    )

                    return

                # Nothing is playing, so the first playlist track starts now.
                first_track = await resolve_track_audio(tracks[0])

                # Resolve and queue the remaining tracks.
                if len(tracks) > 1:
                    guild_queue.extend(
                        [
                            await resolve_track_audio(track)
                            for track in tracks[1:]
                        ]
                    )

                get_player_state(
                    interaction.guild.id
                )["current_track"] = first_track

                source = FFmpegPCMAudio(
                    first_track["stream_url"],
                    before_options=(
                        "-reconnect 1 "
                        "-reconnect_streamed 1 "
                        "-reconnect_delay_max 5"
                    ),
                    options="-vn",
                )

                def after_play(error):
                    if error:
                        print(f"Playback error: {error}")
                        return

                    asyncio.run_coroutine_threadsafe(
                        play_next_in_queue(
                            interaction.guild.id,
                            interaction.channel
                        ),
                        bot.loop
                    )

                voice_client.play(
                    source,
                    after=after_play
                )

                await update_player_panel(
                    interaction.guild.id,
                    interaction.channel.id
                )

                return

            # ---------------------------------------------------------
            # SINGLE TRACK
            # ---------------------------------------------------------
            info = await extract_audio_info(url)

        except Exception as e:
            print(f"QueueAddModal error: {e}")

            await send_temporary_interaction_message(
                interaction,
                "I could not find audio for that URL. Please try another one.",
                ephemeral=False,
                delete_after=3
            )

            return

        # Build track object
        track = compact_track({
            "title": info.get("title", "Unknown title"),
            "source_url": info.get("webpage_url") or info.get("url") or url,
            "url": info.get("webpage_url") or info.get("url") or url,
            "stream_url": info.get("url") or url,
            "artist": info.get("artist") or info.get("uploader"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "requested_by": interaction.user.display_name or interaction.user.name,
        })

        voice_client = interaction.guild.voice_client

        # -------------------------------------------------------------
        # ADD TO EXISTING QUEUE
        # -------------------------------------------------------------
        if (
            voice_client.is_playing()
            or voice_client.is_paused()
            or guild_queue
        ):
            guild_queue.append(track)

            await update_player_panel(
                interaction.guild.id,
                interaction.channel.id
            )

            return

        # -------------------------------------------------------------
        # START PLAYING IMMEDIATELY
        # -------------------------------------------------------------
        get_player_state(
            interaction.guild.id
        )["current_track"] = track

        source = FFmpegPCMAudio(
            track["stream_url"],
            before_options=(
                "-reconnect 1 "
                "-reconnect_streamed 1 "
                "-reconnect_delay_max 5"
            ),
            options="-vn",
        )

        def after_play(error):
            if error:
                print(f"Playback error: {error}")
                return

            asyncio.run_coroutine_threadsafe(
                play_next_in_queue(
                    interaction.guild.id,
                    interaction.channel
                ),
                bot.loop
            )

        voice_client.play(
            source,
            after=after_play
        )

        await update_player_panel(
            interaction.guild.id,
            interaction.channel.id
        )



class QueueView(discord.ui.View):
    def __init__(self, guild_id, channel_id=None, *, timeout=None):
        super().__init__(timeout=timeout)

        self.guild_id = guild_id
        self.channel_id = channel_id

        self.add_button = discord.ui.Button(
            label="Add to Queue",
            emoji="➕",
            style=discord.ButtonStyle.primary,
            row=0
        )

        self.back_button = discord.ui.Button(
            label="Back to Player",
            emoji="🔙",
            style=discord.ButtonStyle.secondary,
            row=0
        )

        self.add_button.callback = self.add_to_queue_callback
        self.back_button.callback = self.back_to_player_callback

        self.add_item(self.add_button)
        self.add_item(self.back_button)

    async def add_to_queue_callback(self, interaction):
        await interaction.response.send_modal(
            QueueAddModal(
                self.guild_id,
                self.channel_id
            )
        )

    async def back_to_player_callback(self, interaction):
        await interaction.response.edit_message(
            embed=build_player_embed(self.guild_id),
            view=MusicPlayerView(
                self.guild_id,
                self.channel_id
            )
        )

class MusicPlayerView(discord.ui.View):
    def __init__(self, guild_id, channel_id=None, *, timeout=None):
        super().__init__(timeout=timeout)

        self.guild_id = guild_id
        self.channel_id = channel_id

        # ─────────────────────────────
        # ROW 0 — MAIN PLAYER CONTROLS
        # ─────────────────────────────

        self.previous_button = discord.ui.Button(
            emoji="⏮️",
            label="Previous",
            custom_id=f"player_previous_{guild_id}",
            style=discord.ButtonStyle.secondary,
            row=0,
        )
        self.previous_button.callback = self.previous_callback
        self.add_item(self.previous_button)

        self.pause_button = discord.ui.Button(
            emoji="⏸️",
            label="Pause",
            custom_id=f"player_pause_{guild_id}",
            style=discord.ButtonStyle.primary,
            row=0,
        )
        self.pause_button.callback = self.pause_resume_callback
        self.add_item(self.pause_button)

        self.skip_button = discord.ui.Button(
            emoji="⏭️",
            label="Skip",
            custom_id=f"player_skip_{guild_id}",
            style=discord.ButtonStyle.secondary,
            row=0,
        )
        self.skip_button.callback = self.skip_callback
        self.add_item(self.skip_button)

        # ─────────────────────────────
        # ROW 1 — SECONDARY CONTROLS
        # ─────────────────────────────

        self.shuffle_button = discord.ui.Button(
            emoji="🔀",
            label="Shuffle",
            custom_id=f"player_shuffle_{guild_id}",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        self.shuffle_button.callback = self.shuffle_callback
        self.add_item(self.shuffle_button)

        self.loop_button = discord.ui.Button(
            emoji="🔁",
            label="Loop",
            custom_id=f"player_loop_{guild_id}",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        self.loop_button.callback = self.loop_callback
        self.add_item(self.loop_button)

        self.queue_button = discord.ui.Button(
            emoji="📋",
            label="Queue",
            custom_id=f"player_queue_{guild_id}",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        self.queue_button.callback = self.queue_callback
        self.add_item(self.queue_button)

        self.stop_button = discord.ui.Button(
            emoji="⏹️",
            label="Stop",
            custom_id=f"player_stop_{guild_id}",
            style=discord.ButtonStyle.danger,
            row=1,
        )
        self.stop_button.callback = self.stop_callback
        self.add_item(self.stop_button)

        self.refresh_state()

    def refresh_state(self):
        guild = bot.get_guild(self.guild_id)
        voice_client = guild.voice_client if guild else None
        state = get_player_state(self.guild_id)

        if voice_client is None:
            self.previous_button.disabled = True

            self.pause_button.emoji = "▶️"
            self.pause_button.label = "Play"
            self.pause_button.disabled = True

            self.skip_button.disabled = True
            self.shuffle_button.disabled = True

            self.loop_button.emoji = "🔁"
            self.loop_button.label = "Loop"
            self.loop_button.disabled = False

            self.queue_button.disabled = False
            self.stop_button.disabled = True

            self.shuffle_button.style = discord.ButtonStyle.secondary
            self.loop_button.style = discord.ButtonStyle.secondary

            return

        # Previous
        self.previous_button.disabled = not bool(
            state.get("history")
        )

        # Pause / Resume
        if voice_client.is_paused():
            self.pause_button.emoji = "▶️"
            self.pause_button.label = "Resume"
        else:
            self.pause_button.emoji = "⏸️"
            self.pause_button.label = "Pause"

        self.pause_button.disabled = not (
            voice_client.is_playing()
            or voice_client.is_paused()
        )

        self.pause_button.style = (
            discord.ButtonStyle.success
            if voice_client.is_playing()
            or voice_client.is_paused()
            else discord.ButtonStyle.primary
        )

        # Skip
        self.skip_button.disabled = not (
            voice_client.is_playing()
            or voice_client.is_paused()
        )

        # Shuffle
        self.shuffle_button.disabled = (
            len(get_server_queue(self.guild_id)) < 2
        )

        if state.get("shuffle"):
            self.shuffle_button.style = discord.ButtonStyle.success
            self.shuffle_button.label = "Shuffle On"
        else:
            self.shuffle_button.style = discord.ButtonStyle.secondary
            self.shuffle_button.label = "Shuffle"

        # Loop
        self.loop_button.emoji = "🔁"

        if state.get("loop") != "off":
            self.loop_button.style = discord.ButtonStyle.success
            self.loop_button.label = "Loop On"
        else:
            self.loop_button.style = discord.ButtonStyle.secondary
            self.loop_button.label = "Loop"

        self.loop_button.disabled = False

        # Queue
        self.queue_button.disabled = False

        # Stop
        self.stop_button.disabled = False

    async def pause_resume_callback(self, interaction):
        await interaction.response.defer()

        if interaction.guild is None:
            await send_temporary_interaction_message(
                interaction,
                "This panel can only be used in a server voice channel."
            )
            return

        voice_client = interaction.guild.voice_client

        if voice_client is None:
            await send_temporary_interaction_message(
                interaction,
                "Vynlo is not connected to a voice channel."
            )
            return

        if interaction.user.voice is None:
            await send_temporary_interaction_message(
                interaction,
                "You need to be in a voice channel to control Vynlo."
            )
            return

        if interaction.user.voice.channel != voice_client.channel:
            await send_temporary_interaction_message(
                interaction,
                "You need to be in the same voice channel as Vynlo."
            )
            return

        if voice_client.is_paused():
            voice_client.resume()

        elif voice_client.is_playing():
            voice_client.pause()

        else:
            await send_temporary_interaction_message(
                interaction,
                "There is no audio to pause or resume."
            )
            return

        await update_player_panel(
            interaction.guild.id,
            interaction.channel.id
        )

    async def previous_callback(self, interaction):
        await interaction.response.defer()

        if interaction.guild is None:
            await send_temporary_interaction_message(
                interaction,
                "This panel can only be used in a server voice channel."
            )
            return

        voice_client = interaction.guild.voice_client

        if voice_client is None:
            await send_temporary_interaction_message(
                interaction,
                "Vynlo is not connected to a voice channel."
            )
            return

        if interaction.user.voice is None:
            await send_temporary_interaction_message(
                interaction,
                "You need to be in a voice channel to control Vynlo."
            )
            return

        if interaction.user.voice.channel != voice_client.channel:
            await send_temporary_interaction_message(
                interaction,
                "You need to be in the same voice channel as Vynlo."
            )
            return

        history = get_player_state(
            interaction.guild.id
        ).get("history", [])

        if not history:
            await send_temporary_interaction_message(
                interaction,
                "There is no previous track in history."
            )
            return

        previous_track = history.pop()

        queue = get_server_queue(interaction.guild.id)
        queue.insert(0, previous_track)

        voice_client.stop()

        await update_player_panel(
            interaction.guild.id,
            interaction.channel.id
        )


    async def skip_callback(self, interaction):
        await interaction.response.defer()

        if interaction.guild is None:
            await send_temporary_interaction_message(
                interaction,
                "This panel can only be used in a server voice channel."
            )
            return

        voice_client = interaction.guild.voice_client

        if voice_client is None:
            await send_temporary_interaction_message(
                interaction,
                "Vynlo is not connected to a voice channel."
            )
            return

        if interaction.user.voice is None:
            await send_temporary_interaction_message(
                interaction,
                "You need to be in a voice channel to control Vynlo."
            )
            return

        if interaction.user.voice.channel != voice_client.channel:
            await send_temporary_interaction_message(
                interaction,
                "You need to be in the same voice channel as Vynlo."
            )
            return

        if not (
            voice_client.is_playing()
            or voice_client.is_paused()
        ):
            await send_temporary_interaction_message(
                interaction,
                "There is nothing playing to skip."
            )
            return

        guild_id = interaction.guild.id

        state = get_player_state(guild_id)
        state["skip_requested"] = True

        # Stop the current track.
        # This triggers the after_play() callback.
        voice_client.stop()

        # Give Discord/FFmpeg a moment to finish stopping.
        await asyncio.sleep(0.15)

        await update_player_panel(
            guild_id,
            interaction.channel.id
        )



    async def stop_callback(self, interaction):
        await interaction.response.defer()

        if interaction.guild is None:
            await send_temporary_interaction_message(
                interaction,
                "This panel can only be used in a server voice channel."
            )
            return

        voice_client = interaction.guild.voice_client

        if voice_client is None:
            await send_temporary_interaction_message(
                interaction,
                "Vynlo is not connected to a voice channel."
            )
            return

        if interaction.user.voice is None:
            await send_temporary_interaction_message(
                interaction,
                "You need to be in a voice channel to control Vynlo."
            )
            return

        if interaction.user.voice.channel != voice_client.channel:
            await send_temporary_interaction_message(
                interaction,
                "You need to be in the same voice channel as Vynlo."
            )
            return

        get_server_queue(interaction.guild.id).clear()
        get_player_state(interaction.guild.id)["current_track"] = None

        voice_client.stop()

        await update_player_panel(
            interaction.guild.id,
            interaction.channel.id
        )

    async def shuffle_callback(self, interaction):
        await interaction.response.defer()

        if interaction.guild is None:
            await send_temporary_interaction_message(
                interaction,
                "This panel can only be used in a server voice channel."
            )
            return

        voice_client = interaction.guild.voice_client

        if voice_client is None:
            await send_temporary_interaction_message(
                interaction,
                "Vynlo is not connected to a voice channel."
            )
            return

        if interaction.user.voice is None:
            await send_temporary_interaction_message(
                interaction,
                "You need to be in a voice channel to control Vynlo."
            )
            return

        if interaction.user.voice.channel != voice_client.channel:
            await send_temporary_interaction_message(
                interaction,
                "You need to be in the same voice channel as Vynlo."
            )
            return

        state = get_player_state(interaction.guild.id)
        queue = get_server_queue(interaction.guild.id)

        if len(queue) < 2:
            await send_temporary_interaction_message(
                interaction,
                "There are not enough tracks to shuffle."
            )
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

        await update_player_panel(
            interaction.guild.id,
            interaction.channel.id
        )

    async def loop_callback(self, interaction):
        await interaction.response.defer()

        if interaction.guild is None:
            await send_temporary_interaction_message(
                interaction,
                "This panel can only be used in a server voice channel."
            )
            return

        voice_client = interaction.guild.voice_client

        if voice_client is None:
            await send_temporary_interaction_message(
                interaction,
                "Vynlo is not connected to a voice channel."
            )
            return

        if interaction.user.voice is None:
            await send_temporary_interaction_message(
                interaction,
                "You need to be in a voice channel to control Vynlo."
            )
            return

        if interaction.user.voice.channel != voice_client.channel:
            await send_temporary_interaction_message(
                interaction,
                "You need to be in the same voice channel as Vynlo."
            )
            return

        cycle_loop_mode(interaction.guild.id)

        await update_player_panel(
            interaction.guild.id,
            interaction.channel.id
        )

    async def queue_callback(self, interaction):
        await interaction.response.edit_message(
            embed=build_queue_embed(interaction.guild.id),
            view=QueueView(
                interaction.guild.id,
                interaction.channel.id
            )
        )


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


def canonical_track_url(track):
    if not isinstance(track, dict):
        return None
    return (
        track.get("stream_url")
        or track.get("url")
        or track.get("source_url")
    )


def compact_track(track):
    if not isinstance(track, dict):
        return track

    url = track.get("source_url") or track.get("url") or track.get("stream_url")
    if url:
        track["source_url"] = track.get("source_url") or url
        track["url"] = track.get("url") or url

    stream_url = track.get("stream_url")
    if stream_url == track.get("url"):
        track.pop("stream_url", None)

    track.pop("thumbnail", None)

    # Keep only metadata we still actually use. This reduces memory without
    # breaking queue resolution, playback, or UI rendering.
    if not track.get("requested_by"):
        track.pop("requested_by", None)

    return track


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
        return [compact_track({
            "title": info.get("title", "Unknown title"),
            "source_url": info.get("webpage_url") or info.get("url") or url,
            "url": info.get("webpage_url") or info.get("url") or url,
            "stream_url": info.get("url") or info.get("webpage_url") or url,
        })]

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
        tracks.append(compact_track({
            "title": entry.get("title", "Unknown title"),
            "source_url": track_url,
            "url": track_url,
            "stream_url": None,
        }))

    return tracks


async def resolve_track_audio(track):
    queue_url = canonical_track_url(track)
    if not queue_url:
        return compact_track(track)

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
    track["url"] = track.get("url") or queue_url
    track["stream_url"] = audio_url
    track["requested_by"] = track.get("requested_by")
    return track


async def play_next_in_queue(guild_id, channel):
    guild = bot.get_guild(guild_id)

    if guild is None:
        print(f"❌ Could not find guild {guild_id}")
        return

    voice_client = guild.voice_client
    guild_queue = queues.get(guild_id, [])
    state = get_player_state(guild_id)

    # Store the track that just finished/skipped in history
    current_track = state.get("current_track")

    if current_track and isinstance(current_track, dict):
        record_history_entry(state, current_track)

    # Nothing left in the queue
    if not guild_queue:
        state["current_track"] = None
        state["skip_requested"] = False

        await update_player_panel(
            guild_id,
            channel.id if channel else None
        )

        return

    # Make sure Vynlo is still connected
    if voice_client is None:
        print("❌ Vynlo is no longer connected to a voice channel.")
        state["current_track"] = None
        state["skip_requested"] = False
        return

    # Get the next track
    next_track = guild_queue.pop(0)

    try:
        next_track = await resolve_track_audio(next_track)

    except Exception as e:
        print(f"❌ Failed to resolve next track: {e}")

        state["current_track"] = None
        state["skip_requested"] = False

        # Try the following track instead
        if guild_queue:
            await play_next_in_queue(guild_id, channel)
        else:
            await update_player_panel(
                guild_id,
                channel.id if channel else None
            )

        return

    title = next_track.get("title", "Unknown title")

    audio_url = canonical_track_url(next_track)

    if not audio_url:
        print(f"❌ No audio URL found for: {title}")

        state["current_track"] = None
        state["skip_requested"] = False

        if guild_queue:
            await play_next_in_queue(guild_id, channel)
        else:
            await update_player_panel(
                guild_id,
                channel.id if channel else None
            )

        return

    state["current_track"] = next_track
    state["skip_requested"] = False

    print(f"▶️ Starting next track: {title}")

    source = FFmpegPCMAudio(
        audio_url,
        before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        options="-vn",
    )

    def after_play(error):
        if error:
            print(f"Playback error: {error}")
            return

        asyncio.run_coroutine_threadsafe(
            play_next_in_queue(
                guild_id,
                channel
            ),
            bot.loop
        )

    try:
        voice_client.play(
            source,
            after=after_play
        )

    except Exception as e:
        print(f"❌ Failed to start audio: {e}")

        state["current_track"] = None

        if guild_queue:
            asyncio.run_coroutine_threadsafe(
                play_next_in_queue(guild_id, channel),
                bot.loop
            )

        return

    await send_temporary_message(
        channel,
        f"Playing **{title}** 🎵"
    )

    await update_player_panel(
        guild_id,
        channel.id if channel else None
    )


async def setup_vynlo_channel(guild):
    channel_name = "VynloMusic🎵"

    print(f"\nChecking channels in {guild.name}...")

    for channel in guild.channels:
        print(f"Found channel: '{channel.name}' | Type: {type(channel).__name__}")

        if isinstance(channel, discord.TextChannel):
            if channel.name.lower() == channel_name.lower():
                print(f"✅ FOUND EXISTING VYNLO CHANNEL: {channel.id}")
                return channel

    print("❌ No VynloMusic-Player found. Creating one...")

    channel = await guild.create_text_channel(
        channel_name,
        topic="🎵 Your Vynlo Music Player"
    )

    print(f"✅ Created VynloMusic: {channel.id}")

    return channel


# this is an event that is triggered when the bot is ready to start working, he will print the bot's username in the console
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    for guild in bot.guilds:
        channel = await setup_vynlo_channel(guild)

        if channel:
            await create_or_update_player_panel(guild, channel)

@bot.event
async def on_guild_join(guild):
    print(f"\n🎉 Vynlo joined a new server: {guild.name}")

    try:
        channel = await setup_vynlo_channel(guild)

        if channel:
            print(f"🎵 Vynlo channel ready: #{channel.name}")

            await create_or_update_player_panel(
                guild,
                channel
            )

            print(f"✅ Player panel created in {guild.name}")

    except Exception as e:
        print(
            f"❌ Failed to set up Vynlo in "
            f"{guild.name}: {type(e).__name__}: {e}"
        )


@bot.event
async def on_guild_remove(guild):
    clear_guild_state(guild.id)


# here we are adding another ! command, this one would be !join
@bot.command()
async def join(ctx):
    await cleanup_user_command_message(ctx)

    if ctx.author.voice is None:
        await send_temporary_message(ctx, "You are not in a voice channel!")
        return
    # We're storing the voice channel in a variable called channel. So this looks where my user is.
    channel = ctx.author.voice.channel
    # then we are telling the bot to connect to the voice channel that the user is in. This is done by using the connect() method from the discord.py library. This method is asynchronous, so we need to use the await keyword before it.
    await channel.connect()
    player_channel = await setup_vynlo_channel(ctx.guild)
    await create_or_update_player_panel(ctx.guild, player_channel)
    await send_temporary_message_info(
    ctx,
    """🎵 **Vynlo Music**

Vynlo is a simple, button-controlled music player built for Discord. Everything you need is available directly from the **VynloMusic** player — no `/play`, `!skip`, or other text commands to remember.

Vynlo will automatically create a **#VynloMusic🎵** channel for your server, with the music player already waiting for you.

**Simply:**

**1.** 🔊 Join a voice channel  
**2.** 🎵 Open **#VynloMusic🎵**  
**3.** ➕ Click **Add to Queue**  
**4.** 🔗 Paste a YouTube link

Vynlo will find you in your voice channel and start playing your music.""",
)


@bot.command()
async def panel(ctx):
    player_channel = await setup_vynlo_channel(ctx.guild)
    await create_or_update_player_panel(ctx.guild, player_channel)
    await send_temporary_message(ctx, "🎵 Player panel ready. Use the buttons below to control the music.")


@bot.command()
async def start(ctx):
    await create_or_update_player_panel(ctx)
    await send_temporary_message(ctx, "🎵 Vynlo is live and ready to control.")

@bot.command()
async def info(ctx):
    await send_temporary_message_info(
    ctx,
    """🎵 **Vynlo Music**

Vynlo is a simple, button-controlled music player built for Discord. Everything you need is available directly from the **VynloMusic** player — no `/play`, `!skip`, or other text commands to remember.

Vynlo will automatically create a **#VynloMusic🎵** channel for your server, with the music player already waiting for you.

**Simply:**

**1.** 🔊 Join a voice channel  
**2.** 🎵 Open **#VynloMusic🎵**  
**3.** ➕ Click **Add to Queue**  
**4.** 🔗 Paste a YouTube link

Vynlo will find you in your voice channel and start playing your music.""",
)


@bot.command()
async def leave(ctx):
    await cleanup_user_command_message(ctx)

    if ctx.voice_client is None:
        await send_temporary_message(ctx, "I am not in a voice channel!")
        return

    guild_queue = get_server_queue(ctx.guild.id)
    guild_queue.clear()
    clear_guild_state(ctx.guild.id)
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

            requester_name = ctx.author.display_name or ctx.author.name
            for track in tracks:
                track["requested_by"] = requester_name

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

                asyncio.run_coroutine_threadsafe(
                    play_next_in_queue(ctx.guild.id, ctx.channel),
                    bot.loop
                )

            ctx.voice_client.play(source, after=after_play)
            asyncio.run_coroutine_threadsafe(update_player_panel(ctx.guild.id, ctx.channel.id), bot.loop)
            return

        info = await extract_audio_info(url)
    except Exception:
        await send_temporary_message(ctx, "I could not find audio for that URL. Please try another one.")
        return

    track = compact_track({
        "title": info.get("title", "Unknown title"),
        "source_url": info.get("webpage_url") or info.get("url") or url,
        "url": info.get("webpage_url") or info.get("url") or url,
        "stream_url": info.get("url") or url,
        "artist": info.get("artist") or info.get("uploader"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "requested_by": ctx.author.display_name or ctx.author.name,
    })

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

        asyncio.run_coroutine_threadsafe(
            play_next_in_queue(ctx.guild.id, ctx.channel),
            bot.loop
        )

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