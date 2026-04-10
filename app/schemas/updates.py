from pydantic import BaseModel, Field


class UpdateCheckResponse(BaseModel):
    update_available: bool
    version: str = Field(default="")
    download_url: str = Field(default="")
    release_notes: str = Field(default="")
    mandatory: bool = Field(default=False)
