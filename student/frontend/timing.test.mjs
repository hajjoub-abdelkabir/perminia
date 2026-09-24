import test from 'node:test';
import assert from 'node:assert/strict';
import { remainingSeconds, settleQuestion } from './src/timing.mjs';

test('30 seconds, rounding and background deadline', () => {
  assert.equal(remainingSeconds(30000, 0), 30);
  assert.equal(remainingSeconds(30000, 2001), 28);
  assert.equal(remainingSeconds(30000, 29999), 1);
  assert.equal(remainingSeconds(30000, 45000), 0);
});
test('unconfirmed selection expires; deadline wins over confirmation', () => {
  assert.deepEqual(settleQuestion('timeout', ['a'], 30000, 30000), {status:'expired',choices:[]});
  assert.deepEqual(settleQuestion('confirm', ['a'], 30000, 30000), {status:'expired',choices:[]});
});
test('multiple selections before deadline count as submitted, not correct', () => {
  assert.deepEqual(settleQuestion('confirm', ['a','b'], 29999, 30000), {status:'answered',choices:['a','b']});
  assert.deepEqual(settleQuestion('skip', ['a'], 1000, 30000), {status:'skipped',choices:[]});
});
