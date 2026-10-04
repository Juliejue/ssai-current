const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname,'../xiaozai-voice.js'),'utf8');
function runtime(response) {
  let systemCalled = false;
  const players = [];
  const sandbox = {
    window:{addEventListener(){},speechSynthesis:{speak(){systemCalled=true;}}},
    Audio:class {constructor(){players.push(this);}pause(){}play(){setTimeout(()=>this.onended&&this.onended(),0);return Promise.resolve();}},
    URL:{createObjectURL:()=> 'blob:test', revokeObjectURL(){}},
    AbortController, Map, setTimeout, clearTimeout,
    fetch:async()=>response,
  };
  vm.createContext(sandbox);vm.runInContext(source,sandbox);
  return {voice:sandbox.window.XiaozaiVoice,players,systemCalled:()=>systemCalled};
}
test('cloud failure reports an actionable error and never uses system narration',async()=>{
 const app=runtime({ok:false,json:async()=>({detail:'请先开通 TTS'})});const states=[];
 await app.voice.speak('我在。','zh',(phase,message)=>states.push({phase,message}));
 assert.equal(states.at(-1).phase,'error');assert.equal(states.at(-1).message,'请先开通 TTS');assert.equal(app.systemCalled(),false);
});
test('successful cloud audio is played and returns to idle',async()=>{
 const app=runtime({ok:true,blob:async()=>({type:'audio/mpeg'})});const states=[];
 await app.voice.speak('慢慢说。','zh',phase=>states.push(phase));
 assert.deepEqual(states,['loading','speaking','idle']);assert.equal(app.systemCalled(),false);
});
test('stopping during fetch prevents stale audio from playing',async()=>{
 let release;const response=new Promise(resolve=>release=resolve);
 const app=runtime({ok:true,blob:()=>response});const states=[];
 const pending=app.voice.speak('我在。','zh',phase=>states.push(phase));
 await Promise.resolve();app.voice.stop();release({});await pending;
 assert.equal(states.includes('speaking'),false);
});
