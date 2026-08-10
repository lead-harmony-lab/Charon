"""tests/config/test_settings.py — Unit tests for charon.config.settings coverage."""

import importlib
from unittest.mock import patch, MagicMock


def test_settings_env_file_exists():
    """Verifies that load_dotenv is called when CHARON_ENV_FILE exists."""
    mock_env_file = MagicMock()
    mock_env_file.exists.return_value = True

    with patch("charon.config.paths.CHARON_ENV_FILE", mock_env_file), \
         patch("dotenv.load_dotenv") as mock_load:
        import charon.config.settings
        importlib.reload(charon.config.settings)
        mock_load.assert_called_once_with(mock_env_file)


def test_settings_env_file_does_not_exist():
    """Verifies that load_dotenv is skipped when CHARON_ENV_FILE does not exist."""
    mock_env_file = MagicMock()
    mock_env_file.exists.return_value = False

    with patch("charon.config.paths.CHARON_ENV_FILE", mock_env_file), \
         patch("dotenv.load_dotenv") as mock_load:
        import charon.config.settings
        importlib.reload(charon.config.settings)
        mock_load.assert_not_called()


def test_settings_defaults(monkeypatch):
    """Verifies default values when environment variables are unset."""
    monkeypatch.delenv("CHARON_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("CHARON_HEAVY_MODEL", raising=False)
    monkeypatch.delenv("CHARON_TRIAGE_MODEL", raising=False)

    mock_env_file = MagicMock()
    mock_env_file.exists.return_value = False

    with patch("charon.config.paths.CHARON_ENV_FILE", mock_env_file):
        import charon.config.settings
        importlib.reload(charon.config.settings)

        assert charon.config.settings.CHARON_API_KEY == "charon-secret-key-change-me"
        assert charon.config.settings.API_KEY_HEADER_NAME == "X-API-Key"
        assert charon.config.settings.OLLAMA_HOST == "http://localhost:11434"
        assert charon.config.settings.DEFAULT_HEAVY_MODEL == "llama3.1"
        assert charon.config.settings.DEFAULT_TRIAGE_MODEL == "llama3.1"


def test_settings_custom_env_vars(monkeypatch):
    """Verifies environment variable overrides."""
    monkeypatch.setenv("CHARON_API_KEY", "custom-secret-key")
    monkeypatch.setenv("OLLAMA_HOST", "http://192.168.1.100:11434")
    monkeypatch.setenv("CHARON_HEAVY_MODEL", "qwen2.5-coder")
    monkeypatch.setenv("CHARON_TRIAGE_MODEL", "phi4")

    mock_env_file = MagicMock()
    mock_env_file.exists.return_value = False

    with patch("charon.config.paths.CHARON_ENV_FILE", mock_env_file):
        import charon.config.settings
        importlib.reload(charon.config.settings)

        assert charon.config.settings.CHARON_API_KEY == "custom-secret-key"
        assert charon.config.settings.OLLAMA_HOST == "http://192.168.1.100:11434"
        assert charon.config.settings.DEFAULT_HEAVY_MODEL == "qwen2.5-coder"
        assert charon.config.settings.DEFAULT_TRIAGE_MODEL == "phi4"
