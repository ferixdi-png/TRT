"""Tests for FAST TOOLS free access logic."""
import pytest
from unittest.mock import AsyncMock, patch

from app.pricing.free_policy import is_fast_tools_free_sku, list_free_skus


class TestFastToolsFreeAccess:
    """Test FAST TOOLS free access restrictions."""
    
    def test_list_free_skus_returns_set(self):
        """Test that list_free_skus returns a set."""
        result = list_free_skus()
        assert isinstance(result, set)
    
    @patch('app.pricing.ssot_catalog.get_all_skus_with_pricing')
    @patch('app.pricing.free_policy.list_free_skus')
    def test_is_fast_tools_free_sku_with_fast_tools_source(self, mock_list_free, mock_get_skus):
        """Test free access with fast_tools source."""
        # Mock data
        mock_list_free.return_value = {"sku1", "sku2", "sku3", "sku4", "sku5", "sku6"}
        mock_get_skus.return_value = {
            "sku1": {"price_rub": 1.0},
            "sku2": {"price_rub": 2.0},
            "sku3": {"price_rub": 3.0},
            "sku4": {"price_rub": 4.0},
            "sku5": {"price_rub": 5.0},
            "sku6": {"price_rub": 6.0},
        }
        
        # Top-5 cheapest should be allowed
        assert is_fast_tools_free_sku("sku1", "fast_tools") == True  # 1.0
        assert is_fast_tools_free_sku("sku5", "fast_tools") == True  # 5.0
        assert is_fast_tools_free_sku("sku6", "fast_tools") == False  # 6.0 (not in top-5)
    
    @patch('app.pricing.free_policy.list_free_skus')
    def test_is_fast_tools_free_sku_wrong_source(self, mock_list_free):
        """Test that wrong source is rejected."""
        mock_list_free.return_value = {"sku1"}
        
        assert is_fast_tools_free_sku("sku1", "main_menu") == False
        assert is_fast_tools_free_sku("sku1", "unknown") == False
        assert is_fast_tools_free_sku("sku1", "") == False
    
    @patch('app.pricing.free_policy.list_free_skus')
    def test_is_fast_tools_free_sku_empty_sku(self, mock_list_free):
        """Test that empty SKU is rejected."""
        mock_list_free.return_value = {"sku1"}
        
        assert is_fast_tools_free_sku("", "fast_tools") == False
        assert is_fast_tools_free_sku(None, "fast_tools") == False
    
    @patch('app.pricing.ssot_catalog.get_all_skus_with_pricing')
    @patch('app.pricing.free_policy.list_free_skus')
    def test_is_fast_tools_free_sku_no_pricing_data(self, mock_list_free, mock_get_skus):
        """Test when SKU has no pricing data."""
        mock_list_free.return_value = {"sku1", "sku2"}
        mock_get_skus.return_value = {
            "sku1": {"price_rub": 1.0},
            # sku2 missing from pricing
        }
        
        assert is_fast_tools_free_sku("sku1", "fast_tools") == True
        assert is_fast_tools_free_sku("sku2", "fast_tools") == False
    
    @patch('app.pricing.ssot_catalog.get_all_skus_with_pricing')
    @patch('app.pricing.free_policy.list_free_skus')
    def test_is_fast_tools_free_sku_deterministic_ordering(self, mock_list_free, mock_get_skus):
        """Test that ordering is deterministic (by price)."""
        mock_list_free.return_value = {"sku_a", "sku_b", "sku_c", "sku_d", "sku_e", "sku_f"}
        mock_get_skus.return_value = {
            "sku_a": {"price_rub": 5.0},
            "sku_b": {"price_rub": 2.0},
            "sku_c": {"price_rub": 8.0},
            "sku_d": {"price_rub": 1.0},
            "sku_e": {"price_rub": 3.0},
            "sku_f": {"price_rub": 4.0},
        }
        
        # Should select top-5 by price: sku_d(1), sku_b(2), sku_e(3), sku_f(4), sku_a(5)
        assert is_fast_tools_free_sku("sku_d", "fast_tools") == True  # 1.0
        assert is_fast_tools_free_sku("sku_b", "fast_tools") == True  # 2.0
        assert is_fast_tools_free_sku("sku_e", "fast_tools") == True  # 3.0
        assert is_fast_tools_free_sku("sku_f", "fast_tools") == True  # 4.0
        assert is_fast_tools_free_sku("sku_a", "fast_tools") == True  # 5.0
        assert is_fast_tools_free_sku("sku_c", "fast_tools") == False  # 8.0 (6th place)


class TestIsFreeGenerationAvailable:
    """Test is_free_generation_available function."""
    
    @pytest.mark.asyncio
    @patch('app.pricing.free_policy.is_fast_tools_free_sku')
    @patch('bot_kie.get_free_generation_status')
    async def test_is_free_generation_available_fast_tools_allowed(self, mock_status, mock_fast_tools):
        """Test free generation when FAST TOOLS allows it."""
        mock_fast_tools.return_value = True
        mock_status.return_value = {"total_remaining": 3}
        
        from bot_kie import is_free_generation_available
        
        result = await is_free_generation_available(123, "sku1", "fast_tools")
        assert result == True
    
    @pytest.mark.asyncio
    @patch('app.pricing.free_policy.is_fast_tools_free_sku')
    async def test_is_free_generation_available_fast_tools_blocked(self, mock_fast_tools):
        """Test free generation when FAST TOOLS blocks it."""
        mock_fast_tools.return_value = False
        
        from bot_kie import is_free_generation_available
        
        result = await is_free_generation_available(123, "sku1", "fast_tools")
        assert result == False
    
    @pytest.mark.asyncio
    @patch('app.pricing.free_policy.is_fast_tools_free_sku')
    @patch('bot_kie.get_free_generation_status')
    async def test_is_free_generation_available_no_remaining(self, mock_status, mock_fast_tools):
        """Test free generation when no remaining quota."""
        mock_fast_tools.return_value = True
        mock_status.return_value = {"total_remaining": 0}
        
        from bot_kie import is_free_generation_available
        
        result = await is_free_generation_available(123, "sku1", "fast_tools")
        assert result == False
    
    @pytest.mark.asyncio
    @patch('app.pricing.free_policy.is_fast_tools_free_sku')
    @patch('bot_kie.get_free_generation_status')
    async def test_is_free_generation_available_wrong_source(self, mock_status, mock_fast_tools):
        """Test free generation with wrong source."""
        mock_fast_tools.return_value = False  # Wrong source gets blocked
        mock_status.return_value = {"total_remaining": 5}
        
        from bot_kie import is_free_generation_available
        
        result = await is_free_generation_available(123, "sku1", "main_menu")
        assert result == False
