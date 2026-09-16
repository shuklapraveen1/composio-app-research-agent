"""Evidence-first research pipeline for the Composio AI Product Ops take-home.

Stage order is fixed by the finalized architecture:

    registry -> normalization -> Channel A research -> evidence extraction ->
    classification -> deterministic validation -> initial dataset ->
    review + Sample A/B selection -> sampled verification -> reconciliation ->
    final dataset -> deterministic analytics -> case studies -> publication

Importing this package must never touch the network, read pipeline data, or
require a secret.
"""

from .constants import PROJECT_NAME, SCHEMA_VERSION

__version__ = "0.1.0"

__all__ = ["PROJECT_NAME", "SCHEMA_VERSION", "__version__"]
