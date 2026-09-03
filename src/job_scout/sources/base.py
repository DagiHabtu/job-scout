"""The `Source` protocol — THE FROZEN SPINE (part 2). See PLAN.md §Spine.

One adapter per source. Adapters map a source's native records onto `Opportunity`, filling only
the fields that source actually knows. Everything derived — eligibility, relevance,
content_fingerprint, remote-status inference — is the pipeline's job. A source never scores and
never classifies eligibility.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..config import SourceConfig
from ..models import Opportunity


@runtime_checkable
class Source(Protocol):
    """Contract for a discovery source.

    - `name`: a stable identifier, used in `Provenance`, per-source metrics, and logs.
    - `fetch(cfg)`: return this source's current postings as `Opportunity` objects with the fields
      this source knows (identity + core + apply_url). Leave derived fields unset.

    Failure semantics (load-bearing — the pipeline relies on them for failure isolation):
      * A single malformed record MUST be skipped and logged, never allowed to abort the batch.
      * A TOTAL source failure (network down, auth rejected, endpoint returning HTML instead of
        JSON) MAY raise — the pipeline runs each source inside its own boundary so one failure
        never kills the run. Do NOT swallow a total failure into a silent empty list; an empty
        list means "this source genuinely has nothing," which is a different fact and drives the
        `gone`-detection logic.

    Zero-cost:
      * fetch() uses only free / no-auth endpoints, or a free-tier key whose quota is documented in
        PLAN.md §6.
    """

    name: str

    def fetch(self, cfg: SourceConfig) -> list[Opportunity]: ...
