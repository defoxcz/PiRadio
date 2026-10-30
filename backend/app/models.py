import re
from urllib.parse import urlparse, parse_qs
from pydantic import BaseModel, Field, field_validator


def youtube_url(value: str) -> str:
    u = urlparse(value)
    if u.scheme != 'https' or u.username or u.password or u.port or u.fragment:
        raise ValueError('Použijte HTTPS odkaz na YouTube video nebo živé vysílání.')
    host = u.hostname
    video = None
    if host in {'youtube.com', 'www.youtube.com', 'm.youtube.com'}:
        if u.path == '/watch':
            video = parse_qs(u.query).get('v', [''])[0]
        elif u.path.startswith('/live/'):
            video = u.path.removeprefix('/live/')
    elif host == 'youtu.be':
        video = u.path.lstrip('/')
    if not video or not re.fullmatch(r'[A-Za-z0-9_-]{11}', video):
        raise ValueError('Vložte přímý odkaz na YouTube video (11 znaků ID).')
    return f'https://www.youtube.com/watch?v={video}'


class StationInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(max_length=2048)
    image: str = Field(default='', max_length=2048)
    favorite: bool = False
    live: bool = True

    @field_validator('name')
    @classmethod
    def name_valid(cls, v):
        if not v.strip():
            raise ValueError('Název nesmí být prázdný.')
        return v.strip()

    @field_validator('url')
    @classmethod
    def url_valid(cls, v):
        return youtube_url(v)

    @field_validator('image')
    @classmethod
    def image_valid(cls, v):
        if not v or re.fullmatch(r'/media/[a-f0-9]{32}\.jpg', v):
            return v
        u = urlparse(v)
        if u.scheme != 'https' or not u.hostname or u.username or u.password:
            raise ValueError('Obrázek musí být nahraný soubor nebo HTTPS adresa.')
        return v


class Volume(BaseModel):
    volume: int = Field(ge=0, le=100, strict=True)


class Play(BaseModel):
    station_id: str


class Settings(BaseModel):
    default_volume: int = Field(default=45, ge=0, le=100)
    audio_device: str = Field(default='auto', min_length=1, max_length=200)
    auto_recover: bool = True
    autoplay: bool = False


class YouTubePlay(BaseModel):
    live: bool = False
    video_id: str = Field(pattern=r'^[A-Za-z0-9_-]{11}$')
    title: str = Field(default='Video YouTube', min_length=1, max_length=100)
