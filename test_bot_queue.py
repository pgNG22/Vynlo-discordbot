import asyncio

import bot


def test_queue_tracks_are_stored_in_order():
    bot.queues.clear()
    guild_id = 123
    bot.queues[guild_id] = [
        {"title": "First Song", "url": "https://example.com/first.mp3"},
        {"title": "Second Song", "url": "https://example.com/second.mp3"},
    ]

    message = bot.build_queue_message(guild_id)

    assert "First Song" in message
    assert "Second Song" in message
    assert "1." in message
    assert "2." in message


def test_build_queue_message_for_empty_queue():
    bot.queues.clear()

    assert bot.build_queue_message(456) == "The queue is empty."


def test_player_state_history_is_bounded():
    bot.player_state.clear()
    state = bot.get_player_state(999)

    for index in range(50):
        bot.record_history_entry(state, {"title": f"Track {index}"})

    assert len(state["history"]) <= 25


def test_compact_track_removes_duplicate_url_fields():
    compact = bot.compact_track({
        "title": "Song",
        "source_url": "https://example.com/watch?v=abc",
        "url": "https://example.com/watch?v=abc",
        "stream_url": "https://example.com/watch?v=abc",
        "thumbnail": "https://example.com/thumb.jpg",
    })

    assert compact["source_url"] == "https://example.com/watch?v=abc"
    assert compact["url"] == "https://example.com/watch?v=abc"
    assert "stream_url" not in compact
    assert "thumbnail" not in compact


def test_build_queue_embed_uses_default_image_for_stable_layout():
    bot.queues.clear()

    embed = bot.build_queue_embed(789)

    assert embed.image is not None
    assert embed.image.url == bot.DEFAULT_EMBED_IMAGE


def test_build_queue_embed_uses_current_track_thumbnail_when_available():
    bot.queues.clear()
    bot.player_state.clear()
    bot.player_state[789] = {
        "current_track": {
            "title": "Now Playing Track",
            "thumbnail": "https://example.com/current-thumb.jpg",
        }
    }
    bot.queues[789] = [{"title": "Queued Track", "thumbnail": "https://example.com/queued-thumb.jpg"}]

    embed = bot.build_queue_embed(789)

    assert embed.image is not None
    assert embed.image.url == "https://example.com/current-thumb.jpg"
    assert embed.title == "LIVE QUEUE"


def test_is_playlist_url_detects_youtube_playlist_links():
    assert bot.is_playlist_url("https://www.youtube.com/watch?v=Qe6T4dSnWhI&list=PLWsZ-9SQjWmE&index=2")
    assert bot.is_playlist_url("https://www.youtube.com/playlist?list=PLWsZ-9SQjWmE")
    assert not bot.is_playlist_url("https://www.youtube.com/watch?v=Qe6T4dSnWhI")


def test_get_playlist_start_index_reads_playlist_ordering():
    assert bot.get_playlist_start_index("https://www.youtube.com/watch?v=Qe6T4dSnWhI&list=PLWsZ-9SQjWmE&index=2") == 1
    assert bot.get_playlist_start_index("https://www.youtube.com/watch?v=Qe6T4dSnWhI&list=PLWsZ-9SQjWmE") == 0


def test_get_playlist_url_canonicalizes_watch_list_urls():
    assert bot.get_playlist_url("https://www.youtube.com/watch?v=yMqBOS_qpYg&list=PLWsZ-9SQjWmE&index=10") == "https://www.youtube.com/playlist?list=PLWsZ-9SQjWmE"


def test_extract_playlist_tracks_keeps_watch_url_as_source_not_stream(monkeypatch):
    class DummyYDL:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=False):
            return {
                "entries": [
                    {
                        "title": "Playlist Song",
                        "webpage_url": "https://www.youtube.com/watch?v=abc123",
                        "url": "https://www.youtube.com/watch?v=abc123",
                    }
                ]
            }

    monkeypatch.setattr(bot.yt_dlp, "YoutubeDL", DummyYDL)
    tracks = asyncio.run(bot.extract_playlist_tracks("https://www.youtube.com/playlist?list=PL123"))

    assert tracks[0]["source_url"] == "https://www.youtube.com/watch?v=abc123"
    assert tracks[0]["stream_url"] is None


def test_extract_audio_info_uses_youtube_fallback_clients(monkeypatch):
    captured = {}

    class DummyYDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=False):
            return {"title": "Fallback Title", "url": "https://example.com/stream.mp3"}

    monkeypatch.setattr(bot.yt_dlp, "YoutubeDL", DummyYDL)

    info = asyncio.run(bot.extract_audio_info("https://www.youtube.com/watch?v=abc123"))

    assert info["title"] == "Fallback Title"
    assert captured["opts"]["extractor_args"]["youtube"] == [
        "player_client=android",
        "player_client=web",
        "player_client=tv_embedded",
    ]


def test_resolve_track_audio_populates_stream_url(monkeypatch):
    async def fake_extract_audio_info(url):
        return {"title": "Resolved Title", "url": "https://example.com/stream.mp3"}

    monkeypatch.setattr(bot, "extract_audio_info", fake_extract_audio_info)
    track = {"title": "Original Title", "source_url": "https://www.youtube.com/watch?v=abc123"}

    resolved = asyncio.run(bot.resolve_track_audio(track))

    assert resolved["title"] == "Resolved Title"
    assert resolved["stream_url"] == "https://example.com/stream.mp3"


def test_play_next_in_queue_sends_track_title(monkeypatch):
    bot.queues.clear()
    bot.queues[99] = [{
        "title": "Track 1",
        "source_url": "https://example.com/track1.mp3",
        "stream_url": "https://example.com/track1.mp3",
    }]

    messages = []

    class FakeVoiceClient:
        def __init__(self):
            self.sources = []

        def play(self, source, after=None):
            self.sources.append(source)

    class FakeGuild:
        id = 99

    class FakeCtx:
        def __init__(self):
            self.guild = FakeGuild()
            self.voice_client = FakeVoiceClient()

        async def send(self, message):
            messages.append(message)

    fake_ctx = FakeCtx()
    monkeypatch.setattr(bot, "resolve_track_audio", lambda track: asyncio.sleep(0, result=track))
    monkeypatch.setattr(bot, "FFmpegPCMAudio", lambda *args, **kwargs: object())

    asyncio.run(bot.play_next_in_queue(fake_ctx))

    assert any("Playing **Track 1**" in message for message in messages)


def test_get_pause_resume_label_uses_current_voice_state():
    class FakeVoiceClient:
        def __init__(self, playing=False, paused=False):
            self._playing = playing
            self._paused = paused

        def is_playing(self):
            return self._playing

        def is_paused(self):
            return self._paused

    assert bot.get_pause_resume_label(FakeVoiceClient(playing=True)) == "Pause"
    assert bot.get_pause_resume_label(FakeVoiceClient(paused=True)) == "Resume"
    assert bot.get_pause_resume_label(FakeVoiceClient()) == "Pause"


def test_build_player_embed_uses_fallback_image_when_idle():
    bot.queues.clear()
    bot.player_state.clear()

    embed = bot.build_player_embed(321)

    assert embed.description is not None
    assert "Nothing is playing right now" in embed.description
    assert embed.image is not None
    assert embed.image.url.startswith("http")


def test_build_player_embed_shows_queue_and_track_details():
    bot.queues.clear()
    bot.queues[321] = [{
        "title": "Sunset Drive",
        "artist": "Nova Bloom",
        "duration": 240,
    }]

    embed = bot.build_player_embed(321)

    assert embed.title == "🎵 VYNLO"
    assert "Sunset Drive" in embed.description
    assert "Nova Bloom" in str(embed.fields[0].value)
    assert "1" in str(embed.fields[1].value)


def test_update_player_panel_creates_panel_when_missing(monkeypatch):
    bot.player_panels.clear()

    class FakeMessage:
        def __init__(self):
            self.id = 555

    class FakeChannel:
        def __init__(self):
            self.sent = []

        async def send(self, **kwargs):
            self.sent.append(kwargs)
            return FakeMessage()

    class FakeGuild:
        def __init__(self):
            self.channel = FakeChannel()
            self.voice_client = None

        def get_channel(self, channel_id):
            return self.channel

    fake_guild = FakeGuild()
    monkeypatch.setattr(bot.bot, "get_guild", lambda guild_id: fake_guild)

    asyncio.run(bot.update_player_panel(321, 999))

    assert (321, 999) in bot.player_panels
    assert fake_guild.channel.sent


def test_build_player_embed_reports_loop_and_volume_state():
    bot.queues.clear()
    bot.player_state.clear()
    bot.queues[321] = [{
        "title": "Sunset Drive",
        "artist": "Nova Bloom",
        "duration": 240,
    }]

    embed = bot.build_player_embed(321)

    assert "Loop: Off" in embed.footer.text
    assert "Volume: 100%" in embed.footer.text


def test_queue_button_opens_modal_for_interactive_queue_entry():
    view = bot.MusicPlayerView(123)

    class FakeInteraction:
        def __init__(self):
            self.guild = type("Guild", (), {"id": 123})()
            self.channel = type("Channel", (), {"id": 456})()
            self.modal = None

        class response:
            @staticmethod
            async def send_modal(modal):
                FakeInteraction.current_modal = modal

    FakeInteraction.current_modal = None

    asyncio.run(view.queue_callback(FakeInteraction()))

    assert FakeInteraction.current_modal is not None
    assert isinstance(FakeInteraction.current_modal, bot.QueueAddModal)


def test_send_temporary_message_sets_auto_delete_timeout():
    sent = {}

    class FakeCtx:
        async def send(self, message, **kwargs):
            sent["message"] = message
            sent["kwargs"] = kwargs

    asyncio.run(bot.send_temporary_message(FakeCtx(), "hello"))

    assert sent["message"] == "hello"
    assert sent["kwargs"]["delete_after"] == 5


def test_send_temporary_interaction_message_is_ephemeral_and_auto_deletes():
    sent = {}

    class FakeInteraction:
        class followup:
            @staticmethod
            async def send(message, ephemeral=True, delete_after=5):
                sent["message"] = message
                sent["ephemeral"] = ephemeral
                sent["delete_after"] = delete_after

    asyncio.run(bot.send_temporary_interaction_message(FakeInteraction(), "hello"))

    assert sent["message"] == "hello"
    assert sent["ephemeral"] is True
    assert sent["delete_after"] == 5


def test_disconnect_after_idle_leaves_empty_voice_channel(monkeypatch):
    class FakeVoiceClient:
        def __init__(self):
            self.disconnected = False

        def is_playing(self):
            return False

        def is_paused(self):
            return False

        async def disconnect(self):
            self.disconnected = True

    voice_client = FakeVoiceClient()
    guild = type("Guild", (), {"voice_client": voice_client})()
    bot.player_state.clear()
    bot.queues.clear()
    bot.get_player_state(123)["current_track"] = {"title": "Finished"}

    async def immediate_sleep(delay):
        assert delay == bot.IDLE_DISCONNECT_SECONDS

    async def fake_update_player_panel(guild_id, channel_id=None):
        assert guild_id == 123

    monkeypatch.setattr(bot.asyncio, "sleep", immediate_sleep)
    monkeypatch.setattr(bot.bot, "get_guild", lambda guild_id: guild)
    monkeypatch.setattr(bot, "update_player_panel", fake_update_player_panel)

    asyncio.run(bot.disconnect_after_idle(123, 456))

    assert voice_client.disconnected
    assert bot.get_player_state(123)["current_track"] is None


def test_disconnect_after_idle_keeps_voice_channel_when_queue_is_refilled(monkeypatch):
    class FakeVoiceClient:
        def __init__(self):
            self.disconnected = False

        def is_playing(self):
            return False

        def is_paused(self):
            return False

        async def disconnect(self):
            self.disconnected = True

    voice_client = FakeVoiceClient()
    guild = type("Guild", (), {"voice_client": voice_client})()
    bot.player_state.clear()
    bot.queues.clear()
    bot.queues[123] = [{"title": "Queued again"}]

    async def immediate_sleep(delay):
        assert delay == bot.IDLE_DISCONNECT_SECONDS

    monkeypatch.setattr(bot.asyncio, "sleep", immediate_sleep)
    monkeypatch.setattr(bot.bot, "get_guild", lambda guild_id: guild)

    asyncio.run(bot.disconnect_after_idle(123, 456))

    assert not voice_client.disconnected
