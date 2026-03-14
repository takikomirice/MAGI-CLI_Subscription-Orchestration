from __future__ import annotations

from abc import ABC, abstractmethod

from magi.models import AdvisorResult


class Provider(ABC):
    @abstractmethod
    def ask(self, prompt: str, model: str = "", effort: str = "") -> AdvisorResult:
        raise NotImplementedError
