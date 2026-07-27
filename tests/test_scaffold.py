from pathlib import Path


def test_phase0_scaffold_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]

    assert (root / "ARCHITECTURE.md").exists()
    assert (root / "SCOPE.md").exists()
    assert (root / "db" / "alembic.ini").exists()
    assert (root / "frontend" / "package.json").exists()
