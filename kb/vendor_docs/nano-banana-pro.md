# Vendor Documentation: nano-banana-pro

**Source**: Pasted from vendor API documentation  
**Date**: 2026-01-XX  
**Status**: Raw documentation (verbatim)

---

## Model: nano-banana-pro

**Endpoints**:
- POST `/api/v1/jobs/createTask`
- GET `/api/v1/jobs/recordInfo?taskId=...`

**Input schema**:
- `prompt` (required, string, max 20000)
- `image_input` (optional, array[URL], up to 8, jpeg/png/webp, max 30MB each)
- `aspect_ratio` (optional enum: 1:1,2:3,3:2,3:4,4:3,4:5,5:4,9:16,16:9,21:9,auto; default 1:1)
- `resolution` (optional enum: 1K,2K,4K; default 1K)
- `output_format` (optional enum: png,jpg; default png)

**Pricing**:
- 18 credits for 1K and 2K (flat)
- 24 credits for 4K

