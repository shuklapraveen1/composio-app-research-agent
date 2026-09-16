"""Deterministic, atomic artifact I/O.

Writes are byte-stable (sorted keys, fixed indent, trailing newline) so that a
re-run with unchanged inputs produces an unchanged file and a diff means a real
change. Writes are also atomic, so an interrupted run cannot leave a truncated
dataset behind.
"""

import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .errors import MissingArtifactError, PipelineError

JSON_INDENT = 2


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write_text(path: Path, text: str) -> Path:
    """Write ``text`` to ``path`` via a same-directory temp file and rename."""
    ensure_parent(path)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=".{}.".format(path.name),
        suffix=".tmp",
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temp_path), str(path))
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return path


def dumps_json(payload: Any) -> str:
    """Canonical JSON text: sorted keys, stable indent, trailing newline."""
    return (
        json.dumps(payload, indent=JSON_INDENT, sort_keys=True, ensure_ascii=False)
        + "\n"
    )


def write_json(path: Path, payload: Any) -> Path:
    return atomic_write_text(path, dumps_json(payload))


def read_json(path: Path, produced_by: Optional[str] = None) -> Any:
    if not path.exists():
        raise MissingArtifactError(path, produced_by=produced_by)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PipelineError(
            "Artifact is not valid JSON", path=str(path), detail=str(exc)
        ) from exc


def write_jsonl(path: Path, rows: Iterable[Any]) -> Path:
    lines = [
        json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        for row in rows
    ]
    return atomic_write_text(path, "".join(line + "\n" for line in lines))


def read_jsonl(path: Path, produced_by: Optional[str] = None) -> List[Any]:
    if not path.exists():
        raise MissingArtifactError(path, produced_by=produced_by)
    rows: List[Any] = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise PipelineError(
                    "Artifact line is not valid JSON",
                    path=str(path),
                    line=number,
                    detail=str(exc),
                ) from exc
    return rows


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], columns: Sequence[str]) -> Path:
    """Write a CSV with an explicit, fixed column order.

    Columns are explicit rather than inferred so the export stays stable even if
    an optional field happens to be absent from the first row.
    """
    import io

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=list(columns), extrasaction="raise", lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({column: _csv_cell(row.get(column)) for column in columns})
    return atomic_write_text(path, buffer.getvalue())


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "|".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return value
