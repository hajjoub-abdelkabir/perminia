import test from 'node:test';
import assert from 'node:assert/strict';
import {readRoute,writeRoute} from './navigation.js';
const calls=[];
globalThis.location={pathname:'/',search:'',hash:''};
globalThis.window=new EventTarget();
globalThis.history=Object.fromEntries(['pushState','replaceState'].map(method=>[method,(_state,_title,url)=>{calls.push(method);location.hash=new URL(url,'http://localhost').hash;}]));
const flush=()=>new Promise(resolve=>queueMicrotask(resolve));
test('related navigation changes are one history entry and retain filters',async()=>{
 writeRoute({page:'lessons',lesson:'asba9ia',position:2});writeRoute({search:'سارة'});await flush();
 assert.equal(calls.length,1);assert.equal(readRoute('position',null),2);assert.equal(readRoute('search',''),'سارة');
 writeRoute({pupil:'example'});await flush();assert.equal(readRoute('search',''),'سارة');
});
test('recording a run replaces history and survives parsing',async()=>{
 const id='bf1472bd-9f88-4a67-a103-69f4d40b5b10';writeRoute({run:id},true);await flush();
 assert.equal(calls.at(-1),'replaceState');assert.equal(readRoute('run',null),id);
});
test('exit removes run and training context',async()=>{
 writeRoute({run:null,training:null,page:'training'});await flush();assert.equal(readRoute('run',null),null);assert.equal(readRoute('page','dashboard'),'training');
});
test('malformed and wrong-type routes safely fall back',()=>{
 location.hash='#page=%7B%7D&position=-2&search=%5B%5D&training=%22wrong%22';
 assert.equal(readRoute('page','dashboard'),'dashboard');assert.equal(readRoute('position',1),1);assert.equal(readRoute('search',''),'');assert.equal(readRoute('training',null),null);
 location.hash='#page=%22missing%22';assert.equal(readRoute('page','dashboard'),'dashboard');
});
test('browser history snapshots retain the selected lesson independently',async()=>{
 writeRoute({page:'lessons',lesson:'speed',position:4});await flush();const saved=location.hash;
 writeRoute({page:'progress'});await flush();location.hash=saved;
 assert.equal(readRoute('page','dashboard'),'lessons');assert.equal(readRoute('position',1),4);
});
