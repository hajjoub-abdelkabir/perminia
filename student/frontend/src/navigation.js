import {useSyncExternalStore} from 'react';
const event='perminia-route';
let pending=null,scheduled=false,replaceOnly=true;
export function readRoute(key,fallback){
 try{const raw=new URLSearchParams(location.hash.slice(1)).get(key);if(raw===null)return fallback;const value=JSON.parse(raw);
 if(key==='position')return Number.isInteger(value)&&value>0&&value<1000?value:fallback;
 if(key==='training')return value&&typeof value==='object'&&((typeof value.runId==='string'&&/^[a-f0-9-]{36}$/.test(value.runId))||value.mode==='adaptive')?value:fallback;
 if(typeof value!=='string'||value.length>500)return fallback;
 if(key==='page'&&!['dashboard','lessons','series','training','notebook','progress','account'].includes(value))return fallback;
 if(key==='schoolTab'&&!['students','teachers','invite'].includes(value))return fallback;
 return value;
 }catch{return fallback;}
}
export function writeRoute(values,replace=false){
 pending={...(pending||{}),...values};replaceOnly=replaceOnly&&replace;
 if(scheduled)return;scheduled=true;
 queueMicrotask(()=>{const query=new URLSearchParams(location.hash.slice(1));for(const [key,value] of Object.entries(pending)){if(value===null||value===undefined||value==='')query.delete(key);else query.set(key,JSON.stringify(value));}
 const next=location.pathname+location.search+(query.size?'#'+query.toString():'');
 if(next!==location.pathname+location.search+location.hash)history[replaceOnly?'replaceState':'pushState'](null,'',next);
 pending=null;scheduled=false;replaceOnly=true;window.dispatchEvent(new Event(event));});
}
function subscribe(callback){window.addEventListener('hashchange',callback);window.addEventListener('popstate',callback);window.addEventListener(event,callback);return()=>{window.removeEventListener('hashchange',callback);window.removeEventListener('popstate',callback);window.removeEventListener(event,callback);};}
export function useRouteState(key,fallback){
 useSyncExternalStore(subscribe,()=>location.hash);
 return [readRoute(key,fallback),value=>writeRoute({[key]:typeof value==='function'?value(readRoute(key,fallback)):value})];
}
