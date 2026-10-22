import test from 'node:test';
import assert from 'node:assert/strict';
import {niceTicks} from '../../site/core.mjs';
test('ticks remain round inside a fixed molecular comparison domain',()=>{
  assert.deepEqual(niceTicks(2.37,2.56),[2.4,2.45,2.5,2.55]);
  assert.deepEqual(niceTicks(-.7,.7,3),[-.5,0,.5]);
});
test('reversed seed axes and invalid domains are handled explicitly',()=>{
  assert.deepEqual(niceTicks(5.6,.4),[4,2]);
  assert.throws(()=>niceTicks(1,1));assert.throws(()=>niceTicks(0,NaN));
});
