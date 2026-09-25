import test from 'node:test';
import assert from 'node:assert/strict';
import {initialState,reduce,createDemoStore,STORAGE_KEY} from './store.js';
test('assignment, reading and completion connect the demo roles',()=>{
 let s=initialState();s=reduce(s,{type:'assign',student:'amina',lesson:'follow'});
 const task=s.tasks.at(-1);s=reduce(s,{type:'complete',id:task.id});assert.equal(s.tasks.at(-1).done,false);
 s=reduce(s,{type:'read',lesson:'follow'});s=reduce(s,{type:'complete',id:task.id});assert.equal(s.tasks.at(-1).done,true);
 assert.equal(s.read.youssef.length,0);
});
test('answers are idempotent; expired answers stay uncounted',()=>{
 let s=reduce(initialState(),{type:'answer',id:'q1',value:-1});s=reduce(s,{type:'answer',id:'q1',value:0});assert.equal(s.answers.q1,-1);
 assert.equal(reduce(s,{type:'answer',id:'unknown',value:1}),s);
});
test('duplicate open tasks do not accumulate',()=>{let s=initialState();assert.equal(reduce(s,{type:'assign',student:'amina',lesson:'observe'}),s);});
test('persist and reset only the namespaced demo state',()=>{
 const map=new Map([['unrelated','keep']]);const storage={getItem:k=>map.get(k),setItem:(k,v)=>map.set(k,v)};
 const store=createDemoStore(storage);store.dispatch({type:'read',lesson:'observe'});
 assert.deepEqual(createDemoStore(storage).getState().read.amina,['observe']);store.dispatch({type:'reset'});
 assert.deepEqual(JSON.parse(map.get(STORAGE_KEY)).read.amina,[]);assert.equal(map.get('unrelated'),'keep');
});
test('unavailable or malformed storage has a usable in-memory fallback',()=>{
 const store=createDemoStore({getItem(){throw Error();},setItem(){throw Error();}});assert.equal(store.isPersistent(),false);
 assert.equal(store.dispatch({type:'role',role:'manager'}).role,'manager');
 assert.equal(createDemoStore({getItem:()=>'{bad'}).getState().role,'student');
 assert.equal(createDemoStore({getItem:()=>JSON.stringify({version:1})}).getState().role,'student');
});
