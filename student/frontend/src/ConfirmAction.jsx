import React,{useEffect,useRef,useState} from 'react';
export default function ConfirmAction({title,children,confirmLabel='تأكيد',onConfirm,onCancel}){
 const ref=useRef(null),lock=useRef(false);const [busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{const previous=document.activeElement;ref.current.showModal();return()=>previous?.isConnected&&previous.focus();},[]);
 async function submit(){if(lock.current)return;lock.current=true;setBusy(true);try{await onConfirm();onCancel();}catch{setError('العملية ما تكملاتش. عاود جرّب.');}finally{lock.current=false;setBusy(false);}}
 return <dialog ref={ref} className="confirm-action" aria-label={title} onCancel={e=>{e.preventDefault();if(!lock.current)onCancel();}}><h2>{title}</h2><div>{children}</div>{error&&<p role="alert">{error}</p>}<div className="confirm-buttons"><button autoFocus className="secondary" disabled={busy} onClick={onCancel}>تراجع</button><button className="primary" disabled={busy} onClick={submit}>{busy?'جارٍ التنفيذ…':confirmLabel}</button></div></dialog>;
}
