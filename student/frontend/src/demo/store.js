export const STORAGE_KEY = 'perminia:public-demo:v1';
export const learners = [
  {id:'amina', name:'أمينة', initial:'أ', tag:'كتبدأ الرحلة', teacher:'الأستاذ ياسين'},
  {id:'youssef', name:'يوسف', initial:'ي', tag:'كيحتاج متابعة', teacher:'الأستاذ ياسين'},
  {id:'salma', name:'سلمى', initial:'س', tag:'كتراجع بانتظام', teacher:'الأستاذة هاجر'},
];
export const lessons = [
  {id:'observe', title:'شوف، ركّز، وافهم', category:'الملاحظة', minutes:3, icon:'◉',
    intro:'التعلم كيبدا بالملاحظة. فهاد المشهد التوضيحي، شوف الألوان والمواقع قبل ما تختار.',
    steps:['شوف المشهد كامل وخد وقتك تميّز العناصر اللي فيه.','السيارة الزرقاء فاليمين والصفراء فاليسار. اللون والموقع جوج معلومات مختلفين.','جرّب التمرين باش تشوف كيفاش كتتحفظ الإجابة وكتبان المراجعة. هادا مثال تقني، ماشي قاعدة أسبقية.']},
  {id:'understand', title:'من الجواب للفهم', category:'طريقة التعلم', minutes:2, icon:'✦',
    intro:'النقطة بوحدها ما كتشرحش فين كاين المشكل. المراجعة كتربط الاختيار بسبب واضح.',
    steps:['قرا شنو كيطلب السؤال بالضبط، بلا ما تعتمد غير على الصورة اللي ولفتي.','من بعد الإجابة، رجع للتفسير وقارن بين السؤال والاختيار ديالك.','تكرار نفس السؤال ما كيثبتش بوحدو الفهم. فالمشروع الكامل، كنراعيو تنوع الأسئلة والأدلة.']},
  {id:'follow', title:'الأستاذ كيكمل الرحلة', category:'التوجيه', minutes:2, icon:'↗',
    intro:'تجربة التعلم كتربط التلميذ بالأستاذ. جرّب تسند مهمة من فضاء الأستاذ وترجع لها هنا.',
    steps:['الأستاذ كيشوف النشاط اللي مسموح ليه يتبعو، وكيحدد الخطوة المناسبة.','التلميذ كيكمل قراءة المهمة وكيأكد الإنجاز. هادشي مختلف على إتقان المفهوم.','الأرقام والحسابات هنا اصطناعية. البيانات الحقيقية كتحتاج backend وصلاحيات ومحتوى معتمد.']},
];
export const questions = [
  {id:'q1', prompt:'فين كاينة السيارة الزرقاء فهاد المشهد؟', choices:['فاليمين','فاليسار'], answer:0, why:'السيارة الزرقاء مرسومة فالجهة اليمنى. هادا قياس ملاحظة بسيط، ماشي سؤال فقانون السير.'},
  {id:'q2', prompt:'شنو لون السيارة اللي فاليسار؟', choices:['زرقاء','صفراء'], answer:1, why:'السيارة اللي فاليسار صفراء. خدمنا هنا اللون والموقع باش نوضحو تجربة السؤال والمراجعة.'},
  {id:'q3', prompt:'واش إكمال قراءة درس كيثبت بوحدو أنك فهمتيه؟', choices:['نعم، القراءة كافية','لا، خاص أدلة أخرى'], answer:1, why:'القراءة نشاط محفوظ؛ قياس الفهم كيحتاج أسئلة متنوعة وأدلة كافية. النتيجة هنا غير ديال المحاكاة.'},
];
export function initialState() {
  return {version:1, role:'student', read:{amina:[],youssef:[],salma:[]}, answers:{},
    tasks:[{id:'welcome',student:'amina',lesson:'observe',done:false}], unassigned:[]};
}
export function validState(s) {
  return s?.version===1 && ['student','instructor','manager'].includes(s.role) &&
    learners.every(l=>Array.isArray(s.read?.[l.id]) && s.read[l.id].every(x=>lessons.some(y=>y.id===x))) &&
    Array.isArray(s.tasks) && s.tasks.length<=30 && s.tasks.every(t=>typeof t.id==='string' && learners.some(l=>l.id===t.student) && lessons.some(l=>l.id===t.lesson) && typeof t.done==='boolean') &&
    s.answers && typeof s.answers==='object' && Object.entries(s.answers).every(([id,value])=>questions.some(q=>q.id===id) && Number.isInteger(value) && value>=-1 && value<=1) &&
    Array.isArray(s.unassigned) && s.unassigned.every(id=>learners.some(l=>l.id===id));
}
export function reduce(s, action) {
  if(action.type==='reset') return initialState();
  if(action.type==='role' && ['student','instructor','manager'].includes(action.role)) return {...s,role:action.role};
  if(action.type==='read' && lessons.some(l=>l.id===action.lesson)) return {...s,read:{...s.read,amina:[...new Set([...s.read.amina,action.lesson])]}};
  if(action.type==='assign' && learners.some(l=>l.id===action.student) && lessons.some(l=>l.id===action.lesson)) {
    if(s.tasks.some(t=>t.student===action.student && t.lesson===action.lesson && !t.done)||s.tasks.length>=30)return s;
    return {...s,tasks:[...s.tasks,{id:`task-${s.tasks.length}`,student:action.student,lesson:action.lesson,done:false}]};
  }
  if(action.type==='complete')return {...s,tasks:s.tasks.map(t=>t.id===action.id && t.student==='amina' && s.read.amina.includes(t.lesson)?{...t,done:true}:t)};
  if(action.type==='answer' && questions.some(q=>q.id===action.id) && [-1,0,1].includes(action.value) && !(action.id in s.answers))return {...s,answers:{...s.answers,[action.id]:action.value}};
  if(action.type==='retry')return {...s,answers:{}};
  if(action.type==='assignment' && learners.some(l=>l.id===action.student))return {...s,unassigned:s.unassigned.includes(action.student)?s.unassigned.filter(x=>x!==action.student):[...s.unassigned,action.student]};
  return s;
}
export function createDemoStore(storage) {
  let current=initialState(), persistent=true;
  try {const raw=storage?.getItem(STORAGE_KEY);if(raw){const parsed=JSON.parse(raw);if(validState(parsed))current=parsed;}} catch {persistent=false;}
  return {
    getState:()=>current,
    isPersistent:()=>persistent,
    dispatch(action){current=reduce(current,action);try{if(!storage)throw new Error('Unavailable');storage.setItem(STORAGE_KEY,JSON.stringify(current));}catch{persistent=false;}return current;},
  };
}
