import os
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "Estatia"
    openai_api_key: str | None = None
    fast_model: str = "gpt-5.4-mini"
    quality_model: str = "gpt-5.5"
    evaluation_threshold: float = 0.72
    max_retries: int = 1
    enable_news_agent: bool = True
    enable_whatsapp_agent: bool = False


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _load_dotenv() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


_load_dotenv()


settings = Settings(
    app_name=os.getenv("ESTATIA_APP_NAME", "Estatia"),
    openai_api_key=os.getenv("OPENAI_API_KEY"),
    fast_model=os.getenv("ESTATIA_FAST_MODEL", "gpt-5.4-mini"),
    quality_model=os.getenv("ESTATIA_QUALITY_MODEL", "gpt-5.5"),
    evaluation_threshold=float(os.getenv("ESTATIA_EVALUATION_THRESHOLD", "0.72")),
    max_retries=int(os.getenv("ESTATIA_MAX_RETRIES", "1")),
    enable_news_agent=_env_bool("ESTATIA_ENABLE_NEWS_AGENT", True),
    enable_whatsapp_agent=_env_bool("ESTATIA_ENABLE_WHATSAPP_AGENT", False),
)
