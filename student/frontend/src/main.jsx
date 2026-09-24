import {useRouteState,writeRoute} from './navigation';
import ShowcaseBanner from './ShowcaseBanner';
import ChatTutor from './ChatTutor';
import SchoolPortal from './SchoolPortal';
import StudentToday from './StudentToday';
import ReviewNotebook from './ReviewNotebook';
import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import Lessons from './Lessons';
import StudentProgress from './StudentProgress';
import TimedSession from './TimedSession';
import TrainingCenter, { SavedTraining } from './TrainingCenter';
import { AccountDialog, AccountPanel, authRequest } from './Account';

function Icon({name, ...props}) {
 const paths = {book:'M4 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-2H4z M20 4h-4a3 3 0 0 0-3 3v14a4 4 0 0 1 4-2h3z', arrow:'M19 12H5m6-6-6 6 6 6', sound:'M11 5 6 9H3v6h3l5 4z M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14',check:'m5 12 4 4L19 6',clock:'M12 8v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',grid:'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z'};
 return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={paths[name] || paths.book}/></svg>;
}
async function request(path, signal) {const response=await fetch('/api/v1/student/preview'+path,{signal});if(!response.ok)throw new Error('request');return response.json();}
function App(){
 const [showAll,setShowAll]=useState(false);
 const [user,setUser]=useState(null);
 const [accountOpen,setAccountOpen]=useState(false);
 const [page,setPage]=useRouteState('page','dashboard');
 const [lessonSlug,setLessonSlug]=useRouteState('lesson',null);
 const [lessonPosition,setLessonPosition]=useRouteState('position',null);
 const [authLoading,setAuthLoading]=useState(true);
 const [authError,setAuthError]=useState('');
 const [authRetry,setAuthRetry]=useState(0);
 const [logoutBusy,setLogoutBusy]=useState(false);
 useEffect(() => {
   let current=true;
   setAuthLoading(true);
   setAuthError('');
   authRequest('/me').then(({user})=>{if(current)setUser(user);})
     .catch(error=>{if(current){if(error.status===401)setUser(null);else setAuthError(error.message);}})
     .finally(()=>{if(current)setAuthLoading(false);});
   return ()=>{current=false;};
 },[authRetry]);
 async function logout(){
   setLogoutBusy(true);setAuthError('');
   try { await authRequest('/logout',{});setUser(null);setPage('dashboard');setActive(null);writeRoute({lesson:null,position:null,chat:null,schoolTab:null,pupil:null,search:null,teacherFilter:null,statusFilter:null}); }
   catch(error){setAuthError(error.message);}
   finally{setLogoutBusy(false);}
 }
 function showAccount(){if(user){setPage('account');setActive(null);}else setAccountOpen(true);}
 const [catalog,setCatalog]=useState(null),[active,setActiveRoute]=useRouteState('series',null),[data,setData]=useState(null),[error,setError]=useState(false),[retry,setRetry]=useState(0);
 useEffect(() => {
   let current = true;
   const controller = new AbortController();
   const timeout = setTimeout(() => controller.abort(), 12000);
   setError(false);
   setData(null);
   if (!active) setCatalog(null);
   request(active ? '/series/' + active : '/series', controller.signal)
     .then(value => {
       if (!current) return;
       if (active) setData(value);
       else setCatalog(value.items);
     })
     .catch(() => { if (current) setError(true); })
     .finally(() => clearTimeout(timeout));
   return () => {
     current = false;
     clearTimeout(timeout);
     controller.abort();
   };
 }, [active, retry]);
 function setActive(value){setActiveRoute(value);writeRoute({run:null,training:null});}
 useEffect(()=>{document.title='PerminIA · '+(user?.role==='school_manager'?'إدارة المدرسة':user?.role==='instructor'?'فضاء الأستاذ':'فضاء التلميذ');},[user?.role]);
 const open=(id)=>{setPage('series');setActive(id);window.scrollTo({top:0});};
 if(authLoading)return <main><p role="status">كنوجدو الحساب ديالك…</p></main>;
 if(user&&['instructor','school_manager'].includes(user.role))return <><SchoolPortal key={user.membership_id} user={user} onLogout={logout} busy={logoutBusy} logoutError={authError}/><ChatTutor key={user.membership_id} user={user}/></>;
 return <div className="shell"><aside className="sidebar"><a className="brand" href="/" aria-label="PerminIA، الصفحة الرئيسية"><img className="brand-logo" src="/brand/perminia-logo-white.png" alt="PerminIA" width="2240" height="800"/></a><p className="side-label">فضاء التلميذ</p>{[['dashboard','اليوم','grid'],['lessons','التعلّم والتدريب','book'],['progress','تقدمي','clock']].map(([id,title,icon])=><button key={id} className={'nav-item '+((page===id||(id==='dashboard'&&page==='notebook')||(id==='lessons'&&['series','training'].includes(page)))?'current':'')} onClick={()=>{setPage(id);setActive(null);}}><Icon name={icon}/>{title}</button>)}<div className="side-note"><span className="small-mark">✦</span><h3>خطوة بخطوة</h3><p>كل سؤال كتفهمو، كيقربك أكثر للسياقة بثقة.</p></div><div className="side-bottom"><span className="avatar">ت</span><div><strong>{user?user.display_name:'تجربة التلميذ'}</strong><small>{user?'حساب التلميذ':'نسخة محلية تجريبية'}</small></div></div></aside>
 <div className="workspace"><header className="topbar"><span>فضاء التلميذ <i>/</i> <strong>{page==='account'?'حسابي':page==='notebook'?'دفتر المراجعة':page==='training'?'تدريبي':page==='dashboard'?'اليوم':page==='progress'?'تقدمي':page==='lessons'?'الدروس':active?'التدريب':'سلاسل التدريب'}</strong></span><div className="header-account"><span className="preview-pill"><span/>نسخة تجريبية</span><button className="account-trigger" disabled={authLoading||!!authError} onClick={showAccount}>{authLoading?'جارٍ التحقق…':user?'حسابي':'تسجيل الدخول'}</button></div></header><main>{authError&&page!=='account'&&<div className="auth-banner" role="alert">{authError}<button className="secondary" onClick={()=>setAuthRetry(n=>n+1)}>إعادة المحاولة</button></div>}{page==='account'&&user&&<AccountPanel user={user} onBack={()=>setPage('series')} onLogout={logout} busy={logoutBusy} error={authError}/>}{accountOpen&&<AccountDialog onClose={()=>setAccountOpen(false)} onSuccess={user=>{setUser(user);setAuthError('');setAccountOpen(false);if(page!=='lessons')setPage('dashboard');setActive(null);}}/>}
 {['lessons','series','training'].includes(page)&&!active&&<nav className="learning-tabs" aria-label="التعلّم والتدريب">{[['lessons','الدروس'],['series','السلاسل'],['training','تدريباتي المحفوظة']].map(([id,title])=><button key={id} aria-current={page===id?'page':undefined} onClick={()=>{setPage(id);setActive(null);}}>{title}</button>)}</nav>}
 {page==='dashboard'&&!authLoading&&<StudentToday key={user?.membership_id||'guest'} user={user} onLogin={()=>setAccountOpen(true)} onSeries={open} onNavigate={(target,slug,position)=>{setLessonPosition(position||null);setLessonSlug(slug||null);setPage(target);setActive(null);}}/>}
 {page==='progress'&&!authLoading&&<StudentProgress key={user?.membership_id||'guest'} user={user} onLogin={()=>setAccountOpen(true)} onNavigate={(target,slug,position)=>{setLessonPosition(position||null);setLessonSlug(slug||null);setPage(target);setActive(null);}}/>}
 {page==='training'&&<TrainingCenter user={user} onLogin={()=>setAccountOpen(true)} onSeries={()=>{setPage('series');setActive(null);}}/>}
 {page==='notebook'&&<button className="secondary" onClick={()=>setPage('dashboard')}>→ العودة إلى اليوم</button>}
 {page==='notebook'&&<ReviewNotebook key={user?.membership_id||'guest'} user={user} onLogin={()=>setAccountOpen(true)} onExplore={()=>{setPage('lessons');setLessonSlug(null);}} onLesson={(slug,position)=>{setLessonSlug(slug);setLessonPosition(position);setPage('lessons');setActive(null);}}/>}
 {page==='lessons'&&<Lessons key={user?.membership_id||'guest'} initialSlug={lessonSlug} initialPosition={lessonPosition} user={user} onLogin={()=>setAccountOpen(true)}/>}
 {!active&&page==='series'&&<><section className="hero"><div><span className="eyebrow">الطريق إلى رخصة السياقة</span><h1>تعلّم بخطوات ثابتة،<br/><em>وسُق بثقة.</em></h1><p>شوف الصورة، سمع السؤال بالدارجة، وجرّب تجاوب.<br/>30 ثانية لكل سؤال. سمع، ركّز، وأكد الجواب ديالك.</p><button className="primary hero-button" onClick={()=>document.getElementById('series')?.scrollIntoView()}>استعراض السلاسل <Icon name="arrow"/></button></div><div className="road-art" aria-hidden="true"><div className="sun"/><svg viewBox="0 0 320 280"><path d="M215-20C330 105 75 65 115 178S230 245 185 310" fill="none" stroke="#c9dcd0" strokeWidth="88"/><path d="M215-20C330 105 75 65 115 178S230 245 185 310" fill="none" stroke="#f7faf4" strokeWidth="3" strokeDasharray="12 14"/><g transform="translate(99 140) rotate(-18)"><rect width="34" height="57" rx="10" fill="#0a5d7a"/><rect x="5" y="10" width="24" height="14" rx="4" fill="#bce9fa"/><rect x="5" y="40" width="24" height="8" rx="2" fill="#29abe2"/></g><circle cx="264" cy="178" r="29" fill="#fff"/><circle cx="264" cy="178" r="23" fill="none" stroke="#f5a623" strokeWidth="5"/><text x="264" y="185" textAnchor="middle" fontSize="20" fill="#0a5d7a">40</text></svg><span className="art-tag"><Icon name="sound"/>بالصوت والصورة</span></div></section>
 <section className="stats" aria-label="محتوى التدريب"><div><Icon name="book"/><strong>{catalog?.length??'—'}</strong><span>سلاسل متاحة</span></div><div><Icon name="grid"/><strong>{catalog?.reduce((n,s)=>n+s.item_count,0)??'—'}</strong><span>سؤال للتدرّب</span></div><div><Icon name="sound"/><strong>بالدارجة</strong><span>سمع وفهم على خاطرك</span></div></section>
 <section id="series"><div className="section-heading"><div><span className="eyebrow">بداية الرحلة</span><h2>اختر سلسلتك</h2><p>بدا بجولة وحدة اليوم. كل مرة كتدرّب فيها، كتولي واجد أكثر.</p></div><button className="secondary" onClick={()=>setShowAll(v=>!v)}>{showAll?'عرض أقل':'جميع السلاسل'}</button></div>{catalog&&<div className="series-grid">{(showAll?catalog:catalog.slice(0,3)).map((s,i)=><article className="series-card" key={s.id}><div className="card-top"><span className="series-number">{String(i+1).padStart(2,'0')}</span><span className="chip soft">معاينة</span></div><h3>السلسلة {i+1}</h3><p>شوف، سمع، وجرّب الأجوبة ديالك.</p><div className="card-meta"><span><Icon name="book"/>{s.item_count} سؤال</span><span><Icon name="sound"/>صوت وصورة</span></div><button className="card-action" onClick={()=>open(s.id)}>{user?'بدء تدريب محفوظ':'بدء المعاينة'} <Icon name="arrow"/></button></article>)}</div>}</section><section className="next-space"><div className="next-symbol">✦</div><div><span className="eyebrow">الخطوة القادمة</span><h2>تعلّم يفهم طريقتك.</h2><p>ففضاء تدريبي تقدر ترجع للجولات المحفوظة وتشوف خريطة الفهم من الأجوبة المعتمدة.</p></div><button className="secondary" onClick={()=>setPage('training')}>فتح تدريبي</button></section></>}
 {active&&user&&<SavedTraining key={active} seriesId={active} onExit={()=>{setActive(null);setPage('training');}}/>}{active&&data&&!user&&<TimedSession key={active} data={data} user={user} onExit={()=>setActive(null)}/>}
 {page==='series'&&(!active||!user)&&(error?<div className="load-state" role="alert"><h2>تعذر تحميل المحتوى</h2><p>ما قدرناش نجيبو الأسئلة دابا. عاود جرّب من بعد شوية.</p><button className="primary" onClick={()=>setRetry(n=>n+1)}>إعادة المحاولة</button></div>:((active&&!data)||(!active&&!catalog))&&<div className="load-state" role="status"><span className="spinner"/>كنوجدو ليك الأسئلة…</div>)}
 <footer>نسخة محلية تجريبية · القراءة والمشاركة كيتحفظو، ونقط المحاكاة موسومة كتجريبية. <a href="/visual/credits.txt" target="_blank" rel="noreferrer">المراجع البصرية</a></footer></main></div><ChatTutor key={user?.membership_id} user={user}/></div>;
}
createRoot(document.getElementById('root')).render(<><ShowcaseBanner/><App/></>);







