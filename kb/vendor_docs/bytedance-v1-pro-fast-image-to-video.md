# Vendor Documentation: bytedance/v1-pro-fast-image-to-video

**Source**: KIE AI API Documentation  
**Date**: 2026-01-XX  
**Status**: Raw documentation (verbatim)

---

## Model: bytedance/v1-pro-fast-image-to-video

**Endpoints**:
- POST `/api/v1/jobs/createTask`
- GET `/api/v1/jobs/recordInfo?taskId=...`

**Input schema**:
- `prompt` (required, string, max 10000)
- `image_url` (required, string, max 10MB, jpeg/png/webp)
- `resolution` (optional enum: 720p,1080p; default 720p)
- `duration` (optional enum: "5","10"; default "5")

**Output media type**: video

**Pricing**:
- Resolution-based pricing (see pricing_rules)

**Important notes**:
- This is an image-to-video model (Pro Fast version)
- `resolution` only has 2 values (720p, 1080p), NO 480p (unlike other v1 models)
- NO parameters: `camera_fixed`, `seed`, `enable_safety_checker`, `end_image_url` (present in other v1 models)
- NO parameters: `fps`, `with_audio`, `width`, `height`, `guidance`, `steps`, `negative_prompt`, `motion`, `style`, `strength`

