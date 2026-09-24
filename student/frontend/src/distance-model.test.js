import {test} from 'node:test';
import assert from 'node:assert/strict';
import {stoppingDistances} from './distance-model.js';
test('unit conversion and total at 36 km/h',()=>{
 const d=stoppingDistances(36,2,5);
 assert.deepEqual(d,{reaction:20,braking:10,total:30});
});
test('doubling speed doubles reaction and quadruples braking',()=>{
 const a=stoppingDistances(40,1,6),b=stoppingDistances(80,1,6);
 assert.equal(b.reaction,a.reaction*2);assert.equal(b.braking,a.braking*4);
});
test('reaction time cannot change braking in this model',()=>{
 const a=stoppingDistances(60,1,6),b=stoppingDistances(60,3,6);
 assert.equal(a.braking,b.braking);assert.equal(b.reaction,3*a.reaction);
});
test('rejects nonphysical inputs',()=>{
 for(const args of [[20,1,0],[-20,1,6],[20,-1,6],[Infinity,1,6],[20,1,NaN]])assert.throws(()=>stoppingDistances(...args),RangeError);
});
