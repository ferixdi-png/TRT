from app.middleware.rate_limit import PerUserRateLimiter, TTLCache


def test_token_bucket_rate_limiter_blocks_and_recovers():
    now = [0.0]

    def time_fn() -> float:
        return now[0]

    limiter = PerUserRateLimiter(rate=1.0, capacity=2.0, time_fn=time_fn)
    assert limiter.check(1)[0] is True
    assert limiter.check(1)[0] is True
    allowed, retry_after = limiter.check(1)
    assert allowed is False
    assert retry_after > 0

    now[0] += 1.0
    allowed, _ = limiter.check(1)
    assert allowed is True


def test_ttl_cache_dedup_expires():
    now = [0.0]

    def time_fn() -> float:
        return now[0]

    cache = TTLCache(ttl_seconds=5.0, time_fn=time_fn)
    assert cache.seen("key") is False
    assert cache.seen("key") is True

    now[0] += 6.0
    assert cache.seen("key") is False
