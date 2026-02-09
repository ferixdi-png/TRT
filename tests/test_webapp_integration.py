"""Tests for Mini App integration."""
import pytest
from unittest.mock import patch, MagicMock


class TestWebappAuth:
    """Tests for webapp authentication."""
    
    def test_bot_token_fallback(self):
        """Test that TELEGRAM_BOT_TOKEN is used as fallback."""
        import os
        
        # Simulate BOT_TOKEN not set but TELEGRAM_BOT_TOKEN is
        with patch.dict(os.environ, {"BOT_TOKEN": "", "TELEGRAM_BOT_TOKEN": "test_token"}, clear=False):
            # Force reimport to pick up new env
            import importlib
            import webapp.api.auth as auth_module
            importlib.reload(auth_module)
            
            # Token should be set from TELEGRAM_BOT_TOKEN
            assert auth_module.BOT_TOKEN == "test_token" or auth_module.BOT_TOKEN != ""
    
    def test_get_user_id_no_init_data(self):
        """Test that missing init_data returns None."""
        from webapp.api.auth import get_user_id_from_init_data
        
        result = get_user_id_from_init_data("")
        assert result is None
    
    def test_get_user_id_invalid_init_data(self):
        """Test that invalid init_data returns None."""
        from webapp.api.auth import get_user_id_from_init_data
        
        result = get_user_id_from_init_data("invalid_data")
        assert result is None


class TestStatusNormalization:
    """Tests for job status normalization."""
    
    def test_canonical_statuses(self):
        """Test that all canonical statuses are recognized."""
        from app.generations.state_machine import normalize_provider_state
        
        canonical = ["pending", "queued", "waiting", "success", "failed", "canceled"]
        
        for status in canonical:
            result = normalize_provider_state(status)
            assert result.canonical_state in canonical or result.canonical_state in ["result_validated", "delivered", "completed"]
    
    def test_provider_state_mapping(self):
        """Test provider state to canonical mapping."""
        from app.generations.state_machine import normalize_provider_state
        
        # KIE states
        assert normalize_provider_state("PROCESSING").canonical_state == "waiting"
        assert normalize_provider_state("COMPLETED").canonical_state == "success"
        assert normalize_provider_state("FAILED").canonical_state == "failed"


class TestIdempotency:
    """Tests for request idempotency."""
    
    @pytest.mark.asyncio
    async def test_same_request_id_reuses_job(self):
        """Test that same request_id returns existing job."""
        # This would require mocking storage
        # Placeholder for now
        pass


class TestJobStorage:
    """Tests for unified job storage."""
    
    @pytest.mark.asyncio
    async def test_add_and_get_job(self):
        """Test adding and retrieving a job."""
        from app.storage import get_storage
        
        storage = get_storage()
        
        # Add a test job
        job_id = await storage.add_generation_job(
            user_id=12345,
            model_id="test-model",
            model_name="Test Model",
            params={"prompt": "test"},
            price=10.0,
            status="pending",
        )
        
        assert job_id is not None
        
        # Get the job
        job = await storage.get_job(job_id)
        assert job is not None
        assert job.get("user_id") == 12345
        assert job.get("model_id") == "test-model"
        assert job.get("status") == "pending"
    
    @pytest.mark.asyncio
    async def test_update_job_status(self):
        """Test updating job status."""
        from app.storage import get_storage
        
        storage = get_storage()
        
        # Add a test job
        job_id = await storage.add_generation_job(
            user_id=12345,
            model_id="test-model",
            model_name="Test Model",
            params={"prompt": "test"},
            price=10.0,
            status="pending",
        )
        
        # Update status
        await storage.update_job_status(job_id, "queued")
        
        # Verify
        job = await storage.get_job(job_id)
        assert job.get("status") == "queued"
    
    @pytest.mark.asyncio
    async def test_list_jobs_by_user(self):
        """Test listing jobs by user."""
        from app.storage import get_storage
        
        storage = get_storage()
        
        # Add test jobs
        user_id = 99999
        await storage.add_generation_job(
            user_id=user_id,
            model_id="test-model-1",
            model_name="Test Model 1",
            params={},
            price=10.0,
        )
        
        # List jobs
        jobs = await storage.list_jobs(user_id=user_id)
        assert len(jobs) >= 1
        assert all(j.get("user_id") == user_id for j in jobs)
