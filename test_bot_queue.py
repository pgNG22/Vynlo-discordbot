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
