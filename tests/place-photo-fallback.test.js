const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'..');
function runtime(){const ctx={window:{},document:{documentElement:{lang:'zh'},createElement:()=>({})}};vm.createContext(ctx);for(const file of ['hong-kong-place-photos.js','place-photo-fallback.js'])vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),ctx);return ctx;}
test('Hong Kong aliases match exact destinations with location bounds',()=>{
 const api=runtime().window.CurrentPlacePhotos;
 assert.equal(api.lookup({placeName:'屯門河道',latitude:22.39,longitude:113.98}).id,'tuen-mun-river');
 assert.equal(api.lookup({placeName:'屯门公园（北门）',city:'香港'}).id,'tuen-mun-park');
 assert.equal(api.lookup({placeName:'香港公园酒店',city:'香港'}),undefined);
 assert.equal(api.lookup({placeName:'香港公园',latitude:39.9,longitude:116.4}),null);
 assert.equal(api.lookup({placeName:'香港公园',city:'深圳市',latitude:22.54,longitude:114.1}),null);
});
test('failed hero tries the next real photo and only shows a placeholder after exhaustion',()=>{
 const ctx=runtime(),api=ctx.window.CurrentPlacePhotos,appended=[];
 const urls=api.lookup({placeName:'屯门河道',city:'香港'}).photos.map(p=>p.url);
 const link={hidden:false},parent={querySelector:()=>link,appendChild:el=>appended.push(el)};
 const img={dataset:{photoCandidates:JSON.stringify(urls),photoIndex:'0'},parentNode:parent,remove(){this.removed=true}};
 api.onError(img);assert.equal(img.src,urls[1]);assert.equal(img.removed,undefined);assert.equal(link.hidden,false);
 api.onError(img);assert.equal(img.src,urls[2]);api.onError(img);assert.equal(img.removed,true);assert.equal(link.hidden,true);assert.equal(appended[0].textContent,'暂无地点实景图');
});
