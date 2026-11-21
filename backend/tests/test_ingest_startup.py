"""Startup keeps the existing database when the configured data file is missing."""

from pathlib import Path

from app import ingest
from app.config import settings


def test_missing_index_keeps_existing_database(monkeypatch, caplog):
    db_path = settings.path(settings.DUCKDB_PATH)
    assert db_path.exists()
    before = db_path.stat().st_mtime_ns
    monkeypatch.setattr(settings, "INDEX_GEOJSON", Path("../frontend/data/missing.geojson"))
    assert ingest.ensure_database() == db_path
    assert db_path.stat().st_mtime_ns == before  # not rebuilt
    assert "not found" in caplog.text
