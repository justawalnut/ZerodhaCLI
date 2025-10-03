"""Configuration loading utilities."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_DIR = Path(os.environ.get("ZERODHACLI_CONFIG_DIR", Path.home() / ".config" / "zerodhacli"))
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass(slots=True)
class KiteCredentials:
    """Holds Zerodha Kite API credentials."""

    api_key: str = ""
    api_secret: str = ""
    access_token: str = ""
    public_token: str = ""
    user_id: str = ""


@dataclass(slots=True)
class AppConfig:
    """Top-level application configuration."""

    creds: KiteCredentials = field(default_factory=KiteCredentials)
    root_url: str = "https://api.kite.trade"
    dry_run: bool = False
    default_product: str = "MIS"
    market_protection: float = 2.5
    autoslice: bool = False
    throttle_warning_threshold: float = 0.8

    @classmethod
    def load(cls, override: Optional[Dict[str, Any]] = None) -> "AppConfig":
        """Load config from disk/.env, applying overrides."""

        _inject_dotenv()

        data: Dict[str, Any] = {}
        if CONFIG_FILE.exists():
            with CONFIG_FILE.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        if override:
            data.update(override)

        defaults = _config_defaults()

        creds_data = data.get("creds", {})
        env_creds = _credentials_from_environment()
        creds_payload = {**creds_data, **env_creds}
        config = cls(
            creds=KiteCredentials(**creds_payload) if creds_payload else KiteCredentials(),
            root_url=data.get("root_url", defaults["root_url"]),
            dry_run=data.get("dry_run", defaults["dry_run"]),
            default_product=data.get("default_product", defaults["default_product"]),
            market_protection=data.get("market_protection", defaults["market_protection"]),
            autoslice=data.get("autoslice", defaults["autoslice"]),
            throttle_warning_threshold=data.get("throttle_warning_threshold", defaults["throttle_warning_threshold"]),
        )
        return config

    def save(self) -> None:
        """Persist configuration to disk."""

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "creds": _filter_empty(_asdict(self.creds)),
            "root_url": self.root_url,
            "dry_run": self.dry_run,
            "default_product": self.default_product,
            "market_protection": self.market_protection,
            "autoslice": self.autoslice,
            "throttle_warning_threshold": self.throttle_warning_threshold,
        }
        with CONFIG_FILE.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)


def _config_defaults() -> Dict[str, Any]:
    template = AppConfig()
    return _asdict(template)


def _dotenv_path() -> Path:
    return Path(os.environ.get("ZERODHACLI_ENV_FILE", Path.cwd() / ".env"))


def _asdict(instance: Any) -> Dict[str, Any]:
    return {field.name: getattr(instance, field.name) for field in fields(instance)}


def _credentials_from_environment() -> Dict[str, str]:
    creds = load_from_env()
    return _filter_empty(_asdict(creds))


def _filter_empty(mapping: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in mapping.items() if value}


def _inject_dotenv() -> None:
    dotenv_file = _dotenv_path()
    if not dotenv_file.exists():
        return
    with dotenv_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                continue
            key, _, raw_value = stripped.partition("=")
            key = key.strip()
            value = raw_value.strip()
            if (value.startswith("\"") and value.endswith("\"")) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            value = value.strip()
            os.environ.setdefault(key, value)


def load_from_env() -> KiteCredentials:
    """Create credentials from environment variables or .env file."""

    env = os.environ
    return KiteCredentials(
        api_key=env.get("ZERODHA_API_KEY") or env.get("KITE_API_KEY", ""),
        api_secret=env.get("ZERODHA_API_SECRET") or env.get("KITE_API_SECRET", ""),
        access_token=env.get("ZERODHA_ACCESS_TOKEN") or env.get("KITE_ACCESS_TOKEN", ""),
        public_token=env.get("ZERODHA_PUBLIC_TOKEN") or env.get("KITE_PUBLIC_TOKEN", ""),
        user_id=env.get("ZERODHA_USER_ID") or env.get("KITE_USER_ID", ""),
    )
