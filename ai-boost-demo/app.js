const C=window.C||[];
const K={state:'aiBoost.v2.state',identity:'aiBoost.identity',legacy:'aiBoost.completedWorks'};
const $=id=>document.getElementById(id);
const today=()=>new Date().toISOString().slice(0,10);
const label={instagram:'Instagram',youtube:'YouTube'};
let filter='all',query='';
const platforms=c=>['instagram','youtube'].filter(p=>c[p]);
function blank(){return{version:2,subscriptions:{},history:{},migrations:{}}}
function save(s){s.updatedAt=new Date().toISOString();localStorage.setItem(K.state,JSON.stringify(s))}
function load(){
 let s=blank();
 try{const x=JSON.parse(localStorage.getItem(K.state)||'null');if(x)s={...s,...x,subscriptions:x.subscriptions||{},history:x.history||{},migrations:x.migrations||{}}}catch{}
 if(!s.migrations.legacy){
  const map={'ferixdi-instagram-profile-demo':'ferixdi:instagram','ferixdi-youtube-channel-demo':'ferixdi:youtube','ilya-instagram-profile-demo':'ilya:instagram','max-instagram-profile-demo':'max:instagram','max-youtube-channel-demo':'max:youtube','alex-instagram-profile-demo':'alex:instagram','alex-youtube-channel-demo':'alex:youtube'};
  try{JSON.parse(localStorage.getItem(K.legacy)||'[]').forEach(x=>{if(map[x])s.history[map[x]]=[...new Set([...(s.history[map[x]]||[]),today()])]})}catch{}
  s.migrations.legacy=true;save(s);
 }
 return s;
}
const me=()=>localStorage.getItem(K.identity)||'';
const key=(id,p)=>id+':'+p;
const done=(s,k)=>(s.history[k]||[]).includes(today());
function tasks(){return C.flatMap(c=>platforms(c).map(p=>({c,p,k:key(c.id,p)}))).filter(x=>x.c.id!==me())}
function requireIdentity(){if(me())return true;openProfile();toast('Найдите себя в списке');return false}
function mark(k){if(!requireIdentity())return;const s=load(),d=new Set(s.history[k]||[]);d.has(today())?d.delete(today()):d.add(today());s.history[k]=[...d].sort().slice(-365);save(s);render();toast(d.has(today())?'Поддержка сохранена':'Отметка снята')}
function sub(k){if(!requireIdentity())return;const s=load();s.subscriptions[k]=!s.subscriptions[k];save(s);render();toast(s.subscriptions[k]?'Подписка отмечена':'Отметка снята')}
function fmt(d){if(!d)return'никогда';return new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'short'}).format(new Date(d+'T12:00:00'))}
function platform(c,p,s){const k=key(c.id,p),d=done(s,k),h=s.history[k]||[],sb=!!s.subscriptions[k],x=c[p];return `<div class="platform ${d?'done':''}" data-task="${k}"><div class="platformTop"><div class="platformName"><span class="icon ${p==='instagram'?'ig':'yt'}">${p==='instagram'?'◉':'▶'}</span>${label[p]} <span class="muted">${x.handle}</span></div>${d?'<span class="badge">✓ Сегодня</span>':''}</div><div class="history">Поддержано дней: <b>${h.length}</b> · Последний раз: ${fmt(h.at(-1))}</div><div class="actions"><a class="open" href="${x.url}" target="_blank" rel="noopener">Открыть свежие</a><button class="support ${d?'active':''}" data-support="${k}">${d?'✓ Поддержал сегодня':'Поддержал сегодня'}</button></div><button class="subscribe ${sb?'active':''}" data-sub="${k}">${sb?'✓ Подписка отмечена':'Отметить, что подписан'}</button></div>`}
function match(c,s){const txt=[c.name,c.brand,...platforms(c).map(p=>c[p].handle)].join(' ').toLowerCase();if(!txt.includes(query.toLowerCase()))return false;if(c.id===me())return filter==='all';const a=platforms(c).map(p=>done(s,key(c.id,p)));if(filter==='todo'&&a.every(Boolean))return false;if(filter==='done'&&!a.every(Boolean))return false;return true}
function render(){
 const s=load(),m=me(),list=C.filter(c=>match(c,s));
 $('creators').innerHTML=list.length?list.map(c=>{const self=c.id===m;const handles=platforms(c).map(p=>c[p].handle).join(' · ');return `<article class="card creator ${self?'self':''}"><div class="creatorHead"><div class="creatorMain"><div class="avatar">${c.avatar}</div><div><div class="creatorName">${c.name}${c.brand?' · '+c.brand:''}</div><div class="handles">${handles}</div></div></div>${self?'<span class="badge">Это вы</span>':''}</div>${self?'<div class="selfNote">Это ваши аккаунты. Они не входят в ваш ежедневный план, но доступны для поддержки всем остальным участникам.</div>':`<div class="platforms">${platforms(c).map(p=>platform(c,p,s)).join('')}</div>`}</article>`}).join(''):'<div class="card empty">Ничего не найдено.</div>';
 document.querySelectorAll('[data-support]').forEach(b=>b.onclick=()=>mark(b.dataset.support));
 document.querySelectorAll('[data-sub]').forEach(b=>b.onclick=()=>sub(b.dataset.sub));
 const t=tasks(),n=t.filter(x=>done(s,x.k)).length,sc=t.filter(x=>s.subscriptions[x.k]).length,all=t.reduce((a,x)=>a+(s.history[x.k]||[]).length,0);
 $('done').textContent=n;$('total').textContent=t.length;$('fill').style.width=(t.length?n/t.length*100:0)+'%';$('subs').textContent=sc+'/'+t.length;$('alltime').textContent=all;
 const who=C.find(c=>c.id===m);$('identity').textContent=who?'Вы: '+who.name+(who.brand?' · '+who.brand:''):'Сначала найдите себя';$('headerName').textContent=who?who.name+(who.brand?' · '+who.brand:''):'Выбрать себя';$('date').textContent=new Intl.DateTimeFormat('ru-RU',{weekday:'long',day:'numeric',month:'long'}).format(new Date());
}
function openProfile(){$('identitySelect').value=me();$('modal').classList.remove('hidden');setTimeout(()=>$('identitySelect').focus(),50)}
function toast(x){$('toast').textContent=x;$('toast').classList.add('show');clearTimeout(window._tt);window._tt=setTimeout(()=>$('toast').classList.remove('show'),1600)}
C.forEach(c=>{const o=document.createElement('option');o.value=c.id;o.textContent=c.name+(c.brand?' · '+c.brand:'');$('identitySelect').appendChild(o)});
$('profileForm').onsubmit=e=>{e.preventDefault();const identity=$('identitySelect').value;if(!identity){toast('Найдите себя в списке');return}localStorage.setItem(K.identity,identity);$('modal').classList.add('hidden');render();const c=C.find(x=>x.id===identity);toast('Готово. Вы — '+c.name+(c.brand?' · '+c.brand:''))};
$('editProfile').onclick=openProfile;
$('search').oninput=e=>{query=e.target.value.trim();render()};
document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));render()});
$('next').onclick=()=>{if(!requireIdentity())return;const s=load(),x=tasks().find(t=>!done(s,t.k));if(!x)return toast('На сегодня всё выполнено 🚀');filter='todo';document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('active',b.dataset.filter==='todo'));render();setTimeout(()=>document.querySelector(`[data-task="${x.k}"]`)?.scrollIntoView({behavior:'smooth',block:'center'}),50)};
render();if(!me())openProfile();