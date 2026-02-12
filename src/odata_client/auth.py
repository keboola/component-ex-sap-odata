from __future__ import annotations

import base64
import logging
from abc import ABC, abstractmethod

import requests


class AuthHandler(ABC):
    """Base class for authentication handlers."""

    @abstractmethod
    def get_auth_headers(self) -> dict[str, str]:
        """Get HTTP headers for authentication."""
        pass

    @abstractmethod
    def get_auth_params(self) -> dict[str, str]:
        """Get query parameters for authentication."""
        pass

    def get_basic_auth_tuple(self) -> tuple[str, str] | None:
        """Get basic auth tuple (username, password) if applicable."""
        return None


class BasicAuthHandler(AuthHandler):
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

    def get_auth_headers(self) -> dict[str, str]:
        credentials = f"{self.username}:{self.password}"
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
        return {"Authorization": f"Basic {encoded}"}

    def get_auth_params(self) -> dict[str, str]:
        """Get query parameters for authentication."""
        return {}

    def get_basic_auth_tuple(self) -> tuple[str, str] | None:
        return self.username, self.password


class OAuthHandler(AuthHandler):
    def __init__(self, token_url: str, client_id: str, client_secret: str):
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: str | None = None

    def _fetch_access_token(self) -> None:
        try:
            response = requests.post(
                self.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            response.raise_for_status()
            token_data = response.json()
            self._access_token = token_data.get("access_token")
            if not self._access_token:
                raise ValueError("No access_token in OAuth response")
        except requests.RequestException as e:
            logging.error(f"Failed to fetch OAuth token: {e}")
            raise ValueError(f"OAuth token request failed: {e}") from e

    def get_auth_headers(self) -> dict[str, str]:
        if not self._access_token:
            self._fetch_access_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    def get_auth_params(self) -> dict[str, str]:
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

    def get_auth_params(self) -> dict[str, str]:
        """Get query parameters for authentication."""
        return {}
