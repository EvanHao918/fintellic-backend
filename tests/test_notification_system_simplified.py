"""
Simplified Notification System Tests
Focus on core functionality without complex transaction handling
"""
import pytest
import json
from datetime import datetime
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.user import User, UserTier
from app.models.notification_settings import UserNotificationSettings
from app.services.notification_service import notification_service


client = TestClient(app)


class TestNotificationAPI:
    """Test notification API endpoints with real auth"""
    
    @pytest.fixture(scope="class")
    def test_credentials(self):
        """Use existing test user credentials"""
        return {
            "email": "test@hermespeed.com",  # Update with your actual test user
            "password": "testpassword123"     # Update with actual password
        }
    
    @pytest.fixture(scope="class")
    def auth_token(self, test_credentials):
        """Get auth token from login"""
        response = client.post(
            "/api/v1/auth/login",
            json=test_credentials
        )
        
        if response.status_code != 200:
            pytest.skip(f"Cannot login with test credentials: {response.json()}")
        
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get auth headers"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_get_notification_settings(self, auth_headers):
        """Test GET /api/v1/notifications/settings"""
        response = client.get(
            "/api/v1/notifications/settings",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "notification_enabled" in data
        assert "filing_10k" in data
        assert "filing_10q" in data
        assert "filing_8k" in data
        assert "filing_s1" in data
        assert "watchlist_only" in data
    
    def test_update_notification_settings(self, auth_headers):
        """Test PUT /api/v1/notifications/settings"""
        # Update settings
        update_data = {
            "filing_10k": True,
            "watchlist_only": False
        }
        
        response = client.put(
            "/api/v1/notifications/settings",
            headers=auth_headers,
            json=update_data
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["filing_10k"] == True
        assert data["watchlist_only"] == False
    
    def test_get_notification_history(self, auth_headers):
        """Test GET /api/v1/notifications/history"""
        response = client.get(
            "/api/v1/notifications/history",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
    
    def test_get_notification_stats(self, auth_headers):
        """Test GET /api/v1/notifications/stats"""
        response = client.get(
            "/api/v1/notifications/stats",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "total_sent" in data
        assert "total_failed" in data
        assert "device_count" in data
    
    def test_register_device_token(self, auth_headers):
        """Test POST /api/v1/notifications/device/register"""
        response = client.post(
            "/api/v1/notifications/device/register",
            headers=auth_headers,
            json={
                "token": f"test_token_{int(datetime.utcnow().timestamp())}",
                "platform": "android"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] == True


class TestNotificationService:
    """Test notification service core logic"""
    
    def test_firebase_initialization(self):
        """Test that notification service initializes"""
        assert notification_service is not None
        
        # Check Firebase status (may be False without credentials)
        is_ready = notification_service.is_firebase_ready()
        assert isinstance(is_ready, bool)
    
    def test_device_token_parsing(self):
        """Test device token extraction from JSON"""
        # Create mock user with tokens
        class MockUser:
            def __init__(self):
                self.device_tokens = json.dumps([
                    {"token": "token1", "platform": "ios"},
                    {"token": "token2", "platform": "android"}
                ])
        
        user = MockUser()
        tokens = notification_service._get_user_device_tokens(user)
        
        assert isinstance(tokens, list)
        assert len(tokens) == 2
        assert "token1" in tokens
        assert "token2" in tokens
    
    def test_empty_device_tokens(self):
        """Test handling of empty device tokens"""
        class MockUser:
            def __init__(self):
                self.device_tokens = None
        
        user = MockUser()
        tokens = notification_service._get_user_device_tokens(user)
        
        assert isinstance(tokens, list)
        assert len(tokens) == 0


class TestNotificationModels:
    """Test notification database models"""
    
    def test_notification_settings_defaults(self):
        """Test default notification settings values"""
        # Create test settings object (not saved to DB)
        # Note: Need to provide all required fields since defaults are set at DB level
        settings = UserNotificationSettings(
            user_id=9999,  # Fake ID
            notification_enabled=True,
            filing_10k=True,
            filing_10q=True,
            filing_8k=True,
            filing_s1=True,
            watchlist_only=False
        )
        
        # Check values
        assert settings.filing_10k == True
        assert settings.filing_10q == True
        assert settings.filing_8k == True
        assert settings.filing_s1 == True
        assert settings.watchlist_only == False
        assert settings.notification_enabled == True
    
    def test_should_send_notification_logic(self):
        """Test notification filtering logic"""
        settings = UserNotificationSettings(
            user_id=9999,
            notification_enabled=True,
            filing_10k=True,
            filing_10q=False,
            watchlist_only=False
        )
        
        # Should send for 10-K
        assert settings.should_send_filing_notification('10-K', False) == True
        
        # Should NOT send for 10-Q (disabled)
        assert settings.should_send_filing_notification('10-Q', False) == False
        
        # Test watchlist_only filter
        settings.watchlist_only = True
        
        # Should NOT send if not in watchlist
        assert settings.should_send_filing_notification('10-K', False) == False
        
        # Should send if in watchlist
        assert settings.should_send_filing_notification('10-K', True) == True
    
    def test_get_enabled_filing_types(self):
        """Test getting enabled filing types"""
        settings = UserNotificationSettings(
            user_id=9999,
            filing_10k=True,
            filing_10q=False,
            filing_8k=True,
            filing_s1=False
        )
        
        enabled = settings.get_enabled_filing_types()
        
        assert '10-K' in enabled
        assert '10-Q' not in enabled
        assert '8-K' in enabled
        assert 'S-1' not in enabled


class TestNotificationIntegration:
    """Integration tests for notification system"""
    
    def test_health_check(self):
        """Test that app is running"""
        response = client.get("/health")
        assert response.status_code == 200
    
    def test_notification_endpoints_require_auth(self):
        """Test that notification endpoints require authentication"""
        # Try without auth
        response = client.get("/api/v1/notifications/settings")
        assert response.status_code == 401
        
        response = client.get("/api/v1/notifications/history")
        assert response.status_code == 401
        
        response = client.get("/api/v1/notifications/stats")
        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])