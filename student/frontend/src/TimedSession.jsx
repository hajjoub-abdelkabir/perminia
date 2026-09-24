import React, { useEffect, useRef, useState } from 'react';
import { remainingSeconds, settleQuestion } from './timing.mjs';
import { journeyRequest } from './journey-api';

export default function TimedSession({ data, onExit, user }) {
  const [sessionId] = useState(()=>crypto.randomUUID());
  const [saveStatus,setSaveStatus]=useState('idle');
  const [saveError,setSaveError]=useState('');
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [results, setResults] = useState({});
  const [seconds, setSeconds] = useState(30);
  const [finished, setFinished] = useState(false);
  const [review, setReview] = useState(false);
  const [audioStatus, setAudioStatus] = useState('waiting');
  const audio = useRef(null);
  const deadline = useRef(0);
  const settled = useRef(false);
  const selection = useRef([]);
  const question = data.questions[index];
  const id = question?.revision_id;
  const selected = answers[id] || [];
  const sound = question?.media.find(m => m.role === 'audio');
  selection.current = selected;

  useEffect(()=>{
    if(!finished||!user||saveStatus!=='idle')return;
    setSaveStatus('saving');
    journeyRequest('/sessions/'+sessionId,{series_id:data.series.id,
      outcomes:data.questions.map(q=>({revision_id:q.revision_id,...results[q.revision_id]}))},'PUT')
      .then(()=>setSaveStatus('saved')).catch(e=>{setSaveError(e.message);setSaveStatus('error');});
  },[finished,user,saveStatus,sessionId]);

  function advance() {
    if (index + 1 === data.questions.length) setFinished(true);
    else setIndex(n => n + 1);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function settle(action) {
    if (settled.current || review) return;
    settled.current = true;
    const result = settleQuestion(action, selection.current, Date.now(), deadline.current);
    setResults(old => ({ ...old, [id]: result }));
    if (result.status !== 'answered') setAnswers(old => ({ ...old, [id]: [] }));
    audio.current?.pause();
    advance();
  }

  useEffect(() => {
    if (finished || review || !id) return;
    settled.current = false;
    deadline.current = Date.now() + 30000;
    setSeconds(30);
    const tick = () => {
      setSeconds(remainingSeconds(deadline.current, Date.now()));
      if (Date.now() >= deadline.current) settle('timeout');
    };
    const timer = setInterval(tick, 100);
    // A background tab cannot extend the question's deadline.
    document.addEventListener('visibilitychange', tick);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', tick);
    };
  }, [id, finished, review]);

  useEffect(() => {
    const player = audio.current;
    if (!player || finished || !sound) return;
    let current = true;
    setAudioStatus('waiting');
    player.src = sound.url;
    player.load();
    const timer = setTimeout(() => {
      player.play().then(() => { if (current) setAudioStatus('playing'); })
        .catch(error => { if (current) setAudioStatus(error.name === 'NotAllowedError' ? 'blocked' : 'error'); });
    }, 2000);
    return () => {
      current = false;
      clearTimeout(timer);
      player.pause();
      player.removeAttribute('src');
      player.load();
    };
  }, [id, finished, review, sound?.url]);

  function toggle(choiceId) {
    if (review || settled.current) return;
    if (Date.now() >= deadline.current) { settle('timeout'); return; }
    setAnswers(old => {
      const values = old[id] || [];
      return { ...old, [id]: values.includes(choiceId) ? values.filter(v => v !== choiceId) : [...values, choiceId] };
    });
  }

  const answered = Object.values(results).filter(r => r.status === 'answered').length;
  const expired = Object.values(results).filter(r => r.status === 'expired').length;
  if (!question) return <p role="status">ما كاين حتى سؤال متاح فهاد السلسلة دابا.</p>;
  return <>
    <audio ref={audio} preload="auto" onEnded={() => setAudioStatus('ended')} onError={() => setAudioStatus('error')} />
    {finished ? <section className="completion">
      <span className="completion-icon">✓</span><span className="eyebrow">نهاية الجولة</span>
      <h1>كل جولة، خطوة إلى الأمام.</h1>
      <p>كملتي السلسلة. هادو أرقام المشاركة ديالك، ماشي عدد الأجوبة الصحيحة.</p>
      <div className="result-stats"><div><strong>{answered}</strong><span>أجوبة مؤكدة</span></div><div><strong>{expired}</strong><span>انتهى وقتها</span></div><div><strong>{data.questions.length - answered - expired}</strong><span>أسئلة متجاوزة</span></div></div>
      <p>الأسئلة اللي سالا وقتها ما تحسباتش، حتى إلا كنتي اخترتي شي جواب بلا ما تأكدو. هادي مشاركة بلا تصحيح، وما كتبدلش معدل الأداء.</p>
      <p role="status">{!user?'دخل للحساب قبل التدريب باش تحفظ الجولات الجاية.':saveStatus==='saved'?'تحفظات الجولة فالداتابيز. غادي تلقاها فـ «رحلتي ← الأداء والتتبع».':saveStatus==='error'?saveError:'كنحفظو الجولة…'}</p>
      {saveStatus==='error'&&<button className="secondary" onClick={()=>setSaveStatus('idle')}>إعادة محاولة الحفظ</button>}
      <div><button className="primary" onClick={() => { setReview(true); setIndex(0); setFinished(false); }}>مراجعة الجولة</button><button className="secondary" onClick={onExit}>العودة إلى السلاسل</button></div>
    </section> : <>
      <button className="back" onClick={onExit}>→ العودة إلى السلاسل</button>
      <div className="session-heading"><div><span className="eyebrow">{review ? 'مراجعة الجولة' : 'تدريب بإيقاع الامتحان'}</span><h1>{data.series.title}</h1><p>{review ? 'هنا تقدر تشوف الاختيارات المؤكدة والأسئلة اللي فات وقتها، بلا ما تبدل النتيجة.' : 'عندك 30 ثانية. سمع، اختار جواب أو أكثر، ومن بعد أكد باش تدوز.'}</p></div><span className="chip">السؤال {index + 1} من {data.questions.length}</span></div>
      <div className="quiz-layout"><section className="question-panel">
        <div className="question-top"><strong>السؤال {String(index + 1).padStart(2, '0')}</strong>{review ? <span className="chip">{results[id]?.status === 'answered' ? 'جواب مؤكد' : results[id]?.status === 'expired' ? 'انتهى الوقت · غير محسوب' : 'متجاوز · غير محسوب'}</span> : <div className={'countdown ' + (seconds <= 8 ? 'urgent' : '')} role="timer" aria-label={'الوقت المتبقي: ' + seconds + ' ثانية'}><svg viewBox="0 0 44 44" aria-hidden="true"><circle cx="22" cy="22" r="19"/><circle cx="22" cy="22" r="19" style={{ strokeDasharray: 119.4, strokeDashoffset: 119.4 * (1 - seconds / 30) }}/></svg><b>{seconds}</b><span>ثانية</span></div>}</div>
        {question.media.filter(m => m.role === 'original_card').map(m => <img key={m.url} className="question-image" src={m.url} alt="الصورة الأصلية ديال سؤال السياقة"/>)}
        <div className="question-body"><div className="audio-status" aria-live="polite"><span className={'sound-bars ' + (audioStatus === 'playing' ? 'playing' : '')}><i/><i/><i/><i/></span>{audioStatus === 'waiting' ? 'الصوت غادي يبدا بعد ثانيتين…' : audioStatus === 'playing' ? 'سمع السؤال مزيان…' : audioStatus === 'ended' ? 'ساليتي السماع.' : audioStatus === 'blocked' ? 'المتصفح طلب الإذن باش يشغل الصوت.' : 'الصوت ما قدرش يخدم دابا.'}{audioStatus === 'blocked' && <button className="back" onClick={() => audio.current.play().then(() => setAudioStatus('playing')).catch(() => setAudioStatus('error'))}>تفعيل الصوت</button>}</div>
        <h2>{question.prompt?.trim() || 'شوف الصورة وسمع السؤال باش تختار الجواب ديالك.'}</h2>
        <div className="choice-groups">{question.groups.map(group => <fieldset key={group.id} disabled={review}><legend>{group.label || 'الاختيارات'}</legend>{question.choices.filter(c => c.group_id === group.id).map(c => <label key={c.id} className={'choice ' + (selected.includes(c.id) ? 'selected' : '')}><input type="checkbox" checked={selected.includes(c.id)} onChange={() => toggle(c.id)}/><span className="choice-number">{c.number}</span><span>{c.text}</span><span className="choice-tick">{selected.includes(c.id) ? '✓' : ''}</span></label>)}</fieldset>)}</div>
        <div className="question-actions">{review ? <><button className="secondary" disabled={index === 0} onClick={() => setIndex(i => i - 1)}>السابق</button><button className="primary" onClick={() => index + 1 === data.questions.length ? setFinished(true) : setIndex(i => i + 1)}>{index + 1 === data.questions.length ? 'ملخص الجولة' : 'التالي'}</button></> : <><button className="secondary" onClick={() => settle('skip')}>تجاوز السؤال</button><span>{selected.length ? `${selected.length} اختيار` : 'اختار ومن بعد أكد'}</span><button className="primary" disabled={!selected.length} onClick={() => settle('confirm')}>تأكيد الإجابة ←</button></>}</div>
        </div></section><aside className="question-map"><span className="eyebrow">جولتك الحالية</span><h3>الطريق إلى السؤال 40</h3><p>أكدتي {answered} جواب. {expired > 0 && `${expired} سؤال سالا وقتو وما تحسبش.`}</p><progress value={Object.keys(results).length} max={data.questions.length}/><div className="number-grid">{data.questions.map((q, i) => <button key={q.revision_id} disabled={!review} aria-label={'السؤال ' + (i + 1)} aria-current={i === index ? 'step' : undefined} className={(i === index ? 'active ' : '') + (results[q.revision_id]?.status || '')} onClick={() => setIndex(i)}>{i + 1}</button>)}</div><div className="map-legend"><span>● مؤكد</span><span>● الوقت منتهٍ</span></div><div className="notice"><strong>30 ثانية لكل سؤال</strong><p>الصوت كيبدا بوحدو بعد ثانيتين. إلا سالا الوقت قبل التأكيد، السؤال ما كيتحسبش وكندوزو للي من بعدو. المراجعة كتفتح ملي تسالي الجولة.</p></div></aside></div>
    </>}
  </>;
}
