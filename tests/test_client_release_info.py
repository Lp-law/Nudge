import json

from client.app import release_info


def test_release_info_loads_valid_source_of_truth() -> None:
    info = release_info.load_release_info()
    assert info.version
    assert info.channel in {"stable", "beta"}


def test_release_info_fallbacks_for_invalid_values(monkeypatch, tmp_path) -> None:
    version_path = tmp_path / "version.json"
    version_path.write_text(
        json.dumps(
            {
                "version": "not-semver",
                "channel": "preview",
                "release_metadata_url": "https://example.com/metadata.json",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(release_info, "VERSION_PATH", version_path)
    info = release_info.load_release_info()
    assert info.version == "0.0.0"
    assert info.channel == "stable"
    assert info.release_metadata_url == "https://example.com/metadata.json"
