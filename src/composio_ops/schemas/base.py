"""Strict model base and shared field types.

Every persisted record inherits from :class:`StrictModel`: unknown fields are
rejected rather than dropped, instances are immutable, and defaults are
validated. That turns a schema drift between two stages into an immediate,
located failure instead of a silently missing column in the final dataset.
"""

from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from .. import constants as C

#: Slug identifying an app across every stage and artifact.
AppId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$",
    ),
]

#: Name of a classified attribute. The attribute vocabulary itself is data, not
#: code: it is defined by the assignment brief and loaded at runtime.
AttributeName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$",
    ),
]

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

#: Values a classification may hold. Deliberately narrow: no nested objects, so
#: every value is representable in both the JSON and the CSV export.
ValuePrimitive = Union[bool, int, float, str, List[str]]


def utc_now() -> datetime:
    """Timezone-aware current time. The only clock the pipeline should use."""
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    """Reject naive datetimes and normalize everything else to UTC."""
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


#: Timestamp type used by every record. Naive datetimes are rejected outright,
#: because a timestamp without an offset cannot be compared across evidence.
UtcDatetime = Annotated[datetime, AfterValidator(ensure_utc)]


class StrictModel(BaseModel):
    """Immutable, extra-forbidding base for all pipeline records."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
        populate_by_name=True,
        use_enum_values=False,
    )

    def to_jsonable(self) -> Dict[str, Any]:
        """JSON-safe dict suitable for :func:`composio_ops.io_utils.write_json`."""
        return self.model_dump(mode="json")


class ArtifactMetadata(StrictModel):
    """Provenance header carried by every artifact the pipeline writes."""

    schema_version: str = C.SCHEMA_VERSION
    stage: C.PipelineStage
    generated_at: UtcDatetime
    seed: int
    record_count: int
    source_fingerprint: str = ""
    notes: str = ""
