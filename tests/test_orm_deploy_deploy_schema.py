from kinglet import orm_deploy


def test_deploy_schema_rejects_invalid_database_name(monkeypatch):
    # Ensure generate_schema returns some SQL without needing real models
    monkeypatch.setattr(
        orm_deploy, "generate_schema", lambda _m: "CREATE TABLE x(id INTEGER);"
    )

    called = {"run": False}

    def fake_run(*args, **kwargs):
        called["run"] = True
        raise AssertionError(
            "subprocess.run should not be called for invalid database name"
        )

    monkeypatch.setattr(orm_deploy.subprocess, "run", fake_run)

    rc = orm_deploy.deploy_schema("tmp_models_mod3", database="bad name", env="local")
    assert rc == 1
    assert called["run"] is False


def test_deploy_schema_valid_invokes_wranger_locally(monkeypatch):
    # Provide minimal schema content
    monkeypatch.setattr(
        orm_deploy, "generate_schema", lambda _m: "CREATE TABLE x(id INTEGER);"
    )

    captured = {"cmd": None}

    class _Result:
        returncode = 0
        stderr = ""

    def fake_run(cmd, capture_output=True, text=True):
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(orm_deploy.subprocess, "run", fake_run)

    rc = orm_deploy.deploy_schema("tmp_models_mod_ok", database="DBTEST", env="local")
    assert rc == 0
    assert captured["cmd"][0:4] == ["npx", "wrangler", "d1", "execute"]
    assert "--local" in captured["cmd"]
    assert any(arg.startswith("--file=") for arg in captured["cmd"])
