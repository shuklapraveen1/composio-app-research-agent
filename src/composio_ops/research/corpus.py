"""Loading the reviewed research corpus from disk.

The corpus lives as one JSON file per supplied category so that a reviewer can
read and diff it by category, and is assembled here into a single sorted
:class:`~composio_ops.schemas.corpus.Corpus`. Assembly is strict: a duplicate
app id, an unknown taxonomy value, or a source without a claim fails the load
rather than producing a half-populated research pass.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from .. import constants as C
from ..errors import ResearchError
from ..io_utils import read_json
from ..schemas.base import ArtifactMetadata
from ..schemas.corpus import Corpus, CorpusEntry

#: Extension of the per-category corpus files.
CORPUS_SUFFIX = ".json"


def corpus_files(corpus_apps_dir: Path) -> List[Path]:
    """Every per-category corpus file, in a stable order."""
    if not corpus_apps_dir.exists():
        raise ResearchError(
            "Research corpus directory is missing",
            path=str(corpus_apps_dir),
            produced_by="the repository; it is tracked input data",
        )
    return sorted(corpus_apps_dir.glob("*{}".format(CORPUS_SUFFIX)))


def _entries_from_file(path: Path) -> List[CorpusEntry]:
    payload: Any = read_json(path)
    if not isinstance(payload, dict) or "entries" not in payload:
        raise ResearchError(
            "Corpus file must be an object with an 'entries' array", path=str(path)
        )
    entries: List[CorpusEntry] = []
    for index, raw in enumerate(payload["entries"]):
        try:
            entries.append(CorpusEntry.model_validate(raw))
        except ValidationError as exc:
            raise ResearchError(
                "Corpus entry is invalid",
                path=str(path),
                index=index,
                app_id=raw.get("app_id") if isinstance(raw, dict) else None,
                detail=exc.errors(include_url=False),
            ) from exc
    return entries


def load_corpus(
    corpus_apps_dir: Path,
    as_of: datetime,
    seed: int,
    expected_app_ids: Optional[List[str]] = None,
) -> Corpus:
    """Assemble the corpus, optionally checking it covers the registry exactly."""
    entries: List[CorpusEntry] = []
    seen: Dict[str, Path] = {}
    files = corpus_files(corpus_apps_dir)
    if not files:
        raise ResearchError(
            "Research corpus is empty", path=str(corpus_apps_dir)
        )

    for path in files:
        for entry in _entries_from_file(path):
            previous = seen.get(entry.app_id)
            if previous is not None:
                raise ResearchError(
                    "Corpus defines the same app twice",
                    app_id=entry.app_id,
                    first=str(previous),
                    second=str(path),
                )
            seen[entry.app_id] = path
            entries.append(entry)

    entries.sort(key=lambda item: item.app_id)

    if expected_app_ids is not None:
        expected = set(expected_app_ids)
        actual = set(seen)
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing or extra:
            raise ResearchError(
                "Corpus does not cover the registry exactly",
                missing=missing[:10],
                missing_count=len(missing),
                unexpected=extra[:10],
                unexpected_count=len(extra),
            )

    metadata = ArtifactMetadata(
        stage=C.PipelineStage.RESEARCH,
        generated_at=as_of,
        seed=seed,
        record_count=len(entries),
        notes="Reviewed source corpus assembled from {} category files.".format(
            len(files)
        ),
    )
    return Corpus(metadata=metadata, entries=entries)
