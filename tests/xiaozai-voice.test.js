const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname,'../xiaozai-voice.js'),'utf8');
function runtime(supported=true) {
  const utterances=[];
  const synthesis={cancel(){},getVoices(){return []},speak(u){utterances.push(u)}};
  const sandbox={window:{addEventListener(){},speechSynthesis:supported?synthesis:null},speechSynthesis:synthesis,SpeechSynthesisUtterance:class{constructor(text){this.text=text}},fetch(){throw Error('Cloud speech must not be called')}};
  vm.createContext(sandbox);vm.runInContext(source,sandbox);
  return {voice:sandbox.window.XiaozaiVoice,utterances};
}
test('demo uses device speech without requesting cloud synthesis',()=>{
 const app=runtime(),states=[];app.voice.speak('我在。','zh',phase=>states.push(phase));
 const u=app.utterances[0];assert.equal(u.text,'我在。');assert.equal(u.lang,'zh-CN');u.onstart();u.onend();assert.deepEqual(states,['speaking','idle']);
});
test('stopping suppresses stale speech callbacks',()=>{
 const app=runtime(),states=[];app.voice.speak('我在。','zh',phase=>states.push(phase));app.voice.stop();app.utterances[0].onend();assert.deepEqual(states,[]);
});
test('unsupported device reports a readable error',()=>{
 const app=runtime(false),states=[];app.voice.speak('我在。','zh',(phase)=>states.push(phase));assert.deepEqual(states,['error']);
});
