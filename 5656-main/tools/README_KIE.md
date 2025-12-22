# KIE Integration Tools

## Sanity Test

Test KIE API connection and model execution:

```bash
# Set environment variables
export KIE_API_KEY=your_api_key
export KIE_MODEL=wan/2-6-text-to-video  # optional
export KIE_PROMPT="A cat walking"  # optional
export KIE_DURATION=5  # optional
export KIE_RESOLUTION=720p  # optional
export KIE_IMAGE_URL=https://...  # optional
export KIE_VIDEO_URL=https://...  # optional

# Run sanity test
python tools/kie_sanity.py
```

Expected output on success:
- CREATE_RESP with code=200 and taskId
- Polling until state=success
- resultUrls in final response

## Validation Demo

Test input validation:

```bash
python tools/kie_validate_demo.py
```

Tests:
- Valid WAN 2.6 input
- Invalid duration
- Missing required prompt
- Image URL validation
