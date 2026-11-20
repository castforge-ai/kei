"""The seats do not get other services' credentials; their own and Kei's settings pass."""
from kei.seats import seat_env, secret_name


def test_other_services_credentials_stay_out(monkeypatch):
    for k in ("GH_TOKEN", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "STRIPE_SECRET_KEY", "DATABASE_URL", "MY_API_KEY",
              "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.setenv(k, "x")
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CLAUDE_CODE_USE_BEDROCK", "KEI_CHARACTER", "HOME", "TEMP"):
        monkeypatch.setenv(k, "y")
    env = {k.upper(): v for k, v in seat_env().items()}
    assert not {"GH_TOKEN", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "STRIPE_SECRET_KEY", "DATABASE_URL",
                "MY_API_KEY", "SUPABASE_SERVICE_ROLE_KEY"} & set(env)
    assert {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CLAUDE_CODE_USE_BEDROCK", "KEI_CHARACTER", "TEMP"} <= set(env)
    assert "PATH" in env


def test_ordinary_names_are_not_secrets():
    assert not secret_name("PATH") and not secret_name("PATHEXT") and not secret_name("USERPROFILE")
