import re

from fastapi import APIRouter, Query

from app.core.config import get_settings
from app.schemas.updates import UpdateCheckResponse


router = APIRouter(prefix="/updates", tags=["updates"])

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-[0-9A-Za-z.-]+)?$")


def _parse_semver(version: str) -> tuple[int, int, int] | None:
    m = _SEMVER_RE.match((version or "").strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


@router.get("/check", response_model=UpdateCheckResponse)
async def check_for_update(
    version: str = Query(default="0.0.0", description="Current client version"),
    channel: str = Query(default="stable", description="Release channel"),
) -> UpdateCheckResponse:
    settings = get_settings()

    latest_raw = (settings.latest_client_version or "").strip()
    download_url = (settings.client_download_url or "").strip()
    mandatory = bool(settings.update_mandatory)
    release_notes = (settings.update_release_notes or "").strip()

    latest_parsed = _parse_semver(latest_raw)
    current_parsed = _parse_semver(version)

    if not latest_parsed or not current_parsed:
        return UpdateCheckResponse(update_available=False)

    if latest_parsed <= current_parsed:
        return UpdateCheckResponse(update_available=False)

    return UpdateCheckResponse(
        update_available=True,
        version=latest_raw,
        download_url=download_url,
        release_notes=release_notes,
        mandatory=mandatory,
    )
