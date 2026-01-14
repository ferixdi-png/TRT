# Render Log Watcher - Setup Guide

**Purpose**: Monitor Render service logs and automatically update Desktop report.

---

## Quick Start

1. **Create `TRT_RENDER.env` on Desktop**:
   ```
   RENDER_API_KEY=your_api_key_here
   RENDER_SERVICE_ID=your_service_id_here
   ```

2. **Run watcher**:
   ```bash
   make render-logs        # Last 30 minutes
   make render-logs-10     # Last 10 minutes
   ```

3. **Check output**:
   - `~/Desktop/TRT_RENDER_LAST_LOGS.txt` - Raw logs
   - `~/Desktop/TRT_REPORT.md` - Updated with summary

---

## How to Get API Keys

### RENDER_API_KEY

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click your profile icon (top right) → **Account Settings**
3. Go to **API Keys** section
4. Click **Create API Key**
5. Give it a name (e.g., "TRT Log Watcher")
6. Copy the key (you won't see it again!)

**Security**: Never commit this key to Git. Store only in `~/Desktop/TRT_RENDER.env`.

### RENDER_SERVICE_ID

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Select your service (e.g., "kie-bot-production")
3. Go to **Settings** tab
4. Find **Service ID** (format: `srv-xxxxx`)
5. Copy the Service ID

**Example**: `srv-abc123def456`

---

## File Locations

### Windows
- Env file: `C:\Users\<YourUsername>\Desktop\TRT_RENDER.env`
- Logs: `C:\Users\<YourUsername>\Desktop\TRT_RENDER_LAST_LOGS.txt`
- Report: `C:\Users\<YourUsername>\Desktop\TRT_REPORT.md`

### macOS/Linux
- Env file: `~/Desktop/TRT_RENDER.env`
- Logs: `~/Desktop/TRT_RENDER_LAST_LOGS.txt`
- Report: `~/Desktop/TRT_REPORT.md`

---

## TRT_RENDER.env Format

```bash
# Render API credentials for log watcher
# DO NOT COMMIT THIS FILE TO GIT!

RENDER_API_KEY=rnd_abc123def456ghi789jkl
RENDER_SERVICE_ID=srv-xyz789uvw456rst123
```

**Important**:
- One key per line
- No quotes needed
- No spaces around `=`
- Lines starting with `#` are comments

---

## What the Watcher Does

1. **Fetches logs** from Render API for last N minutes
2. **Analyzes logs** for:
   - Errors and exceptions
   - Warnings
   - Key events (DISPATCH_OK/FAIL, PASSIVE_REJECT, UNKNOWN_CALLBACK, etc.)
   - Lock acquisition events
3. **Saves raw logs** to `TRT_RENDER_LAST_LOGS.txt`
4. **Updates report** in `TRT_REPORT.md` with:
   - Summary counts
   - Top 10 recent errors
   - Changes since previous run

---

## Troubleshooting

### "TRT_RENDER.env file not found"

**Solution**: Create the file on Desktop with API keys (see above).

### "RENDER_API_KEY not found"

**Solution**: Add `RENDER_API_KEY=...` line to `TRT_RENDER.env`.

### "Failed to fetch logs from Render API"

**Possible causes**:
- Invalid API key → Regenerate in Render Dashboard
- Invalid Service ID → Check Settings tab
- API rate limit → Wait a few minutes and retry
- Network issue → Check internet connection

### "requests library not installed"

**Solution**: 
```bash
pip install requests
```

---

## Security Notes

- ✅ API key stored only on Desktop (not in repo)
- ✅ `.env` file should be in `.gitignore` (already is)
- ✅ Script doesn't modify Render configuration
- ✅ Script doesn't import bot code (safe to run independently)

---

## Integration with CI/CD

**Not recommended**: API keys in CI/CD secrets are acceptable, but this tool is designed for local monitoring.

For CI/CD, use Render's built-in log streaming or webhook notifications.

---

**Last Updated**: 2026-01-14  
**Maintainer**: Cursor Pro Autonomous Senior Engineer

