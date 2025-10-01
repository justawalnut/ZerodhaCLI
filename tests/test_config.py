from pathlib import Path

from zerodhacli.core.config import AppConfig


def test_appconfig_load_reads_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
        KITE_API_KEY=abc123
        KITE_API_SECRET = def456
        KITE_ACCESS_TOKEN = xyz789
        """.strip()
    )

    monkeypatch.setenv("ZERODHACLI_ENV_FILE", str(env_file))
    for key in [
        "KITE_API_KEY",
        "KITE_API_SECRET",
        "KITE_ACCESS_TOKEN",
        "ZERODHA_API_KEY",
        "ZERODHA_API_SECRET",
        "ZERODHA_ACCESS_TOKEN",
    ]:
        monkeypatch.delenv(key, raising=False)

    config = AppConfig.load()

    assert config.creds.api_key == "abc123"
    assert config.creds.api_secret == "def456"
    assert config.creds.access_token == "xyz789"
