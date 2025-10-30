"""Tests for authentication client."""

import pytest
from unittest.mock import AsyncMock, patch
import httpx

from dspace_client import DSpaceAuthClient
from dspace_client.exceptions import AuthenticationError


class TestDSpaceAuthClient:
    """Test DSpaceAuthClient functionality."""
    
    @pytest.mark.asyncio
    async def test_init(self):
        """Test client initialization."""
        auth = DSpaceAuthClient("https://demo.dspace.org")
        assert auth.base_url == "https://demo.dspace.org"
        assert auth.timeout == 30.0
        assert auth.csrf_token is None
        assert auth.jwt_token is None
        assert auth.client is None
    
    @pytest.mark.asyncio
    async def test_verify_server_success(self):
        """Test successful server verification."""
        auth = DSpaceAuthClient("https://demo.dspace.org")
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.head.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            result = await auth.verify_server()
            assert result is True
    
    @pytest.mark.asyncio
    async def test_verify_server_failure(self):
        """Test failed server verification."""
        auth = DSpaceAuthClient("https://demo.dspace.org")
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.head.side_effect = httpx.RequestError("Connection failed")
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            result = await auth.verify_server()
            assert result is False
    
    @pytest.mark.asyncio
    async def test_get_csrf_token_success(self):
        """Test successful CSRF token retrieval."""
        auth = DSpaceAuthClient("https://demo.dspace.org")
        
        # Mock the client and response
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.headers = {"dspace-xsrf-token": "test-csrf-token"}
        mock_client.head.return_value = mock_response
        auth.client = mock_client
        
        token, cookie = await auth.get_csrf_token()
        
        assert token == "test-csrf-token"
        assert cookie == "test-csrf-token"
        assert auth.csrf_token == "test-csrf-token"
        assert auth.csrf_cookie == "test-csrf-token"
    
    @pytest.mark.asyncio
    async def test_get_csrf_token_missing_header(self):
        """Test CSRF token retrieval when header is missing."""
        auth = DSpaceAuthClient("https://demo.dspace.org")
        
        # Mock the client and response
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.headers = {}  # No CSRF token header
        mock_client.head.return_value = mock_response
        auth.client = mock_client
        
        with pytest.raises(AuthenticationError, match="CSRF token not found"):
            await auth.get_csrf_token()
    
    @pytest.mark.asyncio
    async def test_login_success(self):
        """Test successful login."""
        auth = DSpaceAuthClient("https://demo.dspace.org")
        auth.csrf_token = "test-csrf-token"
        auth.csrf_cookie = "test-csrf-token"
        
        # Mock the client and response
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Authorization": "Bearer test-jwt-token"}
        mock_client.post.return_value = mock_response
        auth.client = mock_client
        
        jwt_token = await auth.login("testuser", "testpass")
        
        assert jwt_token == "test-jwt-token"
        assert auth.jwt_token == "test-jwt-token"
    
    @pytest.mark.asyncio
    async def test_login_failure(self):
        """Test failed login."""
        auth = DSpaceAuthClient("https://demo.dspace.org")
        auth.csrf_token = "test-csrf-token"
        auth.csrf_cookie = "test-csrf-token"
        
        # Mock the client and response
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid credentials"
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_client.post.return_value = mock_response
        auth.client = mock_client
        
        with pytest.raises(AuthenticationError, match="Login failed"):
            await auth.login("testuser", "wrongpass")
    
    @pytest.mark.asyncio
    async def test_verify_authentication_success(self):
        """Test successful authentication verification."""
        auth = DSpaceAuthClient("https://demo.dspace.org")
        auth.jwt_token = "test-jwt-token"
        
        # Mock the client and response
        mock_client = AsyncMock()
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"authenticated": True, "eperson": {"name": "Test User"}}
        mock_client.get.return_value = mock_response
        auth.client = mock_client
        
        status = await auth.verify_authentication()
        
        assert status["authenticated"] is True
        assert status["eperson"]["name"] == "Test User"
    
    @pytest.mark.asyncio
    async def test_verify_authentication_failure(self):
        """Test failed authentication verification."""
        auth = DSpaceAuthClient("https://demo.dspace.org")
        auth.jwt_token = "test-jwt-token"
        
        # Mock the client and response
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_client.get.return_value = mock_response
        auth.client = mock_client
        
        with pytest.raises(AuthenticationError, match="Authentication verification failed"):
            await auth.verify_authentication()
    
    @pytest.mark.asyncio
    async def test_authenticate_complete_flow(self):
        """Test complete authentication flow."""
        auth = DSpaceAuthClient("https://demo.dspace.org")
        
        # Mock all the methods
        with patch.object(auth, 'get_csrf_token') as mock_csrf, \
             patch.object(auth, 'login') as mock_login, \
             patch.object(auth, 'verify_authentication') as mock_verify:
            
            mock_csrf.return_value = ("test-csrf-token", "test-csrf-token")
            mock_login.return_value = "test-jwt-token"
            mock_verify.return_value = {"authenticated": True}
            
            jwt, status = await auth.authenticate("testuser", "testpass")
            
            assert jwt == "test-jwt-token"
            assert status["authenticated"] is True
            mock_csrf.assert_called_once()
            mock_login.assert_called_once_with("testuser", "testpass")
            mock_verify.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_is_session_valid_true(self):
        """Test session validity check when session is valid."""
        auth = DSpaceAuthClient("https://demo.dspace.org")
        auth.jwt_token = "test-jwt-token"
        
        # Mock the client and response
        mock_client = AsyncMock()
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"authenticated": True}
        mock_client.get.return_value = mock_response
        auth.client = mock_client
        
        result = await auth.is_session_valid()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_is_session_valid_false(self):
        """Test session validity check when session is invalid."""
        auth = DSpaceAuthClient("https://demo.dspace.org")
        auth.jwt_token = "test-jwt-token"
        
        # Mock the client and response
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_client.get.return_value = mock_response
        auth.client = mock_client
        
        result = await auth.is_session_valid()
        assert result is False
    
    @pytest.mark.asyncio
    async def test_close(self):
        """Test client close."""
        auth = DSpaceAuthClient("https://demo.dspace.org")
        auth.client = AsyncMock()
        
        await auth.close()
        
        assert auth.client is None
