"""Synchronous wrappers for async OData clients.

This module provides synchronous interfaces to the async clients,
allowing them to be used in sync contexts like the Keboola component.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

from .async_v2_client import AsyncODataV2Client
from .async_v4_client import AsyncODataV4Client
from .auth import AuthHandler
from .catalog_parser import ServiceInfo
from .metadata import EntitySet, ODataMetadata, ODataVersion

JsonDict = dict[str, Any]


def _get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    """Get or create an event loop for sync operations.

    This should only be called from synchronous code.
    Creates a new event loop if none exists or if the existing one is closed.
    """
    try:
        # Try to get existing event loop
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_closed():
            # Loop exists but is closed, create new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
    except RuntimeError:
        # No event loop exists, create one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


class SyncODataV4Client:
    """Synchronous wrapper for AsyncODataV4Client.

    Supports context manager protocol for automatic resource cleanup:
        with SyncODataV4Client.from_api_key(...) as client:
            records = client.fetch_with_pagination(...)
    """

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
        self._async_client = AsyncODataV4Client(
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

    def __enter__(self):
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager and cleanup resources."""
        self.close()
        return False

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
    ) -> SyncODataV4Client:
        async_client: AsyncODataV4Client = AsyncODataV4Client.from_basic_auth(  # type: ignore[assignment]
            username=username,
            password=password,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
            enable_parallel=enable_parallel,
            parallel_pages=parallel_pages,
            max_requests_per_second=max_requests_per_second,
        )
        instance = cls.__new__(cls)
        instance._async_client = async_client
        instance._closed = False
        return instance

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
    ) -> SyncODataV4Client:
        async_client: AsyncODataV4Client = AsyncODataV4Client.from_api_key(  # type: ignore[assignment]
            api_key=api_key,
            header_name=header_name,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
            enable_parallel=enable_parallel,
            parallel_pages=parallel_pages,
            max_requests_per_second=max_requests_per_second,
        )
        instance = cls.__new__(cls)
        instance._async_client = async_client
        instance._closed = False
        return instance

    def get_metadata(self, force_refresh: bool = False) -> ODataMetadata:
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(self._async_client.get_metadata(force_refresh))

    def list_entity_sets(self) -> list[EntitySet]:
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(self._async_client.list_entity_sets())

    def list_fields(self, entity_set_name: str) -> list:
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(self._async_client.list_fields(entity_set_name))

    def list_catalog_services(self) -> list[ServiceInfo]:
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(self._async_client.list_catalog_services())

    def test_connection(self) -> tuple[bool, str]:
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(self._async_client.test_connection())

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
        loop = _get_or_create_event_loop()

        async def _async_fetch():
            records = []
            async for record in self._async_client.fetch_entity_set(
                entity_set=entity_set,
                select=select,
                filter_expr=filter_expr,
                expand=expand,
                order_by=order_by,
                top=top,
                skip=skip,
            ):
                records.append(record)
            return records

        records = loop.run_until_complete(_async_fetch())
        yield from records

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
        loop = _get_or_create_event_loop()

        async def _async_fetch():
            records = []
            async for record in self._async_client.fetch_with_pagination(
                entity_set=entity_set,
                select=select,
                filter_expr=filter_expr,
                expand=expand,
                order_by=order_by,
                page_size=page_size,
                max_records=max_records,
            ):
                records.append(record)
            return records

        records = loop.run_until_complete(_async_fetch())
        yield from records

    def get_record_count(self, entity_set: str, filter_expr: str | None = None) -> int | None:
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(self._async_client.get_record_count(entity_set, filter_expr))

    def _get_odata_version(self) -> ODataVersion:
        return self._async_client._get_odata_version()

    def close(self):
        """Close the underlying async client and cleanup resources."""
        if self._closed:
            return

        loop = _get_or_create_event_loop()
        try:
            loop.run_until_complete(self._async_client.close())
        finally:
            self._closed = True


class SyncODataV2Client:
    """Synchronous wrapper for AsyncODataV2Client.

    Supports context manager protocol for automatic resource cleanup:
        with SyncODataV2Client.from_api_key(...) as client:
            records = client.fetch_with_pagination(...)
    """

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
        self._async_client = AsyncODataV2Client(
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

    def __enter__(self):
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager and cleanup resources."""
        self.close()
        return False

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
    ) -> SyncODataV2Client:
        async_client: AsyncODataV2Client = AsyncODataV2Client.from_basic_auth(  # type: ignore[assignment]
                    username=username,
                    password=password,
                    base_url=base_url,
                    timeout=timeout,
                    max_retries=max_retries,
                    verify_ssl=verify_ssl,
                    enable_parallel=enable_parallel,
                    parallel_pages=parallel_pages,
                    max_requests_per_second=max_requests_per_second,
                )
        instance = cls.__new__(cls)
        instance._async_client = async_client
        instance._closed = False
        return instance

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
    ) -> SyncODataV2Client:
        async_client: AsyncODataV2Client = AsyncODataV2Client.from_api_key(  # type: ignore[assignment]
                    api_key=api_key,
                    header_name=header_name,
                    base_url=base_url,
                    timeout=timeout,
                    max_retries=max_retries,
                    verify_ssl=verify_ssl,
                    enable_parallel=enable_parallel,
                    parallel_pages=parallel_pages,
                    max_requests_per_second=max_requests_per_second,
                )
        instance = cls.__new__(cls)
        instance._async_client = async_client
        instance._closed = False
        return instance

    def get_metadata(self, force_refresh: bool = False) -> ODataMetadata:
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(self._async_client.get_metadata(force_refresh))

    def list_entity_sets(self) -> list[EntitySet]:
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(self._async_client.list_entity_sets())

    def list_fields(self, entity_set_name: str) -> list:
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(self._async_client.list_fields(entity_set_name))

    def list_catalog_services(self) -> list[ServiceInfo]:
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(self._async_client.list_catalog_services())

    def test_connection(self) -> tuple[bool, str]:
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(self._async_client.test_connection())

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
        loop = _get_or_create_event_loop()

        async def _async_fetch():
            records = []
            async for record in self._async_client.fetch_entity_set(
                entity_set=entity_set,
                select=select,
                filter_expr=filter_expr,
                expand=expand,
                order_by=order_by,
                top=top,
                skip=skip,
            ):
                records.append(record)
            return records

        records = loop.run_until_complete(_async_fetch())
        yield from records

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
        loop = _get_or_create_event_loop()

        async def _async_fetch():
            records = []
            async for record in self._async_client.fetch_with_pagination(
                entity_set=entity_set,
                select=select,
                filter_expr=filter_expr,
                expand=expand,
                order_by=order_by,
                page_size=page_size,
                max_records=max_records,
            ):
                records.append(record)
            return records

        records = loop.run_until_complete(_async_fetch())
        yield from records

    def get_record_count(self, entity_set: str, filter_expr: str | None = None) -> int | None:
        loop = _get_or_create_event_loop()
        return loop.run_until_complete(self._async_client.get_record_count(entity_set, filter_expr))

    def _get_odata_version(self) -> ODataVersion:
        return self._async_client._get_odata_version()

    def close(self):
        """Close the underlying async client and cleanup resources."""
        if self._closed:
            return

        loop = _get_or_create_event_loop()
        try:
            loop.run_until_complete(self._async_client.close())
        finally:
            self._closed = True
