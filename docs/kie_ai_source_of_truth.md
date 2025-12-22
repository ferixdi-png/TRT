# KIE.AI Source of Truth

**Generated:** 2025-12-22T19:34:50.619046
**Source:** LOCAL_AND_WEB
**Total Models:** 72
**Web Parsed:** True (0 pages)

## API Endpoints

### createTask
- **Method:** POST
- **Path:** /api/v1/jobs/createTask
- **Confirmed from:** kie_client.py

**Request:**
```json
{
  "model": "string (required)",
  "input": {} (required, model-specific),
  "callBackUrl": "string (optional)"
}
```

**Response:**
```json
{
  "code": 200,
  "data": {
    "taskId": "string"
  }
}
```

### recordInfo
- **Method:** GET
- **Path:** /api/v1/jobs/recordInfo
- **Confirmed from:** bot_kie.py, kie_client.py

**Query Parameters:**
- `taskId` (string, required)

**Response:**
```json
{
  "code": 200,
  "data": {
    "state": "waiting|queuing|generating|success|fail",
    "resultJson": "string (JSON)",
    "resultUrls": "array (optional, deprecated)",
    "errorMessage": "string (optional)",
    "failCode": "string (optional)"
  }
}
```

## Result JSON Structure

The `resultJson` field contains a JSON string with the following structure:

```json
{
  "resultUrls": ["url1", "url2", ...],
  "resultWaterMarkUrls": ["url1", "url2", ...]  // Optional, for sora-2-text-to-video
}
```

## States

- `waiting` - Task is waiting to be processed
- `queuing` - Task is in queue
- `generating` - Task is being generated
- `success` - Task completed successfully
- `fail` - Task failed

## Models

Total: 72 models

### bytedance/seedream

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `enable_safety_checker`: boolean [OPTIONAL]
- `guidance_scale`: number [OPTIONAL] (max: 10, min: 1)
- `image_size`: enum [OPTIONAL] (values: [square, square_hd, portrait_4_3, portrait_16_9, landscape_4_3, landscape_16_9])
- `prompt`: string [REQUIRED] (max: 5000)

**Example Payload:**
```json
{
  "model": "bytedance/seedream",
  "input": {
    "prompt": "example"
  }
}
```

### bytedance/seedream-v4-edit

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `image_input`: array [REQUIRED] (item_type: string)
- `image_resolution`: enum [OPTIONAL] (values: [1K, 2K, 4K])
- `image_size`: enum [OPTIONAL] (values: [square, square_hd, portrait_4_3, portrait_3_2, portrait_16_9, landscape_4_3, landscape_3_2, landscape_16_9, landscape_21_9])
- `max_images`: number [OPTIONAL] (max: 6, min: 1)
- `prompt`: string [REQUIRED] (max: 5000)

**Example Payload:**
```json
{
  "model": "bytedance/seedream-v4-edit",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### bytedance/seedream-v4-text-to-image

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `image_resolution`: enum [OPTIONAL] (values: [1K, 2K, 4K])
- `image_size`: enum [OPTIONAL] (values: [square, square_hd, portrait_4_3, portrait_3_2, portrait_16_9, landscape_4_3, landscape_3_2, landscape_16_9, landscape_21_9])
- `max_images`: number [OPTIONAL] (max: 6, min: 1)
- `prompt`: string [REQUIRED] (max: 5000)

**Example Payload:**
```json
{
  "model": "bytedance/seedream-v4-text-to-image",
  "input": {
    "prompt": "example"
  }
}
```

### bytedance/v1-pro-fast-image-to-video

- **Type:** image_to_video
- **Output:** video

**Input Parameters:**
- `duration`: enum [OPTIONAL] (values: [5, 10])
- `image_input`: array [REQUIRED] (item_type: string)
- `prompt`: string [REQUIRED] (max: 10000)
- `resolution`: enum [OPTIONAL] (values: [720p, 1080p])

**Example Payload:**
```json
{
  "model": "bytedance/v1-pro-fast-image-to-video",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### elevenlabs/audio-isolation

- **Type:** audio_to_audio
- **Output:** audio

**Input Parameters:**
- `audio_url`: string [REQUIRED]

**Example Payload:**
```json
{
  "model": "elevenlabs/audio-isolation",
  "input": {
    "audio_url": "example"
  }
}
```

### elevenlabs/sound-effect

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `prompt`: string [REQUIRED]

**Example Payload:**
```json
{
  "model": "elevenlabs/sound-effect",
  "input": {
    "prompt": "example"
  }
}
```

### elevenlabs/speech-to-text

- **Type:** speech_to_text
- **Output:** audio

**Input Parameters:**
- `audio_url`: string [REQUIRED]
- `diarize`: boolean [OPTIONAL]
- `language_code`: string [OPTIONAL] (max: 500)
- `tag_audio_events`: boolean [OPTIONAL]

**Example Payload:**
```json
{
  "model": "elevenlabs/speech-to-text",
  "input": {
    "audio_url": "example"
  }
}
```

### elevenlabs/text-to-speech

- **Type:** text_to_speech
- **Output:** audio

**Input Parameters:**
- `text`: string [REQUIRED]

**Example Payload:**
```json
{
  "model": "elevenlabs/text-to-speech",
  "input": {
    "text": "example"
  }
}
```

### flux-2/flex-image-to-image

- **Type:** image_to_image
- **Output:** image

**Input Parameters:**
- `aspect_ratio`: enum [REQUIRED] (values: [1:1, 4:3, 3:4, 16:9, 9:16, 3:2, 2:3, auto])
- `image_input`: array [REQUIRED] (item_type: string)
- `prompt`: string [REQUIRED] (max: 5000, min: 3)
- `resolution`: enum [REQUIRED] (values: [1K, 2K])

**Example Payload:**
```json
{
  "model": "flux-2/flex-image-to-image",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ],
    "aspect_ratio": "1:1",
    "resolution": "1K"
  }
}
```

### flux-2/flex-text-to-image

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `aspect_ratio`: enum [REQUIRED] (values: [1:1, 4:3, 3:4, 16:9, 9:16, 3:2, 2:3, auto])
- `prompt`: string [REQUIRED] (max: 5000, min: 3)
- `resolution`: enum [REQUIRED] (values: [1K, 2K])

**Example Payload:**
```json
{
  "model": "flux-2/flex-text-to-image",
  "input": {
    "prompt": "example",
    "aspect_ratio": "1:1",
    "resolution": "1K"
  }
}
```

### flux-2/pro-image-to-image

- **Type:** image_to_image
- **Output:** image

**Input Parameters:**
- `aspect_ratio`: enum [REQUIRED] (values: [1:1, 4:3, 3:4, 16:9, 9:16, 3:2, 2:3, auto])
- `image_input`: array [REQUIRED] (item_type: string)
- `prompt`: string [REQUIRED] (max: 5000, min: 3)
- `resolution`: enum [REQUIRED] (values: [1K, 2K])

**Example Payload:**
```json
{
  "model": "flux-2/pro-image-to-image",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ],
    "aspect_ratio": "1:1",
    "resolution": "1K"
  }
}
```

### flux-2/pro-text-to-image

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `aspect_ratio`: enum [REQUIRED] (values: [1:1, 4:3, 3:4, 16:9, 9:16, 3:2, 2:3, auto])
- `prompt`: string [REQUIRED] (max: 5000, min: 3)
- `resolution`: enum [REQUIRED] (values: [1K, 2K])

**Example Payload:**
```json
{
  "model": "flux-2/pro-text-to-image",
  "input": {
    "prompt": "example",
    "aspect_ratio": "1:1",
    "resolution": "1K"
  }
}
```

### flux/kontext

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `prompt`: string [REQUIRED]

**Example Payload:**
```json
{
  "model": "flux/kontext",
  "input": {
    "prompt": "example"
  }
}
```

### google/imagen4

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `aspect_ratio`: enum [OPTIONAL] (values: [1:1, 16:9, 9:16, 3:4, 4:3])
- `negative_prompt`: string [OPTIONAL] (max: 5000)
- `num_images`: enum [OPTIONAL] (values: [1, 2, 3, 4])
- `prompt`: string [REQUIRED] (max: 5000)
- `seed`: string [OPTIONAL] (max: 500)

**Example Payload:**
```json
{
  "model": "google/imagen4",
  "input": {
    "prompt": "example"
  }
}
```

### google/imagen4-fast

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `aspect_ratio`: enum [OPTIONAL] (values: [1:1, 16:9, 9:16, 3:4, 4:3])
- `negative_prompt`: string [OPTIONAL] (max: 5000)
- `num_images`: enum [OPTIONAL] (values: [1, 2, 3, 4])
- `prompt`: string [REQUIRED] (max: 5000)
- `seed`: integer [OPTIONAL]

**Example Payload:**
```json
{
  "model": "google/imagen4-fast",
  "input": {
    "prompt": "example"
  }
}
```

### google/imagen4-ultra

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `aspect_ratio`: enum [OPTIONAL] (values: [1:1, 16:9, 9:16, 3:4, 4:3])
- `negative_prompt`: string [OPTIONAL] (max: 5000)
- `prompt`: string [REQUIRED] (max: 5000)
- `seed`: string [OPTIONAL] (max: 500)

**Example Payload:**
```json
{
  "model": "google/imagen4-ultra",
  "input": {
    "prompt": "example"
  }
}
```

### google/nano-banana

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `image_size`: enum [OPTIONAL] (values: [1:1, 9:16, 16:9, 3:4, 4:3, 3:2, 2:3, 5:4, 4:5, 21:9 ... (+1 more)])
- `output_format`: enum [OPTIONAL] (values: [png, jpeg])
- `prompt`: string [REQUIRED] (max: 5000)

**Example Payload:**
```json
{
  "model": "google/nano-banana",
  "input": {
    "prompt": "example"
  }
}
```

### google/nano-banana-edit

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `image_size`: enum [OPTIONAL] (values: [1:1, 9:16, 16:9, 3:4, 4:3, 3:2, 2:3, 5:4, 4:5, 21:9 ... (+1 more)])
- `image_urls`: array [REQUIRED] (item_type: string)
- `output_format`: enum [OPTIONAL] (values: [png, jpeg])
- `prompt`: string [REQUIRED] (max: 5000)

**Example Payload:**
```json
{
  "model": "google/nano-banana-edit",
  "input": {
    "prompt": "example",
    "image_urls": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### google/nanobanana-gemini-2.5-flash

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `prompt`: string [REQUIRED]

**Example Payload:**
```json
{
  "model": "google/nanobanana-gemini-2.5-flash",
  "input": {
    "prompt": "example"
  }
}
```

### google/veo-3

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `prompt`: string [REQUIRED]

**Example Payload:**
```json
{
  "model": "google/veo-3",
  "input": {
    "prompt": "example"
  }
}
```

### google/veo-3.1

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `prompt`: string [REQUIRED]

**Example Payload:**
```json
{
  "model": "google/veo-3.1",
  "input": {
    "prompt": "example"
  }
}
```

### grok/imagine

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `prompt`: string [REQUIRED]

**Example Payload:**
```json
{
  "model": "grok/imagine",
  "input": {
    "prompt": "example"
  }
}
```

### hailuo/02-image-to-video-pro

- **Type:** image_to_video
- **Output:** video

**Input Parameters:**
- `end_image_url`: string [OPTIONAL]
- `image_input`: array [REQUIRED] (item_type: string)
- `prompt`: string [REQUIRED] (max: 1500)
- `prompt_optimizer`: boolean [OPTIONAL]

**Example Payload:**
```json
{
  "model": "hailuo/02-image-to-video-pro",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### hailuo/02-image-to-video-standard

- **Type:** image_to_video
- **Output:** video

**Input Parameters:**
- `duration`: enum [OPTIONAL] (values: [6, 10])
- `end_image_url`: string [OPTIONAL]
- `image_input`: array [REQUIRED] (item_type: string)
- `prompt`: string [REQUIRED] (max: 1500)
- `prompt_optimizer`: boolean [OPTIONAL]
- `resolution`: enum [OPTIONAL] (values: [512P, 768P])

**Example Payload:**
```json
{
  "model": "hailuo/02-image-to-video-standard",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### hailuo/02-text-to-video-pro

- **Type:** text_to_video
- **Output:** video

**Input Parameters:**
- `prompt`: string [REQUIRED] (max: 1500)
- `prompt_optimizer`: boolean [OPTIONAL]

**Example Payload:**
```json
{
  "model": "hailuo/02-text-to-video-pro",
  "input": {
    "prompt": "example"
  }
}
```

### hailuo/02-text-to-video-standard

- **Type:** text_to_video
- **Output:** video

**Input Parameters:**
- `duration`: enum [OPTIONAL] (values: [6, 10])
- `prompt`: string [REQUIRED] (max: 1500)
- `prompt_optimizer`: boolean [OPTIONAL]

**Example Payload:**
```json
{
  "model": "hailuo/02-text-to-video-standard",
  "input": {
    "prompt": "example"
  }
}
```

### hailuo/2.3

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `prompt`: string [REQUIRED]

**Example Payload:**
```json
{
  "model": "hailuo/2.3",
  "input": {
    "prompt": "example"
  }
}
```

### ideogram/character

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `expand_prompt`: boolean [OPTIONAL]
- `image_size`: enum [OPTIONAL] (values: [square, square_hd, portrait_4_3, portrait_16_9, landscape_4_3, landscape_16_9])
- `negative_prompt`: string [OPTIONAL] (max: 5000)
- `num_images`: enum [OPTIONAL] (values: [1, 2, 3, 4])
- `prompt`: string [REQUIRED] (max: 5000)
- `reference_image_input`: array [REQUIRED] (item_type: string)
- `rendering_speed`: enum [OPTIONAL] (values: [TURBO, BALANCED, QUALITY])
- `style`: enum [OPTIONAL] (values: [AUTO, REALISTIC, FICTION])

**Example Payload:**
```json
{
  "model": "ideogram/character",
  "input": {
    "prompt": "example",
    "reference_image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### ideogram/character-edit

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `expand_prompt`: boolean [OPTIONAL]
- `image_input`: array [REQUIRED] (item_type: string)
- `mask_input`: array [REQUIRED] (item_type: string)
- `num_images`: enum [OPTIONAL] (values: [1, 2, 3, 4])
- `prompt`: string [REQUIRED] (max: 5000)
- `reference_image_input`: array [REQUIRED] (item_type: string)
- `rendering_speed`: enum [OPTIONAL] (values: [TURBO, BALANCED, QUALITY])
- `style`: enum [OPTIONAL] (values: [AUTO, REALISTIC, FICTION])

**Example Payload:**
```json
{
  "model": "ideogram/character-edit",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ],
    "mask_input": [
      "https://example.com/image.jpg"
    ],
    "reference_image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### ideogram/character-remix

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `expand_prompt`: boolean [OPTIONAL]
- `image_input`: array [REQUIRED] (item_type: string)
- `image_size`: enum [OPTIONAL] (values: [square, square_hd, portrait_4_3, portrait_16_9, landscape_4_3, landscape_16_9])
- `negative_prompt`: string [OPTIONAL] (max: 500)
- `num_images`: enum [OPTIONAL] (values: [1, 2, 3, 4])
- `prompt`: string [REQUIRED] (max: 5000)
- `reference_image_input`: array [REQUIRED] (item_type: string)
- `rendering_speed`: enum [OPTIONAL] (values: [TURBO, BALANCED, QUALITY])
- `strength`: number [OPTIONAL] (max: 1, min: 0.1)
- `style`: enum [OPTIONAL] (values: [AUTO, REALISTIC, FICTION])

**Example Payload:**
```json
{
  "model": "ideogram/character-remix",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ],
    "reference_image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### ideogram/v3-edit

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `expand_prompt`: boolean [OPTIONAL]
- `image_input`: array [REQUIRED] (item_type: string)
- `mask_input`: array [REQUIRED] (item_type: string)
- `num_images`: enum [OPTIONAL] (values: [1, 2, 3, 4])
- `prompt`: string [REQUIRED] (max: 5000)
- `rendering_speed`: enum [OPTIONAL] (values: [TURBO, BALANCED, QUALITY])
- `seed`: integer [OPTIONAL]

**Example Payload:**
```json
{
  "model": "ideogram/v3-edit",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ],
    "mask_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### ideogram/v3-reframe

- **Type:** outpaint
- **Output:** unknown

**Input Parameters:**
- `image_input`: array [REQUIRED] (item_type: string)
- `image_size`: enum [REQUIRED] (values: [square, square_hd, portrait_4_3, portrait_16_9, landscape_4_3, landscape_16_9])
- `num_images`: enum [OPTIONAL] (values: [1, 2, 3, 4])
- `rendering_speed`: enum [OPTIONAL] (values: [TURBO, BALANCED, QUALITY])
- `style`: enum [OPTIONAL] (values: [AUTO, GENERAL, REALISTIC, DESIGN])

**Example Payload:**
```json
{
  "model": "ideogram/v3-reframe",
  "input": {
    "image_input": [
      "https://example.com/image.jpg"
    ],
    "image_size": "square"
  }
}
```

### ideogram/v3-remix

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `expand_prompt`: boolean [OPTIONAL]
- `image_input`: array [REQUIRED] (item_type: string)
- `image_size`: enum [OPTIONAL] (values: [square, square_hd, portrait_4_3, portrait_16_9, landscape_4_3, landscape_16_9])
- `negative_prompt`: string [OPTIONAL] (max: 5000)
- `num_images`: enum [OPTIONAL] (values: [1, 2, 3, 4])
- `prompt`: string [REQUIRED] (max: 5000)
- `rendering_speed`: enum [OPTIONAL] (values: [TURBO, BALANCED, QUALITY])
- `seed`: integer [OPTIONAL]
- `strength`: number [OPTIONAL] (max: 1, min: 0.01)
- `style`: enum [OPTIONAL] (values: [AUTO, GENERAL, REALISTIC, DESIGN])

**Example Payload:**
```json
{
  "model": "ideogram/v3-remix",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### ideogram/v3-text-to-image

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `expand_prompt`: boolean [OPTIONAL]
- `image_size`: enum [OPTIONAL] (values: [square, square_hd, portrait_4_3, portrait_16_9, landscape_4_3, landscape_16_9])
- `negative_prompt`: string [OPTIONAL] (max: 5000)
- `num_images`: enum [OPTIONAL] (values: [1, 2, 3, 4])
- `prompt`: string [REQUIRED] (max: 5000)
- `rendering_speed`: enum [OPTIONAL] (values: [TURBO, BALANCED, QUALITY])
- `seed`: integer [OPTIONAL]
- `style`: enum [OPTIONAL] (values: [AUTO, GENERAL, REALISTIC, DESIGN])

**Example Payload:**
```json
{
  "model": "ideogram/v3-text-to-image",
  "input": {
    "prompt": "example"
  }
}
```

### infinitalk/from-audio

- **Type:** audio_to_audio
- **Output:** audio

**Input Parameters:**
- `prompt`: string [REQUIRED]

**Example Payload:**
```json
{
  "model": "infinitalk/from-audio",
  "input": {
    "prompt": "example"
  }
}
```

### kling-2.6/image-to-video

- **Type:** image_to_video
- **Output:** video

**Input Parameters:**
- `duration`: enum [REQUIRED] (values: [5, 10])
- `image_input`: array [REQUIRED] (item_type: string)
- `prompt`: string [REQUIRED] (max: 1000)
- `sound`: boolean [REQUIRED]

**Example Payload:**
```json
{
  "model": "kling-2.6/image-to-video",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ],
    "sound": true,
    "duration": "5"
  }
}
```

### kling-2.6/text-to-video

- **Type:** text_to_video
- **Output:** video

**Input Parameters:**
- `aspect_ratio`: enum [REQUIRED] (values: [1:1, 16:9, 9:16])
- `duration`: enum [REQUIRED] (values: [5, 10])
- `prompt`: string [REQUIRED] (max: 1000)
- `sound`: boolean [REQUIRED]

**Example Payload:**
```json
{
  "model": "kling-2.6/text-to-video",
  "input": {
    "prompt": "example",
    "sound": true,
    "aspect_ratio": "1:1",
    "duration": "5"
  }
}
```

### kling/ai-avatar-v1-pro

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `audio_input`: array [REQUIRED] (item_type: string)
- `image_input`: array [REQUIRED] (item_type: string)
- `prompt`: string [REQUIRED] (max: 5000)

**Example Payload:**
```json
{
  "model": "kling/ai-avatar-v1-pro",
  "input": {
    "image_input": [
      "https://example.com/image.jpg"
    ],
    "audio_input": [
      "https://example.com/image.jpg"
    ],
    "prompt": "example"
  }
}
```

### kling/v1-avatar-standard

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `audio_input`: array [REQUIRED] (item_type: string)
- `image_input`: array [REQUIRED] (item_type: string)
- `prompt`: string [REQUIRED] (max: 5000)

**Example Payload:**
```json
{
  "model": "kling/v1-avatar-standard",
  "input": {
    "image_input": [
      "https://example.com/image.jpg"
    ],
    "audio_input": [
      "https://example.com/image.jpg"
    ],
    "prompt": "example"
  }
}
```

### kling/v2-1-master-image-to-video

- **Type:** image_to_video
- **Output:** video

**Input Parameters:**
- `cfg_scale`: number [OPTIONAL] (max: 1, min: 0)
- `duration`: enum [OPTIONAL] (values: [5, 10])
- `image_input`: array [REQUIRED] (item_type: string)
- `negative_prompt`: string [OPTIONAL] (max: 500)
- `prompt`: string [REQUIRED] (max: 5000)

**Example Payload:**
```json
{
  "model": "kling/v2-1-master-image-to-video",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### kling/v2-1-master-text-to-video

- **Type:** text_to_video
- **Output:** video

**Input Parameters:**
- `aspect_ratio`: enum [OPTIONAL] (values: [16:9, 9:16, 1:1])
- `cfg_scale`: number [OPTIONAL] (max: 1, min: 0)
- `duration`: enum [OPTIONAL] (values: [5, 10])
- `negative_prompt`: string [OPTIONAL] (max: 500)
- `prompt`: string [REQUIRED] (max: 5000)

**Example Payload:**
```json
{
  "model": "kling/v2-1-master-text-to-video",
  "input": {
    "prompt": "example"
  }
}
```

### kling/v2-1-pro

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `cfg_scale`: number [OPTIONAL] (max: 1, min: 0)
- `duration`: enum [OPTIONAL] (values: [5, 10])
- `image_input`: array [REQUIRED] (item_type: string)
- `negative_prompt`: string [OPTIONAL] (max: 500)
- `prompt`: string [REQUIRED] (max: 5000)
- `tail_image_url`: string [OPTIONAL]

**Example Payload:**
```json
{
  "model": "kling/v2-1-pro",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### kling/v2-1-standard

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `cfg_scale`: number [OPTIONAL] (max: 1, min: 0)
- `duration`: enum [OPTIONAL] (values: [5, 10])
- `image_input`: array [REQUIRED] (item_type: string)
- `negative_prompt`: string [OPTIONAL] (max: 500)
- `prompt`: string [REQUIRED] (max: 5000)

**Example Payload:**
```json
{
  "model": "kling/v2-1-standard",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### kling/v2-5-turbo

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `prompt`: string [REQUIRED]

**Example Payload:**
```json
{
  "model": "kling/v2-5-turbo",
  "input": {
    "prompt": "example"
  }
}
```

### kling/v2-5-turbo-image-to-video-pro

- **Type:** image_to_video
- **Output:** video

**Input Parameters:**
- `cfg_scale`: number [OPTIONAL] (max: 1, min: 0)
- `duration`: enum [OPTIONAL] (values: [5, 10])
- `image_input`: array [REQUIRED] (item_type: string)
- `negative_prompt`: string [OPTIONAL] (max: 2496)
- `prompt`: string [REQUIRED] (max: 2500)

**Example Payload:**
```json
{
  "model": "kling/v2-5-turbo-image-to-video-pro",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### kling/v2-5-turbo-text-to-video-pro

- **Type:** text_to_video
- **Output:** video

**Input Parameters:**
- `aspect_ratio`: enum [OPTIONAL] (values: [16:9, 9:16, 1:1])
- `cfg_scale`: number [OPTIONAL] (max: 1, min: 0)
- `duration`: enum [OPTIONAL] (values: [5, 10])
- `negative_prompt`: string [OPTIONAL] (max: 2500)
- `prompt`: string [REQUIRED] (max: 2500)

**Example Payload:**
```json
{
  "model": "kling/v2-5-turbo-text-to-video-pro",
  "input": {
    "prompt": "example"
  }
}
```

### midjourney/api

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `prompt`: string [REQUIRED]

**Example Payload:**
```json
{
  "model": "midjourney/api",
  "input": {
    "prompt": "example"
  }
}
```

### nano-banana-pro

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `aspect_ratio`: enum [OPTIONAL] (values: [1:1, 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9 ... (+1 more)])
- `image_input`: array [REQUIRED] (item_type: string)
- `output_format`: enum [OPTIONAL] (values: [png, jpg])
- `prompt`: string [REQUIRED] (max: 10000)
- `resolution`: enum [OPTIONAL] (values: [1K, 2K, 4K])

**Example Payload:**
```json
{
  "model": "nano-banana-pro",
  "input": {
    "image_input": [
      "https://example.com/image.jpg"
    ],
    "prompt": "example"
  }
}
```

### openai/4o-image

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `prompt`: string [REQUIRED]

**Example Payload:**
```json
{
  "model": "openai/4o-image",
  "input": {
    "prompt": "example"
  }
}
```

### qwen/image-edit

- **Type:** image_edit
- **Output:** image

**Input Parameters:**
- `acceleration`: enum [OPTIONAL] (values: [none, regular, high])
- `enable_safety_checker`: boolean [OPTIONAL]
- `guidance_scale`: number [OPTIONAL] (max: 20, min: 0)
- `image_input`: array [REQUIRED] (item_type: string)
- `image_size`: enum [OPTIONAL] (values: [square, square_hd, portrait_4_3, portrait_16_9, landscape_4_3, landscape_16_9])
- `negative_prompt`: string [OPTIONAL] (max: 500)
- `num_images`: enum [OPTIONAL] (values: [1, 2, 3, 4])
- `num_inference_steps`: number [OPTIONAL] (max: 49, min: 2)
- `output_format`: enum [OPTIONAL] (values: [jpeg, png])
- `prompt`: string [REQUIRED] (max: 2000)

**Example Payload:**
```json
{
  "model": "qwen/image-edit",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### qwen/image-to-image

- **Type:** image_to_image
- **Output:** image

**Input Parameters:**
- `acceleration`: enum [OPTIONAL] (values: [none, regular, high])
- `enable_safety_checker`: boolean [OPTIONAL]
- `guidance_scale`: number [OPTIONAL] (max: 20, min: 0)
- `image_input`: array [REQUIRED] (item_type: string)
- `negative_prompt`: string [OPTIONAL] (max: 500)
- `num_inference_steps`: number [OPTIONAL] (max: 250, min: 2)
- `output_format`: enum [OPTIONAL] (values: [png, jpeg])
- `prompt`: string [REQUIRED] (max: 5000)
- `strength`: number [OPTIONAL] (max: 1, min: 0)

**Example Payload:**
```json
{
  "model": "qwen/image-to-image",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### qwen/text-to-image

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `acceleration`: enum [OPTIONAL] (values: [none, regular, high])
- `enable_safety_checker`: boolean [OPTIONAL]
- `guidance_scale`: number [OPTIONAL] (max: 20, min: 0)
- `image_size`: enum [OPTIONAL] (values: [square, square_hd, portrait_4_3, portrait_16_9, landscape_4_3, landscape_16_9])
- `negative_prompt`: string [OPTIONAL] (max: 500)
- `num_inference_steps`: number [OPTIONAL] (max: 250, min: 2)
- `output_format`: enum [OPTIONAL] (values: [png, jpeg])
- `prompt`: string [REQUIRED] (max: 5000)

**Example Payload:**
```json
{
  "model": "qwen/text-to-image",
  "input": {
    "prompt": "example"
  }
}
```

### recraft/crisp-upscale

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `image_input`: array [REQUIRED] (item_type: string)

**Example Payload:**
```json
{
  "model": "recraft/crisp-upscale",
  "input": {
    "image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### recraft/remove-background

- **Type:** image_edit
- **Output:** image

**Input Parameters:**
- `image_input`: array [REQUIRED] (item_type: string)

**Example Payload:**
```json
{
  "model": "recraft/remove-background",
  "input": {
    "image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### runway/gen-4

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `prompt`: string [REQUIRED]

**Example Payload:**
```json
{
  "model": "runway/gen-4",
  "input": {
    "prompt": "example"
  }
}
```

### seedream/4.5-edit

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `aspect_ratio`: enum [REQUIRED] (values: [1:1, 4:3, 3:4, 16:9, 9:16, 2:3, 3:2, 21:9])
- `image_urls`: array [REQUIRED] (item_type: string)
- `prompt`: string [REQUIRED] (max: 3000)
- `quality`: enum [REQUIRED] (values: [basic, high])

**Example Payload:**
```json
{
  "model": "seedream/4.5-edit",
  "input": {
    "prompt": "example",
    "image_urls": [
      "https://example.com/image.jpg"
    ],
    "aspect_ratio": "1:1",
    "quality": "basic"
  }
}
```

### seedream/4.5-text-to-image

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `aspect_ratio`: enum [REQUIRED] (values: [1:1, 4:3, 3:4, 16:9, 9:16, 2:3, 3:2, 21:9])
- `prompt`: string [REQUIRED] (max: 3000)
- `quality`: enum [REQUIRED] (values: [basic, high])

**Example Payload:**
```json
{
  "model": "seedream/4.5-text-to-image",
  "input": {
    "prompt": "example",
    "aspect_ratio": "1:1",
    "quality": "basic"
  }
}
```

### sora-2-pro-image-to-video

- **Type:** image_to_video
- **Output:** video

**Input Parameters:**
- `aspect_ratio`: enum [OPTIONAL] (values: [portrait, landscape])
- `image_urls`: array [REQUIRED] (item_type: string)
- `n_frames`: enum [OPTIONAL] (values: [10, 15])
- `prompt`: string [REQUIRED] (max: 10000)
- `remove_watermark`: boolean [OPTIONAL]
- `size`: enum [OPTIONAL] (values: [standard, high])

**Example Payload:**
```json
{
  "model": "sora-2-pro-image-to-video",
  "input": {
    "image_urls": [
      "https://example.com/image.jpg"
    ],
    "prompt": "example"
  }
}
```

### sora-2-pro-storyboard

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `prompt`: string [REQUIRED]

**Example Payload:**
```json
{
  "model": "sora-2-pro-storyboard",
  "input": {
    "prompt": "example"
  }
}
```

### sora-2-text-to-video

- **Type:** text_to_video
- **Output:** video

**Input Parameters:**
- `aspect_ratio`: enum [REQUIRED] (values: [portrait, landscape])
- `n_frames`: enum [OPTIONAL] (values: [10, 15])
- `prompt`: string [REQUIRED] (max: 10000)
- `remove_watermark`: boolean [OPTIONAL]

**Example Payload:**
```json
{
  "model": "sora-2-text-to-video",
  "input": {
    "prompt": "example",
    "aspect_ratio": "portrait"
  }
}
```

### sora-watermark-remover

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `video_url`: string [REQUIRED] (max: 500)

**Example Payload:**
```json
{
  "model": "sora-watermark-remover",
  "input": {
    "video_url": "example"
  }
}
```

### suno/v5

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `prompt`: string [REQUIRED]

**Example Payload:**
```json
{
  "model": "suno/v5",
  "input": {
    "prompt": "example"
  }
}
```

### topaz/image-upscale

- **Type:** upscale
- **Output:** image

**Input Parameters:**
- `image_input`: array [REQUIRED] (item_type: string)
- `upscale_factor`: enum [REQUIRED] (values: [1, 2, 4, 8])

**Example Payload:**
```json
{
  "model": "topaz/image-upscale",
  "input": {
    "image_input": [
      "https://example.com/image.jpg"
    ],
    "upscale_factor": "1"
  }
}
```

### topaz/video-upscale

- **Type:** video_upscale
- **Output:** video

**Input Parameters:**
- `upscale_factor`: enum [OPTIONAL] (values: [1, 2, 4])
- `video_input`: array [REQUIRED] (item_type: string)

**Example Payload:**
```json
{
  "model": "topaz/video-upscale",
  "input": {
    "video_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### wan/2-2-a14b-image-to-video-turbo

- **Type:** image_to_video
- **Output:** video

**Input Parameters:**
- `acceleration`: enum [OPTIONAL] (values: [none, regular])
- `aspect_ratio`: enum [OPTIONAL] (values: [auto, 16:9, 9:16, 1:1])
- `enable_prompt_expansion`: boolean [OPTIONAL]
- `image_input`: array [REQUIRED] (item_type: string)
- `prompt`: string [REQUIRED] (max: 5000)
- `resolution`: enum [OPTIONAL] (values: [480p, 580p, 720p])
- `seed`: number [OPTIONAL] (max: 2147483647, min: 0)

**Example Payload:**
```json
{
  "model": "wan/2-2-a14b-image-to-video-turbo",
  "input": {
    "image_input": [
      "https://example.com/image.jpg"
    ],
    "prompt": "example"
  }
}
```

### wan/2-2-a14b-speech-to-video-turbo

- **Type:** speech_to_video
- **Output:** video

**Input Parameters:**
- `audio_input`: array [REQUIRED] (item_type: string)
- `enable_safety_checker`: boolean [OPTIONAL]
- `frames_per_second`: number [OPTIONAL] (max: 60, min: 4)
- `guidance_scale`: number [OPTIONAL] (max: 10, min: 1)
- `image_input`: array [REQUIRED] (item_type: string)
- `negative_prompt`: string [OPTIONAL] (max: 500)
- `num_frames`: number [OPTIONAL] (max: 120, min: 40)
- `num_inference_steps`: number [OPTIONAL] (max: 40, min: 2)
- `prompt`: string [REQUIRED] (max: 5000)
- `resolution`: enum [OPTIONAL] (values: [480p, 580p, 720p])
- `shift`: number [OPTIONAL] (max: 10, min: 1)

**Example Payload:**
```json
{
  "model": "wan/2-2-a14b-speech-to-video-turbo",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ],
    "audio_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### wan/2-2-a14b-text-to-video-turbo

- **Type:** text_to_video
- **Output:** video

**Input Parameters:**
- `acceleration`: enum [OPTIONAL] (values: [none, regular])
- `aspect_ratio`: enum [OPTIONAL] (values: [16:9, 9:16, 1:1])
- `enable_prompt_expansion`: boolean [OPTIONAL]
- `prompt`: string [REQUIRED] (max: 5000)
- `resolution`: enum [OPTIONAL] (values: [480p, 580p, 720p])
- `seed`: number [OPTIONAL] (max: 2147483647, min: 0)

**Example Payload:**
```json
{
  "model": "wan/2-2-a14b-text-to-video-turbo",
  "input": {
    "prompt": "example"
  }
}
```

### wan/2-2-animate-move

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `image_input`: array [REQUIRED] (item_type: string)
- `resolution`: enum [OPTIONAL] (values: [480p, 580p, 720p])
- `video_input`: array [REQUIRED] (item_type: string)

**Example Payload:**
```json
{
  "model": "wan/2-2-animate-move",
  "input": {
    "video_input": [
      "https://example.com/image.jpg"
    ],
    "image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### wan/2-2-animate-replace

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `image_input`: array [REQUIRED] (item_type: string)
- `resolution`: enum [OPTIONAL] (values: [480p, 580p, 720p])
- `video_input`: array [REQUIRED] (item_type: string)

**Example Payload:**
```json
{
  "model": "wan/2-2-animate-replace",
  "input": {
    "video_input": [
      "https://example.com/image.jpg"
    ],
    "image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### wan/2-5-image-to-video

- **Type:** image_to_video
- **Output:** video

**Input Parameters:**
- `duration`: enum [OPTIONAL] (values: [5, 10])
- `enable_prompt_expansion`: boolean [OPTIONAL]
- `image_input`: array [REQUIRED] (item_type: string)
- `negative_prompt`: string [OPTIONAL] (max: 500)
- `prompt`: string [REQUIRED] (max: 800)
- `resolution`: enum [OPTIONAL] (values: [720p, 1080p])

**Example Payload:**
```json
{
  "model": "wan/2-5-image-to-video",
  "input": {
    "prompt": "example",
    "image_input": [
      "https://example.com/image.jpg"
    ]
  }
}
```

### wan/2-5-text-to-video

- **Type:** text_to_video
- **Output:** video

**Input Parameters:**
- `aspect_ratio`: enum [OPTIONAL] (values: [16:9, 9:16, 1:1])
- `duration`: enum [OPTIONAL] (values: [5, 10])
- `enable_prompt_expansion`: boolean [OPTIONAL]
- `negative_prompt`: string [OPTIONAL] (max: 500)
- `prompt`: string [REQUIRED] (max: 800)
- `resolution`: enum [OPTIONAL] (values: [720p, 1080p])

**Example Payload:**
```json
{
  "model": "wan/2-5-text-to-video",
  "input": {
    "prompt": "example"
  }
}
```

### z-image

- **Type:** text_to_image
- **Output:** text

**Input Parameters:**
- `aspect_ratio`: enum [REQUIRED] (values: [1:1, 4:3, 3:4, 16:9, 9:16])
- `prompt`: string [REQUIRED] (max: 1000)

**Example Payload:**
```json
{
  "model": "z-image",
  "input": {
    "prompt": "example",
    "aspect_ratio": "1:1"
  }
}
```

