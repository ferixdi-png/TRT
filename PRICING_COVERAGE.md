# Pricing coverage report

Total models: 75

| Status | Count |
| --- | ---: |
| READY | 52 |
| MISSING_PRICE | 2 |
| MISSING_PARAM_SCHEMA | 21 |
| AMBIGUOUS_SKU | 0 |

## Models

### model-bytedance-seedream
**bytedance/seedream** — `READY`

### model-bytedance-seedream-v4-edit
**bytedance/seedream-v4-edit** — `READY`

### model-bytedance-seedream-v4-text-to-image
**bytedance/seedream-v4-text-to-image** — `READY`

### model-bytedance-v1-pro-fast-image-to-video
**bytedance/v1-pro-fast-image-to-video** — `READY`

### model-elevenlabs-audio-isolation
**elevenlabs/audio-isolation** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-elevenlabs-sound-effect
**elevenlabs/sound-effect** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-elevenlabs-speech-to-text
**elevenlabs/speech-to-text** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-elevenlabs-text-to-speech
**elevenlabs/text-to-speech** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-flux-2-flex-image-to-image
**flux-2/flex-image-to-image** — `READY`

### model-flux-2-flex-text-to-image
**flux-2/flex-text-to-image** — `READY`

### model-flux-2-pro-image-to-image
**flux-2/pro-image-to-image** — `READY`

### model-flux-2-pro-text-to-image
**flux-2/pro-text-to-image** — `READY`

### model-flux-kontext
**flux/kontext** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-google-imagen4
**google/imagen4** — `READY`

### model-google-imagen4-fast
**google/imagen4-fast** — `READY`

### model-google-imagen4-ultra
**google/imagen4-ultra** — `READY`

### model-google-nano-banana
**google/nano-banana** — `READY`

### model-google-nano-banana-edit
**google/nano-banana-edit** — `READY`

### model-google-nanobanana-gemini-2.5-flash
**google/nanobanana-gemini-2.5-flash** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-google-veo-3
**google/veo-3** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-google-veo-3.1
**google/veo-3.1** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-grok-imagine-text-to-image
**grok-imagine/text-to-image** — `READY`

### model-grok-imagine-text-to-video
**grok-imagine/text-to-video** — `READY`

### model-grok-imagine
**grok/imagine** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-hailuo-02-image-to-video-pro
**hailuo/02-image-to-video-pro** — `READY`

### model-hailuo-02-image-to-video-standard
**hailuo/02-image-to-video-standard** — `MISSING_PRICE`

Issues:
- At least one param combination has no price.

SKU diagnostics:
- Expected: hailuo/02-image-to-video-standard::duration=10|resolution=512P, hailuo/02-image-to-video-standard::duration=10|resolution=768P, hailuo/02-image-to-video-standard::duration=6|resolution=512P, hailuo/02-image-to-video-standard::duration=6|resolution=768P
- Found: hailuo/02-image-to-video-standard::duration=10|resolution=512P, hailuo/02-image-to-video-standard::duration=10|resolution=768P, hailuo/02-image-to-video-standard::duration=6|resolution=512P
- Missing: hailuo/02-image-to-video-standard::duration=6|resolution=768P

### model-hailuo-02-text-to-video-pro
**hailuo/02-text-to-video-pro** — `READY`

### model-hailuo-02-text-to-video-standard
**hailuo/02-text-to-video-standard** — `READY`

### model-hailuo-2.3
**hailuo/2.3** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-ideogram-character
**ideogram/character** — `READY`

### model-ideogram-character-edit
**ideogram/character-edit** — `READY`

### model-ideogram-character-remix
**ideogram/character-remix** — `READY`

### model-ideogram-v3-edit
**ideogram/v3-edit** — `READY`

### model-ideogram-v3-reframe
**ideogram/v3-reframe** — `READY`

### model-ideogram-v3-remix
**ideogram/v3-remix** — `READY`

### model-ideogram-v3-text-to-image
**ideogram/v3-text-to-image** — `READY`

### model-infinitalk-from-audio
**infinitalk/from-audio** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-kling-2.6-image-to-video
**kling-2.6/image-to-video** — `MISSING_PARAM_SCHEMA`

Issues:
- Missing enum values for pricing param 'sound'

SKU diagnostics:
- Found: kling-2.6/image-to-video::duration=10|sound=false, kling-2.6/image-to-video::duration=5|sound=false, kling-2.6/image-to-video::duration=5|sound=true

### model-kling-2.6-text-to-video
**kling-2.6/text-to-video** — `MISSING_PARAM_SCHEMA`

Issues:
- Missing enum values for pricing param 'sound'

SKU diagnostics:
- Found: kling-2.6/text-to-video::duration=10|sound=false, kling-2.6/text-to-video::duration=5|sound=false

### model-kling-ai-avatar-v1-pro
**kling/ai-avatar-v1-pro** — `READY`

### model-kling-v1-avatar-standard
**kling/v1-avatar-standard** — `READY`

### model-kling-v2-1-master-image-to-video
**kling/v2-1-master-image-to-video** — `READY`

### model-kling-v2-1-master-text-to-video
**kling/v2-1-master-text-to-video** — `READY`

### model-kling-v2-1-pro
**kling/v2-1-pro** — `READY`

### model-kling-v2-1-standard
**kling/v2-1-standard** — `READY`

### model-kling-v2-5-turbo
**kling/v2-5-turbo** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-kling-v2-5-turbo-image-to-video-pro
**kling/v2-5-turbo-image-to-video-pro** — `READY`

### model-kling-v2-5-turbo-text-to-video-pro
**kling/v2-5-turbo-text-to-video-pro** — `READY`

### model-midjourney-api
**midjourney/api** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-nano-banana-pro
**nano-banana-pro** — `READY`

### model-openai-4o-image
**openai/4o-image** — `READY`

### model-qwen-image-edit
**qwen/image-edit** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-qwen-image-to-image
**qwen/image-to-image** — `READY`

### model-qwen-text-to-image
**qwen/text-to-image** — `READY`

### model-recraft-crisp-upscale
**recraft/crisp-upscale** — `READY`

### model-recraft-remove-background
**recraft/remove-background** — `READY`

### model-runway-gen-4
**runway/gen-4** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-seedream-4.5-edit
**seedream/4.5-edit** — `READY`

### model-seedream-4.5-text-to-image
**seedream/4.5-text-to-image** — `READY`

### model-sora-2-image-to-video
**sora-2-image-to-video** — `MISSING_PARAM_SCHEMA`

Issues:
- Missing schema for pricing param 'size'

SKU diagnostics:
- Found: sora-2-image-to-video::n_frames=10|size=standard, sora-2-image-to-video::n_frames=15|size=standard

### model-sora-2-pro-image-to-video
**sora-2-pro-image-to-video** — `READY`

### model-sora-2-pro-storyboard
**sora-2-pro-storyboard** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-sora-2-pro-text-to-video
**sora-2-pro-text-to-video** — `MISSING_PRICE`

Issues:
- No READY pricing SKUs in SSOT.

SKU diagnostics:

### model-sora-2-text-to-video
**sora-2-text-to-video** — `READY`

SKU diagnostics:
- Expected: sora-2-text-to-video::n_frames=10, sora-2-text-to-video::n_frames=15
- Found: sora-2-text-to-video::n_frames=10, sora-2-text-to-video::n_frames=15

### model-sora-2-watermark-remover
**sora-2-watermark-remover** — `READY`

### model-sora-watermark-remover
**sora-watermark-remover** — `READY`

### model-suno-v5
**suno/v5** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-topaz-image-upscale
**topaz/image-upscale** — `READY`

### model-topaz-video-upscale
**topaz/video-upscale** — `READY`

### model-wan-2-2-a14b-speech-to-video-turbo
**wan/2-2-a14b-speech-to-video-turbo** — `MISSING_PARAM_SCHEMA`

Issues:
- No READY pricing SKUs in SSOT.
- SSOT has unmapped pricing entries (missing param schema).

SKU diagnostics:

### model-wan-2-2-animate-move
**wan/2-2-animate-move** — `READY`

### model-wan-2-2-animate-replace
**wan/2-2-animate-replace** — `READY`

### model-wan-2-5-image-to-video
**wan/2-5-image-to-video** — `READY`

### model-wan-2-5-text-to-video
**wan/2-5-text-to-video** — `READY`

### model-z-image
**z-image** — `READY`
