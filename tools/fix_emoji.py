"""Add emoji to all models without emoji in title_ru."""
import yaml
import re

EMOJI_MAP = {
    'google': '🔍',
    'grok': '🤖',
    'hailuo': '🎥',
    'ideogram': '🎨',
    'kling': '🎬',
    'sora': '🎞️',
    'qwen': '🖼️',
    'recraft': '🛠️',
    'topaz': '💎',
    'wan': '🌊',
    'elevenlabs': '🗣️',
    'gemini': '💬',
    'gpt': '🤖',
    'midjourney': '🎨',
    'infinitalk': '👄',
    'nano-banana': '🍌',
    'z-image': '⚡',
}

TYPE_EMOJI = {
    't2i': '🖼️',
    'i2i': '🎨',
    't2v': '🎬',
    'i2v': '🎥',
    'text_to_speech': '🗣️',
    'speech_to_text': '📝',
    'text_to_music': '🎶',
    'text_to_chat': '💬',
    'upscale': '💎',
    'bg_remove': '✂️',
    'lip_sync': '👄',
    'audio_to_audio': '🎵',
    'text_to_audio': '🔊',
    'watermark_remove': '🧹',
}

def get_emoji(model_id, model_type):
    # Check by model id prefix
    for prefix, emoji in EMOJI_MAP.items():
        if prefix in model_id.lower():
            return emoji
    # Fallback to type
    return TYPE_EMOJI.get(model_type, '✨')

def has_emoji(text):
    if not text:
        return False
    return any(ord(c) > 127 for c in text[:2])

with open('app/kie_catalog/models_pricing.yaml', encoding='utf-8') as f:
    data = yaml.safe_load(f)

models = data.get('models', [])
fixed = 0

for m in models:
    title = m.get('title_ru', '')
    if title and not has_emoji(title):
        emoji = get_emoji(m.get('id', ''), m.get('type', ''))
        m['title_ru'] = f"{emoji} {title}"
        fixed += 1

with open('app/kie_catalog/models_pricing.yaml', 'w', encoding='utf-8') as f:
    yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print(f"Fixed {fixed} models")
