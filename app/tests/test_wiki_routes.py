"""Actual Chat card -> parse -> wiki -> load -> saved/revisited route; layout only is stubbed.
Also: a slow earlier route never renders over the page opened after it (the real route() and views)."""
import html.parser,json,shutil,subprocess,unittest
from pathlib import Path
from urllib.parse import unquote
ROOT=Path(__file__).resolve().parents[2]
NODE=shutil.which('node')
HARNESS=r'''
const fs=require('fs'), app=fs.readFileSync(process.argv[1],'utf8'), chat=fs.readFileSync(process.argv[2],'utf8');
const inputs=JSON.parse(process.argv[3]);
const esc=eval(app.split('\n').find(x=>/^const esc\s*=/.test(x)).replace('const esc =',''));
const fileUrl=x=>x,ico=x=>'',clock=x=>String(x);
let hash='#/ask';const here=()=>hash;
const parse=new Function('here',app.slice(app.indexOf('function parse()'),app.indexOf('// The sidebar row'))+';return parse;')(here);
const cards=new Function('esc','fileUrl','ico','clock','here',chat.slice(chat.indexOf('  function srcHref('),chat.indexOf('  /* markdown-lite'))+';return srcCards;')(esc,fileUrl,ico,clock,here);
const wikiCode=app.slice(app.indexOf('async function wiki('),app.indexOf('// The address an encyclopedia'));
const decodeHTML=x=>x.replaceAll('&amp;','&').replaceAll('&quot;','"').replaceAll('&#39;',"'").replaceAll('&lt;','<').replaceAll('&gt;','>');
(async()=>{
 const output=[];
 for(const article of inputs){
  hash='#/ask';let replaced=null,remembered=null,load=null,firstSaved=null,lastSaved=null;
  const titleEl={textContent:''},toolbar={textContent:''},saved={innerHTML:''};
  const frame={isConnected:false,contentDocument:null,contentWindow:null,addEventListener:(n,f)=>{if(n==='load')load=f}};
  const main={innerHTML:'',classList:{toggle(){}}};
  const $=s=>({'#wframe':frame,'#wtitle':titleEl,'#wsave':saved,'#tbTitle':toolbar,'#wopen':null}[s]);
  const saveButton=i=>{firstSaved??=i;lastSaved=i;return ''};
  const history={replaceState:(a,b,url)=>{replaced=url;hash=url}};
  const fn=new Function('setTitle','zimLabel','zimMain','main','$','backButton','saveButton','esc','IN_WINDOW','window','scrolls','current','performance','history','remember','lookOf','tidyArticle','requestAnimationFrame','setTimeout',wikiCode+';return wiki;');
  const wiki=fn(t=>{titleEl.textContent=t},x=>x,()=>Promise.resolve('/zim/demo.zim/index'),main,$,()=>'',saveButton,esc,true,{}, {},'#test',{now:()=>0},history,i=>{remembered=i},()=>{},()=>null,()=>{},()=>{});
  try{
   const row={kind:'zim',key:'S1',title:article,zim:'zim/demo.zim/'+article,path:'zim/demo.zim/'+article.split('/').map(encodeURIComponent).join('/')};
   const card=cards([row],false);hash=decodeHTML(card.match(/href="([^"]+)"/)[1]);
   const parsed=parse();await wiki(parsed.parts.slice(1).join('/'),parsed.q.get('from'),null);
   const iframe=main.innerHTML.match(/<iframe[^>]+src="([^"]+)"/)[0]+'>',framePath=decodeHTML(iframe.match(/src="([^"]+)"/)[1]);
   const own={textContent:article.replaceAll('_',' '),getBoundingClientRect:()=>({bottom:10}),style:{setProperty(){}}};
   frame.contentDocument={title:own.textContent,getElementById:()=>({}),querySelector:()=>own};frame.contentWindow={location:{pathname:framePath},scrollY:0};
   await load();const again=parse();
   output.push({article,card,iframe,title:titleEl.textContent,framePath,firstSaved,lastSaved,remembered,replaced,revisited:again.parts.slice(1).join('/'),from:again.q.get('from')});
  }catch(e){output.push({article,error:e.name+': '+e.message})}
 }
 console.log(JSON.stringify(output));
})().catch(e=>{console.error(e);process.exit(1)});
'''
class Tags(html.parser.HTMLParser):
 def __init__(self):super().__init__();self.tags=[]
 def handle_starttag(self,tag,attrs):self.tags.append((tag,dict(attrs)))
@unittest.skipUnless(NODE,'needs Node')
class WikiRoutes(unittest.TestCase):
 def test_encoded_card_reader_and_revisit(self):
  articles=['Why?','100%_Juice','X"onmouseover="review','Literal%2FName','Folder/Why?','A&B#C']
  r=subprocess.run([NODE,'-e',HARNESS,str(ROOT/'web/app.js'),str(ROOT/'web/chat.js'),json.dumps(articles)],capture_output=True,text=True,encoding='utf-8',check=True)
  for row in json.loads(r.stdout):
   with self.subTest(article=row['article']):
    self.assertNotIn('error',row,row)
    a=row['article'];expected='demo.zim/'+a
    self.assertEqual(row['revisited'],expected);self.assertEqual(row['title'],a.replace('_',' '));self.assertEqual(row['from'],'#/ask')
    self.assertEqual(row['firstSaved']['href'],row['lastSaved']['href']);self.assertEqual(row['remembered']['href'],row['lastSaved']['href'])
    self.assertEqual(row['replaced'],row['lastSaved']['href']+'?from=%23%2Fask')
    self.assertEqual(unquote(row['framePath']),'/zim/'+expected)
    tags=Tags();tags.feed(row['card']+row['iframe'])
    card_attrs=next(a for n,a in tags.tags if n=='a')
    self.assertEqual(set(card_attrs),{'class','href','id','data-type'})
    self.assertEqual(card_attrs['data-type'],'wiki')
    self.assertEqual(set(next(a for n,a in tags.tags if n=='iframe')),{'class','id','title','src'})
 def test_malformed_encodings_are_not_silently_reinterpreted(self):
  app=(ROOT/'web/app.js').read_text(encoding='utf-8');parse=app[app.index('function parse()'):app.index('// The sidebar row')]
  script='const here=()=>process.argv[1];'+parse+';try{parse();process.stdout.write("accepted")}catch(e){process.stdout.write(e.name)}'
  for route in ('#/wiki/demo.zim/bad%','#/wiki/demo.zim/%GG','#/wiki/demo.zim/%C0%AF'):
   with self.subTest(route=route):
    r=subprocess.run([NODE,'-e',script,route],capture_output=True,text=True,encoding='utf-8',check=True);self.assertEqual(r.stdout,'URIError')
STALE_HARNESS=r'''
const fs=require('fs'),[app,chat,map]=process.argv.slice(1,4).map(f=>fs.readFileSync(f,'utf8'));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
// The text of the function (or one-line let/const) starting at the first line matching re; a function ends at the first indent+'}' line
function grab(text,re,indent=''){const L=text.split('\n'),i=L.findIndex(l=>re.test(l));if(i<0)return '';if(!/\{\s*(\/\/.*)?$/.test(L[i]))return L[i];let j=i+1;while(L[j]!==indent+'}')j++;return L.slice(i,j+1).join('\n')}
const any=()=>new Proxy(function(){},{get:(t,k)=>k===Symbol.toPrimitive?()=>'':k==='then'?undefined:any(),apply:()=>any(),construct:()=>any(),set:()=>true,has:()=>true});
// Runs code inside with(scope): a global the code reaches for that the case did not give is a do-nothing stand-in
function loadIn(code,over,ret){
 const own=new Set([...code.matchAll(/^(?:async )?(?:function|const|let)\s+([\w$]+)/gm)].map(m=>m[1]));   // the code's own top-level names
 const scope=new Proxy(over,{has:(t,k)=>typeof k==='string'&&(k in t||(!(k in globalThis)&&!own.has(k))),get:(t,k)=>k===Symbol.unscopables?undefined:k in t?t[k]:any(),set:(t,k,v)=>{t[k]=v;return true}});
 return new Function('scope',`with (scope) { ${code}\n return { ${ret} } }`)(scope);
}
// [name, address, view function in app.js (or ''), the stand-in it waits on first, what that wait answers, and optionally a
// pattern: then only the call whose first argument matches waits, and it fails; the others answer at once]
const CASES=[['home','#/guides','home','continueItems',[]],['videos','#/videos','videosHome','api',[]],['video row','#/videos/all','videoRow','api',{title:'T',items:[],total:0}],
 ['watch','#/watch/v1','watch','api',{title:'T',path:'p'}],['reader','#/read/d1','reader','api',{kind:'pdf',title:'T',path:'p'}],['encyclopedias','#/encyclopedias','encyclopedias','zimsHere',[]],
 ['library','#/library','library','zimsHere',[]],['shelf','#/shelf/s','shelfPage','api',[{id:'s',title:'S'}]],['collection','#/collection?name=n','collectionPage','api',{items:[],more:false}],
 ['saved','#/saved','savedPage','recents',[]],['not found','#/not-found','notFoundPage','api',{notes:[]}],['about','#/about','about','libInfo',{}],['chat','#/ask?about=x','','describe',{about:'doc:A:1'}],['map','#/map','','localHome',{}],['failing view','#/saved','','savedPage',null],
 ['watch, transcript fails','#/watch/v1','watch','api',{title:'T',path:'p'},/^\/api\/transcript\//]];   // wonderdawg on #444: A's failed transcript must not replace B's captions
(async()=>{
 const out=[];
 for(const [name,hash,view,gated,value,only] of CASES){
  let release;const gate=new Promise(r=>release=r),writes=[];
  const el=()=>new Proxy({},{set:(t,k)=>{if(k==='innerHTML'||k==='textContent')writes.push(k);return true},get:(t,k)=>k==='insertAdjacentHTML'?()=>writes.push(k):k==='then'?undefined:any()});
  const main=new Proxy({},{set:(t,k,v)=>{t[k]=v;if(k==='innerHTML')writes.push('main');return true},get:(t,k)=>k in t?t[k]:any()});
  const document={body:{className:''},activeElement:null,title:''};
  const over={main,document,hash:'',navStack:[],scrolls:{},current:null,swapping:false,navAt:0,navEnd:0,keepNav(){},_replace(){},history:{state:null,replaceState(){}},sessionStorage:{setItem(){}},
   here:()=>over.hash,topics:async()=>[],emptyState:(i,t)=>'ERR '+t,setTitle:()=>writes.push('title'),notFound(){},startHere(){},restoreScroll(){},requestAnimationFrame(){},scrollY:0,
   $:()=>el(),$$:()=>[],store:{get:(k,d)=>d,set(){}},prepareHub:async()=>{main.innerHTML='NEW'},
   [gated]:only?async p=>{if(!only.test(p))return value;await gate;throw new Error('gone')}:name==='failing view'?async()=>{await gate;throw new Error('gone')}:async()=>{await gate;return value}};
  const page=(src,re)=>`(() => { ${grab(src,re,'  ')}\n return page })()`;
  const code=[grab(app,/^let (routeSeq|leaving)\b/),grab(app,/^const stale\b/),grab(app,/^let searchSeq\b/),grab(app,/^function parse\(/),grab(app,/^async function route\(/),
   view?grab(app,new RegExp('^async function '+view+'\\(')):'',
   'const Chat = { page: '+page(chat,/^  async function page\(main, parts/)+', count: () => 0 };',
   'const MapView = { stop() { }, page: '+page(map,/^  async function page\(main, q/)+' };'].join('\n');
  const r=loadIn(code,over,'route');
  const go=h=>{over.hash=h;return r.route()};
  try{
   const a=go(hash);await sleep(5);   // the first page is under way, waiting on `gated`
   await go('#/prepare');writes.length=0;
   release();await a;await sleep(5);
   out.push({name,main:main.innerHTML,body:document.body.className,writes,aboutCtx:over.aboutCtx||null});   // chat.js's aboutCtx lands on `over`
  }catch(e){out.push({name,error:e.name+': '+e.message})}
 }
 console.log(JSON.stringify(out));
})().catch(e=>{console.error(e);process.exit(1)});
'''
@unittest.skipUnless(NODE,'needs Node')
class StaleRoutes(unittest.TestCase):
 def test_a_slow_earlier_page_does_not_render_over_a_newer_one(self):
  r=subprocess.run([NODE,'-e',STALE_HARNESS,*(str(ROOT/'web'/f) for f in ('app.js','chat.js','map.js'))],capture_output=True,text=True,encoding='utf-8',check=True)
  for row in json.loads(r.stdout):
   with self.subTest(view=row['name']):
    self.assertNotIn('error',row,row)
    self.assertEqual(row['main'],'NEW',row);self.assertEqual(row['body'],'v-prepare',row);self.assertEqual(row['writes'],[],row)
    self.assertIsNone(row['aboutCtx'],row)   # Codex on #444: a stale chat must not hand its document to the chat now open
if __name__=='__main__':unittest.main()
