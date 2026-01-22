import json
import re

import pytest

from app.diagnostics.billing_preflight import run_billing_preflight


class FakeStorage:
    def __init__(self, partner_id: str = "partner-01"):
        self.partner_id = partner_id
        self.data = {}
        self.diagnostics_storage = None
        self.force_string_payload = False

    async def write_json_file(self, filename, data):
        if self.force_string_payload:
            self.data[filename] = json.dumps(data)
        else:
            self.data[filename] = data

    async def read_json_file(self, filename, default=None):
        if filename in self.data:
            return self.data[filename]
        return default or {}


class FakeConn:
    def __init__(self, responses):
        self.responses = responses

    async def execute(self, query, *args):
        return None

    async def fetchval(self, query, *args):
        return self.responses[_query_key(query)]

    async def fetchrow(self, query, *args):
        return self.responses[_query_key(query)]

    async def fetch(self, query, *args):
        return self.responses[_query_key(query)]


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


def _query_key(query: str) -> str:
    match = re.search(r"billing_preflight:([a-z0-9_]+)", query)
    if not match:
        raise KeyError(f"Unknown query: {query}")
    return match.group(1)


def _base_responses():
    return {
        "column_type": {"data_type": "jsonb", "udt_name": "jsonb"},
        "partners_count": 0,
        "partners_sample": [],
        "partners_top": [],
        "partners_missing": 0,
        "partner_present": None,
        "balances_total": 0,
        "balances_partners": 0,
        "balances_updated_24h": 0,
        "balances_negative": 0,
        "free_total": 0,
        "free_partners": 0,
        "free_range": {"min_used": None, "max_used": None},
        "free_violations": 0,
        "attempts_total": 0,
        "attempts_last_24h": 0,
        "request_id_present": 0,
        "request_id_duplicates": 0,
        "stale_pending": 0,
    }


@pytest.mark.asyncio
async def test_billing_preflight_empty_db_ready():
    responses = _base_responses()
    fake_conn = FakeConn(responses)
    fake_pool = FakePool(fake_conn)
    storage = FakeStorage()

    report = await run_billing_preflight(storage, fake_pool)

    assert report["result"] == "READY"
    assert "initialized=0" in report["sections"]["balances"]["details"]
    assert "initialized=0" in report["sections"]["free_limits"]["details"]


@pytest.mark.asyncio
async def test_billing_preflight_counts_two_partners():
    responses = _base_responses()
    responses.update(
        {
            "partners_count": 2,
            "partners_sample": [{"partner_id": "partner-01"}, {"partner_id": "shop-02"}],
            "partners_top": [
                {"partner_id": "partner-01", "file_count": 8},
                {"partner_id": "shop-02", "file_count": 5},
            ],
            "partner_present": 1,
            "balances_total": 5,
            "balances_partners": 2,
            "balances_updated_24h": 1,
            "free_total": 3,
            "free_partners": 2,
            "free_range": {"min_used": 0, "max_used": 2},
            "attempts_total": 4,
            "attempts_last_24h": 2,
            "request_id_present": 1,
        }
    )
    fake_conn = FakeConn(responses)
    fake_pool = FakePool(fake_conn)
    storage = FakeStorage()

    report = await run_billing_preflight(storage, fake_pool)

    assert report["result"] == "READY"
    assert report["sections"]["tenants"]["meta"]["partners_found"] == 2
    assert report["sections"]["balances"]["details"].startswith("records=5")


@pytest.mark.asyncio
async def test_billing_preflight_detects_violations():
    responses = _base_responses()
    responses.update(
        {
            "partners_count": 1,
            "partners_sample": [{"partner_id": "partner-01"}],
            "partners_top": [{"partner_id": "partner-01", "file_count": 5}],
            "partner_present": 1,
            "balances_total": 2,
            "balances_partners": 1,
            "balances_negative": 1,
            "free_total": 1,
            "free_partners": 1,
            "free_range": {"min_used": 0, "max_used": 10},
            "free_violations": 1,
            "attempts_total": 2,
            "attempts_last_24h": 1,
            "request_id_present": 1,
            "request_id_duplicates": 1,
        }
    )
    fake_conn = FakeConn(responses)
    fake_pool = FakePool(fake_conn)
    storage = FakeStorage()

    report = await run_billing_preflight(storage, fake_pool)

    assert report["result"] == "DEGRADED"
    assert report["sections"]["balances"]["status"] == "DEGRADED"
    assert report["sections"]["attempts"]["status"] == "DEGRADED"


@pytest.mark.asyncio
async def test_billing_preflight_no_pii_in_report():
    responses = _base_responses()
    responses.update(
        {
            "partners_count": 1,
            "partners_sample": [{"partner_id": "partner-01"}],
            "partners_top": [{"partner_id": "partner-01", "file_count": 3}],
            "partner_present": 1,
        }
    )
    fake_conn = FakeConn(responses)
    fake_pool = FakePool(fake_conn)
    storage = FakeStorage()

    report = await run_billing_preflight(storage, fake_pool)
    report_json = str(report)

    assert "partner-01" not in report_json
    assert "p***01" in report_json


@pytest.mark.asyncio
async def test_billing_preflight_text_payload_compatible():
    responses = _base_responses()
    responses.update(
        {
            "column_type": {"data_type": "text", "udt_name": "text"},
            "balances_total": 1,
            "balances_partners": 1,
            "free_total": 1,
            "free_partners": 1,
            "attempts_total": 1,
        }
    )
    fake_conn = FakeConn(responses)
    fake_pool = FakePool(fake_conn)
    storage = FakeStorage()

    report = await run_billing_preflight(storage, fake_pool)

    assert report["result"] == "READY"


@pytest.mark.asyncio
async def test_billing_preflight_json_payload_compatible():
    responses = _base_responses()
    responses.update(
        {
            "column_type": {"data_type": "json", "udt_name": "json"},
            "balances_total": 2,
            "balances_partners": 1,
            "free_total": 1,
            "free_partners": 1,
            "attempts_total": 1,
        }
    )
    fake_conn = FakeConn(responses)
    fake_pool = FakePool(fake_conn)
    storage = FakeStorage()

    report = await run_billing_preflight(storage, fake_pool)

    assert report["result"] == "READY"


@pytest.mark.asyncio
async def test_billing_preflight_aggregate_failure_degraded():
    responses = _base_responses()
    responses.update(
        {
            "balances_total": RuntimeError("json cast failed"),
            "balances_total_fallback": 1,
        }
    )

    class ErroringConn(FakeConn):
        async def fetchval(self, query, *args):
            value = self.responses[_query_key(query)]
            if isinstance(value, Exception):
                raise value
            return value

    fake_conn = ErroringConn(responses)
    fake_pool = FakePool(fake_conn)
    storage = FakeStorage()

    report = await run_billing_preflight(storage, fake_pool)

    assert report["result"] == "DEGRADED"
    assert report["sections"]["balances"]["status"] == "UNKNOWN"


@pytest.mark.asyncio
async def test_billing_preflight_storage_rw_fallback_degraded():
    responses = _base_responses()
    fake_conn = FakeConn(responses)
    fake_pool = FakePool(fake_conn)

    class FailingDiagnosticsStorage(FakeStorage):
        async def write_json_file(self, filename, data):
            raise PermissionError("tenant denied")

    storage = FakeStorage()
    storage.diagnostics_storage = FailingDiagnosticsStorage(partner_id="diagnostics")

    report = await run_billing_preflight(storage, fake_pool)

    assert report["result"] == "DEGRADED"
    assert report["sections"]["storage_rw"]["status"] == "DEGRADED"
    assert report["sections"]["storage_rw"]["meta"]["fallback_used"] is True


@pytest.mark.asyncio
async def test_billing_preflight_storage_rw_handles_string_payload():
    responses = _base_responses()
    fake_conn = FakeConn(responses)
    fake_pool = FakePool(fake_conn)

    storage = FakeStorage()
    storage.force_string_payload = True

    report = await run_billing_preflight(storage, fake_pool)

    assert report["result"] == "READY"
    assert report["sections"]["storage_rw"]["status"] == "OK"
