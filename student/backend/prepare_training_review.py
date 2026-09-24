"""Export a private review packet. This never approves or publishes source content."""
import argparse
import json
from pathlib import Path
from import_dataset import connect

def fetch_packet(c, series_id=None):
    c.row_factory=__import__('psycopg').rows.dict_row
    series=c.execute("SELECT * FROM content.preview_series WHERE (%s::uuid IS NULL OR id=%s::uuid) ORDER BY source_key LIMIT 1", (series_id,series_id)).fetchone()
    if not series:raise ValueError('Import the question bank first')
    items=c.execute('''SELECT p.*,r.content_hash,r.needs_prompt_reconstruction,r.status,s.base_url,s.rights_status,
      q.source_key,q.duplicate_family_id,l.explanation
      FROM content.preview_questions p JOIN content.question_revisions r ON r.id=p.revision_id
      JOIN content.questions q ON q.id=r.question_id JOIN ingestion.content_sources s ON s.id=q.source_id
      JOIN content.question_localizations l ON l.revision_id=r.id AND l.locale='ary-MA'
      WHERE p.series_id=%s ORDER BY p.position''',(series['id'],)).fetchall()
    for item in items:
        rid=item['revision_id']
        item['source_answer_numbers']=[r['source_choice_number'] for r in c.execute('SELECT ch.source_choice_number FROM content.answer_keys k JOIN content.choices ch ON ch.id=k.choice_id WHERE k.revision_id=%s ORDER BY ch.source_choice_number',(rid,)).fetchall()]
        item['media']=c.execute('''SELECT m.role,m.asset_id,a.sha256,a.object_key,m.reveal_stage,m.embedded_choice_numbers
          FROM content.question_media m JOIN content.media_assets a ON a.id=m.asset_id WHERE m.revision_id=%s ORDER BY m.role,m.position''',(rid,)).fetchall()
        item['group_rules']=c.execute('SELECT position,selection_min,selection_max,rule_reviewed FROM content.choice_groups WHERE revision_id=%s ORDER BY position',(rid,)).fetchall()
        item['review']={'decision':'pending','reviewer':None,'verified_explanation':None,'concept_codes':[],
          'misconceptions':[],'family_review':None,'evidence_refs':[],'rights_evidence_ref':None}
    counts=c.execute("SELECT (SELECT count(*) FROM content.preview_questions) AS preview_questions,(SELECT count(*) FROM content.content_reviews WHERE decision='approved' AND NOT superseded) AS approved_reviews,(SELECT count(*) FROM content.preview_questions p JOIN content.question_revisions r ON r.id=p.revision_id WHERE r.needs_prompt_reconstruction) AS missing_prompts,(SELECT count(*) FROM content.concepts) AS concepts").fetchone()
    return {'purpose':'private editorial review, not an approval','series':series,'audit':counts,'items':items}

def run(output):
    output.mkdir(parents=True,exist_ok=True)
    with connect() as c:
        packet=fetch_packet(c)
    series,counts,items=packet['series'],packet['audit'],packet['items']
    (output/'series-01-review.json').write_text(json.dumps(packet,default=str,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# حزمة مراجعة السلسلة الأولى','',
      'هذه نسخة خاصة للمراجعة؛ مفاتيح المصدر والتفسيرات ليست معتمدة. لا تُنسخ إلى ملفات الواجهة العامة. لم ننشئ توقيع مراجع أو إذناً بالاستعمال.',
      '',f"الحالة: {counts['preview_questions']} سؤال معاينة، {counts['missing_prompts']} نصاً ناقصاً، {counts['approved_reviews']} مراجعة مصادق عليها، {counts['concepts']} مفهوم مسجل.",
      '', 'الخطوات: التحقق من الصورة والصوت والنص؛ مراجعة حدود اختيار الأجوبة والمفتاح والشرح؛ ربط مفهوم محدد وخطأ شائع؛ تحديد العائلات المتشابهة؛ إرفاق مصدر داعم وإذن استعمال. تصحيح المحتوى المنشور يتطلب نسخة جديدة. عتبات الإتقان ليست معيار امتحان رسمياً.',
      '', '## الأسئلة المرشحة','']
    for i in items:
        lines += [f"### {i['position']}. {i['source_key']}",'',i['prompt'] or '**النص ناقص: يستلزم تفريغ الصوت وفحص الصورة.**','',
          'مفتاح المصدر غير المعتمد: '+', '.join(map(str,i['source_answer_numbers'])),
          'حالة حقوق المصدر: '+i['rights_status'],
          'الشرح المورّد غير المعتمد: '+(i['explanation'] or 'غير متوفر'),'']
        for m in i['media']:
            if m['role'] in ('original_card','audio'):lines += [f"[{m['role']}](http://localhost:8001/api/v1/student/preview/media/{m['asset_id']})"]
        lines+=['','قرار المراجع: **معلّق**. التفاصيل والبصمة والاختيارات في ملف JSON.','']
    (output/'REVIEW_PACKET.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'questions':len(items),'missing_prompts_in_packet':sum(i['needs_prompt_reconstruction'] for i in items),'audit':counts,'published':False}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();run(args.output)
