"""realtime — no models on purpose.

This app holds behaviour only: two websocket consumers and a broadcast()
helper that takes plain dicts. Because it imports nothing from any other
app, it can sit at the end of every import chain without creating a cycle.

You are allowed to delete this whole app and poll GET /api/state every
2 seconds instead. See section 08 of the blueprint.
"""
