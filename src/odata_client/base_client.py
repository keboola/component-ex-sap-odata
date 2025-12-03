import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

import requests
from keboola.component.dao import OauthCredentials
from keboola.component.exceptions import UserException

from odata_client.auth import AuthHandler, BasicAuthHandler, OAuthHandler
from odata_client.metadata import EntitySet, MetadataParser, ODataMetadata, ODataVersion


class ODataClientBase(ABC):
    def __init__(
        self,
        base_url: str,
        auth_handler: AuthHandler,
        timeout: int = 60,
        max_retries: int = 3,
        verify_ssl: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth_handler = auth_handler
        self.timeout = timeout
        self.max_retries = max_retries
        self.verify_ssl = verify_ssl
        self._session = requests.Session()
        self._metadata: ODataMetadata | None = None

    @classmethod
    def from_oauth(
        cls,
        oauth: OauthCredentials,
        base_url: str,
        timeout: int = 60,
        max_retries: int = 3,
        verify_ssl: bool = True,
    ) -> "ODataClientBase":
        auth_handler = OAuthHandler(oauth)
        return cls(
            base_url=base_url,
            auth_handler=auth_handler,
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
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
    ) -> "ODataClientBase":
        auth_handler = BasicAuthHandler(username, password)
        return cls(
            base_url=base_url,
            auth_handler=auth_handler,
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
        )

    def _make_request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> requests.Response:
        request_headers = self.auth_handler.get_auth_headers()
        request_headers["Accept"] = "application/json"
        if headers:
            request_headers.update(headers)

        for attempt in range(self.max_retries):
            try:
                response = self._session.request(
                    method=method,
                    url=url,
                    params=params,
                    headers=request_headers,
                    json=json_data,
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                )
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 401:
                    raise UserException(f"Authentication failed: {e}") from e
                if e.response is not None and e.response.status_code == 403:
                    raise UserException(f"Access forbidden: {e}") from e
                if e.response is not None and e.response.status_code == 404:
                    raise UserException(f"Resource not found: {e}") from e
                if e.response is not None and e.response.status_code >= 500 and attempt < self.max_retries - 1:
                    logging.warning(f"Server error (attempt {attempt + 1}/{self.max_retries}): {e}")
                    continue
                raise UserException(f"HTTP error: {e}") from e
            except requests.exceptions.Timeout as e:
                if attempt < self.max_retries - 1:
                    logging.warning(f"Request timeout (attempt {attempt + 1}/{self.max_retries}): {e}")
                    continue
                raise UserException(f"Request timeout after {self.max_retries} attempts") from e
            except requests.exceptions.RequestException as e:
                raise UserException(f"Request failed: {e}") from e

        raise UserException(f"Request failed after {self.max_retries} attempts")

    def get_metadata(self, force_refresh: bool = False) -> ODataMetadata:
        if self._metadata is not None and not force_refresh:
            return self._metadata

        metadata_url = f"{self.base_url}/$metadata"
        headers = self.auth_handler.get_auth_headers()
        headers["Accept"] = "application/xml"

        try:
            response = self._session.get(
                metadata_url,
                headers=headers,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            self._metadata = MetadataParser.parse(response.text, self._get_odata_version())
            return self._metadata
        except requests.exceptions.HTTPError as e:
            raise UserException(f"Failed to fetch metadata: {e}") from e
        except Exception as e:
            raise UserException(f"Failed to parse metadata: {e}") from e

    def list_entity_sets(self) -> list[EntitySet]:
        metadata = self.get_metadata()
        return metadata.list_entity_sets()

    def list_fields(self, entity_set_name: str) -> list:
        metadata = self.get_metadata()
        entity_set = metadata.get_entity_set(entity_set_name)
        if entity_set is None:
            raise UserException(f"Entity set '{entity_set_name}' not found")
        return entity_set.properties

    def test_connection(self) -> tuple[bool, str]:
        try:
            metadata = self.get_metadata(force_refresh=True)
            entity_count = len(self.list_entity_sets())
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
    ) -> Iterator[dict[str, Any]]:
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
    ) -> Iterator[dict[str, Any]]:
        pass

    @abstractmethod
    def get_record_count(self, entity_set: str, filter_expr: str | None = None) -> int | None:
        pass
