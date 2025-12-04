from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from keboola.component.dao import OauthCredentials
from keboola.component.exceptions import UserException
from keboola.http_client import HttpClient
from requests import HTTPError, RequestException, Timeout

from odata_client.auth import ApiKeyAuthHandler, AuthHandler, BasicAuthHandler, OAuthHandler
from odata_client.metadata import EntitySet, MetadataParser, ODataMetadata, ODataVersion

# Type alias for JSON-serializable data
JsonDict = dict[str, "JsonValue"]
JsonValue = str | int | float | bool | None | list["JsonValue"] | JsonDict


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
        self._metadata: ODataMetadata | None = None
        self._client = HttpClient(
            base_url=self.base_url + "/",
            max_retries=max_retries,
            backoff_factor=0.3,
            status_forcelist=(500, 502, 503, 504),
            auth_header=auth_handler.get_auth_headers(),
        )

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

    @classmethod
    def from_api_key(
        cls,
        api_key: str,
        header_name: str,
        base_url: str,
        timeout: int = 60,
        max_retries: int = 3,
        verify_ssl: bool = True,
    ) -> "ODataClientBase":
        auth_handler = ApiKeyAuthHandler(api_key, header_name)
        return cls(
            base_url=base_url,
            auth_handler=auth_handler,
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
        )

    def _get_json(
        self,
        endpoint_path: str,
        params: dict[str, str] | None = None,
        is_absolute_path: bool = False,
    ) -> JsonDict:
        try:
            return self._client.get(
                endpoint_path=endpoint_path,
                params=params,
                headers={"Accept": "application/json"},
                is_absolute_path=is_absolute_path,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
        except HTTPError as e:
            resp = getattr(e, "response", None)
            code = resp.status_code if resp is not None else None
            if code == 401:
                raise UserException(f"Authentication failed: {e}") from e
            if code == 403:
                raise UserException(f"Access forbidden: {e}") from e
            if code == 404:
                raise UserException(f"Resource not found: {e}") from e
            raise UserException(f"HTTP error: {e}") from e
        except Timeout as e:
            raise UserException(f"Request timeout after {self.timeout}s") from e
        except RequestException as e:
            raise UserException(f"Request failed: {e}") from e

    def _get_raw(
        self,
        endpoint_path: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        is_absolute_path: bool = False,
    ) -> str:
        try:
            response = self._client.get_raw(
                endpoint_path=endpoint_path,
                params=params,
                headers=headers,
                is_absolute_path=is_absolute_path,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            return response.text
        except HTTPError as e:
            resp = getattr(e, "response", None)
            code = resp.status_code if resp is not None else None
            if code == 401:
                raise UserException(f"Authentication failed: {e}") from e
            if code == 403:
                raise UserException(f"Access forbidden: {e}") from e
            if code == 404:
                raise UserException(f"Resource not found: {e}") from e
            raise UserException(f"HTTP error: {e}") from e
        except Timeout as e:
            raise UserException(f"Request timeout after {self.timeout}s") from e
        except RequestException as e:
            raise UserException(f"Request failed: {e}") from e

    def get_metadata(self, force_refresh: bool = False) -> ODataMetadata:
        if self._metadata is not None and not force_refresh:
            return self._metadata

        try:
            metadata_text = self._get_raw(
                endpoint_path="$metadata",
                headers={"Accept": "application/xml"},
            )
            self._metadata = MetadataParser.parse(metadata_text, self._get_odata_version())
            return self._metadata
        except UserException:
            raise
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
    ) -> Iterator[JsonDict]:
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
    ) -> Iterator[JsonDict]:
        """Fetch entity set with automatic pagination."""
        pass

    @abstractmethod
    def get_record_count(self, entity_set: str, filter_expr: str | None = None) -> int | None:
        pass
