"""Channel A research: observations in, classified records out."""

from .buildability import combine, commercial_accessibility, credential_accessibility
from .buildability import technical_feasibility
from .confidence import calculate as calculate_confidence
from .confidence import explain as explain_confidence
from .corpus import load_corpus
from .evidence import EvidenceIndex, build_evidence, evidence_id_for
from .providers import (
    ComposioProvider,
    CorpusProvider,
    DirectProvider,
    ResearchProvider,
    build_provider,
)
from .rules import IMPROVEMENTS, ClassifierVersion, classify
from .runner import persist, research_registry

__all__ = [
    "ClassifierVersion",
    "ComposioProvider",
    "CorpusProvider",
    "DirectProvider",
    "EvidenceIndex",
    "IMPROVEMENTS",
    "ResearchProvider",
    "build_evidence",
    "build_provider",
    "calculate_confidence",
    "classify",
    "combine",
    "commercial_accessibility",
    "credential_accessibility",
    "evidence_id_for",
    "explain_confidence",
    "load_corpus",
    "persist",
    "research_registry",
    "technical_feasibility",
]
