export async function schoolRequest(path,body){
 const response=await fetch('/api/v1/school'+path,{credentials:'same-origin',method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json','X-Sya9a-Request':'student'},body:body===undefined?undefined:JSON.stringify(body)});
 const data=await response.json();if(!response.ok)throw new Error(data.detail||'تعذر تحميل المعطيات.');return data;
}
