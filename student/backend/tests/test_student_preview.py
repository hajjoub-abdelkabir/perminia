"""Real HTTP contract checks against the running local student API/proxy."""
import json
import os
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from uuid import uuid4

BASE = os.environ.get('STUDENT_TEST_URL', 'http://127.0.0.1:8000')
PREFIX = '/api/v1/student/preview'


def get(path, headers=None):
    return urlopen(Request(BASE + path, headers=headers or {}), timeout=15)


class StudentPreviewTests(unittest.TestCase):
    def test_all_series_and_media(self):
        with get(PREFIX+'/series') as response:
            catalog=json.load(response)
        self.assertEqual(catalog['mode'], 'local_preview')
        self.assertEqual(len(catalog['items']), 10)
        counts={'questions':0, 'choices':0, 'images':0, 'audio':0}
        media_urls=set()
        for series in catalog['items']:
            with get(PREFIX+'/series/'+series['id']) as response:
                payload=json.load(response)
            questions=payload['questions']
            self.assertEqual(len(questions), series['item_count'])
            self.assertEqual([q['position'] for q in questions],list(range(1,41)))
            for q in questions:
                self.assertEqual(set(q), {'position','revision_id','response_type','prompt','choices','groups','media'})
                numbers=[c['number'] for c in q['choices']]
                self.assertEqual(numbers, sorted(numbers))
                for c in q['choices']:
                    self.assertEqual(set(c), {'id','number','text','group_id'})
                self.assertEqual({m['role'] for m in q['media']}, {'original_card','audio'})
                counts['questions']+=1
                counts['choices']+=len(q['choices'])
                for media in q['media']:
                    counts['audio' if media['role']=='audio' else 'images']+=1
                    media_urls.add(media['url'])
        for url in media_urls:
            with get(url, {'Range':'bytes=0-15'}) as response:
                self.assertEqual(response.status,206)
                self.assertEqual(len(response.read()),16)
                self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
        self.assertEqual(counts, {'questions':400,'choices':1005,'images':400,'audio':400})
        print('Verified counts:',counts,'unique served assets:',len(media_urls))

    def test_invalid_and_missing_ids(self):
        for suffix,code in [('/series/nope',422),('/series/'+str(uuid4()),404),('/media/'+str(uuid4()),404),('/media/not-a-path',422)]:
            with self.assertRaises(HTTPError) as result:
                get(PREFIX+suffix)
            self.assertEqual(result.exception.code,code)

    def test_preview_flag_defaults_closed(self):
        from app.student import preview_enabled
        from fastapi import HTTPException
        previous=os.environ.pop('STUDENT_PREVIEW_ENABLED',None)
        try:
            with self.assertRaises(HTTPException) as result:
                preview_enabled()
            self.assertEqual(result.exception.status_code,404)
        finally:
            if previous is not None:
                os.environ['STUDENT_PREVIEW_ENABLED']=previous

    def test_runtime_cannot_read_answers(self):
        from app.db import engine
        from sqlalchemy import text
        from sqlalchemy.exc import DBAPIError
        with engine.connect() as connection:
            for table in ('content.answer_keys','ingestion.source_records'):
                with self.assertRaises(DBAPIError):
                    connection.execute(text('SELECT * FROM '+table+' LIMIT 1'))
                connection.rollback()

if __name__=='__main__':
    unittest.main()
