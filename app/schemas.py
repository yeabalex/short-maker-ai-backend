from pydantic import BaseModel

class SubtitleRequest(BaseModel):
    url: str
    title: str
    lang: str = "en"

class DownloadRequest(BaseModel):
    url: str
    title: str

class ShortSubtitleRequest(BaseModel):
    subtitle_file: str
