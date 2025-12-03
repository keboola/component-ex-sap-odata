import logging
from abc import ABC, abstractmethod
from typing import Any

import requests
from keboola.component.dao import OauthCredentials


class AuthHandler(ABC):
    @abstractmethod
    def get_auth_headers(self) -> dict[str, str]:
        pass

    @abstractmethod
    def get_auth_params(self) -> dict[str, Any]:
        pass

    def refresh_token_if_needed(self) -> bool:
        return False


class BasicAuthHandler(AuthHandler):
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._csrf_token: str | None = None

    def get_auth_headers(self) -> dict[str, str]:
        import base64

        credentials = f"{self.username}:{self.password}"
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
        headers = {"Authorization": f"Basic {encoded}"}

        if self._csrf_token:
            headers["X-CSRF-Token"] = self._csrf_token

        return headers

    def get_auth_params(self) -> dict[str, Any]:
        return {}

    def fetch_csrf_token(self, base_url: str, session: requests.Session | None = None) -> str | None:
        try:
            headers = self.get_auth_headers()
            headers["X-CSRF-Token"] = "Fetch"

            if session:
                response = session.get(base_url, headers=headers, timeout=30)
            else:
                response = requests.get(base_url, headers=headers, timeout=30)

            response.raise_for_status()
            self._csrf_token = response.headers.get("X-CSRF-Token")
            return self._csrf_token
        except Exception as e:
            logging.warning(f"Failed to fetch CSRF token: {e}")
            return None


class OAuthHandler(AuthHandler):
    def __init__(self, oauth_credentials: OauthCredentials):
        self.oauth = oauth_credentials
        self._access_token: str | None = None
        self._csrf_token: str | None = None
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

        if self._csrf_token:
            headers["X-CSRF-Token"] = self._csrf_token

        return headers

    def get_auth_params(self) -> dict[str, Any]:
        return {}

    def fetch_csrf_token(self, base_url: str, session: requests.Session | None = None) -> str | None:
        try:
            headers = self.get_auth_headers()
            headers["X-CSRF-Token"] = "Fetch"

            if session:
                response = session.get(base_url, headers=headers, timeout=30)
            else:
                response = requests.get(base_url, headers=headers, timeout=30)

            response.raise_for_status()
            self._csrf_token = response.headers.get("X-CSRF-Token")
            return self._csrf_token
        except Exception as e:
            logging.warning(f"Failed to fetch CSRF token: {e}")
            return None

    @property
    def access_token(self) -> str | None:
        return self._access_token
