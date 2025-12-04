from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class PaginationStrategy(ABC):
    @abstractmethod
    def get_next_page_params(self, response: dict[str, Any]) -> dict[str, Any] | None:
        pass

    @abstractmethod
    def get_next_page_url(self, response: dict[str, Any]) -> str | None:
        pass


class ServerDrivenPagination(PaginationStrategy):
    def __init__(self, is_v4: bool = False):
        self.is_v4 = is_v4

    def get_next_page_params(self, response: dict[str, Any]) -> dict[str, Any] | None:
        return None

    def get_next_page_url(self, response: dict[str, Any]) -> str | None:
        if self.is_v4:
            return response.get("@odata.nextLink")
        d = response.get("d", {})
        if isinstance(d, dict):
            return d.get("__next")
        return None


class ClientDrivenPagination(PaginationStrategy):
    def __init__(self, page_size: int = 1000):
        self.page_size = page_size
        self.current_skip = 0

    def get_next_page_params(self, response: dict[str, Any]) -> dict[str, Any] | None:
        results = self._get_results(response)
        if len(results) < self.page_size:
            return None

        self.current_skip += self.page_size
        return {
            "$top": str(self.page_size),
            "$skip": str(self.current_skip),
        }

    def get_next_page_url(self, response: dict[str, Any]) -> str | None:
        return None

    def _get_results(self, response: dict[str, Any]) -> list:
        if "value" in response:
            return response.get("value", [])
        d = response.get("d", {})
        if isinstance(d, dict):
            return d.get("results", [])
        return []

    def reset(self) -> None:
        self.current_skip = 0
