"""Chat Z-Image mode: auto-responds to text messages in a target public chat
with Z-Image generations + short charismatic phrases.

Enabled by setting CHAT_ZIMAGE_CHAT=@public_username env var.
"""

from app.chat_zimage.handler import register_chat_zimage_handler  # noqa: F401
