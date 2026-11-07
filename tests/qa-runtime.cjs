const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const code = fs.readFileSync(require('node:path').join(__dirname, '../app.js'), 'utf8');
const storage = new Map();
const els = new Map();
const events = {};
const queue = [];
let currentHash = '';
function element(id) {
  if (!els.has(id)) els.set(id, { innerHTML: '', value: '', isConnected: true, style: {}, classList: {add(){}, remove(){}, toggle(){}}, focus(){}, addEventListener(type, fn) {this[type] = fn;} });
  return els.get(id);
}
const location = { get hash(){return currentHash;}, set hash(v){ if(v !== currentHash){currentHash = v; queue.push(()=>events.hashchange?.());}} };
const sandbox = { console, URL, Date, Blob, location, setTimeout:()=>0, clearTimeout(){}, FormData: class { constructor(target){this.data=target.data;} get(k){return this.data[k];} *[Symbol.iterator](){yield* Object.entries(this.data);} }, localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)}, window:{addEventListener:(k,v)=>events[k]=v,scrollTo(){}},document:{activeElement:element('focused'),body:{style:{}},getElementById:element,querySelectorAll:()=>[],querySelector:()=>element('query'),addEventListener(){},createElement:()=>({click(){}})}};
vm.createContext(sandbox); vm.runInContext(code,sandbox);
const run = s=>vm.runInContext(s,sandbox);
function submit(id,data) {element(id).submit({preventDefault(){},target:{data}});}
function flush(){while(queue.length)queue.shift()();}
let checks=0;
function check(name, fn){try{fn(); console.log('PASS '+name);checks++;}catch(e){console.error('FAIL '+name+': '+e.message);process.exitCode=1;}}
check('Every page renders',()=>{for(const p of ['overview','campaigns','content','calendar','opportunities','fans','commerce','revenue','agents','roster','integrations']){run(`page=${JSON.stringify(p)};shell()`);assert(element('app').innerHTML.includes('<main'));}});
check('All six campaign types render distinct relevant plans',()=>{const firstSteps=new Set();for(const type of ['Release rollout','Livestream growth','Merchandise drop','Brand partnerships','PR campaign','Always-on growth']){run(`state.campaigns.push({id:'typed',artist:'ralfy',name:'Typed plan',type:${JSON.stringify(type)},date:'2026-12-01',goal:'QA',status:'Draft',progress:0});campaignDetail('typed')`);let first=run(`campaignPlans[${JSON.stringify(type)}][0][0]`);firstSteps.add(first);assert(element('overlay').innerHTML.includes(first));run("state.campaigns=state.campaigns.filter(c=>c.id!=='typed')");}assert.equal(firstSteps.size,6);});
check('Draft campaign saves, activates, completes and persists',()=>{run("page='campaigns';location.hash='#campaigns'");flush();run('newCampaign()');submit('campaign-form',{name:'QA release',type:'Release rollout',date:'2026-12-01',goal:'Grow owned fans'});run("action('activate:'+state.campaigns[0].id)");assert.equal(run('state.campaigns[0].status'),'Active');run("action('complete:'+state.campaigns[0].id)");assert.equal(run('state.campaigns[0].status'),'Completed');assert(JSON.parse(storage.get('stinc-os-demo-v1')).campaigns.some(x=>x.name==='QA release'));});
check('Campaign created from overview retains review dialog after route event',()=>{run("page='overview';location.hash='#overview'");flush();run('newCampaign()');submit('campaign-form',{name:'QA from overview',type:'Release rollout',date:'2026-12-01',goal:'Grow fans'});flush();assert(element('overlay').innerHTML.includes('QA from overview'));});
check('Adding source creates three artist-specific candidates',()=>{const n=run('state.clips.length');run('addSource()');submit('source-form',{title:'QA live',url:'https://youtube.com/watch?v=qa',type:'YouTube video'});flush();assert.equal(run('state.clips.length'),n+3);assert(run("state.clips.slice(-3).every(x=>x.artist===state.artist&&x.url.includes('youtube.com'))"));});
check('Clip editing schedules and calendar renders then unschedules',()=>{run('clipDetail(state.clips.at(-1).id)');submit('clip-form',{hook:'QA hook',caption:'QA caption',platform:'TikTok',date:'2026-12-01',time:'19:30'});assert.equal(run('state.clips.at(-1).status'),'Scheduled');assert(run('calendar()').includes('19:30'));run("action('unschedule:'+state.clips.at(-1).id)");assert.equal(run('state.clips.at(-1).status'),'Needs review');});
check('Pitch saved and pipeline state persists',()=>{run("leadDetail('o1')");element('pitch').value='QA pitch';run("action('save-pitch:o1')");assert.equal(run("state.pitches.o1"),'QA pitch');assert.equal(run("state.leads[0].stage"),'Draft ready');});
check('Artist campaigns and content isolate correctly',()=>{run("state.artist='roster'");assert.equal(run('own(state.campaigns).length'),1);assert.equal(run('own(state.clips).length'),0);run("state.artist='ralfy'");});
check('Fan saved offer reopens selected',()=>{run('fanForm()');submit('fan-form',{headline:'QA fan',offer:'Merchandise early access',cta:'Join'});run('fanForm()');assert(/<option[^>]*selected[^>]*>Merchandise early access/.test(element('overlay').innerHTML));});
check('Fan capture and opportunities remain artist-specific',()=>{run("state.artist='roster';fanForm()");assert(!element('overlay').innerHTML.includes('QA fan'));assert(!run('opportunities()').includes('Independent streetwear partner'));run('newLead()');submit('lead-form',{name:'QA emerging partner',type:'Brands & partnerships',category:'Live',reason:'New audience fit'});assert(run('opportunities()').includes('QA emerging partner'));run("state.artist='ralfy'");assert(!run('opportunities()').includes('QA emerging partner'));});
check('Agent pause prevents task execution and resume restores it',()=>{run("action('toggle-agent:partnership')");let count=run('state.activity.length');run("action('run-agent:partnership')");assert.equal(run('state.activity.length'),count);run("action('toggle-agent:partnership');action('run-agent:partnership')");assert.equal(run('state.activity.length'),count+1);});
check('User-authored campaign markup is escaped in views',()=>{run("state.campaigns.push({id:'safe',artist:'ralfy',name:'<script>alert(1)</script>',type:'Release rollout',date:'2026-12-01',goal:'<img onerror=alert(1)>',status:'Draft',progress:0});filter='All'");const html=run('campaigns()');assert(html.includes('&lt;script&gt;'));assert(!html.includes('<script>alert'));});
check('Content and campaign status filters work',()=>{run("state.artist='ralfy';filter='Completed'");assert(run('campaigns()').includes('QA release'));assert(!run('campaigns()').includes('The next chapter'));run("filter='Scheduled'");assert(run('content()').includes('A moment for the day ones'));assert(!run('content()').includes('The story behind the record'));});
console.log(`${checks} checks passed`);
