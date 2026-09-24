"""Read-only audit of imported content, archive checksums and runtime privileges."""
import hashlib
import json
from pathlib import Path
from import_dataset import connect

def report():
    with connect() as c:
        counts={}
        for table in ['ingestion.content_sources','ingestion.import_batches','ingestion.source_records','ingestion.enrichment_candidates','content.questions','content.question_revisions','content.choice_groups','content.choices','content.answer_keys','content.media_assets','content.assessments','content.assessment_revisions','content.assessment_items']:
            counts[table]=c.execute('SELECT count(*) FROM '+table).fetchone()[0]
        counts['draft_questions']=c.execute("SELECT count(*) FROM content.question_revisions WHERE status='draft'").fetchone()[0]
        counts['published_questions']=c.execute('SELECT count(*) FROM content.published_question_prompts').fetchone()[0]
        counts['reconstructed_prompts']=c.execute('SELECT count(*) FROM content.question_revisions WHERE needs_prompt_reconstruction').fetchone()[0]
        counts['remote_audio']=c.execute("SELECT count(*) FROM content.media_assets WHERE availability='remote_only' AND mime='audio/mpeg'").fetchone()[0]
        counts['latest_questions_with_local_audio']=c.execute("WITH latest AS (SELECT DISTINCT ON(question_id) id FROM content.question_revisions ORDER BY question_id,revision_number DESC) SELECT count(*) FROM latest r JOIN content.question_media m ON m.revision_id=r.id AND m.role='audio' JOIN content.media_assets a ON a.id=m.asset_id WHERE a.availability='local' AND a.duration_seconds>0").fetchone()[0]
        counts['local_audio_assets']=c.execute("SELECT count(*) FROM content.media_assets WHERE mime='audio/mpeg' AND availability='local'").fetchone()[0]
        assets=c.execute("SELECT object_key,sha256 FROM content.media_assets WHERE availability='local'").fetchall()
        for key,expected in assets:
            p=(Path('/content')/key).resolve()
            if not p.is_relative_to(Path('/content')): raise AssertionError('Asset outside content volume')
            if hashlib.sha256(p.read_bytes()).hexdigest()!=expected: raise AssertionError('Media checksum mismatch')
        counts['verified_local_media']=len(assets)
        counts['schema_tables']=c.execute("SELECT count(*) FROM pg_tables WHERE schemaname IN ('content','ingestion','identity','learning','intelligence')").fetchone()[0]
        role=c.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname='sya9a_student_runtime'").fetchone()
        assert role==(False,False)
        assert not c.execute("SELECT has_table_privilege('sya9a_student_runtime','content.answer_keys','SELECT')").fetchone()[0]
        print(json.dumps({'counts':counts,'runtime_superuser':False,'runtime_bypassrls':False,'runtime_can_read_answer_keys':False},ensure_ascii=False,indent=2))
if __name__=='__main__': report()
