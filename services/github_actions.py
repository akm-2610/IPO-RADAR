"""Optional, failure-tolerant GitHub Actions configuration and status."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

import requests
from dotenv import dotenv_values, set_key

LOGGER = logging.getLogger("ipo_radar.github")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
_INITIAL_ENVIRONMENT = {
    key: os.environ[key]
    for key in ("GITHUB_REPOSITORY", "GITHUB_TOKEN")
    if key in os.environ
}
DEFAULT_CONFIG = {"github_repository": "", "github_token": ""}
_REPOSITORY_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]+$"
)


def load_config(
    *,
    settings_path: Path | None = None,
    env_path: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Load GitHub settings in environment > .env > settings.json > defaults order."""
    settings_path = settings_path or PROJECT_ROOT / "config" / "settings.json"
    env_path = env_path or PROJECT_ROOT / ".env"
    environment = environ if environ is not None else os.environ
    config = dict(DEFAULT_CONFIG)

    try:
        stored = json.loads(settings_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        stored = {}
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        LOGGER.warning("GitHub settings file could not be loaded; using remaining configuration sources: %s", error)
        stored = {}

    if isinstance(stored, dict):
        config["github_repository"] = str(
            stored.get("github_repository", stored.get("GITHUB_REPOSITORY", "")) or ""
        ).strip()
        config["github_token"] = str(
            stored.get("github_token", stored.get("GITHUB_TOKEN", "")) or ""
        ).strip()
    else:
        LOGGER.warning("GitHub settings file has an invalid structure; using remaining configuration sources.")

    try:
        dotenv_config = dotenv_values(env_path)
    except (OSError, UnicodeError) as error:
        LOGGER.warning("GitHub .env configuration could not be loaded: %s", error)
        dotenv_config = {}

    for config_key, env_key in (
        ("github_repository", "GITHUB_REPOSITORY"),
        ("github_token", "GITHUB_TOKEN"),
    ):
        dotenv_value = dotenv_config.get(env_key)
        environment_value = environment.get(env_key)
        if dotenv_value is not None:
            config[config_key] = dotenv_value.strip()
        if environment_value is not None:
            config[config_key] = environment_value.strip()
    return config


def save_github_configuration(
    repository: str,
    *,
    token: str | None = None,
    env_path: Path | None = None,
) -> None:
    """Persist user-entered GitHub settings in the ignored local .env file."""
    env_path = env_path or PROJECT_ROOT / ".env"
    if repository and not _valid_repository(repository.strip()):
        raise ValueError("Repository must use the owner/repository format.")
    try:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        set_key(env_path, "GITHUB_REPOSITORY", repository.strip(), quote_mode="always")
        if "GITHUB_REPOSITORY" not in _INITIAL_ENVIRONMENT:
            os.environ["GITHUB_REPOSITORY"] = repository.strip()
        if token is not None:
            set_key(env_path, "GITHUB_TOKEN", token.strip(), quote_mode="always")
            if "GITHUB_TOKEN" not in _INITIAL_ENVIRONMENT:
                os.environ["GITHUB_TOKEN"] = token.strip()
    except (OSError, UnicodeError) as error:
        raise OSError("Unable to save GitHub configuration to .env.") from error


def get_github_repository(config: Mapping[str, str] | None = None) -> str:
    return (config if config is not None else load_config()).get("github_repository", "").strip()


def get_github_token(config: Mapping[str, str] | None = None) -> str:
    return (config if config is not None else load_config()).get("github_token", "").strip()


def get_latest_actions_run(
    config: Mapping[str, str] | None = None,
    *,
    session: requests.Session | None = None,
    timeout: float = 6.0,
) -> dict[str, Any]:
    """Return a normalized status result; GitHub configuration/network issues never escape."""
    config = config if config is not None else load_config()
    repository = get_github_repository(config)
    token = get_github_token(config)
    if not repository:
        return _result(
            "not_configured",
            "GitHub Actions monitoring not configured.",
            repository="",
        )
    if not _valid_repository(repository):
        return _result(
            "error",
            "Invalid GitHub repository format. Use owner/repository.",
            repository=repository,
        )

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token

    http = session or requests.Session()
    try:
        response = http.get(
            f"https://api.github.com/repos/{repository}/actions/runs?per_page=1",
            headers=headers,
            timeout=timeout,
        )
    except requests.Timeout:
        return _result("warning", "GitHub API request timed out. Try again shortly.", repository=repository)
    except requests.RequestException:
        return _result(
            "warning",
            "GitHub API is unreachable. Check internet connectivity and try again.",
            repository=repository,
        )

    if response.status_code == 401:
        return _result(
            "error",
            "GitHub rejected the token. Check that it is valid and has Actions read access.",
            repository=repository,
        )
    if response.status_code in {403, 429}:
        rate_limited = _is_rate_limited(response)
        if rate_limited:
            return _result(
                "warning",
                "GitHub API rate limit reached. Wait for the reset or configure a token.",
                repository=repository,
            )
        if token:
            message = "GitHub denied access. Check token permissions and repository access."
        else:
            message = "GitHub denied this request. Verify the repository is public or configure a token."
        return _result("error", message, repository=repository)
    if response.status_code == 404:
        if token:
            message = (
                "GitHub could not access this repository. Verify the Personal Access Token "
                "is valid and has Actions read permission and repository access."
            )
        else:
            message = "Repository not found or private. Verify its name or configure a Personal Access Token."
        return _result("error", message, repository=repository)
    if not response.ok:
        return _result(
            "error" if response.status_code < 500 else "warning",
            f"GitHub API returned HTTP {response.status_code}. Try again later.",
            repository=repository,
        )

    try:
        payload = response.json()
    except ValueError:
        return _result("error", "GitHub returned an unreadable API response.", repository=repository)
    if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
        return _result("error", "GitHub returned an unexpected Actions response.", repository=repository)
    runs = payload["workflow_runs"]
    if not runs:
        return _result(
            "info",
            "Repository is connected, but no workflow runs were found.",
            repository=repository,
        )
    run = runs[0]
    if not isinstance(run, dict):
        return _result("error", "GitHub returned an invalid workflow run.", repository=repository)

    status = str(run.get("status") or "unknown")
    conclusion = str(run.get("conclusion") or "—")
    result_status = "healthy"
    message = "Latest GitHub Actions run loaded."
    if status != "completed":
        result_status = "warning"
        message = f"Latest workflow run is {status}."
    elif conclusion != "success":
        result_status = "error" if conclusion in {"failure", "timed_out", "action_required"} else "warning"
        message = f"Latest workflow run concluded: {conclusion}."

    started = run.get("run_started_at") or run.get("created_at")
    ended = run.get("updated_at") if status == "completed" else None
    return _result(
        result_status,
        message,
        repository=repository,
        workflow_name=run.get("name") or f"Workflow {run.get('workflow_id', 'unknown')}",
        branch=run.get("head_branch") or "Unknown",
        run_status=status,
        conclusion=conclusion,
        run_url=run.get("html_url") or "",
        start_time=started or "Unknown",
        duration=_format_duration(started, ended),
    )


def render_actions_status(result: Mapping[str, Any], st_module: Any = None) -> None:
    """Render a compact user-facing status card without ever rendering credentials."""
    if st_module is None:
        import streamlit as st_module

    status = result.get("status")
    message = str(result.get("message", "GitHub Actions status unavailable."))
    if status == "healthy":
        st_module.success(f"✅ Healthy — {message}")
    elif status in {"warning", "not_configured"}:
        if status == "not_configured":
            st_module.info(f"🔵 {message}")
        else:
            st_module.warning(f"⚠ Warning — {message}")
    elif status == "info":
        st_module.info(f"🔵 {message}")
    else:
        st_module.error(f"❌ Error — {message}")

    if status in {"healthy", "warning", "error"} and result.get("workflow_name"):
        details = (
            ("Workflow", result.get("workflow_name")),
            ("Branch", result.get("branch")),
            ("Status", result.get("run_status")),
            ("Conclusion", result.get("conclusion")),
            ("Started", result.get("start_time")),
            ("Duration", result.get("duration")),
        )
        for offset in range(0, len(details), 3):
            for column, (label, value) in zip(
                st_module.columns(3),
                details[offset : offset + 3],
            ):
                column.metric(label, str(value or "Unknown"))
        url = result.get("run_url")
        if (
            isinstance(url, str)
            and url.startswith("https://")
            and urlsplit(url).hostname == "github.com"
        ):
            st_module.markdown(f"[Open latest workflow run]({url})")


def _format_duration(started: Any, ended: Any) -> str:
    if not started:
        return "Unknown"
    try:
        start_time = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
        end_time = (
            datetime.fromisoformat(str(ended).replace("Z", "+00:00"))
            if ended
            else datetime.now(timezone.utc)
        )
        seconds = max(0, int((end_time - start_time).total_seconds()))
    except (TypeError, ValueError):
        return "Unknown"
    minutes, remaining_seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m {remaining_seconds}s"


def _result(status: str, message: str, **details: Any) -> dict[str, Any]:
    return {"status": status, "message": message, **details}


def _valid_repository(repository: str) -> bool:
    if not _REPOSITORY_PATTERN.fullmatch(repository):
        return False
    _, name = repository.split("/", 1)
    return name not in {".", ".."} and not name.endswith(".")


def _is_rate_limited(response: requests.Response) -> bool:
    if response.status_code == 429 or response.headers.get("X-RateLimit-Remaining") == "0":
        return True
    try:
        payload = response.json()
    except ValueError:
        return False
    message = payload.get("message", "") if isinstance(payload, dict) else ""
    return "rate limit" in str(message).casefold()
