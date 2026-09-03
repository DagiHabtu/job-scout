"""Configuration — validated at startup so a bad config fails loud and early, not mid-run.

Preferences (non-secret, structured) load from a YAML file and are version-controllable. Secrets
(the optional Adzuna key, optional SMTP creds) load from the environment / a gitignored .env and
never touch the repo. Ethiopia lives here as DEFAULT USER CONTEXT — it is configuration, not logic,
so relocation or a change in circumstances is a config edit, not a code change.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .models import EmploymentType, RemoteStatus


class Location(BaseModel):
    country_code: str = "ET"                 # ISO-3166 alpha-2
    country_name: str = "Ethiopia"
    city: str | None = "Addis Ababa"
    timezone: str = "Africa/Addis_Ababa"     # EAT, UTC+3 — used for scheduling and TZ-overlap scoring


class UserProfile(BaseModel):
    """What the user is looking for and what they are eligible for. All of this is configurable."""

    # what they want
    target_roles: list[str] = Field(default_factory=lambda: ["software engineer intern", "backend intern"])
    target_technologies: list[str] = Field(default_factory=lambda: ["python", "sql", "docker"])
    preferred_industries: list[str] = Field(default_factory=list)
    employment_types: list[EmploymentType] = Field(
        default_factory=lambda: [EmploymentType.INTERNSHIP, EmploymentType.STIPEND_PROGRAM]
    )
    experience_level: str = "entry"          # free text used as an embedding signal
    education: str | None = None

    # where they are / what they can take (drives eligibility — see eligibility.py)
    location: Location = Field(default_factory=Location)
    remote_preference: RemoteStatus = RemoteStatus.REMOTE
    # countries the user is ALREADY authorized to work in. For an ET-resident with no other
    # authorization this is just ["ET"] — the eligibility classifier reads this, so it must be honest.
    work_authorization: list[str] = Field(default_factory=lambda: ["ET"])

    # soft signals
    keywords_prioritize: list[str] = Field(default_factory=list)
    keywords_penalize: list[str] = Field(default_factory=list)
    companies_prioritize: list[str] = Field(default_factory=list)
    companies_exclude: list[str] = Field(default_factory=list)


class ScoringConfig(BaseModel):
    # a disqualifying eligibility category only hard-excludes at/above this confidence
    eligibility_disqualify_confidence: float = 0.75
    # opportunities below this final relevance score are not surfaced/notified
    relevance_threshold: float = 0.45
    # consecutive SUCCESSFUL runs a posting must be absent from a source before it is marked GONE
    gone_after_missing_runs: int = 2
    # embedding model id (local, free). Downloaded once from HuggingFace at first use.
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    # bumping this invalidates cached embedding verdicts (e.g. after editing the profile)
    profile_version: int = 1


class SourceConfig(BaseModel):
    """Which sources are enabled and their (free) parameters.

    ATS APIs are company-scoped: you provide the board tokens/slugs to poll. Secrets come from env.
    """

    enabled: list[str] = Field(default_factory=lambda: ["greenhouse"])
    greenhouse_boards: list[str] = Field(default_factory=list)   # board tokens, e.g. "stripe"
    lever_sites: list[str] = Field(default_factory=list)         # site slugs
    ashby_orgs: list[str] = Field(default_factory=list)
    adzuna_country: str = "gb"                                   # Adzuna requires a country code
    adzuna_queries: list[str] = Field(default_factory=list)

    # secrets — populated from env in AppConfig.load(), never from the YAML file
    adzuna_app_id: str | None = None
    adzuna_app_key: str | None = None


class NotifyConfig(BaseModel):
    mode: str = "file"                       # "file" (zero-dep default) | "email"
    digest_path: str = "data/digest.html"
    # email is the optional free upgrade (Gmail SMTP + app password); creds come from env
    smtp_host: str | None = None
    smtp_user: str | None = None
    smtp_to: str | None = None


class AppConfig(BaseModel):
    profile: UserProfile = Field(default_factory=UserProfile)
    sources: SourceConfig = Field(default_factory=SourceConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    notify: NotifyConfig = Field(default_factory=NotifyConfig)
    db_path: str = "data/scout.db"

    @classmethod
    def load(cls, path: str | Path = "config/profile.yaml") -> "AppConfig":
        """Load YAML preferences, then overlay secrets from the environment.

        Missing YAML is not fatal — sensible defaults let the system run for a first look. Secrets
        stay in env: `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS` (pass
        is read at send time, not stored here), `SMTP_TO`.
        """
        data: dict = {}
        p = Path(path)
        if p.exists():
            data = yaml.safe_load(p.read_text()) or {}
        cfg = cls(**data)
        cfg.sources.adzuna_app_id = os.getenv("ADZUNA_APP_ID") or cfg.sources.adzuna_app_id
        cfg.sources.adzuna_app_key = os.getenv("ADZUNA_APP_KEY") or cfg.sources.adzuna_app_key
        cfg.notify.smtp_host = os.getenv("SMTP_HOST") or cfg.notify.smtp_host
        cfg.notify.smtp_user = os.getenv("SMTP_USER") or cfg.notify.smtp_user
        cfg.notify.smtp_to = os.getenv("SMTP_TO") or cfg.notify.smtp_to
        return cfg
