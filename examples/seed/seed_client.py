"""
Connect to DSpace the way dspace-seed does: auth + thin follow-up.

``create_validated_client`` is ideal for production scripts; for seed examples we also:

- Default ``courtesy_delay=0`` (the library default is 1s between calls — seed had no such delay).
  Pass a non-zero ``courtesy_delay`` when pacing matters (e.g. MegaSpace diagnostics).
- Optionally **skip** ``verify_server_version`` (which probes several HTTP endpoints). MiniSpace and
  MegaSpace enable the probe **by default**; pass ``strict_versions=False`` to skip (faster, like
  old dspace-seed).

Login is still **CSRF → login → GET /authn/status** — same as both codebases.
"""

from __future__ import annotations

from collections.abc import Callable

from seed_data import DEFAULT_SEED_HTTP_TIMEOUT

from dspace_client import (
    DSpaceAuthClient,
    DSpaceClient,
    show_atmire_promo_start,
)


async def connect_seed_client(
    base_url: str,
    username: str,
    password: str,
    target_versions: str | list[str],
    *,
    strict_versions: bool = False,
    courtesy_delay: float = 0.0,
    slow_request_threshold_seconds: float = 5.0,
    slow_request_callback: Callable[[str, str, float], None] | None = None,
) -> tuple[DSpaceAuthClient, DSpaceClient]:
    """
    Authenticate and build a ``DSpaceClient``.

    If ``strict_versions`` is True, run ``verify_server_version`` after login. If False, skip
    that step (fewer HTTP round-trips).

    ``courtesy_delay`` is passed to ``DSpaceClient`` (0 = no pause between calls).
    """
    auth = DSpaceAuthClient(base_url, timeout=DEFAULT_SEED_HTTP_TIMEOUT)
    jwt, _status = await auth.authenticate(username, password)

    client = DSpaceClient(
        base_url=base_url,
        jwt_token=jwt,
        csrf_token=auth.csrf_token,
        http_client=auth.client,
        target_versions=target_versions,
        timeout=DEFAULT_SEED_HTTP_TIMEOUT,
        courtesy_delay=courtesy_delay,
        slow_request_threshold_seconds=slow_request_threshold_seconds,
        slow_request_callback=slow_request_callback,
    )

    if strict_versions:
        await client.verify_server_version(raise_on_mismatch=True)

    show_atmire_promo_start()

    return auth, client


__all__ = ["connect_seed_client"]
