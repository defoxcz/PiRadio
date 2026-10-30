"""YouTube Data API search. API credentials never leave the backend."""
import asyncio
import html
import re
import time
from collections import OrderedDict
import httpx
from fastapi import HTTPException


class YouTubeSearch:
    def __init__(self, key, transport=None):
        self.key = key
        self.transport = transport
        self.cache = OrderedDict()
        self.lock = asyncio.Lock()

    async def search(self, query, live=False, page=''):
        query = query.strip()
        if not query:
            raise HTTPException(422, 'Zadejte hledaný text.')
        if not self.key:
            raise HTTPException(503, 'Vyhledávání YouTube není nastavené. Na serveru doplňte PIRADIO_YOUTUBE_API_KEY a restartujte službu.')
        cache_key = (query, live, page)
        async with self.lock:
            cached = self.cache.get(cache_key)
            if cached and cached[0] > time.monotonic():
                return cached[1]
            params = {'part': 'snippet', 'type': 'video', 'q': query, 'maxResults': 12, 'relevanceLanguage': 'cs'}
            if live:
                params['eventType'] = 'live'
            if page:
                params['pageToken'] = page
            try:
                async with httpx.AsyncClient(timeout=8, follow_redirects=False, transport=self.transport) as client:
                    response = await client.get('https://www.googleapis.com/youtube/v3/search', params=params, headers={'X-Goog-Api-Key': self.key})
                if response.status_code == 403:
                    raise HTTPException(503, 'YouTube vyhledávání odmítl. Zkontrolujte API klíč, povolení YouTube Data API v3 a dostupnou kvótu.')
                if response.status_code == 400:
                    raise HTTPException(422, 'YouTube odmítl hledání nebo stránkování. Spusťte nové hledání.')
                if response.status_code != 200 or len(response.content) > 2_000_000:
                    raise HTTPException(502, 'YouTube vyhledávání je dočasně nedostupné.')
                data = response.json()
                items = []
                for item in data.get('items', []):
                    video = item.get('id', {}).get('videoId', '')
                    snippet = item.get('snippet', {})
                    if not isinstance(video, str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}', video):
                        continue
                    items.append({'video_id': video, 'title': html.unescape(str(snippet.get('title', 'Video YouTube')))[:100],
                                  'channel': html.unescape(str(snippet.get('channelTitle', '')))[:200],
                                  'live': snippet.get('liveBroadcastContent') == 'live',
                                  'url': f'https://www.youtube.com/watch?v={video}',
                                  'image': f'https://i.ytimg.com/vi/{video}/hqdefault.jpg'})
                page = data.get('nextPageToken')
                result = {'items': items, 'next_page': page if isinstance(page, str) and re.fullmatch(r'[A-Za-z0-9_=-]{1,256}', page) else None}
            except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                raise HTTPException(502, 'YouTube vyhledávání se nepodařilo načíst.') from None
            self.cache[cache_key] = (time.monotonic() + 120, result)
            self.cache.move_to_end(cache_key)
            while len(self.cache) > 64:
                self.cache.popitem(last=False)
            return result
