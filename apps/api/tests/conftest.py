import pytest


SLOW_TEST_TOKENS = (
    "run_", "map_", "approval", "retry", "recovery", "cache",
    "provider", "skill", "reference", "project_assets", "state_patch",
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "slow: integration tests that exercise asynchronous workflow execution",
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark network-like workflow integration tests so fast feedback stays fast."""
    for item in items:
        if any(token in item.name.lower() for token in SLOW_TEST_TOKENS):
            item.add_marker(pytest.mark.slow)
