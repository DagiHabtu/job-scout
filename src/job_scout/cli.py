"""Command-line entrypoint — ONE idempotent run, decoupled from scheduling.

Scheduling (cron / GitHub Actions) is deliberately NOT this module's concern: the scheduler calls
`job-scout` once; this runs the pipeline once and exits. That separation is what lets the same
command run under Actions, a local cron, or a human at a terminal, unchanged.

Phase 0: no live source adapters exist yet (they fan out AFTER Gate 0). `build_sources` therefore
resolves an empty set for now and the command runs clean with zero sources — the wiring is proven
before the adapters land. Each adapter registers here as it is built.
"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import AppConfig
from .pipeline import RunSummary, run_once
from .sources.base import Source

log = logging.getLogger("job_scout")

# Maps an enabled-source name (config.sources.enabled) to a zero-arg factory. Populated as adapters
# are built post-Gate-0 (greenhouse done; lever, ashby, adzuna, known_programs to come).
def _greenhouse_factory() -> Source:
    from .sources.greenhouse import GreenhouseSource

    return GreenhouseSource()


def _known_programs_factory() -> Source:
    from .sources.known_programs import KnownProgramsSource

    return KnownProgramsSource()


def _lever_factory() -> Source:
    from .sources.lever import LeverSource

    return LeverSource()


def _ashby_factory() -> Source:
    from .sources.ashby import AshbySource

    return AshbySource()


_REGISTRY: dict[str, "callable[[], Source]"] = {
    "greenhouse": _greenhouse_factory,
    "known_programs": _known_programs_factory,
    "lever": _lever_factory,
    "ashby": _ashby_factory,
}


def build_sources(cfg: AppConfig) -> list[Source]:
    """Instantiate the adapters named in `cfg.sources.enabled` that are registered. Unknown names
    are logged and skipped rather than crashing the run (a config can name a not-yet-built source)."""
    sources: list[Source] = []
    for name in cfg.sources.enabled:
        factory = _REGISTRY.get(name)
        if factory is None:
            log.warning("no adapter registered for source %r (skipping)", name)
            continue
        sources.append(factory())
    return sources


def _load_embedding_model(cfg: AppConfig):
    """Best-effort load of the optional local embedding model. None → lexical scoring (still $0)."""
    from .score import load_model

    return load_model(cfg.scoring.embedding_model)


def run(argv: list[str] | None = None) -> RunSummary:
    parser = argparse.ArgumentParser(prog="job-scout", description="Zero-cost, eligibility-first job scout — one run.")
    parser.add_argument("-c", "--config", default="config/profile.yaml", help="path to the YAML profile")
    parser.add_argument("--no-model", action="store_true", help="skip the embedding model; use lexical scoring only")
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose logging")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = AppConfig.load(args.config)
    sources = build_sources(cfg)
    if not sources:
        log.warning("no sources resolved — running an empty pass (Phase 0 has no adapters yet)")
    model = None if args.no_model else _load_embedding_model(cfg)

    summary = run_once(cfg, sources, model=model)
    log.info(
        "run %s: discovered=%d deduped=%d survived=%d lifecycle=%s notified=%d digest=%s",
        summary.run_id, summary.discovered, summary.after_dedupe, summary.after_filter,
        summary.lifecycle, summary.notified, summary.digest_path,
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    try:
        run(argv)
    except Exception:  # a run-level failure is a real error the scheduler should see (nonzero exit)
        log.exception("run failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
