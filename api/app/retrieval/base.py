"""The retriever interface. The rest of the API only ever sees this."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..schemas import Passage


class RetrievalError(Exception):
    """The index or the embedding model could not be reached."""


@dataclass(frozen=True)
class IndexInfo:
    """What the collection says about itself: how big it is and how it was built."""

    count: int
    embed_model: str | None
    index_id: str


class Retriever(Protocol):
    name: str

    def retrieve(self, question: str, k: int) -> list[Passage]:
        """Return up to k passages, best first."""
        ...

    def index_info(self) -> IndexInfo:
        """Describe the index. Raises RetrievalError when it cannot be reached."""
        ...