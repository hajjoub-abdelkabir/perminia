import React, { useEffect, useRef, useState } from 'react';

export async function authRequest(path, body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch('/api/v1/auth' + path, {
      method: body === undefined ? 'GET' : 'POST',
      credentials: 'same-origin',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json', 'X-Sya9a-Request': 'student' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(typeof data.detail === 'string' ? data.detail : 'راجع المعطيات اللي دخلتي.');
      error.status = response.status;
      throw error;
    }
    return data;
  } catch (error) {
    if (error.status) throw error;
    throw new Error('ما قدرناش نتاصلو بالخادم. تأكد من الاتصال وعاود جرّب.');
  } finally {
    clearTimeout(timeout);
  }
}

export function AccountDialog({ onClose, onSuccess }) {
  const [mode, setMode] = useState('login');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice,setNotice]=useState('');
  const [showPassword, setShowPassword] = useState(false);
  const dialog = useRef(null);
  const email = useRef(null);
  const submitting = useRef(false);

  useEffect(() => {
    const previous = document.activeElement;
    dialog.current.showModal();
    email.current?.focus();
    return () => { previous?.focus(); };
  }, []);

  async function submit(event) {
    event.preventDefault();
    if (submitting.current) return;
    const fields = new FormData(event.currentTarget);
    const body = { email: fields.get('email'), password: fields.get('password') };
    if (mode === 'activate') {
      body.display_name = fields.get('display_name');
      body.invitation_code = fields.get('invitation_code').trim();
    }
    if(mode==='recover')body.recovery_code=fields.get('recovery_code').trim();
    if(mode!=='login'){
      if (body.password !== fields.get('confirm_password')) {
        setError('كلمتا السر ما متطابقينش. عاود كتبهم بجوج.');
        return;
      }
    }
    submitting.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await authRequest('/' + mode, body);
      if(mode==='recover'){setMode('login');setShowPassword(false);setNotice('تبدلات كلمة السر وتسدو الجلسات القديمة. دخل دابا بالكلمة الجديدة.');}
      else onSuccess(result.user);
    } catch (e) {
      setError(e.message);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  function changeMode() {
    setMode(m => m === 'login' ? 'activate' : 'login');
    setError('');
    setShowPassword(false);setNotice('');
  }

  return <dialog className="account-dialog" aria-label={mode === 'recover'?'استرجاع الحساب':mode === 'login' ? 'تسجيل الدخول' : 'تفعيل حساب المدرسة'} ref={dialog} onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <button className="dialog-close" type="button" aria-label="إغلاق" disabled={busy} onClick={onClose}>×</button>
    <div className="account-intro"><img className="account-logo" src="/brand/perminia-logo.png" alt="PerminIA" width="2240" height="800"/><span className="eyebrow">حساب المدرسة</span><h2>{mode === 'recover'?'استرجع حسابك':mode === 'login' ? 'مرحباً بعودتك' : 'انضم إلى مدرستك'}</h2><p>{mode === 'recover'?'طلب رمز الاسترجاع من مدير المدرسة، ودخل البريد ديال حسابك واختار كلمة سر جديدة. إلا كنت مدير، تواصل مع مسؤول المنصة.':mode === 'login' ? 'دخل للحساب ديالك وكمل الرحلة من هنا.' : 'دخل رمز الدعوة والبريد اللي تعطات ليه. الحساب غادي يرتبط بمدرستك بوحدو.'}</p></div>
    {notice&&<p role="status" className="school-success">{notice}</p>}
    <form key={mode} onSubmit={submit}>
      <fieldset disabled={busy}>
        {mode === 'activate' && <label>رمز الدعوة<input name="invitation_code" dir="ltr" autoComplete="off" required minLength={43} maxLength={43} placeholder="رمز الدعوة الخاص بك"/></label>}
        {mode === 'activate' && <label>الاسم<input name="display_name" autoComplete="nickname" required minLength={2} maxLength={80} placeholder="الاسم اللي بغيتي نستعملو"/></label>}
        {mode === 'recover' && <label>رمز الاسترجاع<input name="recovery_code" dir="ltr" autoComplete="off" required minLength={43} maxLength={43}/></label>}
        <label>البريد الإلكتروني<input ref={email} name="email" type="email" dir="ltr" autoComplete="email" required maxLength={254} placeholder="you@example.com"/></label>
        <label>كلمة المرور<div className="password-field"><input aria-label="كلمة المرور" name="password" type={showPassword ? 'text' : 'password'} dir="auto" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required minLength={mode === 'login' ? 1 : 12} maxLength={128}/><button type="button" aria-label={showPassword ? 'إخفاء كلمة المرور' : 'إظهار كلمة المرور'} aria-pressed={showPassword} onClick={() => setShowPassword(v => !v)}>{showPassword ? 'إخفاء' : 'إظهار'}</button></div></label>
        {mode !== 'login' && <><small className="input-hint">اختار كلمة سر طويلة، فيها 12 حرف على الأقل. تقدر تستعمل جملة ساهلة عليك تتفكرها.</small><label>تأكيد كلمة المرور<input name="confirm_password" type={showPassword ? 'text' : 'password'} autoComplete="new-password" required minLength={12} maxLength={128}/></label></>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="primary auth-submit" type="submit">{busy ? 'جارٍ التحقق…' : mode === 'login' ? 'تسجيل الدخول' : mode==='recover'?'حفظ كلمة السر الجديدة':'تفعيل الحساب'}</button>
        <p className="account-switch">{mode === 'login' ? 'توصلتي بدعوة من المدرسة؟' : 'عندك حساب من قبل؟'} <button type="button" onClick={changeMode}>{mode === 'login' ? 'تفعيل دعوة' : 'تسجيل الدخول'}</button></p>
        {mode==='login'&&<p className="account-switch"><button type="button" onClick={()=>{setMode('recover');setError('');setNotice('');setShowPassword(false);}}>نسيت كلمة المرور؟</button></p>}
      </fieldset>
    </form>
    <p className="account-footnote">التسجيل كيتدار غير بدعوة خاصة بالمدرسة. إلا ما عندكش الرمز، تواصل معاها. استرجاع الحساب كيتدار برمز مؤقت من المدرسة؛ البريد الأوتوماتيكي باقي ما تفعّلش.</p>
  </dialog>;
}

export function AccountPanel({ user, onBack, onLogout, busy, error }) {
  return <section className="account-page">
    <button className="back" onClick={onBack}>→ العودة إلى السلاسل</button>
    <div className="account-heading"><span className="profile-avatar">{user.display_name.slice(0,1)}</span><div><span className="eyebrow">حساب التلميذ</span><h1>مرحباً، {user.display_name}</h1><p>هاد الفضاء ديالك. القراءة والتدريبات المحفوظة مربوطين بالحساب ديالك.</p></div></div>
    <dl className="account-details"><div><dt>مدرسة السياقة</dt><dd>{user.school_name || 'حساب تجريبي غير مرتبط بمدرسة'}</dd></div><div><dt>الاسم</dt><dd>{user.display_name}</dd></div><div><dt>البريد الإلكتروني</dt><dd dir="ltr">{user.email}</dd></div><div><dt>صنف الرخصة</dt><dd>{user.category_id}</dd></div><div><dt>لغة التعلم</dt><dd>الدارجة المغربية</dd></div><div><dt>تاريخ الانضمام</dt><dd>{new Date(user.created_at).toLocaleDateString('ar-MA')}</dd></div></dl>
    <div className="notice"><strong>المحاولات المحفوظة</strong><p>تقدر ترجع للجولات المحفوظة من «التعلّم والتدريب». نقط التصحيح كتبان غير للأسئلة المعتمدة.</p></div>
    {error && <p className="form-error" role="alert">{error}</p>}
    <button className="secondary logout-button" disabled={busy} onClick={onLogout}>{busy ? 'جارٍ تسجيل الخروج…' : 'تسجيل الخروج'}</button>
  </section>;
}

