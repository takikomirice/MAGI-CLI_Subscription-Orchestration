from __future__ import annotations

from abc import ABC, abstractmethod

from magi.cancellation import RunCancellation
from magi.models import AdvisorResult


class Provider(ABC):
    @abstractmethod
    def ask(
        self,
        prompt: str,
        model: str = "",
        effort: str = "",
        cancellation: RunCancellation | None = None,
    ) -> AdvisorResult:
        raise NotImplementedError
