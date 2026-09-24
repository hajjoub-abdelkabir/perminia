"""Curated draft annotations and a private, offline editorial workbench.

No generated assertion in this file is a signed review or a legal answer key.
"""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

VERSION = 'training-editorial-v1'
# One primary concept per question for this first editorial pass. More granular
# links can be proposed after the scene/audio review; weights are not inferred.
CONCEPTS = [
    ('overtaking.checks', 'overtaking', 'شروط بدء التجاوز'),
    ('priority.left_turn', 'priority', 'الأسبقية عند الانعطاف يساراً'),
    ('parking.side', 'parking', 'جهة التوقف في طريق باتجاهين'),
    ('priority.signs', 'priority', 'الأسبقية حسب التشوير'),
    ('lighting.glare', 'lighting', 'تجنب الإبهار بالأضواء'),
    ('speed.context', 'speed_distance', 'اختيار السرعة حسب التشوير والسياق'),
    ('maneuvers.descent', 'maneuvers', 'التحكم في المركبة أثناء النزول'),
    ('priority.right', 'priority', 'الأسبقية لليمين'),
    ('priority.pedestrians', 'priority', 'التعامل مع ممر الراجلين'),
    ('signs.lanes', 'signs', 'الأسهم والخطوط واختيار المسلك'),
    ('highway.identify', 'highway', 'تمييز الطريق السيار والطريق السريع'),
    ('priority.narrow', 'priority', 'التقابل في ممر ضيق'),
    ('priority.exit', 'priority', 'الخروج إلى الطريق من مكان جانبي'),
    ('overtaking.markings', 'overtaking', 'التجاوز حسب الخطوط الأرضية'),
    ('overtaking.slope', 'overtaking', 'التقابل في المنحدرات'),
    ('safety.horn', 'safety_emergency', 'التنبيه عند وجود خطر'),
    ('lighting.fog', 'lighting', 'استعمال الأضواء في الضباب'),
    ('safety.tyres', 'safety_emergency', 'ضغط العجلات واستهلاك الوقود'),
    ('parking.signs', 'parking', 'نطاق منع التوقف'),
    ('highway.merge', 'highway', 'الاندماج وتقدير المسافة والسرعة'),
    ('distance.weather', 'speed_distance', 'مسافة الأمان وضعف الرؤية'),
    ('parking.reserved', 'parking', 'الأماكن المحجوزة للتوقف'),
    ('signs.vehicle_scope', 'signs', 'العلامات الخاصة بفئات المركبات'),
    ('safety.substances', 'safety_emergency', 'تأثير الكحول والأدوية على السياقة'),
    ('overtaking.right', 'overtaking', 'تجاوز مركبة من جهة اليمين'),
    ('signs.narrowing', 'signs', 'قراءة علامة تضيق الطريق'),
]
ASSIGNMENTS = [
    0,1,2,3,4,5,6,7,5,7,8,9,10,0,11,12,13,14,3,15,
    0,16,17,18,19,20,0,7,13,21,5,22,4,23,16,8,24,22,25,19,
]
FLAGS = {
    1: 'راجع شروط التجاوز كاملة؛ الشرح كيختزل القرار فاتباع سيارة أخرى.',
    4: 'خاص تمييز حق الأسبقية حسب العلامة عن حجم الطريق.',
    6: 'خاص سند تنظيمي وحديث للسرعة؛ علامة دخول المدينة بوحدها ما كافياش لهذا الشرح العددي.',
    7: 'أولوية عالية: الشرح على الفرامل والنزول محتاج تصحيح تقني وتحديد السياق قبل الاستعمال.',
    9: 'أولوية عالية: الشرح كيعمم 100 كلم/س انطلاقاً من نوع الطريق؛ خاص مراجعة العلامات والنص التنظيمي.',
    11: 'الصورة تفحصات: 1 نوقف، 2 نكمل طريقي. ما فيهاش سؤال مستقل؛ الصياغة المقترحة تحريرية والصوت باقي خاصو مراجعة.',
    15: 'أولوية عالية: عبارة «اللول كيدوز» خاصها تحقق من عرض القنطرة والتشوير والسياق.',
    18: 'راجع شروط التقابل فالمنحدر والاستثناءات؛ ما نعمموش الشرح على أي مركبة.',
    25: 'أولوية عالية: الشرح كيبرر التسارع بعدد السيارات؛ خاص فحص الموقف والاندماج والمسافة بلا تحويله لقاعدة عامة.',
    31: 'انتهاء منع خاص ما كيعطيش بوحدو قيمة سرعة جديدة؛ خاص تدقيق الاستنتاج العددي.',
    33: 'راجع الصورة والصوت لتحديد شنو كيعني استعمال ضو التقابل لمدة قصيرة هنا.',
    35: 'خاص التفريق بين أضواء الضباب الأمامية والخلفية وحالة الرؤية فالصورة.',
    36: 'الصورة تفحصات: 1 نكمل طريقي، 2 نوقف. ترتيب مخالف للسؤال 11؛ ما نبدلوش أرقام الاختيارات.',
    40: 'أولوية عالية: ما نحوّلوش حق الأسبقية لتوجيه مطلق بعدم تخفيف السرعة. خاص شرح مرتبط بالخطر والاندماج.',
}
HIGH = {7,9,15,25,31,40}
SOURCES = [
    {'id':'narsa-speed', 'url':'https://www.narsa-securiteroutiere.ma/fr/la-vitesse-excessive/',
     'checked_at':'2026-09-15', 'scope':'مرجع توعوي للسرعة حسب السياق؛ لا يحسم وحده مفاتيح الأسئلة ولا يعوض النص التنظيمي.'},
    {'id':'narsa-fog', 'url':'https://www.narsa-securiteroutiere.ma/fr/nos-tips-pour-une-conduite-sure-par-temps-de-brouillard/',
     'checked_at':'2026-09-15', 'scope':'مرجع توعوي للمسافة والرؤية في الضباب؛ لا يثبت حالة المشهد المصور.'},
    {'id':'narsa-lights', 'url':'https://www.narsa-securiteroutiere.ma/fr/quels-feux-pour-quel-usage/',
     'checked_at':'2026-09-15', 'scope':'مدخل لمراجعة أنواع الأضواء؛ التفاصيل العددية تحتاج سنداً تنظيمياً مستقلاً.'},
]

def fingerprint(item):
    # Includes text, choices, key, media hashes and group bounds, not just the
    # importer hash (which is not refreshed by every subsequent editorial edit).
    return hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False,
                                    default=str, separators=(',', ':')).encode()).hexdigest()

def build(packet):
    if [q['source_key'] for q in packet['items']] != [f'qz_1_{n}' for n in range(1,41)]:
        raise ValueError('This curated pass applies only to the 40 questions of source series 1')
    candidates=[]
    for item,index in zip(packet['items'],ASSIGNMENTS):
        n=item['position'];code=CONCEPTS[index][0]
        # Conservative proposed shared families, not automatically applied to
        # live questions: similarity must be checked across images/audio first.
        group = {11:11,36:11,8:8,10:8,28:8,14:14,21:14}.get(n,n)
        refs=['narsa-speed'] if n in (6,9,31,38) else ['narsa-fog'] if n in (22,26,35) else ['narsa-lights'] if n in (5,33) else []
        candidates.append({
            'revision_id':item['revision_id'],'source_key':item['source_key'],
            'base_fingerprint':fingerprint(item),'base_content_hash':item['content_hash'],
            'concept_codes':[code], 'family_candidate':f's1-scene-{group:02}',
            'priority':'high' if n in HIGH else 'normal',
            'notes':FLAGS.get(n,'ربط مقترح انطلاقاً من النص والشرح المورّد؛ خاص مراجعة المشهد والصوت والأجوبة.'),
            'prompt_candidate':'فهاد الحالة، شنو ندير؟' if n in (11,36) else None,
            'prompt_basis':'editorial proposal after visual inspection, not audio transcription' if n in (11,36) else None,
            'reference_ids':refs, 'state':'pending',
        })
    return {'version':VERSION,'series_id':packet['series']['id'],
            'purpose':'draft proposals only; no approval or publication',
            'concepts':[{'code':c,'topic_id':t,'label':l} for c,t,l in CONCEPTS],
            'references':SOURCES,'candidates':candidates}

def write_bundle(packet_path, output, media_root):
    packet=json.loads(packet_path.read_text(encoding='utf-8-sig'));proposals=build(packet)
    output.mkdir(parents=True,exist_ok=True)
    (output/'editorial-proposals.json').write_text(json.dumps(proposals,ensure_ascii=False,indent=2),encoding='utf-8')
    # Copy only hash-verified image/audio from the authorized local source.
    media_root=media_root.resolve();media_dir=output/'media';media_dir.mkdir(exist_ok=True)
    display=json.loads(json.dumps(packet))
    for item in display['items']:
        for m in item['media']:
            if m['role'] not in ('audio','original_card'): continue
            parts=Path(m['object_key']).parts
            if len(parts)<4 or parts[0]!='imports':raise ValueError('Unexpected media key')
            source=(media_root/Path(*parts[2:])).resolve()
            if not source.is_relative_to(media_root) or source.suffix.lower() not in ('.jpg','.jpeg','.png','.mp3'):
                raise ValueError('Unsafe media path')
            if hashlib.sha256(source.read_bytes()).hexdigest()!=m['sha256']:raise ValueError(f'Media hash mismatch: {source.name}')
            target=m['sha256']+source.suffix.lower();shutil.copyfile(source,media_dir/target)
            m['local_url']='media/'+target
    payload=json.dumps({'packet':display,'proposals':proposals},ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    template=(Path(__file__).parent/'editorial_workbench.html').read_text(encoding='utf-8')
    (output/'index.html').write_text(template.replace('__EDITORIAL_DATA__',payload),encoding='utf-8')
    report=['# المراجعة التحريرية — السلسلة الأولى','',
      '40 ربطاً مقترحاً و26 مفهوماً. لا توجد موافقة أو تعديل لمفاتيح الأجوبة. عائلات المواقف مقترحة فقط.','',
      'فُحصت صورتا السؤالين 11 و36؛ صياغة السؤال المضافة اقتراح تحريري وليست تفريغاً للصوت. مراجعة الصوت والمشهد الكامل والأجوبة تبقى مطلوبة لكل سؤال.','',
      '## ترتيب المراجعة','']
    for p in proposals['candidates']:
        if p['source_key'].split('_')[-1] in {str(n) for n in FLAGS}:
            report.append(f"- {p['source_key']} ({p['priority']}): {p['notes']}")
    report+=['','## مصادر مساعدة','']+[f"- [{r['id']}]({r['url']}): {r['scope']}" for r in SOURCES]
    report+=['','## الاستعمال','',
      'افتح index.html محلياً. اختار سؤالاً، اسمع الصوت وشوف الصورة، وسجل الملاحظات. الحفظ محلي في المتصفح؛ صدّر نسخة JSON باش تحتافظ بها. لا توجد أزرار اعتماد أو نشر، والتصدير لا يغير قاعدة البيانات.','',
      'المراجعة القادمة: حسم المفاتيح والشروحات وحدود الاختيارات ومراجعة حقوق الاستعمال، ثم تسجيل القرار بهوية مراجع حقيقي. المصدر التوعوي ليس تصريحاً باستعمال الصور أو تسجيلات الصوت.']
    (output/'EDITORIAL_AUDIT.md').write_text('\n'.join(report),encoding='utf-8')
    return {'questions':len(proposals['candidates']),'concepts':len(CONCEPTS),'high_priority':len(HIGH),'published':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--packet',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--media-root',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(write_bundle(args.packet,args.output,args.media_root)))
