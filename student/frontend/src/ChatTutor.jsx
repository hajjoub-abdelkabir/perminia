import React,{useEffect,useRef,useState} from 'react';
import {useRouteState} from './navigation';
import './chat.css';

async function api(path='',body,method){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),55000);
 try{
  const r=await fetch('/api/v1/chat'+path,{method:method||(body===undefined?'GET':'POST'),credentials:'same-origin',signal:controller.signal,headers:{'Content-Type':'application/json','X-Sya9a-Request':'student'},body:body===undefined?undefined:JSON.stringify(body)});
  const d=await r.json();if(!r.ok)throw new Error(typeof d.detail==='string'?d.detail:'راجع السؤال ديالك؛ ما تكتب حتى مفتاح سري أو كلمة السر.');return d;
 }catch(e){if(e.name==='AbortError')throw new Error('الجواب خذا وقت. حدّث المحادثة باش تشوف واش تحفظ، قبل ما تعاود ترسل.');throw e;}finally{clearTimeout(timer);}
}
export default function ChatTutor({user}){
 const [route,setRoute]=useRouteState('chat',null);
 if(!user)return null;
 return <><button className="chat-launch" onClick={()=>setRoute('new')} aria-label="فتح مساعد البيرمي"><span aria-hidden="true">✦</span> مساعد البيرمي</button>{route&&<ChatPanel key={user.membership_id} initialId={route==='new'?null:route} onClose={()=>setRoute(null)} onSelect={setRoute}/>}</>;
}
function ChatPanel({initialId,onClose,onSelect}){
 const dialog=useRef(),end=useRef(),lock=useRef(false),request=useRef(null),generation=useRef(0),created=useRef(null);
 const [threads,setThreads]=useState([]),[current,setCurrent]=useState(initialId),[turns,setTurns]=useState([]),[message,setMessage]=useState(''),[config,setConfig]=useState(null),[consent,setConsent]=useState(false),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState(''),[remove,setRemove]=useState(false),[historyOpen,setHistoryOpen]=useState(false);
 useEffect(()=>{const previous=document.activeElement;dialog.current.showModal();return()=>{generation.current++;previous?.isConnected&&previous.focus();};},[]);
 useEffect(()=>{let alive=true;Promise.all([api('/status'),api('/threads')]).then(([s,t])=>{if(alive){setConfig(s);setThreads(t.items);}}).catch(()=>{if(alive)setError('ما قدرناش نجيبو المحادثات. سد المساعد وعاود حلو.');});return()=>{alive=false;};},[]);
 useEffect(()=>{if(created.current===current&&current){created.current=null;return;}const version=++generation.current;setError('');setRemove(false);setLoading(true);request.current=null;setMessage('');setTurns([]);
  if(!current){setLoading(false);return;}
  api('/threads/'+current).then(d=>{if(generation.current===version)setTurns(d.turns);}).catch(e=>{if(generation.current===version)setError(e.message);}).finally(()=>{if(generation.current===version)setLoading(false);});
 },[current]);
 useEffect(()=>{if(turns.length||busy)end.current?.scrollIntoView({block:'nearest',behavior:'instant'});},[turns,busy]);
 function select(id){if(lock.current)return;setCurrent(id);onSelect(id||'new');setConsent(false);setHistoryOpen(false);}
 async function refresh(){if(lock.current)return;const version=generation.current;try{const d=await api('/threads/'+current);if(generation.current===version){setTurns(d.turns);setError('');}}catch(e){if(generation.current===version)setError(e.message);}}
 async function send(e){e.preventDefault();if(lock.current||!message.trim()||!config?.enabled||(!current&&!consent))return;
  lock.current=true;setBusy(true);setError('');
  try{
   let id=current;
   if(!id){id=(await api('/threads',{consent:true})).id;created.current=id;setCurrent(id);onSelect(id);}
   const text=message.trim();const ticket=request.current?.message===text?request.current:{request_id:crypto.randomUUID(),message:text};request.current=ticket;
   const result=await api('/threads/'+id+'/messages',ticket);
   // Closing the panel never cancels a server-side generation; the saved thread can be reopened.
   if(!dialog.current?.isConnected)return;
   setTurns(old=>[...old.filter(t=>t.id!==result.id),result]);setMessage('');request.current=null;
   setThreads((await api('/threads')).items);
  }catch(e){if(dialog.current?.isConnected)setError(e.message);}finally{lock.current=false;if(dialog.current?.isConnected)setBusy(false);}
 }
 async function erase(){if(lock.current)return;lock.current=true;setBusy(true);try{await api('/threads/'+current,undefined,'DELETE');setThreads(old=>old.filter(t=>t.id!==current));lock.current=false;select(null);}catch(e){setError(e.message);}finally{lock.current=false;setBusy(false);}}
 const pending=turns.some(t=>t.status==='pending');
 return <dialog ref={dialog} className="chat-dialog" aria-labelledby="chat-title" onCancel={e=>{e.preventDefault();onClose();}}>
  <header className="chat-header"><div><span className="chat-spark" aria-hidden="true">✦</span><div><h2 id="chat-title">مساعد البيرمي</h2><p>نفهمو القاعدة، خطوة بخطوة.</p></div></div><button className="chat-close" onClick={onClose} aria-label="إغلاق المساعد">×</button></header>
  <div className="chat-toolbar"><button disabled={busy} onClick={()=>select(null)}>＋ محادثة جديدة</button><button aria-expanded={historyOpen} onClick={()=>setHistoryOpen(v=>!v)}>المحادثات ({threads.length})</button>{current&&<button disabled={busy||pending} onClick={()=>setRemove(true)}>حذف المحادثة</button>}</div>
  {historyOpen&&<nav className="chat-history" aria-label="محادثاتي">{threads.length?threads.map(t=><button key={t.id} disabled={busy} aria-current={current===t.id?'true':undefined} onClick={()=>select(t.id)}>{t.title}</button>):<p>مازال ما عندك حتى محادثة محفوظة.</p>}</nav>}
  {remove&&<section className="chat-delete" aria-label="تأكيد الحذف"><p>نمحو هاد المحادثة والذاكرة ديالها؟ ما غاديش تقدر ترجعها من التطبيق.</p><button disabled={busy} onClick={()=>setRemove(false)}>تراجع</button><button disabled={busy} onClick={erase}>تأكيد الحذف</button></section>}
  <div className="chat-notice">{config?.enabled?'مساعد تعليمي يقدر يغلط؛ فشي قرار قانوني تأكد مع الأستاذ أو NARSA.':'المساعد باقي كيتوجد؛ الإرسال غادي يتفتح ملي تتفعل الخدمة.'}{config?.draft_sources&&<strong> المراجع التجريبية مازال خاصها مراجعة الأستاذ.</strong>}</div>
  <div className="chat-messages" aria-busy={busy||loading}>
   {loading?<p role="status">كنجيبو المحادثة…</p>:!turns.length?<div className="chat-welcome"><span aria-hidden="true">✦</span><h3>شنو بغيتي تفهم اليوم؟</h3><p>سول بالدارجة، وكمّل بأسئلة أخرى فـنفس المحادثة. ما تحتاجش تعاود السياق كل مرة.</p><div>{['شرح ليا الأسبقية لليمين بمثال','شنو الفرق بين مسافة الأمان ومسافة الوقوف؟','كيفاش نشرح علامات التشوير بطريقة بسيطة؟'].map(q=><button key={q} onClick={()=>setMessage(q)}>{q}</button>)}</div></div>:turns.map(t=><React.Fragment key={t.id}><article className="chat-bubble chat-user"><small>أنت</small><p>{t.question}</p></article><article className="chat-bubble chat-assistant"><small>مساعد البيرمي{t.provider==='groq'?' · الخدمة الاحتياطية':''}</small>{t.status==='pending'?<p>الجواب كيتوجد. تقدر تحدّث المحادثة من الزر لتحت.</p>:t.status==='failed'?<p>ما قدرناش نكملو هاد الجواب. السؤال محفوظ؛ تقدر تعاود تسولو.</p>:<p>{t.answer}</p>}{t.sources?.length>0&&<details><summary>المراجع المستعملة ({t.sources.length})</summary>{t.sources.map(s=><section key={s.id}><strong>{s.lesson_title} · {s.title}</strong><small>{s.status==='draft'?'محتوى تجريبي غير معتمد':'محتوى الدرس'}</small><p>{s.excerpt}</p></section>)}</details>}</article></React.Fragment>)}
   {busy&&<p className="chat-thinking" role="status">كنقلب فالمراجع وكنوجد الشرح…</p>}<div ref={end}/>
  </div>
  <div className="chat-feedback" aria-live="polite">{error&&<p role="alert">{error}</p>}{current&&<button disabled={busy} onClick={refresh}>تحديث المحادثة</button>}</div>
  <form className="chat-compose" onSubmit={send}>
   {!current&&<label className="chat-consent"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>موافق يتعالج نص المحادثة والمراجع عند OpenAI، وعند Groq إلا استعملنا البديل. ما ندخلش كلمات السر ولا معطيات شخصية حساسة.</label>}
   <label htmlFor="chat-question">سؤالك</label><div><textarea id="chat-question" maxLength={1500} rows={2} value={message} disabled={busy||pending||loading} onChange={e=>setMessage(e.target.value)} placeholder="مثلاً: علاش نعطيه الأسبقية فهاد الحالة؟"/><button className="primary" disabled={busy||loading||pending||!config?.enabled||(!current&&!consent)||!message.trim()} type="submit">{busy?'جارٍ التحضير…':'إرسال'}</button></div>
   <small>المحادثة خاصة بحسابك. الذاكرة حتى 20 سؤال، وبحد أقصى للنص؛ تقدر تحذفها. {message.length}/1500</small>
  </form>
 </dialog>;
}
