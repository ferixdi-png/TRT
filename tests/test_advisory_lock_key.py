from app.utils.pg_advisory_lock import INT32_MAX, INT32_MIN, split_int64_to_int32_pair


def test_split_int64_pair_handles_unsigned_overflow_case():
    raw_key = 18204928085951819256
    assert raw_key > 2**63 - 1
    key_a, key_b = split_int64_to_int32_pair(raw_key)
    assert INT32_MIN <= key_a <= INT32_MAX
    assert INT32_MIN <= key_b <= INT32_MAX
