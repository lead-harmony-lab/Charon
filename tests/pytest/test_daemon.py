import asyncio
import runpy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from charon.daemon import app, daemon, engine, lifespan, main


class TestDaemonAppConfig:
    """Tests FastAPI application metadata and route configuration."""

    def test_app_metadata(self):
        """Verify FastAPI app instance metadata."""
        assert isinstance(app, FastAPI)
        assert app.title == "Charon Engine API Gateway"
        assert app.version == "3.1.0"
        assert "FastAPI Network Gateway" in app.description

    def test_app_middleware_configured(self):
        """Verify CORS and APIKey middleware are registered on app."""
        middleware_names = [m.cls.__name__ for m in app.user_middleware]
        assert "APIKeyMiddleware" in middleware_names
        assert "CORSMiddleware" in middleware_names


class TestDaemonLifespan:
    """Tests async startup and graceful shutdown behavior of the gateway lifespan."""

    @pytest.mark.asyncio
    async def test_lifespan_lifecycle_and_task_cancellation(self):
        """Verify state initialization, background task spawning, and cleanup cancellation."""
        test_app = FastAPI()

        # Mock long-running background workers that block until cancelled
        async def mock_worker(*args, **kwargs):
            await asyncio.sleep(3600)

        with patch.object(daemon, "process_queue", side_effect=mock_worker) as mock_queue, \
             patch.object(daemon, "start_overseer_reporter", side_effect=mock_worker) as mock_overseer:

            async with lifespan(test_app):
                # Verify state binding on startup
                assert test_app.state.daemon == daemon
                assert test_app.state.engine == engine

                # Verify workers were invoked
                mock_queue.assert_called_once()
                mock_overseer.assert_called_once_with(interval=30)

            # Upon exiting contextmanager, tasks should be cancelled and gathered cleanly
            # No unhandled exception should leak out of lifespan


class TestDaemonCLI:
    """Tests CLI invocation and execution entrypoints."""

    def test_main_runs_uvicorn(self):
        """Verify main() invokes uvicorn with expected parameters."""
        with patch("uvicorn.run") as mock_uvicorn_run:
            main()
            mock_uvicorn_run.assert_called_once_with(
                "charon.daemon:app",
                host="0.0.0.0",
                port=8000,
                log_level="info",
            )

    def test_module_entrypoint_execution(self):
        """Verify top-level module execution (if __name__ == '__main__')."""
        with patch("uvicorn.run") as mock_uvicorn_run, \
             patch("charon.config.paths.ensure_ecosystem_directories"), \
             patch("charon.config.logging.setup_logging"):

            runpy.run_module("charon.daemon", run_name="__main__")
            mock_uvicorn_run.assert_called_once()
