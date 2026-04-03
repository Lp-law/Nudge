import json
import re
from dataclasses import dataclass

from .runtime_paths import resource_path

VERSION_PATH = resource_path("release", "version.json")
CHANNELS = {"stable", "beta"}
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    channel: str
    release_metadata_url: str

    @property
    def display_label(self) -> str:
        if self.channel == "stable":
            return self.version
        return f"{self.version} ({self.channel})"


def _coerce_version(raw: object) -> str:
    value = str(raw or "").strip()
    if SEMVER_PATTERN.match(value):
        return value
    return "0.0.0"


def _coerce_channel(raw: object) -> str:
    value = str(raw or "stable").strip().lower()
    if value in CHANNELS:
        return value
    return "stable"


def load_release_info() -> ReleaseInfo:
    try:
        raw = json.loads(VERSION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return ReleaseInfo(version="0.0.0", channel="stable", release_metadata_url="")

    return ReleaseInfo(
        version=_coerce_version(raw.get("version")),
        channel=_coerce_channel(raw.get("channel")),
        release_metadata_url=str(raw.get("release_metadata_url") or "").strip(),
    )
