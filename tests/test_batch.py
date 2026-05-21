"""Tests for batch item creation."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from dspace_client.batch import BatchItemCreator
from dspace_client.concurrency import ConcurrencyConfig


@pytest.mark.asyncio
async def test_batch_uses_shared_adaptive_semaphore():
    client = MagicMock()
    client.create_item = AsyncMock(return_value={"uuid": "item-1"})
    client.create_bundle = AsyncMock(return_value={"uuid": "bundle-1"})

    batch = BatchItemCreator(client, config=ConcurrencyConfig(initial=2, max_concurrency=4))

    mock_semaphore = AsyncMock()
    mock_semaphore.__aenter__ = AsyncMock(return_value=mock_semaphore)
    mock_semaphore.__aexit__ = AsyncMock(return_value=None)
    batch.controller.semaphore = mock_semaphore

    await batch._execute_batch_with_concurrency(
        [
            batch._create_single_item_with_bitstream(
                {"title": "Item 1"},
                "collection-uuid",
            ),
            batch._create_single_item_with_bitstream(
                {"title": "Item 2"},
                "collection-uuid",
            ),
        ]
    )

    assert mock_semaphore.__aenter__.await_count == 2
    assert mock_semaphore.__aexit__.await_count == 2
