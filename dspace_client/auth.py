"""Authentication client for DSpace REST API."""

import httpx
import os
import time
from typing import Optional
from rich.console import Console

from .exceptions import AuthenticationError

console = Console()


class DSpaceAuthClient:
    """Handles DSpace authentication flow: CSRF → Login → JWT."""
    
    def __init__(self, base_url: str, timeout: float = 30.0):
        """
        Initialize auth client.
        
        Args:
            base_url: DSpace server base URL (e.g., https://demo.dspace.org)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.csrf_token: Optional[str] = None
        self.csrf_cookie: Optional[str] = None
        self.jwt_token: Optional[str] = None
        # Use a persistent client to maintain cookies across requests
        self.client: Optional[httpx.AsyncClient] = None
        # Track session timing for proactive refresh
        self._last_auth_time: Optional[float] = None
        # Max session age before we proactively refresh, in seconds
        # Default ~25 minutes; configurable via env for tuning.
        self.max_session_age_seconds: float = float(
            os.environ.get("DSPACE_SESSION_MAX_AGE_SECONDS", str(25 * 60))
        )
    
    async def _ensure_client(self):
        """
        Ensure we have a persistent HTTP client.
        
        CRITICAL: We must use ONE client for the entire auth flow because:
        - DSpace sets DSPACE-XSRF-COOKIE during CSRF request
        - httpx stores cookies in the client instance
        - New client = lost cookies = 403 errors
        
        See API_GOTCHAS.md for details.
        """
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)
    
    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None
    
    async def verify_server(self) -> bool:
        """
        Verify that the DSpace server is reachable.
        
        Returns:
            True if server responds, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.head(f"{self.base_url}/server/api")
                return response.status_code in (200, 302, 404)  # 404 is OK, means API exists
        except (httpx.RequestError, httpx.HTTPStatusError):
            return False
    
    async def get_csrf_token(self) -> tuple[str, str]:
        """
        Step 1: Get CSRF token from DSpace.
        
        According to CSRF documentation:
        - Server sends token in DSPACE-XSRF-TOKEN header
        - Server sets DSPACE-XSRF-COOKIE cookie
        - Client must send token in X-XSRF-TOKEN header for modifying requests
        - Server compares header value with cookie value
        
        Returns:
            Tuple of (csrf_token, csrf_cookie_value)
        
        Raises:
            AuthenticationError: If CSRF token cannot be obtained
        """
        try:
            await self._ensure_client()
            
            # console.print(f"[dim]→ HEAD {self.base_url}/server/api/security/csrf[/dim]")
            response = await self.client.head(f"{self.base_url}/server/api/security/csrf")
            
            # console.print(f"[dim]← Status: {response.status_code}[/dim]")
            
            # Extract CSRF token from header
            csrf_token = response.headers.get("dspace-xsrf-token")
            if not csrf_token:
                console.print("[red]Available headers:[/red]")
                for key, value in response.headers.items():
                    console.print(f"  {key}: {value}")
                raise AuthenticationError("CSRF token not found in response headers")
            
            # console.print(f"[dim]  CSRF Token (from header): {csrf_token[:20]}...[/dim]")
            
            # Check if server set a cookie (it should be stored in client.cookies)
            # console.print(f"[dim]  Cookies in client jar:[/dim]")
            # for cookie in self.client.cookies.jar:
            #     console.print(f"[dim]    {cookie.name} = {cookie.value[:20]}...[/dim]")
            
            self.csrf_token = csrf_token
            # Store for reference, but client will handle sending it
            self.csrf_cookie = csrf_token
            return csrf_token, csrf_token
        
        except httpx.RequestError as e:
            raise AuthenticationError(f"Failed to get CSRF token: {e}")
    
    async def login(self, username: str, password: str) -> str:
        """
        Step 2: Login with username and password to get JWT.
        
        According to authentication.md:
        - POST to /api/authn/login with form-encoded user/password
        - Must include X-XSRF-TOKEN header and DSPACE-XSRF-COOKIE cookie
        - Returns JWT in Authorization header
        
        Args:
            username: DSpace admin username
            password: DSpace admin password
        
        Returns:
            JWT bearer token
        
        Raises:
            AuthenticationError: If login fails
        """
        if not self.csrf_token or not self.csrf_cookie:
            await self.get_csrf_token()
        
        try:
            await self._ensure_client()
            
            # console.print(f"\n[dim]→ POST {self.base_url}/server/api/authn/login[/dim]")
            # console.print(f"[dim]  Headers:[/dim]")
            # console.print(f"[dim]    Content-Type: application/x-www-form-urlencoded[/dim]")
            # console.print(f"[dim]    X-XSRF-TOKEN: {self.csrf_token[:20]}...[/dim]")
            # console.print(f"[dim]  Cookies (auto-sent by client):[/dim]")
            # for cookie in self.client.cookies.jar:
            #     console.print(f"[dim]    {cookie.name} = {cookie.value[:20]}...[/dim]")
            # console.print(f"[dim]  Body: user={username}&password=***[/dim]")
            
            # Let httpx automatically send cookies from previous requests
            response = await self.client.post(
                f"{self.base_url}/server/api/authn/login",
                data={
                    "user": username,
                    "password": password,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-XSRF-TOKEN": self.csrf_token,
                },
            )
            
            console.print(f"[dim]← Status: {response.status_code}[/dim]")
            
            if response.status_code != 200:
                console.print(f"[red]Login failed![/red]")
                console.print(f"[red]Response headers:[/red]")
                for key, value in response.headers.items():
                    console.print(f"  {key}: {value}")
                console.print(f"[red]Response body:[/red]")
                console.print(response.text[:500])
                raise AuthenticationError(
                    f"Login failed with status {response.status_code}: {response.text}"
                )
            
            # ⚠️ CRITICAL: Check if CSRF token was refreshed
            # DSpace often sends a NEW CSRF token after successful login.
            # We MUST use this new token for all subsequent requests.
            # Using the old token will result in 403 "Invalid CSRF token" errors.
            # This was discovered through debugging - see HISTORY.md for details.
            new_csrf_token = response.headers.get("dspace-xsrf-token")
            if new_csrf_token and new_csrf_token != self.csrf_token:
                # console.print(f"[dim]  CSRF Token refreshed: {new_csrf_token[:20]}... (was {self.csrf_token[:20]}...)[/dim]")
                self.csrf_token = new_csrf_token
                self.csrf_cookie = new_csrf_token
            
            # Extract JWT from Authorization header
            auth_header = response.headers.get("Authorization")
            if not auth_header:
                console.print("[red]No Authorization header in response![/red]")
                console.print("[red]Available headers:[/red]")
                for key, value in response.headers.items():
                    console.print(f"  {key}: {value}")
                raise AuthenticationError("JWT token not found in response")
            
            if not auth_header.startswith("Bearer "):
                raise AuthenticationError(f"Invalid Authorization header format: {auth_header}")
            
            jwt_token = auth_header.replace("Bearer ", "")
            # console.print(f"[dim]  JWT Token: {jwt_token[:20]}...[/dim]")
            
            self.jwt_token = jwt_token
            # Record successful auth time for proactive refresh logic
            self._last_auth_time = time.time()
            return jwt_token
        
        except httpx.RequestError as e:
            raise AuthenticationError(f"Login request failed: {e}")
    
    async def verify_authentication(self) -> dict:
        """
        Step 3: Verify authentication status.
        
        Returns:
            Status information from DSpace
        
        Raises:
            AuthenticationError: If verification fails
        """
        if not self.jwt_token:
            raise AuthenticationError("No JWT token available. Please login first.")
        
        try:
            await self._ensure_client()
            
            # console.print(f"\n[dim]→ GET {self.base_url}/server/api/authn/status[/dim]")
            # console.print(f"[dim]  Headers:[/dim]")
            # console.print(f"[dim]    Authorization: Bearer {self.jwt_token[:20]}...[/dim]")
            
            response = await self.client.get(
                f"{self.base_url}/server/api/authn/status",
                headers={
                    "Authorization": f"Bearer {self.jwt_token}",
                },
            )
            
            # console.print(f"[dim]← Status: {response.status_code}[/dim]")
            
            if response.status_code != 200:
                console.print(f"[red]Verification failed![/red]")
                console.print(f"[red]Response:[/red] {response.text[:500]}")
                raise AuthenticationError(
                    f"Authentication verification failed: {response.status_code}"
                )
            
            status = response.json()
            
            if not status.get("authenticated"):
                console.print(f"[red]Status response indicates not authenticated:[/red]")
                console.print(f"  {status}")
                raise AuthenticationError("Authentication verification failed: not authenticated")
            
            # console.print(f"[dim]  Authenticated: {status.get('authenticated')}[/dim]")
            return status
        
        except httpx.RequestError as e:
            raise AuthenticationError(f"Authentication verification request failed: {e}")
    
    async def authenticate(self, username: str, password: str) -> tuple[str, dict]:
        """
        Complete authentication flow: CSRF → Login → Verify.
        
        Args:
            username: DSpace admin username
            password: DSpace admin password
        
        Returns:
            Tuple of (jwt_token, status_info)
        
        Raises:
            AuthenticationError: If any step fails
        """
        await self.get_csrf_token()
        jwt_token = await self.login(username, password)
        status = await self.verify_authentication()
        return jwt_token, status
    
    async def ensure_session(self, username: str, password: str, force: bool = False) -> str:
        """
        Ensure there is a valid, reasonably fresh authenticated session.
        
        This is designed for long-running jobs:
        - Uses a configurable max session age (default ~25 minutes).
        - Can be forced to re-authenticate unconditionally (e.g. after a 401).
        
        Args:
            username: DSpace admin username
            password: DSpace admin password
            force: If True, always re-authenticate, ignoring cached state.
        
        Returns:
            Current JWT token (possibly refreshed)
        """
        if force or not self.jwt_token or not self._last_auth_time:
            jwt, _ = await self.authenticate(username, password)
            return jwt
        
        now = time.time()
        age = now - self._last_auth_time
        if age >= self.max_session_age_seconds:
            console.print(
                f"[dim]Refreshing DSpace session (age {int(age)}s ≥ "
                f"max {int(self.max_session_age_seconds)}s)[/dim]"
            )
            jwt, _ = await self.authenticate(username, password)
            return jwt
        
        return self.jwt_token
    
    async def is_session_valid(self) -> bool:
        """
        Check if the current session (JWT token) is still valid.
        
        Returns:
            True if session is valid, False if expired or invalid
        """
        if not self.jwt_token:
            return False
        
        try:
            await self._ensure_client()
            
            response = await self.client.get(
                f"{self.base_url}/server/api/authn/status",
                headers={
                    "Authorization": f"Bearer {self.jwt_token}",
                },
            )
            
            if response.status_code != 200:
                return False
            
            status = response.json()
            return status.get("authenticated", False)
        
        except (httpx.RequestError, Exception):
            return False
