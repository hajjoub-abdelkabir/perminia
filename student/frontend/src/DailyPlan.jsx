import {NotebookPreview} from './ReviewNotebook';
import React,{useEffect,useState} from 'react';
import {journeyRequest} from './journey-api';
import './daily-plan.css';

const label=s=>(s||'').replace(/\([^)]*[A-Za-z][^)]*\)/g,'').trim();
export default function DailyPlan({onNavigate,dailyMinutes}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
 useEffect(()=>{let active=true;setError('');setData(null);journeyRequest('/daily-plan').then(d=>active&&setData(d)).catch(e=>active&&setError(e.message));return()=>{active=false;};},[dailyMinutes,retry]);
 const open=s=>onNavigate('lessons',s.slug,s.position);
 return <section className="sd-panel daily-plan"><div className="sd-heading"><div><span className="eyebrow">كل فقرة، خطوة جديدة</span><h2>برنامج القراءة اليومي</h2></div><span className="dp-sun" aria-hidden="true">☀</span></div>
 {error?<div role="alert"><p>{error}</p><button className="secondary" onClick={()=>setRetry(x=>x+1)}>إعادة المحاولة</button></div>:!data?<p role="status">كنوجدو الخطوة المناسبة ليك…</p>:<>
 <div className="dp-progress"><strong>{Math.min(data.completed_today,data.target)} / {data.target}</strong><div><b>{data.target_met?'كملتي هدف القراءة اليوم!':'فقرات اليوم'}</b><p>{data.target_met?'خطوة زوينة. تقدر ترتاح أو ترجع لشي فقرة بغيتي تثبتها.':'الإنجاز كيتحسب ملي تعلّم الفقرة كمكتملة داخل الدرس.'}</p></div></div>
 <progress max={data.target} value={Math.min(data.completed_today,data.target)} aria-label="إنجاز هدف القراءة اليومي"/>
 <p className="sd-note">حوالي 5 دقايق لكل فقرة، حتى لـ6 فقرات فالنهار. الوقت تقديري، خذ الوقت اللي محتاج.</p>
 <details className="daily-options"><summary>فقرات البرنامج ({data.tasks.length})</summary><div className="dp-tasks">{data.tasks.map((s,i)=><button className="dp-task" key={s.revision_id+':'+s.position} onClick={()=>open(s)}><span className="dp-number">{i+1}</span><span><small>{label(s.lesson_title)}</small><strong>{label(s.title)}</strong></span><span aria-hidden="true">←</span></button>)}</div></details>
 {!data.tasks.length&&!data.target_met&&<p>{data.all_read?'كملتي قراءة الدروس المتاحة. رجع لشي فقرة باش تراجعها على راحتك.':'باقي ما كايناش فقرات متاحة.'}</p>}
 {data.tasks[0]&&<button className="primary dp-resume" onClick={()=>open(data.tasks[0])}>قراءة الفقرة التالية ← <small>{label(data.tasks[0].title)}</small></button>}
 {data.resume&&<button className="secondary dp-resume" onClick={()=>open(data.resume)}>{data.resume.updated_at?'الرجوع لآخر فقرة':'بدء القراءة'} ← <small>{label(data.resume.title)}</small></button>}
 {!!data.bookmarks.length&&<details className="dp-bookmarks"><summary>الفقرات المحفوظة للمراجعة</summary>{data.bookmarks.map(s=><button key={s.revision_id+':'+s.position} onClick={()=>open(s)}>☆ {label(s.title)}</button>)}</details>}
 <NotebookPreview onNavigate={onNavigate}/><p className="sd-note">هاد البرنامج من القراءة المسجلة ديالك، ماشي من النقط التجريبية. إكمال القراءة ما كيثبتش الإتقان. اليوم محسوب بتوقيت المغرب.</p>
 </>}
 </section>;
}
