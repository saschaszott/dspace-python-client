"""Tests for core DSpace client."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from dspace_client import DSpaceClient
from dspace_client.exceptions import DSpaceAPIError, VersionIncompatibilityError


class TestDSpaceClient:
    """Test DSpaceClient functionality."""
    
    @pytest.mark.asyncio
    async def test_init(self, mock_http_client):
        """Test client initialization."""
        client = DSpaceClient(
            base_url="https://demo.dspace.org",
            jwt_token="test-jwt-token",
            csrf_token="test-csrf-token",
            http_client=mock_http_client,
            target_versions="bleeding-edge"
        )
        
        assert client.base_url == "https://demo.dspace.org"
        assert client.jwt_token == "test-jwt-token"
        assert client.csrf_token == "test-csrf-token"
        assert client.client == mock_http_client
        assert client.timeout == 30.0
        assert client.max_retries == 3
        assert client.validator is not None
        assert client.docs_fetcher is not None
    
    @pytest.mark.asyncio
    async def test_get_headers_without_csrf(self, mock_dspace_client):
        """Test getting headers without CSRF token."""
        headers = mock_dspace_client._get_headers(include_csrf=False)
        
        expected = {
            "Authorization": "Bearer mock-jwt-token",
            "Content-Type": "application/json"
        }
        assert headers == expected
    
    @pytest.mark.asyncio
    async def test_get_headers_with_csrf(self, mock_dspace_client):
        """Test getting headers with CSRF token."""
        headers = mock_dspace_client._get_headers(include_csrf=True)
        
        expected = {
            "Authorization": "Bearer mock-jwt-token",
            "Content-Type": "application/json",
            "X-XSRF-TOKEN": "mock-csrf-token"
        }
        assert headers == expected
    
    @pytest.mark.asyncio
    async def test_request_success(self, mock_dspace_client):
        """Test successful request."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"uuid": "test-uuid", "name": "Test"}
        mock_dspace_client.client.request.return_value = mock_response
        
        response = await mock_dspace_client._request("GET", "core/communities")
        
        assert response == mock_response
        mock_dspace_client.client.request.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_request_error(self, mock_dspace_client):
        """Test request with error response."""
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_response.headers = {"Content-Type": "application/json"}
        mock_dspace_client.client.request.return_value = mock_response
        
        with pytest.raises(DSpaceAPIError, match="GET.*failed with status 400"):
            await mock_dspace_client._request("GET", "core/communities")
    
    @pytest.mark.asyncio
    async def test_create_community_success(self, mock_dspace_client, sample_community_data):
        """Test successful community creation."""
        # Create a mock response object with synchronous json() method
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = sample_community_data
        mock_dspace_client._request = AsyncMock(return_value=mock_response)
        
        result = await mock_dspace_client.create_community("Test Community")
        
        assert result == sample_community_data
        mock_dspace_client._request.assert_called_once_with(
            "POST", "core/communities", json_data={
                "name": "Test Community",
                "metadata": {
                    "dc.title": [{"value": "Test Community", "language": None, "authority": None, "confidence": -1}]
                }
            }
        )
    
    @pytest.mark.asyncio
    async def test_create_community_with_metadata(self, mock_dspace_client, sample_community_data):
        """Test community creation with custom metadata."""
        custom_metadata = {
            "dc.title": [{"value": "Custom Title", "language": None, "authority": None, "confidence": -1}],
            "dc.description": [{"value": "Custom Description", "language": None, "authority": None, "confidence": -1}]
        }
        
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = sample_community_data
        mock_dspace_client._request = AsyncMock(return_value=mock_response)
        
        result = await mock_dspace_client.create_community(
            "Test Community",
            metadata=custom_metadata
        )
        
        assert result == sample_community_data
        mock_dspace_client._request.assert_called_once_with(
            "POST", "core/communities", json_data={
                "name": "Test Community",
                "metadata": custom_metadata
            }
        )
    
    @pytest.mark.asyncio
    async def test_create_community_with_parent(self, mock_dspace_client, sample_community_data):
        """Test community creation with parent."""
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = sample_community_data
        mock_dspace_client._request = AsyncMock(return_value=mock_response)
        
        result = await mock_dspace_client.create_community(
            "Test Subcommunity",
            parent_uuid="parent-uuid"
        )
        
        assert result == sample_community_data
        mock_dspace_client._request.assert_called_once_with(
            "POST", "core/communities?parent=parent-uuid", json_data={
                "name": "Test Subcommunity",
                "metadata": {
                    "dc.title": [{"value": "Test Subcommunity", "language": None, "authority": None, "confidence": -1}]
                }
            }
        )
    
    @pytest.mark.asyncio
    async def test_delete_community(self, mock_dspace_client):
        """Test community deletion."""
        mock_dspace_client._request = AsyncMock()
        
        await mock_dspace_client.delete_community("test-uuid")
        
        mock_dspace_client._request.assert_called_once_with(
            "DELETE", "core/communities/test-uuid"
        )
    
    @pytest.mark.asyncio
    async def test_create_collection_success(self, mock_dspace_client, sample_collection_data):
        """Test successful collection creation."""
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = sample_collection_data
        mock_dspace_client._request = AsyncMock(return_value=mock_response)
        
        result = await mock_dspace_client.create_collection(
            "Test Collection",
            "parent-community-uuid"
        )
        
        assert result == sample_collection_data
        mock_dspace_client._request.assert_called_once_with(
            "POST", "core/collections?parent=parent-community-uuid", json_data={
                "name": "Test Collection",
                "metadata": {
                    "dc.title": [{"value": "Test Collection", "language": None, "authority": None, "confidence": -1}]
                }
            }
        )
    
    @pytest.mark.asyncio
    async def test_create_item_success(self, mock_dspace_client, sample_item_data):
        """Test successful item creation."""
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = sample_item_data
        mock_dspace_client._request = AsyncMock(return_value=mock_response)
        
        result = await mock_dspace_client.create_item(
            "Test Item",
            "owning-collection-uuid"
        )
        
        assert result == sample_item_data
        mock_dspace_client._request.assert_called_once_with(
            "POST", "core/items?owningCollection=owning-collection-uuid", json_data={
                "name": "Test Item",
                "metadata": {
                    "dc.title": [{"value": "Test Item", "language": None, "authority": None, "confidence": -1}]
                },
                "inArchive": True,
                "discoverable": True,
                "withdrawn": False,
                "type": "item"
            }
        )
    
    @pytest.mark.asyncio
    async def test_create_bundle_success(self, mock_dspace_client):
        """Test successful bundle creation."""
        bundle_data = {"uuid": "bundle-uuid", "name": "ORIGINAL"}
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = bundle_data
        mock_dspace_client._request = AsyncMock(return_value=mock_response)
        
        result = await mock_dspace_client.create_bundle("item-uuid", "ORIGINAL")
        
        assert result == bundle_data
        mock_dspace_client._request.assert_called_once_with(
            "POST", "core/items/item-uuid/bundles", json_data={
                "name": "ORIGINAL",
                "metadata": {}
            }
        )
    
    @pytest.mark.asyncio
    async def test_upload_bitstream_success(self, mock_dspace_client):
        """Test successful bitstream upload."""
        bitstream_data = {"uuid": "bitstream-uuid", "name": "test.txt"}
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = bitstream_data
        mock_dspace_client.client.post.return_value = mock_response
        
        result = await mock_dspace_client.upload_bitstream(
            "bundle-uuid",
            "test.txt",
            b"test content"
        )
        
        assert result == bitstream_data
        mock_dspace_client.client.post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_bitstream_error(self, mock_dspace_client):
        """Test bitstream upload with error."""
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.text = "Upload failed"
        mock_dspace_client.client.post.return_value = mock_response
        
        with pytest.raises(DSpaceAPIError, match="Bitstream upload failed"):
            await mock_dspace_client.upload_bitstream(
                "bundle-uuid",
                "test.txt",
                b"test content"
            )
    
    @pytest.mark.asyncio
    async def test_create_eperson_success(self, mock_dspace_client):
        """Test successful EPerson creation."""
        eperson_data = {"uuid": "eperson-uuid", "email": "test@example.com"}
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = eperson_data
        mock_dspace_client._request = AsyncMock(return_value=mock_response)
        
        result = await mock_dspace_client.create_eperson(
            "test@example.com",
            "John",
            "Doe"
        )
        
        assert result == eperson_data
        mock_dspace_client._request.assert_called_once_with(
            "POST", "eperson/epersons", json_data={
                "email": "test@example.com",
                "metadata": {
                    "eperson.firstname": [{"value": "John", "language": None, "authority": None, "confidence": -1}],
                    "eperson.lastname": [{"value": "Doe", "language": None, "authority": None, "confidence": -1}]
                },
                "canLogIn": True,
                "requireCertificate": False,
                "type": "eperson"
            }
        )
    
    @pytest.mark.asyncio
    async def test_create_group_success(self, mock_dspace_client):
        """Test successful group creation."""
        group_data = {"uuid": "group-uuid", "name": "Test Group"}
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = group_data
        mock_dspace_client._request = AsyncMock(return_value=mock_response)
        
        result = await mock_dspace_client.create_group("Test Group", "Test Description")
        
        assert result == group_data
        mock_dspace_client._request.assert_called_once_with(
            "POST", "eperson/groups", json_data={
                "name": "Test Group",
                "metadata": {
                    "dc.description": [{"value": "Test Description", "language": None, "authority": None, "confidence": -1}]
                }
            }
        )
