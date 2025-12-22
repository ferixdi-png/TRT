# Entrypoint Analysis

## Dockerfile Entrypoint
- **File:** `Dockerfile`
- **Line 54:** `CMD ["python3", "bot_kie.py"]`
- **Entrypoint:** `bot_kie.py` is the main entrypoint for Render/Docker

## Health Check
- **Line 50-51:** Health check uses Python to check `http://localhost:10000/health`
- **Port:** 10000 (exposed on line 47)

## Main Function
- **File:** `bot_kie.py`
- **Function:** `async def main()` (line 24118)
- **Called via:** `asyncio.run(main())` at module level

## Conclusion
The bot starts with `python3 bot_kie.py` which calls `main()` function.
