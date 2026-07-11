from __future__ import annotations


def test_startup_mutation_flags_default_to_safe_off(monkeypatch) -> None:
    from app.core.config import Settings

    monkeypatch.delenv("PRICING_SCHEDULER_ENABLED", raising=False)
    monkeypatch.delenv("AUTONOMOUS_AGENTS_ENABLED", raising=False)

    settings = Settings.from_env()

    assert settings.pricing_scheduler_enabled is False
    assert settings.autonomous_agents_enabled is False


def test_explicit_worker_opt_in_is_preserved(monkeypatch) -> None:
    from app.core.config import Settings

    monkeypatch.setenv("PRICING_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("AUTONOMOUS_AGENTS_ENABLED", "yes")

    settings = Settings.from_env()

    assert settings.pricing_scheduler_enabled is True
    assert settings.autonomous_agents_enabled is True


def test_cpu_seed_is_disabled_without_explicit_opt_in(monkeypatch) -> None:
    import app.main as main

    monkeypatch.delenv("CPU_SPECS_SEED_ON_START", raising=False)

    class FailingRepository:
        def import_cpu_specs(self, **_kwargs):
            raise AssertionError("CPU seeding should be disabled by default")

    main._seed_cpu_specs_safely(FailingRepository())


def test_cpu_seed_can_be_explicitly_enabled(monkeypatch) -> None:
    import app.main as main

    monkeypatch.setenv("CPU_SPECS_SEED_ON_START", "true")

    class Repository:
        called = False

        def import_cpu_specs(self, **_kwargs):
            self.called = True
            return type("Response", (), {"imported_count": 0, "skipped_count": 0})()

    repository = Repository()
    main._seed_cpu_specs_safely(repository)

    assert repository.called is True


def test_public_release_metadata_is_safe_and_has_contract_version(monkeypatch) -> None:
    from app.core.version import public_release_metadata

    monkeypatch.delenv("API_CONTRACT_VERSION", raising=False)
    metadata = public_release_metadata(
        service="backend",
        environment="production",
        release_info={"release": "0.1.0", "git_sha": None, "build_time": None},
    )

    assert metadata["service"] == "backend"
    assert metadata["release"] == "0.1.0"
    assert metadata["api_contract_version"] == "1"
    assert "neo4j_password" not in metadata
    assert "admin_api_key" not in metadata
