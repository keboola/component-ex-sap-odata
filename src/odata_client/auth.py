import base64
from abc import ABC, abstractmethod
from typing import Any

from keboola.component.dao import OauthCredentials


class AuthHandler(ABC):
    @abstractmethod
    def get_auth_headers(self) -> dict[str, str]:
        pass

    @abstractmethod
    def get_auth_params(self) -> dict[str, Any]:
        pass

    def get_basic_auth_tuple(self) -> tuple[str, str] | None:
        return None


class BasicAuthHandler(AuthHandler):
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

    def get_auth_headers(self) -> dict[str, str]:
        credentials = f"{self.username}:{self.password}"
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
        return {"Authorization": f"Basic {encoded}"}

    def get_auth_params(self) -> dict[str, Any]:
        return {}

    def get_basic_auth_tuple(self) -> tuple[str, str] | None:
        return (self.username, self.password)


class OAuthHandler(AuthHandler):
    def __init__(self, oauth_credentials: OauthCredentials):
        self.oauth = oauth_credentials
        self._access_token: str | None = None
        self._extract_access_token()

    def _extract_access_token(self) -> None:
        if self.oauth.data:
            self._access_token = self.oauth.data.get("access_token")
            if not self._access_token:
                self._access_token = self.oauth.data.get("token")

    def get_auth_headers(self) -> dict[str, str]:
        headers = {}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    def get_auth_params(self) -> dict[str, Any]:
        return {}

    @property
    def access_token(self) -> str | None:
        return self._access_token


class ApiKeyAuthHandler(AuthHandler):
    def __init__(self, api_key: str, header_name: str = "APIKey"):
        self.api_key = api_key
        self.header_name = header_name

    def get_auth_headers(self) -> dict[str, str]:
        return {self.header_name: self.api_key}

    def get_auth_params(self) -> dict[str, Any]:
        return {}
