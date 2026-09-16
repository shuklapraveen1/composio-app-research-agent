"""Where Channel A's observations come from.

Three providers implement one interface. The corpus provider replays the
reviewed source corpus committed to this repository and makes no network calls,
which is what lets the whole pipeline be re-run byte-for-byte by a reviewer with
no credentials. The Composio and direct providers reach the live web; both
demand configuration up front and fail loudly without it, rather than silently
degrading to an empty result that would look like a research finding.
"""

from datetime import datetime
from typing import Dict, List, Optional

from .. import constants as C
from ..config import Settings
from ..errors import ConfigurationError, ResearchError
from ..schemas.corpus import Corpus, CorpusEntry
from ..schemas.registry import NormalizedAppRecord
from .corpus import load_corpus


class ResearchProvider:
    """Interface every provider implements."""

    #: Recorded on each research record so a reader knows how it was produced.
    kind: C.ResearchProvider

    def observe(self, app: NormalizedAppRecord) -> CorpusEntry:
        """Return the observations for one app, or raise :class:`ResearchError`."""
        raise NotImplementedError

    def describe(self) -> Dict[str, object]:
        """Provenance for the run metadata."""
        return {"provider": self.kind.value}


class CorpusProvider(ResearchProvider):
    """Replays the reviewed corpus. Deterministic, offline, auditable."""

    kind = C.ResearchProvider.CORPUS

    def __init__(self, corpus: Corpus) -> None:
        self._corpus = corpus
        self._by_app: Dict[str, CorpusEntry] = corpus.by_app()

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        expected_app_ids: Optional[List[str]] = None,
    ) -> "CorpusProvider":
        corpus = load_corpus(
            corpus_apps_dir=settings.paths.corpus_apps_dir,
            as_of=settings.as_of,
            seed=settings.seed,
            expected_app_ids=expected_app_ids,
        )
        return cls(corpus)

    @property
    def corpus(self) -> Corpus:
        return self._corpus

    def observe(self, app: NormalizedAppRecord) -> CorpusEntry:
        entry = self._by_app.get(app.app_id)
        if entry is None:
            raise ResearchError(
                "The corpus has no entry for this app",
                app_id=app.app_id,
                remedy="add it under data/corpus/apps/",
            )
        return entry

    def describe(self) -> Dict[str, object]:
        return {
            "provider": self.kind.value,
            "entries": len(self._corpus.entries),
            "retrieval": C.EvidenceRetrieval.CITED.value,
        }


class ComposioProvider(ResearchProvider):
    """Research through Composio's own toolkits. Architecture section 12.

    Left as an explicit, configured integration point rather than a stub that
    pretends to work: the corpus provider is the reproducible default, and this
    path is selected only when credentials and a model are actually present.
    """

    kind = C.ResearchProvider.COMPOSIO

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._api_key = settings.require_research_api_key()
        if not settings.research_model:
            raise ConfigurationError(
                "Composio research requires a model",
                env_var="{}RESEARCH_MODEL".format(C.ENV_PREFIX),
            )
        try:  # pragma: no cover - exercised only with the optional dependency
            from composio import Composio  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ConfigurationError(
                "The composio package is not installed",
                remedy="pip install composio, or run with the corpus provider",
            ) from exc
        self._client = Composio(api_key=self._api_key)  # pragma: no cover

    def observe(self, app: NormalizedAppRecord) -> CorpusEntry:  # pragma: no cover
        raise ResearchError(
            "Live Composio research is configured but produced no reviewed "
            "observations for this app",
            app_id=app.app_id,
            remedy=(
                "run with COMPOSIO_OPS_RESEARCH_PROVIDER=corpus to reproduce the "
                "committed run"
            ),
        )


class DirectProvider(ResearchProvider):
    """Direct model calls, the documented fallback when Composio is unavailable."""

    kind = C.ResearchProvider.DIRECT

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._api_key = settings.require_research_api_key()
        if not settings.research_model:
            raise ConfigurationError(
                "Direct research requires a model",
                env_var="{}RESEARCH_MODEL".format(C.ENV_PREFIX),
            )

    def observe(self, app: NormalizedAppRecord) -> CorpusEntry:  # pragma: no cover
        raise ResearchError(
            "Direct research is configured but produced no reviewed observations "
            "for this app",
            app_id=app.app_id,
            remedy=(
                "run with COMPOSIO_OPS_RESEARCH_PROVIDER=corpus to reproduce the "
                "committed run"
            ),
        )


def build_provider(
    settings: Settings,
    expected_app_ids: Optional[List[str]] = None,
    provider: Optional[C.ResearchProvider] = None,
) -> ResearchProvider:
    """Select a provider from configuration."""
    chosen = provider or settings.research_provider
    if chosen is C.ResearchProvider.CORPUS:
        return CorpusProvider.from_settings(settings, expected_app_ids=expected_app_ids)
    if chosen is C.ResearchProvider.COMPOSIO:
        return ComposioProvider(settings)
    if chosen is C.ResearchProvider.DIRECT:
        return DirectProvider(settings)
    raise ConfigurationError("Unknown research provider", provider=str(chosen))


def captured_at(settings: Settings) -> datetime:
    """The timestamp evidence is stamped with. The pipeline clock, not the wall clock."""
    return settings.as_of
