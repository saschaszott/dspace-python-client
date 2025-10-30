"""Git-based documentation fetcher for DSpace REST API."""

import asyncio
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Union
from datetime import datetime, timedelta
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

from .exceptions import DocumentationError, NetworkError

console = Console()


class RestContractFetcher:
    """
    Manages DSpace REST API documentation with git-based updates.
    
    Uses git clone + fetch to keep docs fresh and track changes.
    """
    
    GITHUB_REPO = "DSpace/RestContract"
    GITHUB_URL = "https://github.com/DSpace/RestContract.git"
    # Store git repos in project directory (excluded from git)
    CACHE_DIR = Path("docs") / "dspace-rest-api"
    
    VERSION_MAPPING = {
        "bleeding-edge": "main",  # Latest development branch
        "7.0": "dspace-7_x",
        "7.1": "dspace-7_x", 
        "7.2": "dspace-7_x",
        "7.3": "dspace-7_x",
        "7.4": "dspace-7_x",
        "7.5": "dspace-7_x",
        "7.6": "dspace-7_x",
        "8.0": "dspace-8.0",
        "9.0": "main",  # DSpace 9 is on main
    }
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize documentation fetcher.
        
        Args:
            cache_dir: Custom cache directory (defaults to docs/dspace-rest-api/)
        """
        self.cache_dir = cache_dir or self.CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    async def fetch_version(self, version: str, force_update: bool = False) -> Path:
        """
        Clone/fetch REST contract for specific DSpace version.
        
        CALLED AUTOMATICALLY on DSpaceClient initialization.
        
        Args:
            version: "bleeding-edge", "7.0", "8.0", "9.0", etc.
            force_update: Force git fetch even if recently updated
        
        Returns:
            Path to git repository directory
        
        Raises:
            ValueError: If version is not supported
            NetworkError: If GitHub is unreachable
        """
        if version not in self.VERSION_MAPPING:
            raise ValueError(f"Unsupported DSpace version: {version}")
        
        branch = self.VERSION_MAPPING[version]
        repo_path = self.cache_dir / version
        
        try:
            # Check if repo exists
            if repo_path.exists() and (repo_path / ".git").exists():
                # Repository exists, check if we need to update
                if not force_update and not self.should_update(version):
                    console.print(f"[dim]Using cached docs for {version}[/dim]")
                    return repo_path
                
                # Update existing repository
                console.print(f"[cyan]Updating docs for {version}...[/cyan]")
                await self._update_repository(repo_path, branch)
            else:
                # Clone new repository
                console.print(f"[cyan]Fetching docs for {version}...[/cyan]")
                await self._clone_repository(repo_path, branch)
            
            # Update last update time
            self._update_last_update_time(version)
            
            return repo_path
        
        except subprocess.CalledProcessError as e:
            raise NetworkError(f"Git operation failed: {e}")
        except Exception as e:
            raise DocumentationError(f"Failed to fetch documentation: {e}")
    
    async def _clone_repository(self, repo_path: Path, branch: str):
        """Clone the RestContract repository."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"Cloning {branch} branch...", total=None)
            
            # Clone the repository
            cmd = ["git", "clone", "--depth", "1", "--branch", branch, self.GITHUB_URL, str(repo_path)]
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                raise NetworkError(f"Git clone failed: {stderr.decode()}")
            
            progress.update(task, description=f"✓ Cloned {branch} branch")
    
    async def _update_repository(self, repo_path: Path, branch: str):
        """Update existing repository with latest changes."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"Updating {branch} branch...", total=None)
            
            # Fetch latest changes
            cmd = ["git", "fetch", "origin", branch]
            result = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                raise NetworkError(f"Git fetch failed: {stderr.decode()}")
            
            # Reset to latest commit
            cmd = ["git", "reset", "--hard", f"origin/{branch}"]
            result = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                raise NetworkError(f"Git reset failed: {stderr.decode()}")
            
            progress.update(task, description=f"✓ Updated {branch} branch")
    
    async def update_all_versions(self) -> Dict[str, bool]:
        """
        Update all cached versions with latest changes.
        
        Returns:
            Dict mapping version to success status
        """
        results = {}
        
        for version in self.list_cached_versions():
            try:
                await self.fetch_version(version, force_update=True)
                results[version] = True
            except Exception as e:
                console.print(f"[red]Failed to update {version}: {e}[/red]")
                results[version] = False
        
        return results
    
    def get_last_update_time(self, version: str) -> Optional[datetime]:
        """Get timestamp of last successful update for version."""
        timestamp_file = self.cache_dir / f"{version}.last_update"
        if timestamp_file.exists():
            try:
                timestamp_str = timestamp_file.read_text().strip()
                return datetime.fromisoformat(timestamp_str)
            except ValueError:
                return None
        return None
    
    def should_update(self, version: str, max_age_hours: int = 24) -> bool:
        """Check if version needs updating based on age."""
        last_update = self.get_last_update_time(version)
        if last_update is None:
            return True
        
        age = datetime.now() - last_update
        return age > timedelta(hours=max_age_hours)
    
    def _update_last_update_time(self, version: str):
        """Update the last update timestamp for a version."""
        timestamp_file = self.cache_dir / f"{version}.last_update"
        timestamp_file.write_text(datetime.now().isoformat())
    
    def list_cached_versions(self) -> List[str]:
        """List locally cached documentation versions."""
        versions = []
        for item in self.cache_dir.iterdir():
            if item.is_dir() and (item / ".git").exists():
                versions.append(item.name)
        return sorted(versions)
    
    def get_endpoint_docs(self, endpoint: str, version: str) -> str:
        """Get documentation for specific endpoint from git repo."""
        repo_path = self.cache_dir / version
        if not repo_path.exists():
            return f"Documentation for {version} not found. Run fetch_version('{version}') first."
        
        # Look for markdown files that might contain endpoint documentation
        docs_files = list(repo_path.glob("**/*.md"))
        
        # Simple search for endpoint in markdown files
        for doc_file in docs_files:
            try:
                content = doc_file.read_text(encoding='utf-8')
                if endpoint.lower() in content.lower():
                    return content
            except Exception:
                continue
        
        return f"No documentation found for endpoint '{endpoint}' in version {version}"
    
    def validate_operation(self, operation: str, endpoint: str, versions: List[str]) -> bool:
        """
        Validate if operation is supported across all target versions.
        
        Returns True if compatible with ALL versions, False otherwise.
        """
        # This is a placeholder - in a full implementation, this would:
        # 1. Parse the REST contract documentation
        # 2. Extract endpoint definitions and supported operations
        # 3. Check if the operation is documented for the endpoint
        # 4. Verify compatibility across all target versions
        
        # For now, assume all operations are supported
        # This will be enhanced when we implement full documentation parsing
        return True
    
    def get_repo_status(self, version: str) -> Dict[str, str]:
        """Get git status information for a version."""
        repo_path = self.cache_dir / version
        if not repo_path.exists():
            return {"status": "not_found"}
        
        try:
            # Get current branch
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            current_branch = result.stdout.strip() if result.returncode == 0 else "unknown"
            
            # Get last commit hash
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            last_commit = result.stdout.strip() if result.returncode == 0 else "unknown"
            
            # Get last commit date
            result = subprocess.run(
                ["git", "log", "-1", "--format=%ci"],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            last_commit_date = result.stdout.strip() if result.returncode == 0 else "unknown"
            
            return {
                "status": "available",
                "branch": current_branch,
                "last_commit": last_commit,
                "last_commit_date": last_commit_date,
                "last_update": str(self.get_last_update_time(version) or "never")
            }
        
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def get_version_status(self, version: str) -> dict:
        """Get status information for a specific version."""
        try:
            version_dir = self.cache_dir / version
            if not version_dir.exists():
                return {"status": "not_fetched", "branch": "-", "last_update": "never"}
            
            # Get current branch
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=version_dir,
                capture_output=True,
                text=True,
                check=True
            )
            current_branch = result.stdout.strip()
            
            # Get last commit info
            result = subprocess.run(
                ["git", "log", "-1", "--format=%H %ci"],
                cwd=version_dir,
                capture_output=True,
                text=True,
                check=True
            )
            if result.stdout.strip():
                last_commit, last_commit_date = result.stdout.strip().split(" ", 1)
            else:
                last_commit = "unknown"
                last_commit_date = "unknown"
            
            return {
                "status": "available",
                "branch": current_branch,
                "last_commit": last_commit,
                "last_commit_date": last_commit_date,
                "last_update": str(self.get_last_update_time(version) or "never")
            }
        
        except Exception as e:
            return {"status": "error", "error": str(e)}


def cli_main():
    """CLI entry point for dspace-docs command."""
    import typer
    from rich.table import Table
    
    app = typer.Typer(
        name="dspace-docs",
        help="Manage DSpace REST API documentation",
        no_args_is_help=True,
    )
    
    @app.command("list")
    def list_versions():
        """List available documentation versions."""
        fetcher = RestContractFetcher()
        
        console.print("[bold]Available DSpace REST API Documentation:[/bold]")
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Version", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Branch", style="blue")
        table.add_column("Last Update", style="dim")
        
        for version in fetcher.VERSION_MAPPING.keys():
            status = fetcher.get_version_status(version)
            table.add_row(
                version,
                status.get("status", "unknown"),
                status.get("branch", "-"),
                status.get("last_update", "-")
            )
        
        console.print(table)
    
    @app.command("fetch")
    def fetch_version(version: str = typer.Argument(..., help="Version to fetch (e.g., 7.6, 8.0, 9.0, bleeding-edge)")):
        """Fetch documentation for a specific version."""
        fetcher = RestContractFetcher()
        
        console.print(f"[dim]Fetching DSpace REST API docs for version: {version}...[/dim]")
        
        try:
            result = asyncio.run(fetcher.fetch_version(version))
            console.print(f"[green]✓[/green] Documentation for {version} ready at: {result}")
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    
    @app.command("update")
    def update_all():
        """Update all cached documentation versions."""
        fetcher = RestContractFetcher()
        
        console.print("[dim]Updating all cached documentation...[/dim]")
        
        try:
            results = asyncio.run(fetcher.update_all_versions())
            console.print("[green]✓[/green] Update complete!")
            
            for version, success in results.items():
                status = "✓" if success else "✗"
                console.print(f"  {status} {version}")
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    
    @app.command("status")
    def show_status():
        """Show status of all documentation versions."""
        fetcher = RestContractFetcher()
        
        console.print("[bold]DSpace REST API Documentation Status:[/bold]")
        
        for version in fetcher.VERSION_MAPPING.keys():
            status = fetcher.get_version_status(version)
            console.print(f"\n[bold]{version}:[/bold]")
            console.print(f"  Status: {status.get('status', 'unknown')}")
            console.print(f"  Branch: {status.get('branch', '-')}")
            console.print(f"  Last Update: {status.get('last_update', '-')}")
            if status.get('error'):
                console.print(f"  Error: {status['error']}")
    
    app()
