const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../此在-current-原型.html'),'utf8');
const fn=source.slice(source.indexOf('  function submitReflect(text){'),source.indexOf('  function setNaturalStatus('));
const original='还不错夕阳照在水面上挺好看的。';
function runtime(responses){
 const input={value:original},button={disabled:false,textContent:'发送'},requests=[];
 const ctx={state:{draft:{placeId:'river'},mood:'tired',reflectHistory:[]},document:{getElementById:id=>id==='reflect-input'?input:id==='reflect-submit'?button:null},placeById:()=>({placeName:'屯门河道',factorOptions:[]}),moodById:()=>({name:'累但静不下来'}),uiCopy:x=>x,setReflectCap(){},showVoiceState(){},render(){button.disabled=ctx.state.reflectSending},CurrentAI:{reflectOn(text,context){requests.push({text,context});let r=responses.shift();return r instanceof Error?Promise.reject(r):Promise.resolve(r)}}};
 vm.createContext(ctx);vm.runInContext(fn,ctx);return{ctx,input,button,requests};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
test('already transcribed words send successfully and user can continue the conversation',async()=>{
 const r=runtime([{acknowledgement:'水面上的夕阳，这一刻你觉得好看。',change_score:null},{acknowledgement:'你现在轻松了一些。',change_score:2}]);
 r.ctx.submitReflect();await settle();assert.equal(r.requests[0].text,original);assert.equal(r.ctx.state.reflectHistory[0].text,original);assert.equal(r.ctx.state.reflectText,'');assert.equal(r.ctx.state.reflectSending,false);
 r.input.value='是的，现在放松多了';r.ctx.submitReflect();await settle();assert.equal(r.ctx.state.reflectHistory.length,2);assert.equal(r.ctx.state.reflect.change_score,2);
});
test('empty response preserves the words and retry succeeds without asking to speak again',async()=>{
 const r=runtime([{acknowledgement:null,status:'unavailable'},{acknowledgement:'收到你的夕阳体验。',change_score:null}]);r.ctx.submitReflect();await settle();assert.equal(r.ctx.state.reflectText,original);assert.equal(r.button.disabled,false);assert.match(r.ctx.state.reflectNote,/回复/);assert.doesNotMatch(r.ctx.state.reflectNote,/没听准|再说一次/);r.ctx.submitReflect();await settle();assert.equal(r.ctx.state.reflectHistory.length,1);
});
test('network failure keeps transcript and releases send button',async()=>{
 const r=runtime([new Error('network')]);r.ctx.submitReflect();await settle();assert.equal(r.ctx.state.reflectSending,false);assert.equal(r.ctx.state.reflectText,original);assert.match(r.ctx.state.reflectNote,/连接不上/);
});
