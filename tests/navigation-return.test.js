const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', '此在-current-原型.html'), 'utf8');
const goSource = html.slice(html.indexOf('function go(hash){'), html.indexOf('function isRelayDesk(){'));
const resumeSource = html.slice(html.indexOf('function resumeAfterMap(){'), html.indexOf('document.addEventListener("visibilitychange"'));

test('returning home clears the previous request instead of sending it again', () => {
  const state = {route:'#/moments', talkText:'上次说的私密内容', talkTyping:true};
  const context = {
    state, location:{hash:''}, CurrentAI:{cancelVoice:() => {}},
    window:{speechSynthesis:{cancel:() => { context.speechCancelled = true; }}},
    document:{querySelector:() => null}, render:() => {}
  };
  vm.createContext(context);
  vm.runInContext(goSource + '\ngo("#/talk");', context);
  assert.equal(state.talkText, '');
  assert.equal(state.talkTyping, false);
  assert.equal(state.route, '#/talk');
  assert.equal(context.speechCancelled, true);
});

test('a map preview prompts for explicit departure only after the user returns', () => {
  let renders = 0;
  const state = {
    route:'#/offer',
    navigationReturn:{placeId:'river', launchedAt:1000, left:false, prompt:false}
  };
  const context = {state, Date:{now:() => 3000}, render:() => { renders++; }};
  vm.createContext(context);
  vm.runInContext(resumeSource + '\nglobalThis.resume = resumeAfterMap;', context);
  context.resume();
  assert.equal(renders, 0, 'opening a map is not departure or a return');
  state.navigationReturn.left = true;
  context.resume();
  assert.equal(state.navigationReturn.prompt, true);
  assert.equal(renders, 1);
  context.resume();
  assert.equal(renders, 1, 'a focus and pageshow pair must not create duplicate prompts');
});
