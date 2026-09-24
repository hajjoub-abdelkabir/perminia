import React,{useEffect,useRef,useState} from 'react';
import './lesson-stage.css';

function Car({color,label}){return <g><rect x="-19" y="-33" width="38" height="66" rx="12" fill={color} stroke="white" strokeWidth="3"/><rect x="-13" y="-23" width="26" height="16" rx="5" fill="#143f51"/><text y="18" textAnchor="middle" fill="#123f51" fontSize="18" fontWeight="900">{label}</text><path d="m-7 -40 7 -8 7 8" fill="none" stroke={color} strokeWidth="4"/></g>;}

export function PriorityScene(){
 const [variant,setVariant]=useState(0),[choice,setChoice]=useState(null),[run,setRun]=useState(0);
 const scene=useRef(null);const [paused,setPaused]=useState(false);
 const correct=variant===0?2:1;
 const answer=choice!==null;
 return <section className="priority-lab" aria-label="تجربة أسبقية اليمين"><div className="stage-eyebrow"><span>مختبر الطريق</span><span>01 / تفاعل</span></div><div className="stage-intro"><h3>شكون يدوز اللول؟</h3><p>شوف يمين كل سيارة. هاد المثال بلا علامات، بلا ضواو وبلا شرطي.</p></div>
 <div ref={scene} className={'intersection '+(run?'is-playing':'')+(paused?' is-paused':'')} key={variant+':'+run}>
 <svg viewBox="0 0 680 440" role="img" aria-label={variant===0?'السيارة 1 جاية من التحت والسيارة 2 جاية من اليمين':'السيارة 1 جاية من التحت والسيارة 2 جاية من اليسار'}>
 <rect width="680" height="440" rx="24" fill="#e5f2ed"/>
 <g fill="#bddfcf"><circle cx="75" cy="75" r="28"/><circle cx="606" cy="365" r="30"/><circle cx="82" cy="370" r="20"/><circle cx="596" cy="64" r="20"/></g>
 <g fill="#c9e5dc" stroke="#fff" strokeWidth="5"><rect x="140" y="38" width="90" height="80" rx="15"/><rect x="465" y="320" width="82" height="85" rx="15"/></g>
 <path d="M260 0H420V140H680V300H420V440H260V300H0V140H260Z" fill="#3d5964" stroke="#fcffff" strokeWidth="6"/>
 <path d="M340 0V135M340 305V440M0 220H255M425 220H680" stroke="#d7e7e8" strokeWidth="3" strokeDasharray="13 13"/>
 <rect x="270" y="150" width="140" height="140" rx="22" fill="#6c8790" opacity=".25"/>
 <g className={'vehicle vehicle-one '+(correct===1?'first':'second')} style={{'--dx':'0px','--dy':'-345px'}} transform="translate(380 370)"><Car color="#55d0f0" label="1"/></g>
 <g className={'vehicle vehicle-two '+(correct===2?'first':'second')} style={{'--dx':variant===0?'-550px':'550px','--dy':'0px'}} transform={variant===0?'translate(585 180)':'translate(95 260)'}><g transform={variant===0?'rotate(-90)':'rotate(90)'}><Car color="#ffc04d" label="2"/></g></g>
 <g fill="#fff" opacity=".75"><path d="m380 325 -7 12h14Z"/><path d={variant===0?'m540 180 12 -7v14Z':'m140 260 -12 -7v14Z'}/></g>
 </svg><span className="scene-label">{run?'الترتيب: '+correct+' ثم '+(correct===1?2:1):'لاحظ • فكّر • اختار'}</span>{run>0&&<button className="motion-pause" onClick={()=>setPaused(p=>!p)}>{paused?'متابعة الحركة':'إيقاف الحركة'}</button>}
 </div>
 <div className="scene-choices" aria-label="اختيار السيارة الأولى">{[1,2].map(n=><button key={n} className={'car-choice car-'+n} aria-pressed={choice===n} onClick={()=>{setChoice(n);setRun(0);}}><span>{n}</span>السيارة {n}</button>)}</div>
 {answer&&<div className={'scene-feedback '+(choice===correct?'correct':'retry')} role="status"><strong>{choice===correct?'مزيان، لاحظتي جهة اليمين!':'قريب! نرجعو نشوفو اليمين ديال كل وحدة.'}</strong><p>{variant===0?'السيارة 2 جاية من يمين السيارة 1، ويمينها هي خاوي فهاد المشهد. كتدوز 2، ومن بعدها 1.':'دابا السيارة 1 هي اللي جاية من يمين السيارة 2. كتدوز 1، ومن بعدها 2.'}</p><button className="play-button" onClick={()=>{setPaused(false);setRun(n=>n+1);scene.current?.scrollIntoView({block:"center",behavior:"instant"});}}>{run?'إعادة العرض':'شاهد الحركة'} ▷</button><p className="motion-alternative">الترتيب: السيارة {correct} ← السيارة {correct===1?2:1}</p></div>}
 <button className="scene-switch" onClick={()=>{setVariant(v=>1-v);setChoice(null);setRun(0);}}>تغيير الحالة ↻</button><small className="scene-note">هاد المحاولة للتدريب، ما كتزادش لنقطة الامتحان.</small>
 </section>;
}

export function LessonMedia({media=[]}){
 const [active,setActive]=useState(0),[failed,setFailed]=useState(false),[zoom,setZoom]=useState(false);
 const dialog=useRef(null),trigger=useRef(null),video=useRef(null);const asset=media[active];
 useEffect(()=>{const node=video.current;return()=>node?.pause();},[active]);
 useEffect(()=>{if(zoom){dialog.current?.showModal();return()=>trigger.current?.focus();}},[zoom]);
 if(!asset)return null;
 return <section className="lesson-media-stage" aria-label="الشرح البصري"><div className="stage-eyebrow"><span>شوف الفكرة</span><span>{asset.media_type==='video'?'مثال متحرك للفقرة':'رسم توضيحي للفقرة'}</span></div><h3>{asset.title}</h3>
 {failed?<p role="status">الوسيط ما تحملش. تقدر تكمل الشرح أو <button className="quiet-button" onClick={()=>setFailed(false)}>تعيد المحاولة</button>.</p>:asset.media_type==='video'?<div className="lesson-video"><video key={asset.asset_id} ref={video} controls playsInline preload="none" poster={asset.has_poster?asset.url+'/poster':undefined} onError={()=>setFailed(true)} aria-label={asset.title}><source src={asset.url} type="video/mp4"/>{asset.has_captions&&<track kind="captions" src={asset.url+'/captions'} srcLang="ar" label="الدارجة المغربية" default/>}</video><p>شغّل المثال، ووقفو فوقاش بغيتي باش تلاحظ كل مرحلة. الترجمة متاحة من زر CC.</p>{asset.video_summary&&<div className="video-summary"><strong>ملخص المراحل</strong><p>{asset.video_summary}</p></div>}</div>:<button ref={trigger} className="diagram-button" onClick={()=>setZoom(true)} aria-label={'تكبير '+asset.title}><img src={asset.url} alt={asset.alt||asset.title} loading="lazy" onError={()=>setFailed(true)}/><span>تكبير الرسم ⤢</span></button>}
 {media.length>1&&<div className="media-options">{media.map((m,i)=><button key={m.asset_id} aria-pressed={i===active} onClick={()=>{setActive(i);setFailed(false);}}>{m.media_type==='video'?'▷ فيديو توضيحي':'▧ رسم توضيحي'}{media.filter(x=>x.media_type===m.media_type).length>1?' '+(i+1):''}</button>)}</div>}
 {zoom&&<dialog ref={dialog} className="media-zoom" onCancel={()=>setZoom(false)} aria-label={asset.title}><button className="secondary" onClick={()=>setZoom(false)}>إغلاق</button><img src={asset.url} alt={asset.alt||asset.title}/></dialog>}
 </section>;
}
