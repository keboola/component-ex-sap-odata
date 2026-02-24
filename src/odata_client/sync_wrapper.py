"""Synchronous wrappers for async OData clients.

This module provides synchronous interfaces to the async clients,
allowing them to be used in sync contexts like the Keboola component.

Architecture
------------
A single dedicated background thread runs an ``asyncio`` event loop
(``loop.run_forever()``).  All async operations are submitted to that
loop via ``asyncio.run_coroutine_threadsafe``, which:

* ensures that all httpx connections share one event loop (avoiding
  cross-loop contamination of asyncio primitives), and
* allows streaming generators to transfer records through a bounded
  ``queue.Queue`` instead of buffering the entire result set in memory.
"""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import Iterator
from typing import Any, Self

from .async_base_client import AsyncODataClientBase
from .async_v2_client import AsyncODataV2Client
from .async_v4_client import AsyncODataV4Client
from .auth import ApiKeyAuthHandler, AuthHandler, BasicAuthHandler
from .catalog_parser import ServiceInfo
from .metadata import EntitySet, ODataMetadata, ODataVersion

JsonDict = dict[str, Any]

# Sentinel object used to signal end-of-stream through the queue.
_SENTINEL = object()


class SyncODataClientWrapper:
    """Generic synchronous wrapper for an async OData client.

    Subclasses must set ``_async_client_class`` to the concrete async client
    type (``AsyncODataV4Client`` or ``AsyncODataV2Client``).

    Supports the context-manager protocol::

        with SyncODataV4Client(base_url=..., auth_handler=...) as client:
            for record in client.fetch_with_pagination("MyEntity"):
                ...
    """

    _async_client_class: type[AsyncODataClientBase]

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        base_url: str,
        auth_handler: AuthHandler,
        timeout: int = 60,
        max_retries: int = 3,
        verify_ssl: bool = True,
        enable_parallel: bool = True,
        parallel_pages: int = 5,
        max_requests_per_second: float | None = None,
    ):
        self._async_client = self._async_client_class(
            base_url=base_url,
            auth_handler=auth_handler,
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
            enable_parallel=enable_parallel,
            parallel_pages=parallel_pages,
            max_requests_per_second=max_requests_per_second,
        )
        self._closed = False

        # Dedicated event loop running on a background daemon thread.
        # Using a single loop for all async operations ensures that httpx
        # connections and asyncio primitives (locks, semaphores) are bound
        # to the same loop throughout the lifetime of this client.
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    # ------------------------------------------------------------------
    # Factory class methods
    # ------------------------------------------------------------------

    @classmethod
    def from_basic_auth(
        cls,
        username: str,
        password: str,
        base_url: str,
        timeout: int = 60,
        max_retries: int = 3,
        verify_ssl: bool = True,
        enable_parallel: bool = True,
        parallel_pages: int = 5,
        max_requests_per_second: float | None = None,
    ) -> Self:
        return cls(
            base_url=base_url,
            auth_handler=BasicAuthHandler(username, password),
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
            enable_parallel=enable_parallel,
            parallel_pages=parallel_pages,
            max_requests_per_second=max_requests_per_second,
        )

    @classmethod
    def from_api_key(
        cls,
        api_key: str,
        header_name: str,
        base_url: str,
        timeout: int = 60,
        max_retries: int = 3,
        verify_ssl: bool = True,
        enable_parallel: bool = True,
        parallel_pages: int = 5,
        max_requests_per_second: float | None = None,
    ) -> Self:
        return cls(
            base_url=base_url,
            auth_handler=ApiKeyAuthHandler(api_key, header_name),
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
            enable_parallel=enable_parallel,
            parallel_pages=parallel_pages,
            max_requests_per_second=max_requests_per_second,
        )

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False

    # ------------------------------------------------------------------
    # Sync-to-async bridge helpers
    # ------------------------------------------------------------------

    def _run_sync(self, coro) -> Any:
        """Submit *coro* to the background event loop and block until done."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def _stream_sync(self, async_gen_thunk) -> Iterator[JsonDict]:
        """Stream records from an async generator into a synchronous iterator.

        Records are transferred through a bounded queue (max 200 items) so
        that at most 200 records are held in memory at any one time regardless
        of total dataset size.

        Args:
            async_gen_thunk: Zero-argument callable that returns an async
                iterator when called.  It is invoked inside the producer
                coroutine so that the async iterator is created in the context
                of the background event loop.
        """
        q: queue.Queue = queue.Queue(maxsize=200)

        async def _producer() -> None:
            loop = asyncio.get_running_loop()
            exc_to_put: Exception | None = None
            try:
                async for item in async_gen_thunk():
                    # run_in_executor offloads the blocking q.put() to a thread-pool
                    # worker so the event loop thread stays free for I/O while the
                    # consumer is slow (e.g. writing CSV).
                    await loop.run_in_executor(None, q.put, item)
            except Exception as exc:
                exc_to_put = exc
            if exc_to_put is not None:
                await loop.run_in_executor(None, q.put, exc_to_put)
            await loop.run_in_executor(None, q.put, _SENTINEL)

        asyncio.run_coroutine_threadsafe(_producer(), self._loop)

        while True:
            item = q.get()
            if item is _SENTINEL:
                break
            if isinstance(item, Exception):
                raise item
            yield item

    # ------------------------------------------------------------------
    # Public API (one-shot coroutines)
    # ------------------------------------------------------------------

    def get_metadata(self, force_refresh: bool = False) -> ODataMetadata:
        return self._run_sync(self._async_client.get_metadata(force_refresh))

    def list_entity_sets(self) -> list[EntitySet]:
        return self._run_sync(self._async_client.list_entity_sets())

    def list_fields(self, entity_set_name: str) -> list:
        return self._run_sync(self._async_client.list_fields(entity_set_name))

    def list_catalog_services(self) -> list[ServiceInfo]:
        return self._run_sync(self._async_client.list_catalog_services())

    def test_connection(self) -> tuple[bool, str]:
        return self._run_sync(self._async_client.test_connection())

    def get_record_count(self, entity_set: str, filter_expr: str | None = None) -> int | None:
        return self._run_sync(self._async_client.get_record_count(entity_set, filter_expr))

    def _get_odata_version(self) -> ODataVersion:
        return self._async_client._get_odata_version()

    # ------------------------------------------------------------------
    # Public API (streaming)
    # ------------------------------------------------------------------

    def fetch_entity_set(
        self,
        entity_set: str,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        top: int | None = None,
        skip: int | None = None,
    ) -> Iterator[JsonDict]:
        client = self._async_client
        return self._stream_sync(
            lambda: client.fetch_entity_set(
                entity_set=entity_set,
                select=select,
                filter_expr=filter_expr,
                expand=expand,
                order_by=order_by,
                top=top,
                skip=skip,
            )
        )

    def fetch_with_pagination(
        self,
        entity_set: str,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        page_size: int = 1000,
        max_records: int | None = None,
    ) -> Iterator[JsonDict]:
        client = self._async_client
        return self._stream_sync(
            lambda: client.fetch_with_pagination(
                entity_set=entity_set,
                select=select,
                filter_expr=filter_expr,
                expand=expand,
                order_by=order_by,
                page_size=page_size,
                max_records=max_records,
            )
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close HTTP connections and stop the background event loop."""
        if self._closed:
            return
        self._closed = True  # set early to prevent re-entry
        try:
            future = asyncio.run_coroutine_threadsafe(self._async_client.close(), self._loop)
            future.result(timeout=10)
        except Exception:
            pass  # best-effort cleanup
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except RuntimeError:
            pass  # loop already closed/stopped
        self._loop_thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Concrete wrappers
# ---------------------------------------------------------------------------


class SyncODataV4Client(SyncODataClientWrapper):
    """Synchronous wrapper for AsyncODataV4Client."""

    _async_client_class = AsyncODataV4Client


class SyncODataV2Client(SyncODataClientWrapper):
    """Synchronous wrapper for AsyncODataV2Client."""

    _async_client_class = AsyncODataV2Client
