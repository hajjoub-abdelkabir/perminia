import hashlib
import json
from pathlib import Path
from import_dataset import connect
from audio_metadata import probe_audio
source=Path('/imports')
raw={q['key']:q for q in json.loads((source/'questions.json').read_text())}
with connect() as c:
    rows=c.execute("""WITH latest AS (SELECT DISTINCT ON(question_id) id,question_id FROM content.question_revisions ORDER BY question_id,revision_number DESC)
    SELECT q.source_key,m.asset_id,a.object_key,a.sha256,a.duration_seconds,a.audio_sample_rate,a.audio_channels,m.reveal_stage
    FROM latest r JOIN content.questions q ON q.id=r.question_id
    JOIN content.question_media m ON m.revision_id=r.id AND m.role='audio'
    JOIN content.media_assets a ON a.id=m.asset_id WHERE a.availability='local' ORDER BY q.source_key""").fetchall()
    assert len(rows)==400 and {r[0] for r in rows}==set(raw)
    for key,asset,object_key,sha,duration,rate,channels,stage in rows:
        original=(source/raw[key]['localAudioPath']).read_bytes()
        stored=(Path('/content')/object_key).read_bytes()
        assert hashlib.sha256(original).hexdigest()==sha==hashlib.sha256(stored).hexdigest()
        assert float(duration)>0 and rate>0 and channels in (1,2)
    result={'question_audio_links':len(rows),'distinct_audio_assets':len({r[1] for r in rows}),'all_question_mappings_and_sha256_verified':True,'min_duration_seconds':float(min(r[4] for r in rows)),'max_duration_seconds':float(max(r[4] for r in rows)),'total_duration_seconds_by_question':float(sum(r[4] for r in rows)),'withheld_pending_review':sum(r[7]=='withheld' for r in rows),'migration':c.execute('SELECT version_num FROM alembic_version').fetchone()[0]}
    print(json.dumps(result,indent=2))
