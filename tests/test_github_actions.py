import json

import requests

from services.github_actions import (
    get_github_repository,
    get_github_token,
    get_latest_actions_run,
    load_config,
    render_actions_status,
    save_github_configuration,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self.ok = 200 <= status_code < 400
        self._payload = payload if payload is not None else {"workflow_runs": []}
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse()
        self.error = error
        self.calls = []

    def get(self, url, *, headers, timeout):
        self.calls.append((url, headers, timeout))
        if self.error:
            raise self.error
        return self.response


def test_load_config_uses_env_then_dotenv_then_settings_then_defaults(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"github_repository": "json/repo", "github_token": "json-secret"}),
        encoding="utf-8",
    )
    env_path = tmp_path / ".env"
    env_path.write_text(
        "GITHUB_REPOSITORY=dotenv/repo\nGITHUB_TOKEN=dotenv-secret\n",
        encoding="utf-8",
    )

    config = load_config(
        settings_path=settings_path,
        env_path=env_path,
        environ={"GITHUB_REPOSITORY": "environment/repo"},
    )

    assert get_github_repository(config) == "environment/repo"
    assert get_github_token(config) == "dotenv-secret"

    fallback = load_config(
        settings_path=settings_path,
        env_path=tmp_path / "missing.env",
        environ={},
    )
    assert fallback == {
        "github_repository": "json/repo",
        "github_token": "json-secret",
    }


def test_missing_repository_returns_user_facing_info_without_request():
    session = FakeSession()

    result = get_latest_actions_run(
        {"github_repository": "", "github_token": "secret"},
        session=session,
    )

    assert result["status"] == "not_configured"
    assert result["message"] == "GitHub Actions monitoring not configured."
    assert session.calls == []


def test_invalid_repository_format_does_not_make_request():
    session = FakeSession()

    result = get_latest_actions_run(
        {"github_repository": "https://github.com/owner/repo", "github_token": ""},
        session=session,
    )

    assert result["status"] == "error"
    assert "owner/repository" in result["message"]
    assert session.calls == []


def test_public_repository_fetch_does_not_require_token():
    session = FakeSession(
        FakeResponse(
            payload={
                "workflow_runs": [
                    {
                        "name": "Daily IPO-RADAR",
                        "head_branch": "main",
                        "status": "completed",
                        "conclusion": "success",
                        "html_url": "https://github.com/owner/repo/actions/runs/99",
                        "run_started_at": "2026-10-31T10:00:00Z",
                        "updated_at": "2026-10-31T10:03:12Z",
                    }
                ]
            }
        )
    )

    result = get_latest_actions_run(
        {"github_repository": "owner/repo", "github_token": ""},
        session=session,
    )

    assert result["status"] == "healthy"
    assert result["workflow_name"] == "Daily IPO-RADAR"
    assert result["branch"] == "main"
    assert result["duration"] == "3m 12s"
    assert "Authorization" not in session.calls[0][1]


def test_invalid_token_and_private_repo_errors_are_actionable_and_sanitized():
    session = FakeSession(FakeResponse(status_code=401))
    result = get_latest_actions_run(
        {"github_repository": "owner/repo", "github_token": "do-not-display"},
        session=session,
    )

    assert result["status"] == "error"
    assert "valid" in result["message"]
    assert "do-not-display" not in str(result)
    assert session.calls[0][1]["Authorization"] == "Bearer do-not-display"

    private_repo = get_latest_actions_run(
        {"github_repository": "owner/private", "github_token": ""},
        session=FakeSession(FakeResponse(status_code=404)),
    )
    assert private_repo["status"] == "error"
    assert "Personal Access Token" in private_repo["message"]


def test_rate_limit_and_timeout_are_nonfatal():
    rate_limited = get_latest_actions_run(
        {"github_repository": "owner/repo", "github_token": ""},
        session=FakeSession(
            FakeResponse(status_code=403, headers={"X-RateLimit-Remaining": "0"})
        ),
    )
    timeout = get_latest_actions_run(
        {"github_repository": "owner/repo", "github_token": ""},
        session=FakeSession(error=requests.Timeout()),
    )

    assert rate_limited["status"] == "warning"
    assert "rate limit" in rate_limited["message"]
    assert timeout["status"] == "warning"
    assert "timed out" in timeout["message"]


def test_github_server_failure_and_malformed_response_are_reported():
    server_error = get_latest_actions_run(
        {"github_repository": "owner/repo", "github_token": ""},
        session=FakeSession(FakeResponse(status_code=503)),
    )
    invalid_payload = get_latest_actions_run(
        {"github_repository": "owner/repo", "github_token": ""},
        session=FakeSession(FakeResponse(payload={"unexpected": []})),
    )

    assert server_error["status"] == "warning"
    assert "HTTP 503" in server_error["message"]
    assert invalid_payload["status"] == "error"
    assert "unexpected" in invalid_payload["message"]


def test_saving_github_settings_updates_only_local_env(tmp_path):
    env_path = tmp_path / ".env"

    save_github_configuration("owner/repo", token="secret", env_path=env_path)
    contents = env_path.read_text(encoding="utf-8")

    assert "GITHUB_REPOSITORY=" in contents
    assert "GITHUB_TOKEN=" in contents
    assert "secret" in contents


def test_render_status_never_renders_config_or_token():
    class FakeColumn:
        def metric(self, label, value):
            output.append((label, value))

    class FakeStreamlit:
        def __getattr__(self, name):
            def record(*args, **kwargs):
                output.append((name, args, kwargs))

            return record

        def columns(self, count):
            return [FakeColumn() for _ in range(count)]

    output = []
    render_actions_status(
        {
            "status": "healthy",
            "message": "Latest GitHub Actions run loaded.",
            "repository": "owner/repo",
            "workflow_name": "Daily",
            "branch": "main",
            "run_status": "completed",
            "conclusion": "success",
            "start_time": "2026-10-31T10:00:00Z",
            "duration": "3m 12s",
            "run_url": "https://github.com/owner/repo/actions/runs/99",
            "token": "never-render-this",
        },
        st_module=FakeStreamlit(),
    )

    assert "never-render-this" not in str(output)


def test_unconfigured_status_renders_an_information_card():
    output = []

    class FakeStreamlit:
        def info(self, message):
            output.append(message)

    render_actions_status(
        {
            "status": "not_configured",
            "message": "GitHub Actions monitoring not configured.",
        },
        st_module=FakeStreamlit(),
    )

    assert output == ["🔵 GitHub Actions monitoring not configured."]
