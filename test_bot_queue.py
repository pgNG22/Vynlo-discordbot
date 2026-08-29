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
