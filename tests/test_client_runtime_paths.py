from pathlib import Path

from client.app import runtime_paths


def test_resource_path_points_to_repo_layout_when_not_frozen() -> None:
    icon_path = runtime_paths.resource_path("assets", "nudge.ico")
    guide_path = runtime_paths.resource_path("app", "user_guide_content.json")
    assert icon_path.exists()
    assert guide_path.exists()


def test_bundle_root_prefers_meipass_when_frozen(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(runtime_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime_paths.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert runtime_paths.bundle_root() == Path(tmp_path)
