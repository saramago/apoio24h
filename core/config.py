from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(base_dir: Path = BASE_DIR) -> None:
    env_path = base_dir / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    prompt_file: Path
    openai_api_key: str
    openai_model: str
    mbway_mode: str
    mbway_phone: str
    mbway_sandbox_delay_seconds: float
    sibs_client_id: str
    sibs_client_secret: str
    sibs_bearer_token: str
    sibs_terminal_id: str
    sibs_channel: str
    sibs_base_url: str
    admin_token: str
    session_memory_ttl_seconds: int
    enable_provider_refresh_jobs: bool
    provider_refresh_interval_seconds: int


def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        base_dir=BASE_DIR,
        prompt_file=BASE_DIR / "prompts" / "advisor_system.txt",
        openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
        mbway_mode=os.environ.get("MBWAY_MODE", "mock").strip().lower() or "mock",
        mbway_phone=os.environ.get("MBWAY_PHONE", "912606050").strip() or "912606050",
        mbway_sandbox_delay_seconds=float(os.environ.get("MBWAY_SANDBOX_DELAY_SECONDS", "3")),
        sibs_client_id=os.environ.get("SIBS_CLIENT_ID", "").strip(),
        sibs_client_secret=os.environ.get("SIBS_CLIENT_SECRET", "").strip(),
        sibs_bearer_token=os.environ.get("SIBS_BEARER_TOKEN", "").strip(),
        sibs_terminal_id=os.environ.get("SIBS_TERMINAL_ID", "").strip(),
        sibs_channel=os.environ.get("SIBS_CHANNEL", "web").strip() or "web",
        sibs_base_url=os.environ.get("SIBS_BASE_URL", "https://sandbox.sibspayments.com").strip()
        or "https://sandbox.sibspayments.com",
        admin_token=os.environ.get("ADMIN_TOKEN", "").strip(),
        session_memory_ttl_seconds=int(os.environ.get("SESSION_MEMORY_TTL_SECONDS", "1800")),
        enable_provider_refresh_jobs=os.environ.get("ENABLE_PROVIDER_REFRESH_JOBS", "0").strip() == "1",
        provider_refresh_interval_seconds=int(os.environ.get("PROVIDER_REFRESH_INTERVAL_SECONDS", "3600")),
    )
