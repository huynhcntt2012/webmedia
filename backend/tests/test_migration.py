from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_single_linear_baseline():
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["0010_content_access"]
    assert scripts.get_revision("0009_payments").down_revision == "0008_reader"
    assert scripts.get_revision("0008_reader").down_revision == "0007_comic_admin"
    assert scripts.get_revision("0007_comic_admin").down_revision == "0006_playback"
    assert scripts.get_revision("0006_playback").down_revision == "0005_media_uploads"
    assert scripts.get_revision("0005_media_uploads").down_revision == "0004_admin_catalogue"
    assert scripts.get_revision("0004_admin_catalogue").down_revision == "0003_auth"
    assert scripts.get_revision("0003_auth").down_revision == "0002_domain"
    assert scripts.get_revision("0002_domain").down_revision == "0001_bootstrap"
    assert scripts.get_revision("0001_bootstrap").down_revision is None
