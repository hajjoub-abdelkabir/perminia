export async function journeyRequest(path='',body,method='POST') {
  const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),30000);
  try {
    const r=await fetch('/api/v1/student/journey'+path,{credentials:'same-origin',signal:controller.signal,
      method:body===undefined?'GET':method,headers:body===undefined?{}:{'Content-Type':'application/json','X-Sya9a-Request':'student'},
      body:body===undefined?undefined:JSON.stringify(body)});
    const data=await r.json();
    if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'ما قدرناش نكملو الطلب.');
    return data;
  } catch(e) {if(e.name==='AbortError'||e instanceof TypeError)throw new Error('الاتصال تعطل. عاود جرّب.');throw e;}
  finally {clearTimeout(timeout);}
}
