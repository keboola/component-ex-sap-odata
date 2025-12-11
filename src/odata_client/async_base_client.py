from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, cast

from keboola.component.dao import OauthCredentials
from keboola.component.exceptions import UserException
from keboola.http_client import AsyncHttpClient

from .auth import ApiKeyAuthHandler, AuthHandler, BasicAuthHandler, OAuthHandler
from .metadata import EntitySet, MetadataParser, ODataMetadata, ODataVersion

# Type alias for JSON-serializable data
JsonDict = dict[str, Any]


class AsyncODataClientBase(ABC):
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
        self.base_url = base_url.rstrip("/")
        self.auth_handler = auth_handler
        self.timeout = timeout
        self.max_retries = max_retries
        self.verify_ssl = verify_ssl
        self.enable_parallel = enable_parallel
        self.parallel_pages = parallel_pages
        self._metadata: ODataMetadata | None = None
        self._client = AsyncHttpClient(
            base_url=self.base_url + "/",
            retries=max_retries,
            timeout=float(timeout),
            verify_ssl=verify_ssl,
            retry_status_codes=[500, 502, 503, 504],
            auth_header=auth_handler.get_auth_headers(),
            backoff_factor=0.3,
            max_requests_per_second=max_requests_per_second,
        )

    @classmethod
    def from_oauth(
        cls,
        oauth: OauthCredentials,
        base_url: str,
        timeout: int = 60,
        max_retries: int = 3,
        verify_ssl: bool = True,
        enable_parallel: bool = True,
        parallel_pages: int = 5,
        max_requests_per_second: float | None = None,
    ) -> AsyncODataClientBase:
        auth_handler = OAuthHandler(oauth)
        return cls(
            base_url=base_url,
            auth_handler=auth_handler,
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
            enable_parallel=enable_parallel,
            parallel_pages=parallel_pages,
            max_requests_per_second=max_requests_per_second,
        )

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
    ) -> AsyncODataClientBase:
        auth_handler = BasicAuthHandler(username, password)
        return cls(
            base_url=base_url,
            auth_handler=auth_handler,
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
    ) -> AsyncODataClientBase:
        auth_handler = ApiKeyAuthHandler(api_key, header_name)
        return cls(
            base_url=base_url,
            auth_handler=auth_handler,
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
            enable_parallel=enable_parallel,
            parallel_pages=parallel_pages,
            max_requests_per_second=max_requests_per_second,
        )

    async def __aenter__(self):
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *args):
        await self._client.__aexit__(*args)

    async def close(self):
        await self._client.close()

    async def _get_json(
        self,
        endpoint_path: str,
        params: dict[str, str] | None = None,
        is_absolute_path: bool = False,
    ) -> JsonDict:
        try:
            return cast(
                JsonDict,
                await self._client.get(
                    endpoint=endpoint_path,
                    params=params,
                    headers={"Accept": "application/json"},
                    is_absolute_path=is_absolute_path,
                ),
            )
        except Exception as e:
            # AsyncHttpClient raises httpx exceptions
            error_msg = str(e)
            if "401" in error_msg:
                raise UserException(f"Authentication failed: {e}") from e
            if "403" in error_msg:
                raise UserException(f"Access forbidden: {e}") from e
            if "404" in error_msg:
                raise UserException(f"Resource not found: {e}") from e
            if "timeout" in error_msg.lower():
                raise UserException(f"Request timeout after {self.timeout}s") from e
            raise UserException(f"Request failed: {e}") from e

    async def _get_raw(
        self,
        endpoint_path: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        is_absolute_path: bool = False,
    ) -> str:
        try:
            response = await self._client.get_raw(
                endpoint=endpoint_path,
                params=params,
                headers=headers,
                is_absolute_path=is_absolute_path,
            )
            response.raise_for_status()
            return response.text
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg:
                raise UserException(f"Authentication failed: {e}") from e
            if "403" in error_msg:
                raise UserException(f"Access forbidden: {e}") from e
            if "404" in error_msg:
                raise UserException(f"Resource not found: {e}") from e
            if "timeout" in error_msg.lower():
                raise UserException(f"Request timeout after {self.timeout}s") from e
            raise UserException(f"Request failed: {e}") from e

    async def get_metadata(self, force_refresh: bool = False) -> ODataMetadata:
        if self._metadata is not None and not force_refresh:
            return self._metadata

        try:
            metadata_text = await self._get_raw(
                endpoint_path="$metadata",
                headers={"Accept": "application/xml"},
            )
            self._metadata = MetadataParser.parse(metadata_text, self._get_odata_version())
            return self._metadata
        except UserException:
            raise
        except Exception as e:
            raise UserException(f"Failed to parse metadata: {e}") from e

    async def list_entity_sets(self) -> list[EntitySet]:
        metadata = await self.get_metadata()
        return metadata.list_entity_sets()

    async def list_fields(self, entity_set_name: str) -> list:
        metadata = await self.get_metadata()
        entity_set = metadata.get_entity_set(entity_set_name)
        if entity_set is None:
            raise UserException(f"Entity set '{entity_set_name}' not found")
        return entity_set.properties

    async def test_connection(self) -> tuple[bool, str]:
        try:
            metadata = await self.get_metadata(force_refresh=True)
            entity_sets = await self.list_entity_sets()
            entity_count = len(entity_sets)
            version = metadata.version.value.upper()
            return True, f"Connection successful. OData {version} service detected with {entity_count} entity sets."
        except UserException as e:
            return False, str(e)
        except Exception as e:
            return False, f"Connection failed: {e}"

    @abstractmethod
    def _get_odata_version(self) -> ODataVersion:
        pass

    @abstractmethod
    def fetch_entity_set(
        self,
        entity_set: str,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        top: int | None = None,
        skip: int | None = None,
    ) -> AsyncIterator[JsonDict]:
        """Fetch entity set without pagination."""
        pass

    @abstractmethod
    def fetch_with_pagination(
        self,
        entity_set: str,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        expand: list[str] | None = None,
        order_by: str | None = None,
        page_size: int = 1000,
        max_records: int | None = None,
    ) -> AsyncIterator[JsonDict]:
        """Fetch entity set with automatic pagination."""
        pass

    @abstractmethod
    async def get_record_count(self, entity_set: str, filter_expr: str | None = None) -> int | None:
        pass
