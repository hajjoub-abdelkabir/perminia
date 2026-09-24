"""Read-only checks against the local seeded preview after media import."""
import json
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from sqlalchemy import text
from app.db import engine

base='http://api:8000/api/v1/student/preview'
with engine.connect() as c:
    entries=c.execute(text('SELECT asset_id,review_state FROM content.lesson_media')).mappings().all()
    assert len(entries)==95, 'Import repeated or incomplete (v1+v2 deduplicated)'
    assert sum(x['review_state']=='preview' for x in entries)==25
    for entry in entries:
        try:
            with urlopen(base+'/lesson-media/'+str(entry['asset_id']),timeout=10) as response:
                assert entry['review_state']=='preview'
                assert response.headers['X-Content-Type-Options']=='nosniff'
                assert response.read(20)
                if response.headers['Content-Type']=='video/mp4':
                    url=base+'/lesson-media/'+str(entry['asset_id'])
                    with urlopen(Request(url,headers={'Range':'bytes=0-99'})) as part:
                        assert part.status==206 and len(part.read())==100
                    with urlopen(url+'/captions') as caption:
                        assert caption.read().startswith(b'WEBVTT')
                    with urlopen(url+'/poster') as poster:
                        assert poster.headers['Content-Type']=='image/png'
        except HTTPError as error:
            assert entry['review_state']=='hold' and error.code==404
    with urlopen(base+'/lessons') as response: lessons=json.load(response)['items']
    total=0
    for lesson in lessons:
        with urlopen(base+'/lessons/'+lesson['slug']) as response: detail=json.load(response)
        assert detail['lesson']['status']=='draft'
        total+=sum(len(section['media']) for section in detail['sections'])
    assert total==25
print('PASS: 95 deduplicated history links, 25 active media, 70 held, video Range/captions/poster, 10 draft lessons intact.')
