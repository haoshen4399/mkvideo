from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, model: str | None = None) -> str:
        raise NotImplementedError
