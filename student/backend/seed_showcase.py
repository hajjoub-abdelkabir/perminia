"""Original synthetic fixtures, strictly confined to the isolated showcase database.

The publication records below attest only to these simple shape/color test fixtures.
They must never be used to approve any imported driving-law question.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
from uuid import uuid4

from app.auth import password_hash
from import_dataset import connect
from provision_school import create_school

SOURCE = 'perminia-original-synthetic-showcase-v1'


def seed(connection, media_root, account_path):
    if os.environ.get('PERMINIA_SYNTHETIC_SHOWCASE') != 'true':
        raise ValueError('Explicit synthetic-showcase mode required.')
    database = connection.execute('SELECT current_database()').fetchone()[0]
    if database != 'perminia_showcase' and not database.startswith('sya9a_student_test_auth_'):
        raise ValueError('Refusing to seed a development or production database.')
    connection.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (SOURCE,))
    found = connection.execute('SELECT id FROM ingestion.content_sources WHERE name=%s', (SOURCE,)).fetchone()
    if found:
        if not account_path.is_file():
            raise ValueError('Private account file missing. No passwords will be reset.')
        saved = json.loads(account_path.read_text(encoding='utf-8'))
        if saved.get('source') != SOURCE or len(saved.get('accounts', [])) != 6:
            raise ValueError('Showcase account manifest mismatch.')
        return {'status': 'already_seeded'}
    for table in ('identity.users', 'content.questions', 'content.lessons', 'ingestion.content_sources'):
        if connection.execute('SELECT EXISTS(SELECT 1 FROM '+table+')').fetchone()[0]:
            raise ValueError('Only an empty, freshly migrated showcase database may be seeded.')
    if account_path.exists():
        raise ValueError('Existing credential file found without matching DB. Refusing to overwrite it.')

    def one(statement, params=()):
        return connection.execute(statement, params).fetchone()[0]

    accounts = []
    schools = []
    for code, name in [('showcase-atlas', 'مدرسة أطلس — عرض اصطناعي'), ('showcase-rif', 'مدرسة الريف — عرض اصطناعي')]:
        tenant = create_school(connection, code, name)['school_id']
        members = {}
        for role, label in [('school_manager', 'مدير'), ('instructor', 'أستاذ'), ('student', 'متعلم')]:
            user = one('INSERT INTO identity.users(auth_subject) VALUES(%s) RETURNING id', (SOURCE+':'+code+':'+role,))
            member = one('INSERT INTO identity.memberships(tenant_id,user_id,role) VALUES(%s,%s,%s) RETURNING id', (tenant,user,role))
            password = secrets.token_urlsafe(20)
            email = f'{role}@{code}.example.test'
            connection.execute('INSERT INTO identity.local_accounts(membership_id,email,display_name,password_hash) VALUES(%s,%s,%s,%s)',
                               (member,email,label+' تجريبي',password_hash(password)))
            if role == 'student':
                connection.execute("INSERT INTO identity.learner_profiles(membership_id,tenant_id,category_id) VALUES(%s,%s,'B')", (member,tenant))
            accounts.append({'school':code, 'role':role, 'email':email, 'password':password})
            members[role] = member
        connection.execute('INSERT INTO identity.school_student_links(tenant_id,student_id,teacher_id,assigned_by) VALUES(%s,%s,%s,%s)',
                           (tenant,members['student'],members['instructor'],members['school_manager']))
        schools.append((tenant,members))

    source = one("INSERT INTO ingestion.content_sources(name,base_url,rights_status,rights_evidence_ref) VALUES(%s,'https://example.test','permitted','Original synthetic shapes and text in seed_showcase.py; not driving-law material') RETURNING id", (SOURCE,))
    batch = one("INSERT INTO ingestion.import_batches(source_id,input_sha256,importer_version,enrichment_script_sha256,archive_key,status) VALUES(%s,'synthetic-v1','showcase-v1','synthetic-v1','generated-by-seed_showcase.py','complete') RETURNING id", (source,))
    reviewer_user = one('INSERT INTO identity.users(auth_subject) VALUES(%s) RETURNING id', (SOURCE+':fixture-validation',))
    reviewer = one("INSERT INTO identity.memberships(tenant_id,user_id,role) VALUES(%s,%s,'reviewer') RETURNING id", (schools[0][0],reviewer_user))
    connection.execute("INSERT INTO content.topics(id,label) VALUES('showcase-observation','ملاحظة الأشكال — تجريبي')")
    concept = one("INSERT INTO content.concepts(topic_id,code,label) VALUES('showcase-observation','synthetic-observation','تمييز الأشكال — مثال تقني وليس مهارة سياقة') RETURNING id")
    series = one("INSERT INTO content.assessments(source_id,source_key,kind,title) VALUES(%s,'showcase','source_series','ملاحظة الأشكال — عرض تقني') RETURNING id", (source,))
    assessment = one("INSERT INTO content.assessment_revisions(assessment_id,revision_number,item_count,pool_manifest_hash) VALUES(%s,1,8,'synthetic-v1') RETURNING id", (series,))

    for n in range(8):
        blue_circle = n % 2 == 0
        prompt = 'شنو الشكل اللي باللون الأزرق فهاد الصورة؟ هادا تمرين اصطناعي لعرض التطبيق فقط.'
        explanation = 'الدائرة زرقاء والمربع أصفر.' if blue_circle else 'المربع أزرق والدائرة صفراء.'
        record = one("INSERT INTO ingestion.source_records(batch_id,source_key,source_series_key,source_position,source_url,raw_payload,raw_sha256) VALUES(%s,%s,'showcase',%s,'https://example.test','{}','synthetic-v1') RETURNING id", (batch,f'q-{n}',n+1))
        question = one("INSERT INTO content.questions(source_id,source_key,category_id) VALUES(%s,%s,'B') RETURNING id", (source,f'q-{n}'))
        digest = hashlib.sha256((str(question)+prompt+explanation).encode()).hexdigest()
        revision = one("INSERT INTO content.question_revisions(question_id,revision_number,response_type,content_hash,source_record_id) VALUES(%s,1,'single',%s,%s) RETURNING id", (question,digest,record))
        connection.execute("INSERT INTO content.question_localizations VALUES(%s,'ary-MA',%s,%s)", (revision,prompt,explanation))
        group = one('INSERT INTO content.choice_groups(revision_id,position,selection_min,selection_max,rule_reviewed) VALUES(%s,1,1,1,true) RETURNING id', (revision,))
        for number, label in [(1,'الدائرة'), (2,'المربع')]:
            choice = one('INSERT INTO content.choices(revision_id,group_id,source_choice_number,display_position) VALUES(%s,%s,%s,%s) RETURNING id', (revision,group,number,number))
            connection.execute("INSERT INTO content.choice_localizations VALUES(%s,'ary-MA',%s)", (choice,label))
            if number == (1 if blue_circle else 2):
                connection.execute('INSERT INTO content.answer_keys VALUES(%s,%s)', (revision,choice))
        # Alternating families intentionally have different positions/size, purely for UI testing.
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400" viewBox="0 0 800 400"><rect width="800" height="400" rx="32" fill="#edf7fb"/><circle cx="{210+n*8}" cy="200" r="80" fill="{"#0a5d7a" if blue_circle else "#f5a623"}"/><rect x="510" y="120" width="160" height="160" rx="12" fill="{"#f5a623" if blue_circle else "#0a5d7a"}"/></svg>'.encode()
        key = f'showcase/shapes-{n}.svg'
        path = media_root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(svg)
        asset = one("INSERT INTO content.media_assets(source_id,sha256,object_key,original_url,mime,byte_size,availability) VALUES(%s,%s,%s,%s,'image/svg+xml',%s,'local') RETURNING id", (source,hashlib.sha256(svg).hexdigest(),key,'https://example.test/'+key,len(svg)))
        connection.execute("INSERT INTO content.question_media(revision_id,asset_id,role,locale,position,reveal_stage) VALUES(%s,%s,'original_card','ary-MA',1,'question')", (revision,asset))
        connection.execute("INSERT INTO content.question_concepts(revision_id,concept_id,weight,approval_status) VALUES(%s,%s,1,'approved')", (revision,concept))
        for aspect in ('prompt','answer_key','explanation','media','groups','rights'):
            connection.execute("INSERT INTO content.content_reviews(revision_id,reviewer_id,aspect,decision,content_hash,reason) VALUES(%s,%s,%s,'approved',%s,'SYNTHETIC SOFTWARE FIXTURE ONLY: shape/color truth specified in source. No driving-law accreditation.')", (revision,reviewer,aspect,digest))
        connection.execute("UPDATE content.question_revisions SET status='published' WHERE id=%s", (revision,))
        connection.execute('INSERT INTO content.assessment_items VALUES(%s,%s,%s,%s)', (assessment,n+1,revision,question))

    for n, title in enumerate(['كيفاش تجرّب التعلم', 'كيفاش تجرّب المتابعة'], 1):
        lesson, rev = uuid4(), uuid4()
        record = one("INSERT INTO ingestion.source_records(batch_id,source_key,source_series_key,source_position,source_url,raw_payload,raw_sha256) VALUES(%s,%s,'showcase-lessons',%s,'https://example.test','{}','synthetic-v1') RETURNING id", (batch,f'lesson-{n}',n))
        connection.execute('INSERT INTO content.lessons(id,source_id,source_key,slug,position) VALUES(%s,%s,%s,%s,%s)', (lesson,source,f'lesson-{n}',f'showcase-{n}',n))
        connection.execute("INSERT INTO content.lesson_revisions(id,lesson_id,source_record_id,content_hash,title_ar,summary_darija,common_mistakes_darija,coach_tip) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                           (rev,lesson,record,f'synthetic-lesson-{n}',title,'هاد الدرس الأصلي غير باش تجرّب القراءة والحفظ، ماشي درس فقانون السير.','قرا الفكرة وكمل الخطوة باش يبان التقدم.','جرب تبدل الحساب وتشوف المهمة من جهة الأستاذ.'))
        for pos, (heading, body) in enumerate([
            ('اكتشاف الفكرة','شوف الفرق بين الدائرة والمربع. فهاد العرض كنستعملو أشكال بسيطة باش نبيّنو كيفاش كتخدم رحلة التعلم بلا محتوى قانوني غير معتمد.'),
            ('الحفظ والمتابعة','كمل القراءة وعلّم الفقرة كمقروءة. رجع للصفحة وغادي تلقى التقدم محفوظ فقاعدة البيانات؛ القراءة بوحدها ماشي إتقان.'),
            ('التدريب','جرّب سلسلة الأشكال، أكد الأجوبة وشوف النتيجة. من بعد افتح تدريباتي المحفوظة باش تشوف كيفاش كيتحسب الدليل الاصطناعي.')], 1):
            connection.execute('INSERT INTO content.lesson_sections VALUES(%s,%s,%s,%s)', (rev,pos,heading,body))
        if n == 1:
            for tenant, members in schools:
                connection.execute('INSERT INTO learning.lesson_section_progress(tenant_id,membership_id,revision_id,section_position,completed) VALUES(%s,%s,%s,1,true)', (tenant,members['student'],rev))
                connection.execute("INSERT INTO learning.school_tasks(tenant_id,student_id,assigned_by,kind,target_id,title,note) VALUES(%s,%s,%s,'lesson',%s,%s,%s)",
                                   (tenant,members['student'],members['instructor'],rev,title,'مهمة اصطناعية: كمل القراءة وارجع أكد الإنجاز.'))

    account_path.parent.mkdir(parents=True, exist_ok=True)
    with account_path.open('x', encoding='utf-8') as f:
        json.dump({'source':SOURCE,'accounts':accounts}, f, ensure_ascii=False, indent=2)
    account_path.chmod(0o600)
    return {'status':'created','schools':2,'accounts':6,'synthetic_questions':8,'synthetic_lessons':2}


if __name__ == '__main__':
    with connect() as connection:
        result = seed(connection, Path('/content'), Path('/showcase/accounts.json'))
    print(json.dumps(result))
