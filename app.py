"""app.py v4.3 - Multi-threaded, preload, notes highlight"""
import json, os, sys, urllib.parse, traceback, base64, time as _time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from datetime import datetime, timedelta

# ── Timezone: luôn chạy theo giờ Việt Nam (UTC+7) ──────────────────────────
if hasattr(_time, 'tzset'):
    os.environ['TZ'] = os.environ.get('APP_TZ', 'Asia/Ho_Chi_Minh')
    _time.tzset()

sys.path.insert(0, os.path.dirname(__file__))
from modules import db, fetcher, translator, exporter
from modules.scheduler import Scheduler, load_config, save_config

db.init_db()

def do_fetch(date, label, cutoff_hour=None, count_per_topic=3, use_wayback=None):
    cfg = load_config()
    if count_per_topic is None: count_per_topic = cfg.get('articles_per_topic_per_fetch', 3)
    today = datetime.now().strftime('%Y-%m-%d')
    if date > today: return 0
    sid, sno = db.create_session(date, label)
    existing = db.get_existing_urls(date)
    global_urls = db.get_all_urls()
    try:
        articles = fetcher.fetch_news(date, existing, count_per_topic=count_per_topic,
                                       cutoff_hour=cutoff_hour, global_urls=global_urls,
                                       use_wayback=use_wayback)
        if cfg.get('auto_translate', True): articles = translator.translate_articles(articles)
        added = db.save_articles(articles, sid, sno)
        db.update_session_count(sid, added)
        db.log_fetch(date, sno, 'success', added)
        wb_tag = ' [Wayback]' if use_wayback else ''
        print(f"[Fetch] {date} #{sno} '{label}'{wb_tag}: {added} bài")
        return added
    except Exception as e:
        db.log_fetch(date, sno, 'error', 0, str(e))
        traceback.print_exc()
        return 0

def do_cleanup():
    db.cleanup_old(load_config().get('keep_days', 30))

scheduler = Scheduler(do_fetch, do_cleanup)

HTML = r'''<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NewsReader v4</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@300;400;500;600;700;800&display=swap');
:root{--bg:#0c0f1a;--bg2:#141829;--bg3:#1c2038;--bg4:#252a45;--text:#e2e8f0;--text2:#94a3b8;--text3:#64748b;--accent:#6366f1;--accent2:#818cf8;--green:#10b981;--green2:#059669;--red:#ef4444;--orange:#f59e0b;--blue:#3b82f6;--cyan:#06b6d4;--border:#2a2f4a;--radius:12px;--shadow:0 4px 24px rgba(0,0,0,0.3);}
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:'Be Vietnam Pro',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;}
::-webkit-scrollbar{width:6px;} ::-webkit-scrollbar-track{background:var(--bg2);} ::-webkit-scrollbar-thumb{background:var(--bg4);border-radius:3px;}

.header{background:linear-gradient(135deg,var(--bg2),var(--bg3));border-bottom:1px solid var(--border);padding:12px 20px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;}
.header h1{font-size:18px;font-weight:800;background:linear-gradient(135deg,var(--accent2),var(--cyan));-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.hc{display:flex;gap:8px;align-items:center;flex-wrap:wrap;}
.btn{background:var(--bg3);color:var(--text2);border:1px solid var(--border);padding:7px 13px;border-radius:8px;cursor:pointer;font-size:12px;font-family:inherit;transition:all .2s;}
.btn:hover{background:var(--bg4);color:var(--text);}
.btn-p{background:var(--accent);color:#fff;border-color:var(--accent);}
.btn-p:hover{background:var(--accent2);}
.btn-g{background:var(--green2);color:#fff;border-color:var(--green2);}
.btn-sm{padding:4px 9px;font-size:11px;}
.fs{font-size:11px;color:var(--text3);padding:3px 9px;background:var(--bg3);border-radius:16px;}
.fs.ld{color:var(--orange);}

/* Calendar */
.cw{position:relative;}
.ct{background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:7px 14px;border-radius:8px;cursor:pointer;font-family:inherit;font-size:13px;font-weight:600;display:flex;align-items:center;gap:6px;min-width:150px;justify-content:center;}
.ct:hover{border-color:var(--accent);}
.cd{display:none;position:absolute;top:calc(100% + 4px);right:0;background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:14px;z-index:200;box-shadow:var(--shadow);min-width:290px;}
.cd.open{display:block;}
.ch{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;}
.ch span{font-size:13px;font-weight:700;}
.ch button{background:transparent;border:none;color:var(--text2);cursor:pointer;font-size:16px;padding:2px 6px;border-radius:4px;}
.ch button:hover{background:var(--bg3);}
.cg{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;text-align:center;}
.cg .dl{font-size:10px;color:var(--text3);padding:4px 0;font-weight:600;}
.cg .dy{font-size:12px;padding:7px 3px;border-radius:5px;cursor:pointer;color:var(--text2);transition:all .15s;}
.cg .dy:hover{background:var(--bg4);color:var(--text);}
.cg .dy.td{border:1px solid var(--accent);color:var(--accent2);}
.cg .dy.sel{background:var(--accent);color:#fff;font-weight:700;}
.cg .dy.om{color:var(--bg4);cursor:default;} .cg .dy.om:hover{background:transparent;}
.cg .dy.fu{color:var(--bg4);cursor:not-allowed;opacity:.4;} .cg .dy.fu:hover{background:transparent;}
.cg .dy.hd::after{content:'';display:block;width:4px;height:4px;background:var(--green);border-radius:50%;margin:1px auto 0;}

.tabs{display:flex;gap:2px;padding:6px 20px;background:var(--bg2);border-bottom:1px solid var(--border);overflow-x:auto;}
.tab{padding:9px 16px;cursor:pointer;border-radius:7px 7px 0 0;font-size:12px;font-weight:500;color:var(--text3);transition:all .2s;border:1px solid transparent;border-bottom:none;white-space:nowrap;}
.tab:hover{color:var(--text2);background:var(--bg3);}
.tab.active{color:var(--accent2);background:var(--bg3);border-color:var(--border);font-weight:600;}

.content{padding:16px 20px;max-width:1400px;margin:0 auto;}
.panel{display:none;}.panel.active{display:block;}

/* Dashboard */
.dg{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:18px;}
.sc{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:14px;text-align:center;transition:transform .2s;}
.sc:hover{transform:translateY(-2px);}
.sc .n{font-size:26px;font-weight:800;}
.sc .l{font-size:10px;color:var(--text3);margin-top:3px;text-transform:uppercase;letter-spacing:.5px;}
.sc.intl .n{color:var(--blue);} .sc.vn .n{color:var(--green);} .sc.fin .n{color:var(--cyan);}
.sc.pol .n{color:var(--accent2);} .sc.tech .n{color:var(--orange);} .sc.hot .n{color:var(--red);}
.sc.total .n{color:var(--text);}
.ib{display:flex;gap:4px;align-items:flex-end;height:55px;margin-top:6px;}
.ib .bar{flex:1;border-radius:3px 3px 0 0;position:relative;}
.ib .bar span{position:absolute;top:-16px;left:50%;transform:translateX(-50%);font-size:10px;color:var(--text3);}

/* Collapsible topic groups */
.tg{margin-bottom:16px;background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;}
.tg-head{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;cursor:pointer;user-select:none;transition:background .2s;}
.tg-head:hover{background:var(--bg3);}
.tg-head .left{display:flex;align-items:center;gap:8px;}
.tg-head .badge{font-size:11px;padding:3px 10px;border-radius:16px;font-weight:600;}
.badge-fin{background:rgba(6,182,212,.15);color:var(--cyan);}
.badge-pol{background:rgba(129,140,248,.15);color:var(--accent2);}
.badge-tech{background:rgba(245,158,11,.15);color:var(--orange);}
.badge-gen{background:rgba(100,116,139,.15);color:var(--text3);}
.tg-head .count{font-size:11px;color:var(--text3);}
.tg-head .arrow{color:var(--text3);font-size:14px;transition:transform .2s;}
.tg-head.open .arrow{transform:rotate(180deg);}
.tg-body{display:none;padding:0 12px 12px;}
.tg-body.open{display:block;}

/* Article card */
.ac{background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:8px;transition:all .2s;position:relative;}
.ac:hover{border-color:var(--accent);transform:translateX(3px);}
.ac.read{opacity:.7;} .ac.read::before{content:'✓';position:absolute;top:8px;right:12px;color:var(--green);font-size:12px;font-weight:700;}
.ac .ti{font-weight:600;font-size:13px;line-height:1.5;color:var(--text);}
.ac .tv{font-size:12px;color:var(--accent2);margin-top:3px;}
.ac .de{font-size:12px;color:var(--text2);margin-top:6px;line-height:1.6;max-height:none;}
.ac .meta{display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap;}
.ac .meta span{font-size:11px;color:var(--text3);}
.ac .meta .src{font-weight:600;color:var(--text2);}
.ac .stars{color:var(--orange);font-size:12px;}
.ac .acts{display:flex;gap:4px;margin-left:auto;}
.ac .acts button{background:var(--bg4);border:1px solid var(--border);color:var(--text2);padding:4px 9px;border-radius:6px;cursor:pointer;font-size:11px;font-family:inherit;transition:all .15s;}
.ac .acts button:hover{background:var(--accent);color:#fff;border-color:var(--accent);}

/* Reader */
.ro{display:none;position:fixed;inset:0;z-index:999;background:rgba(0,0,0,.7);backdrop-filter:blur(4px);}
.ro.open{display:flex;justify-content:center;align-items:start;padding-top:24px;}
.rp{background:var(--bg);width:92%;max-width:880px;max-height:calc(100vh - 48px);border-radius:14px;border:1px solid var(--border);overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.5);}
.rh{position:sticky;top:0;background:var(--bg2);padding:12px 18px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;z-index:2;}
.rh h2{font-size:14px;font-weight:700;flex:1;margin-right:10px;}
.rx{background:var(--bg3);border:1px solid var(--border);color:var(--text2);width:32px;height:32px;border-radius:8px;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.rx:hover{background:var(--red);color:#fff;}
.rb{padding:20px;}
.rb .pr{margin-bottom:14px;}
.rb .pe{font-size:15px;line-height:1.8;color:var(--text);margin-bottom:4px;}
.rb .pv{font-size:14px;line-height:1.7;color:var(--accent2);font-style:italic;padding-left:12px;border-left:3px solid var(--accent);}
.rb img{max-width:100%;border-radius:8px;margin:8px 0;}
.rl{text-align:center;padding:45px;color:var(--text3);font-size:13px;}
.rl .sp{width:32px;height:32px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin 1s linear infinite;margin:0 auto 12px;}
@keyframes spin{to{transform:rotate(360deg);}}

/* Vocab highlight in reader */
.rb .vocab-hl{background:rgba(250,204,21,.35);border-radius:3px;padding:0 2px;color:#fef9c3;}
.rb .vocab-note{background:rgba(239,68,68,.45);border-radius:3px;padding:0 2px;color:#fecaca;border-bottom:2px solid #ef4444;}
.rb .pv .vocab-hl{background:rgba(250,204,21,.3);color:#fef08a;}
.rb .pv .vocab-note{background:rgba(239,68,68,.4);color:#fecaca;border-bottom:2px solid #ef4444;}
.rb .vocab-num{font-size:9px;font-weight:700;vertical-align:super;margin-left:2px;opacity:.85;letter-spacing:.3px;}

.vp{display:none;position:fixed;z-index:1001;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:7px;box-shadow:var(--shadow);}
.vp.open{display:flex;gap:5px;}
.vp button{padding:4px 10px;border-radius:6px;border:1px solid var(--border);font-size:11px;font-family:inherit;cursor:pointer;}
.vp .bt{background:var(--green2);color:#fff;} .vp .bh{background:var(--orange);color:#fff;}

/* Vocab list */
.vi{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:11px;margin-bottom:7px;display:flex;align-items:center;gap:12px;}
.vi .og{font-weight:600;color:var(--text);flex:1;font-size:13px;}
.vi .tr{color:var(--text2);flex:1;font-size:12px;}
.vi .tb{font-size:10px;padding:2px 7px;border-radius:16px;font-weight:600;}
.td{background:rgba(16,185,129,.1);color:var(--green);}
.tc{background:rgba(245,158,11,.1);color:var(--orange);}
.tc-note{background:rgba(239,68,68,.15);color:var(--red);}
.vi .db{background:transparent;border:none;color:var(--text3);cursor:pointer;font-size:15px;padding:3px;}
.vi .db:hover{color:var(--red);}
.ve{text-align:center;padding:36px;color:var(--text3);}

#notesArea{width:100%;min-height:180px;background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);color:var(--text);padding:14px;font-size:13px;line-height:1.7;font-family:inherit;resize:vertical;}
#notesArea:focus{outline:none;border-color:var(--accent);}
.sg{background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:18px;margin-bottom:14px;}
.sg h3{font-size:14px;font-weight:700;margin-bottom:12px;}
.sr{display:flex;align-items:center;gap:10px;margin-bottom:10px;}
.sr label{font-size:12px;color:var(--text2);min-width:140px;}
.sr input[type="text"],.sr input[type="number"]{background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:7px 10px;border-radius:8px;font-family:inherit;font-size:12px;}
.sr input:focus{outline:none;border-color:var(--accent);}

.toast{position:fixed;bottom:20px;right:20px;z-index:9999;background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius);padding:10px 18px;color:var(--text);font-size:12px;box-shadow:var(--shadow);transform:translateY(80px);opacity:0;transition:all .3s;}
.toast.show{transform:translateY(0);opacity:1;}
.toast.success{border-left:4px solid var(--green);}
.toast.error{border-left:4px solid var(--red);}

@media(max-width:768px){.header{padding:8px 12px;flex-wrap:wrap;gap:6px;}.content{padding:10px 12px;}.tabs{padding:6px 12px;}.dg{grid-template-columns:repeat(2,1fr);}.rp{width:98%;}.cd{right:-30px;min-width:270px;}}
</style>
</head>
<body>

<div class="header">
  <h1>📰 NewsReader v4</h1>
  <div class="hc">
    <span class="fs" id="fs">Sẵn sàng</span>
    <div class="cw">
      <button class="ct" id="calT" onclick="togCal()">📅 <span id="dd"></span></button>
      <div class="cd" id="calD">
        <div class="ch"><button onclick="calN(-1)">‹</button><span id="calM"></span><button onclick="calN(1)">›</button></div>
        <div class="cg" id="calG"></div>
      </div>
    </div>
    <button class="btn btn-p" onclick="fetchNow()">⟳ Cập nhật</button>
    <button class="btn" id="waybackBtn" onclick="fetchWayback()" title="Lấy tin từ archive.org cho ngày quá khứ" style="display:none;">🕰️ Lịch sử</button>
    <button class="btn btn-g" onclick="exportExcel()">📊 Excel</button>
    <button class="btn" onclick="exportWord()">📄 Word</button>
  </div>
</div>

<div class="tabs">
  <div class="tab active" data-tab="dashboard" onclick="sTab('dashboard')">📊 Dashboard</div>
  <div class="tab" data-tab="intl" onclick="sTab('intl')">🌍 Quốc tế</div>
  <div class="tab" data-tab="vn" onclick="sTab('vn')">🇻🇳 Việt Nam</div>
  <div class="tab" data-tab="vocab" onclick="sTab('vocab')">📝 Từ vựng</div>
  <div class="tab" data-tab="notes" onclick="sTab('notes')">📒 Ghi chú</div>
  <div class="tab" data-tab="settings" onclick="sTab('settings')">⚙️ Cài đặt</div>
</div>

<div class="content">
  <div class="panel active" id="panel-dashboard">
    <div class="dg" id="dS"></div><div id="dC"></div>
    <h3 style="margin:14px 0 8px;color:var(--text2);font-size:14px;">🔥 Tin nổi bật</h3>
    <div id="dH"></div>
  </div>
  <div class="panel" id="panel-intl"><div id="intlA"></div></div>
  <div class="panel" id="panel-vn"><div id="vnA"></div></div>
  <div class="panel" id="panel-vocab">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
      <h3 style="color:var(--text2);font-size:14px;">📝 Từ vựng ngày <span id="vD"></span></h3>
      <button class="btn btn-sm btn-g" onclick="exportVocab()">📥 Xuất Excel</button>
    </div>
    <p style="font-size:11px;color:var(--text3);margin-bottom:12px;">Chọn từ trong bài đọc song ngữ → lưu dịch/chú ý. Từ sẽ được highlight khi mở lại bài.</p>
    <div id="vL"></div>
  </div>
  <div class="panel" id="panel-notes">
    <h3 style="margin-bottom:10px;color:var(--text2);font-size:14px;">📒 Ghi chú ngày <span id="nD"></span></h3>
    <textarea id="notesArea" placeholder="Nhập ghi chú..."></textarea>
    <div style="margin-top:8px;text-align:right;"><button class="btn btn-p" onclick="saveNote()">💾 Lưu</button></div>
  </div>
  <div class="panel" id="panel-settings">
    <div class="sg"><h3>⏰ Mốc tự động</h3><p style="font-size:11px;color:var(--text3);margin-bottom:10px;">Lỡ mốc → mốc sau bù.</p><div id="fSlots"></div><button class="btn btn-sm" onclick="addSlot()">+ Thêm mốc</button></div>
    <div class="sg"><h3>📰 Số tin</h3><div class="sr"><label>Bài / chủ đề / mốc:</label><input type="number" id="cA" min="1" max="20" value="3" style="width:70px;"></div></div>
    <div class="sg"><h3>🔧 Khác</h3><div class="sr"><label>Tự dịch:</label><input type="checkbox" id="cT" checked></div><div class="sr"><label>Giữ dữ liệu (ngày):</label><input type="number" id="cK" min="1" max="365" value="30" style="width:70px;"></div><div class="sr"><label>Port:</label><input type="number" id="cP" min="1024" max="65535" value="8765" style="width:90px;"></div></div>
    <button class="btn btn-p" onclick="saveCfg()">💾 Lưu cài đặt</button>
  </div>
</div>

<div class="ro" id="ro" onclick="crBg(event)">
  <div class="rp"><div class="rh"><h2 id="rT">...</h2><button class="rx" onclick="cr()">✕</button></div><div class="rb" id="rB"><div class="rl"><div class="sp"></div>Đang tải...</div></div></div>
</div>
<div class="vp" id="vPop"><button class="bt" onclick="svV('translate')">📖 Lưu từ vựng</button><button class="bh" onclick="saveNote_sel()">📝 Ghi chú</button></div>
<div class="toast" id="toast"></div>

<script>
let cD=new Date().toISOString().slice(0,10), cVY, cVM;
let arts=[], voc=[], aDates=new Set(), rUrl='', selTxt='';
let contentCache={}; // url→{title,paragraphs,paragraphs_vi,images}

document.addEventListener('DOMContentLoaded',()=>{
  const n=new Date(); cVY=n.getFullYear(); cVM=n.getMonth();
  uDD(); loadDay(); loadCfg(); loadDates();
  document.addEventListener('click',e=>{if(!e.target.closest('.cw'))document.getElementById('calD').classList.remove('open');});
});

// Calendar
function togCal(){const d=document.getElementById('calD');d.classList.toggle('open');if(d.classList.contains('open'))rCal();}
function calN(d){cVM+=d;if(cVM>11){cVM=0;cVY++;}if(cVM<0){cVM=11;cVY--;}rCal();}
async function loadDates(){try{const r=await fetch('/api/dates');aDates=new Set(await r.json());}catch(e){}}
function rCal(){
  const ms=['Tháng 1','Tháng 2','Tháng 3','Tháng 4','Tháng 5','Tháng 6','Tháng 7','Tháng 8','Tháng 9','Tháng 10','Tháng 11','Tháng 12'];
  document.getElementById('calM').textContent=`${ms[cVM]} ${cVY}`;
  const today=new Date().toISOString().slice(0,10), first=new Date(cVY,cVM,1), sd=first.getDay(), dim=new Date(cVY,cVM+1,0).getDate(), pdm=new Date(cVY,cVM,0).getDate();
  let h=['CN','T2','T3','T4','T5','T6','T7'].map(d=>`<div class="dl">${d}</div>`).join('');
  for(let i=sd-1;i>=0;i--)h+=`<div class="dy om">${pdm-i}</div>`;
  for(let d=1;d<=dim;d++){
    const ds=`${cVY}-${String(cVM+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const iT=ds===today,iS=ds===cD,iF=ds>today,iD=aDates.has(ds);
    let c='dy';if(iT)c+=' td';if(iS)c+=' sel';if(iF)c+=' fu';if(iD)c+=' hd';
    h+=`<div class="${c}" onclick="${iF?'':`selD('${ds}')`}">${d}</div>`;
  }
  const tc=sd+dim,rm=(7-(tc%7))%7;for(let i=1;i<=rm;i++)h+=`<div class="dy om">${i}</div>`;
  document.getElementById('calG').innerHTML=h;
}
function selD(ds){const t=new Date().toISOString().slice(0,10);if(ds>t)return;cD=ds;uDD();loadDay();document.getElementById('calD').classList.remove('open');const d=new Date(ds);cVY=d.getFullYear();cVM=d.getMonth();}
function uDD(){
  document.getElementById('dd').textContent=cD;document.getElementById('vD').textContent=cD;document.getElementById('nD').textContent=cD;
  // Show Wayback button only for past dates
  const today=new Date().toISOString().slice(0,10);
  const wb=document.getElementById('waybackBtn');
  if(wb){
    const daysAgo=Math.floor((new Date(today)-new Date(cD))/(1000*60*60*24));
    wb.style.display=(cD<today && daysAgo>=1)?'':'none';
    wb.textContent=daysAgo>7?`🕰️ Lịch sử (${daysAgo}d)`:'🕰️ Lịch sử';
  }
}

function sTab(n){document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.tab===n));document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.id==='panel-'+n));}

async function loadDay(){
  try{const r=await fetch('/api/day?date='+cD),d=await r.json();arts=d.articles||[];voc=d.vocab||[];
    rDash(d);rArts(arts.filter(a=>a.category==='international'),'intlA');rArts(arts.filter(a=>a.category==='vietnam'),'vnA');rVoc(voc);document.getElementById('notesArea').value=d.notes||'';
    // Pre-load article content in background
    preloadArticles();
  }catch(e){toast('Lỗi: '+e.message,'error');}
}

// Pre-load article content in parallel (3 at a time)
async function preloadArticles(){
  const urls=arts.filter(a=>a.url&&!contentCache[a.url]).map(a=>a.url);
  const batch=3;
  for(let i=0;i<urls.length;i+=batch){
    const chunk=urls.slice(i,i+batch);
    await Promise.allSettled(chunk.map(async url=>{
      try{
        const r=await fetch('/api/reader?url='+encodeURIComponent(url));
        const data=await r.json();
        if(data.success)contentCache[url]=data;
      }catch(e){}
    }));
  }
}

// Dashboard
function rDash(d){
  const a=d.articles||[],intl=a.filter(x=>x.category==='international'),vn=a.filter(x=>x.category==='vietnam');
  const fin=a.filter(x=>x.topic==='finance'),pol=a.filter(x=>x.topic==='politics'),tech=a.filter(x=>x.topic==='tech_ai');
  const hot=a.filter(x=>(x.importance||3)>=4),imp=[0,0,0,0,0];a.forEach(x=>{const i=(x.importance||3)-1;if(i>=0&&i<5)imp[i]++;});
  const mx=Math.max(...imp,1);
  document.getElementById('dS').innerHTML=`
    <div class="sc total"><div class="n">${a.length}</div><div class="l">Tổng</div></div>
    <div class="sc intl"><div class="n">${intl.length}</div><div class="l">Quốc tế</div></div>
    <div class="sc vn"><div class="n">${vn.length}</div><div class="l">Việt Nam</div></div>
    <div class="sc fin"><div class="n">${fin.length}</div><div class="l">Tài chính</div></div>
    <div class="sc pol"><div class="n">${pol.length}</div><div class="l">Chính trị</div></div>
    <div class="sc tech"><div class="n">${tech.length}</div><div class="l">AI & Tech</div></div>
    <div class="sc hot"><div class="n">${hot.length}</div><div class="l">🔥 Nổi bật</div></div>
    <div class="sc"><div class="n">${a.filter(x=>(x.importance||3)===3).length}</div><div class="l">Đáng đọc</div></div>`;
  const cols=['#64748b','#3b82f6','#06b6d4','#f59e0b','#ef4444'],labs=['Thấp','BT','Đáng đọc','Quan trọng','Rất QT'];
  document.getElementById('dC').innerHTML=`<div style="background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:14px;margin-bottom:14px;"><h4 style="font-size:12px;color:var(--text2);margin-bottom:8px;">📊 Phân bố mức độ</h4><div class="ib">${imp.map((c,i)=>`<div class="bar" style="height:${Math.max(4,c/mx*100)}%;background:${cols[i]};"><span>${c}</span></div>`).join('')}</div><div style="display:flex;justify-content:space-around;margin-top:6px;">${labs.map((l,i)=>`<span style="font-size:9px;color:${cols[i]};">${l}</span>`).join('')}</div></div>`;
  const ha=a.filter(x=>(x.importance||3)>=4).sort((a,b)=>(b.importance||3)-(a.importance||3));
  document.getElementById('dH').innerHTML=ha.length?ha.map(x=>acHtml(x)).join(''):'<p style="color:var(--text3);font-size:12px;">Chưa có tin nổi bật</p>';
}

// Collapsible article groups
function rArts(ar,cid){
  const el=document.getElementById(cid);
  if(!ar.length){el.innerHTML='<p style="color:var(--text3);text-align:center;padding:36px;">Chưa có bài</p>';return;}
  const bt={};ar.forEach(a=>{(bt[a.topic]=bt[a.topic]||[]).push(a);});
  const tn={finance:'💰 Tài chính',politics:'🏛️ Chính trị',tech_ai:'🤖 AI & Tech',general:'📋 Chung'};
  const bc={finance:'badge-fin',politics:'badge-pol',tech_ai:'badge-tech',general:'badge-gen'};
  let h='';
  for(const[topic,items]of Object.entries(bt)){
    const sorted=items.sort((a,b)=>(b.importance||3)-(a.importance||3));
    const tid=cid+'_'+topic;
    h+=`<div class="tg">
      <div class="tg-head open" onclick="togTG('${tid}')">
        <div class="left"><span class="badge ${bc[topic]||'badge-gen'}">${tn[topic]||topic}</span><span class="count">${items.length} bài</span></div>
        <span class="arrow">▼</span>
      </div>
      <div class="tg-body open" id="${tid}">${sorted.map(a=>acHtml(a)).join('')}</div>
    </div>`;
  }
  el.innerHTML=h;
}
function togTG(id){const b=document.getElementById(id),h=b.previousElementSibling;b.classList.toggle('open');h.classList.toggle('open');}

function acHtml(a){
  const imp=a.importance||3,stars='★'.repeat(imp)+'☆'.repeat(5-imp),cat=a.category==='international'?'🌍':'🇻🇳';
  const rd=a.is_read?'read':'';
  const desc=a.description||'';
  const descVi=a.description_vi||'';
  const showDesc=a.category==='international'?(descVi||desc):desc;
  return`<div class="ac ${rd}"><div class="ti">${cat} ${esc(a.title)}</div>${a.title_vi&&a.category==='international'?`<div class="tv">→ ${esc(a.title_vi)}</div>`:''} ${showDesc?`<div class="de">${esc(showDesc).slice(0,350)}</div>`:''}<div class="meta"><span class="src">${esc(a.source||'')}</span><span class="stars">${stars}</span><span>S#${a.session_no||1}</span><div class="acts"><button onclick="openArt(${a.id})">📖 Đọc</button><button onclick="rate(${a.id},${Math.min(5,imp+1)})">👍</button><button onclick="rate(${a.id},${Math.max(1,imp-1)})">👎</button><button onclick="openLink(${a.id})">🔗</button></div></div></div>`;
}
function openArt(id){const a=arts.find(x=>x.id===id);if(a&&a.url)oR(a.url,a.title,a.id);}
function openLink(id){const a=arts.find(x=>x.id===id);if(a&&a.url)window.open(a.url,'_blank');}
function esc(s){return(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}

// Reader with cache + vocab highlighting
async function oR(url,title,aid){
  if(!url)return;
  rUrl=url;
  const artObj=arts.find(x=>x.id===aid);
  const artCat=artObj?artObj.category:'international';
  document.getElementById('ro').classList.add('open');
  document.getElementById('rT').textContent=title||'Đang tải...';
  // Mark as read
  if(aid)fetch('/api/read',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:aid})}).catch(()=>{});

  // Check cache first
  if(contentCache[url]){
    renderReader(contentCache[url],artCat);
    return;
  }
  document.getElementById('rB').innerHTML=`<div class="rl"><div class="sp"></div>Đang tải bài viết...</div>`;
  try{
    const r=await fetch('/api/reader?url='+encodeURIComponent(url));
    const data=await r.json();
    if(!data.success)throw new Error(data.error||'Không tải được');
    contentCache[url]=data;
    renderReader(data,artCat);
  }catch(e){
    document.getElementById('rB').innerHTML=`<div style="text-align:center;padding:36px;color:var(--text3);"><p>⚠️ ${esc(e.message)}</p><p style="margin-top:10px;"><a href="${esc(url)}" target="_blank" style="color:var(--accent2);">🔗 Mở trong trình duyệt</a></p></div>`;
  }
}

function renderReader(data,artCat){
  document.getElementById('rT').textContent=data.title||'';
  const vocWords=voc.filter(v=>v.article_url===rUrl);
  const isVN=artCat==='vietnam';
  let h='';
  if(data.fallback_msg)h+=`<div style="background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3);border-radius:8px;padding:10px 14px;margin-bottom:14px;font-size:12px;color:var(--orange);">⚠️ ${esc(data.fallback_msg)}</div>`;
  if(data.images&&data.images.length>0)h+=`<img src="${esc(data.images[0].src)}" alt="" onerror="this.style.display='none'">`;
  const paras=data.paragraphs||[];
  const parasVi=data.paragraphs_vi||[];
  // Global counter so each highlight cluster has a unique number across the whole article
  let clusterNum=0;
  for(let i=0;i<paras.length;i++){
    const p=paras[i]||{};
    const vi=parasVi[i]||null;
    const pText=p.text||'';
    const tag=p.tag||'p';
    const hd=(tag==='h2'||tag==='h3')?' style="font-weight:700;font-size:16px;margin-top:14px;"':'';
    // Only vocab entries that were saved FROM this paragraph (or legacy -1 = unknown → show everywhere)
    const paraVocabs=vocWords.filter(v=>{
      const pi=(v.paragraph_index==null)?-1:v.paragraph_index;
      return pi===i||pi===-1;
    });
    // Assign a number to each vocab entry in this paragraph
    const numbered=paraVocabs.map(v=>({...v, _num: ++clusterNum}));
    const enHtml=hlText(esc(pText), numbered, false);
    const viHtml=vi?hlText(esc(vi.text||''), numbered, true):'';
    if(isVN){
      h+=`<div class="pr" data-pi="${i}"><div class="pe"${hd}>${enHtml}</div></div>`;
    }else{
      h+=`<div class="pr" data-pi="${i}"><div class="pe"${hd}>${enHtml}</div>${viHtml?`<div class="pv">${viHtml}</div>`:''}</div>`;
    }
  }
  h+=`<div style="margin-top:18px;padding-top:12px;border-top:1px solid var(--border);text-align:center;"><a href="${esc(data.url||rUrl)}" target="_blank" style="color:var(--accent2);font-size:12px;">🔗 Mở bài gốc</a></div>`;
  document.getElementById('rB').innerHTML=h;
}

// Highlight helper: position-based, no nesting, first-occurrence per vocab.
// text: HTML-escaped plain text. vocabs: list with _num. useTranslated: highlight translated_text (for Vietnamese version).
function hlText(text, vocabs, useTranslated){
  if(!vocabs.length)return text;
  const matches=[];
  for(const v of vocabs){
    const rawWord=useTranslated?(v.translated_text||''):(v.original_text||'');
    if(!rawWord||rawWord.trim().length<2)continue;
    // Escape the search word and also escape it the same way as the text
    const escWord=esc(rawWord.trim());
    const re=new RegExp(escRe(escWord),'i');
    const m=text.match(re);
    if(m&&m.index>=0){
      matches.push({start:m.index, end:m.index+m[0].length, vocab:v});
    }
  }
  if(!matches.length)return text;
  // Sort by position; drop overlaps (keep earliest)
  matches.sort((a,b)=>a.start-b.start);
  const clean=[];let lastEnd=0;
  for(const m of matches){
    if(m.start>=lastEnd){clean.push(m);lastEnd=m.end;}
  }
  // Build output
  let out='';let pos=0;
  for(const m of clean){
    out+=text.substring(pos,m.start);
    const cls=m.vocab.type==='note'?'vocab-note':'vocab-hl';
    const tip=esc(m.vocab.translated_text||m.vocab.original_text||'');
    out+=`<span class="${cls}" title="${tip}">${text.substring(m.start,m.end)}<sup class="vocab-num">[${m.vocab._num}]</sup></span>`;
    pos=m.end;
  }
  out+=text.substring(pos);
  return out;
}
function escRe(s){return s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}
function cr(){document.getElementById('ro').classList.remove('open');rUrl='';}
function crBg(e){if(e.target===document.getElementById('ro'))cr();}

// Vocab selection
let selPi=-1;  // paragraph index of the current selection
document.addEventListener('mouseup',e=>{
  const sel=window.getSelection().toString().trim(),pp=document.getElementById('vPop');
  if(sel&&sel.length>0&&sel.length<500&&document.getElementById('ro').classList.contains('open')){
    selTxt=sel;
    // Walk up from the selection anchor to find the .pr element with data-pi
    selPi=-1;
    try{
      let node=window.getSelection().anchorNode;
      while(node&&node!==document.body){
        if(node.nodeType===1&&node.getAttribute&&node.getAttribute('data-pi')!=null){
          selPi=parseInt(node.getAttribute('data-pi'));break;
        }
        node=node.parentNode;
      }
    }catch(err){selPi=-1;}
    pp.style.left=e.clientX+'px';pp.style.top=(e.clientY-46)+'px';pp.classList.add('open');
  }else{pp.classList.remove('open');}
});
// Touch support for mobile
document.addEventListener('touchend',e=>{
  setTimeout(()=>{
    const sel=window.getSelection().toString().trim(),pp=document.getElementById('vPop');
    if(sel&&sel.length>0&&sel.length<500&&document.getElementById('ro').classList.contains('open')){
      selTxt=sel;selPi=-1;
      try{
        let node=window.getSelection().anchorNode;
        while(node&&node!==document.body){
          if(node.nodeType===1&&node.getAttribute&&node.getAttribute('data-pi')!=null){
            selPi=parseInt(node.getAttribute('data-pi'));break;
          }
          node=node.parentNode;
        }
      }catch(err){selPi=-1;}
      const t=e.changedTouches&&e.changedTouches[0];
      if(t){pp.style.left=t.clientX+'px';pp.style.top=(t.clientY-60)+'px';}
      pp.classList.add('open');
    }
  },10);
});
async function svV(vt){
  if(!selTxt)return;document.getElementById('vPop').classList.remove('open');
  try{const r=await fetch('/api/vocab',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:cD,text:selTxt,type:'translate',url:rUrl,title:document.getElementById('rT').textContent,paragraph_index:selPi})});
    const d=await r.json();toast(`Đã lưu từ vựng: "${d.translated}"`,'success');
    await loadDay();
    if(contentCache[rUrl]){const artObj=arts.find(x=>x.url===rUrl);renderReader(contentCache[rUrl],artObj?artObj.category:'international');}
  }catch(e){toast('Lỗi','error');}
}
async function saveNote_sel(){
  if(!selTxt)return;document.getElementById('vPop').classList.remove('open');
  const artTitle=document.getElementById('rT').textContent||'';
  const noteText=document.getElementById('notesArea').value||'';
  const newEntry=`\n📌 [${artTitle}]\n"${selTxt}"\n`;
  const updated=noteText+newEntry;
  document.getElementById('notesArea').value=updated;
  try{
    await fetch('/api/notes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:cD,content:updated})});
    await fetch('/api/vocab',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:cD,text:selTxt,type:'note',url:rUrl,title:artTitle,paragraph_index:selPi})});
    toast('Đã ghi chú (highlight đỏ)','success');
    await loadDay();
    if(contentCache[rUrl]){const artObj=arts.find(x=>x.url===rUrl);renderReader(contentCache[rUrl],artObj?artObj.category:'international');}
  }catch(e){toast('Lỗi','error');}
}

function rVoc(items){
  const el=document.getElementById('vL');
  if(!items.length){el.innerHTML='<div class="ve">Chưa có từ vựng ngày này.<br>Mở bài đọc → chọn từ → "Lưu từ vựng".</div>';return;}
  el.innerHTML=items.map(v=>{const isNote=v.type==='note';return`<div class="vi"><span class="og">${esc(v.original_text)}</span><span class="tr">${esc(v.translated_text||'')}</span><span class="tb ${isNote?'tc-note':'td'}">${isNote?'📝 Ghi chú':'📖 Dịch'}</span><span style="font-size:10px;color:var(--text3);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(v.article_title||'')}</span><button class="db" onclick="delV(${v.id})">✕</button></div>`;}).join('');
}
async function delV(id){try{await fetch('/api/vocab?id='+id,{method:'DELETE'});toast('Đã xóa','success');loadDay();}catch(e){}}

async function rate(id,imp){try{await fetch('/api/rate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,importance:imp})});loadDay();}catch(e){}}

async function fetchNow(){
  const today=new Date().toISOString().slice(0,10);
  if(cD>today){toast('Không thể cập nhật ngày tương lai','error');return;}
  const el=document.getElementById('fs');el.textContent='Đang cập nhật...';el.classList.add('ld');
  try{const r=await fetch('/api/fetch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:cD})});
    const d=await r.json();el.textContent=`+${d.added}`;el.classList.remove('ld');
    toast(d.added>0?`Cập nhật: ${d.added} bài`:(d.message||'Không có tin mới'),d.added>0?'success':'error');
    loadDay();loadDates();
  }catch(e){el.textContent='Lỗi';el.classList.remove('ld');toast('Lỗi','error');}
  setTimeout(()=>{el.textContent='Sẵn sàng';},5000);
}

async function fetchWayback(){
  const today=new Date().toISOString().slice(0,10);
  if(cD>=today){toast('Chế độ Lịch sử chỉ dùng cho ngày quá khứ','error');return;}
  const daysAgo=Math.floor((new Date(today)-new Date(cD))/(1000*60*60*24));
  if(!confirm(`Lấy tin ngày ${cD} (${daysAgo} ngày trước) từ Wayback Machine?\n\n⏱️ Thời gian: ~20–40 giây (đã tối ưu song song)\n📊 Không phải nguồn nào cũng có archive — thường Al Jazeera, TechCrunch, The Verge có nhiều archive nhất.`))return;
  const el=document.getElementById('fs');el.textContent='🕰️ Tra archive (song song)...';el.classList.add('ld');
  const wb=document.getElementById('waybackBtn');if(wb)wb.disabled=true;
  // Animated progress hint
  let dots=0;
  const tick=setInterval(()=>{dots=(dots+1)%4;el.textContent='🕰️ Tra archive'+'.'.repeat(dots);},600);
  try{
    const r=await fetch('/api/fetch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:cD,use_wayback:true})});
    const d=await r.json();clearInterval(tick);el.textContent=`+${d.added}`;el.classList.remove('ld');
    if(d.added>0){toast(`Wayback: ${d.added} bài cho ${cD}`,'success');}
    else{toast(d.message||'Wayback không có snapshot cho ngày này — thử ngày khác','error');}
    loadDay();loadDates();
  }catch(e){clearInterval(tick);el.textContent='Lỗi';el.classList.remove('ld');toast('Lỗi Wayback: '+e.message,'error');}
  finally{if(wb)wb.disabled=false;setTimeout(()=>{el.textContent='Sẵn sàng';},5000);}
}

async function saveNote(){try{await fetch('/api/notes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:cD,content:document.getElementById('notesArea').value})});toast('Đã lưu','success');}catch(e){}}

function exportExcel(){window.open('/api/export/excel?date='+cD,'_blank');}
function exportWord(){window.open('/api/export/word?date='+cD,'_blank');}
function exportVocab(){window.open('/api/export/vocab?date='+cD,'_blank');}

async function loadCfg(){try{const r=await fetch('/api/config'),c=await r.json();document.getElementById('cT').checked=c.auto_translate!==false;document.getElementById('cK').value=c.keep_days||30;document.getElementById('cP').value=c.port||8765;document.getElementById('cA').value=c.articles_per_topic_per_fetch||3;rSlots(c.extra_fetches||[]);}catch(e){}}
function rSlots(s){document.getElementById('fSlots').innerHTML=s.map((v,i)=>`<div class="sr"><label>Mốc ${i+1}:</label><input type="text" class="si" value="${v}" placeholder="HH:MM" style="width:70px;"><button class="btn btn-sm" onclick="rmSlot(${i})" style="color:var(--red);">✕</button></div>`).join('');}
function addSlot(){const s=Array.from(document.querySelectorAll('.si')).map(i=>i.value);s.push('00:00');rSlots(s);}
function rmSlot(i){const s=Array.from(document.querySelectorAll('.si')).map(x=>x.value);s.splice(i,1);rSlots(s);}
async function saveCfg(){const s=Array.from(document.querySelectorAll('.si')).map(i=>i.value).filter(v=>/^\d{2}:\d{2}$/.test(v));try{await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({extra_fetches:s,auto_translate:document.getElementById('cT').checked,keep_days:parseInt(document.getElementById('cK').value),port:parseInt(document.getElementById('cP').value),articles_per_topic_per_fetch:parseInt(document.getElementById('cA').value)})});toast('Đã lưu','success');}catch(e){toast('Lỗi','error');}}

function toast(m,t='success'){const el=document.getElementById('toast');el.textContent=m;el.className='toast show '+t;setTimeout(()=>el.classList.remove('show'),3500);}
</script>
</body>
</html>'''

class Handler(BaseHTTPRequestHandler):
    def log_message(self,f,*a):pass

    def _auth_ok(self):
        cfg = load_config()
        user = os.environ.get('AUTH_USER') or cfg.get('auth_user', '')
        pw   = os.environ.get('AUTH_PASS') or cfg.get('auth_pass', '')
        if not user or not pw:
            return True
        hdr = self.headers.get('Authorization', '')
        if not hdr.startswith('Basic '):
            return False
        try:
            decoded = base64.b64decode(hdr[6:]).decode('utf-8', 'replace')
            u, _, p = decoded.partition(':')
            return u == user and p == pw
        except Exception:
            return False

    def _require_auth(self):
        if self._auth_ok():
            return False
        body = b'Unauthorized'
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="NewsReader"')
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def _json(self,d,s=200):
        b=json.dumps(d,ensure_ascii=False).encode('utf-8')
        self.send_response(s);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def _html(self,h):
        b=h.encode('utf-8');self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def _file(self,d,fn,ct):
        self.send_response(200);self.send_header('Content-Type',ct);self.send_header('Content-Disposition',f'attachment; filename="{fn}"');self.send_header('Content-Length',str(len(d)));self.end_headers();self.wfile.write(d)
    def _body(self):
        l=int(self.headers.get('Content-Length',0));return json.loads(self.rfile.read(l)) if l else {}

    def do_GET(self):
        if self._require_auth(): return
        p=urllib.parse.urlparse(self.path);path=p.path;q=dict(urllib.parse.parse_qsl(p.query))
        if path in('/',''):self._html(HTML)
        elif path=='/reader':
            # Standalone reader page (linked from Excel exports)
            url=q.get('url','')
            cat=q.get('cat','international')
            reader_html=f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Đọc song ngữ</title>
<style>@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;600;700&display=swap');
*{{margin:0;padding:0;box-sizing:border-box;}}body{{font-family:'Be Vietnam Pro',sans-serif;background:#0c0f1a;color:#e2e8f0;padding:24px;max-width:860px;margin:0 auto;}}
h1{{font-size:20px;margin-bottom:20px;color:#818cf8;}}.loading{{text-align:center;padding:60px;color:#64748b;}}
.pr{{margin-bottom:16px;}}.pe{{font-size:15px;line-height:1.8;margin-bottom:4px;}}.pv{{font-size:14px;line-height:1.7;color:#818cf8;font-style:italic;padding-left:14px;border-left:3px solid #6366f1;}}
img{{max-width:100%;border-radius:8px;margin:10px 0;}}.err{{color:#ef4444;text-align:center;padding:40px;}}
a{{color:#818cf8;}}h2.pe,h3.pe{{font-weight:700;font-size:18px;margin-top:18px;}}
.vocab-hl{{background:rgba(250,204,21,.35);border-radius:3px;padding:0 2px;color:#fef9c3;}}
.vocab-note{{background:rgba(239,68,68,.45);border-radius:3px;padding:0 2px;color:#fecaca;border-bottom:2px solid #ef4444;}}
.pv .vocab-hl{{background:rgba(250,204,21,.3);color:#fef08a;}}
.pv .vocab-note{{background:rgba(239,68,68,.4);color:#fecaca;border-bottom:2px solid #ef4444;}}
.vocab-num{{font-size:9px;font-weight:700;vertical-align:super;margin-left:2px;opacity:.85;letter-spacing:.3px;}}</style></head>
<body><div id="c"><div class="loading">⏳ Đang tải và dịch bài viết...</div></div>
<script>
const artCat="{cat}";
async function load(){{
  const url="{url.replace('"','%22')}";
  if(!url){{document.getElementById('c').innerHTML='<div class="err">Không có URL</div>';return;}}
  try{{
    const r=await fetch('/api/reader?url='+encodeURIComponent(url));
    const d=await r.json();
    if(!d.success)throw new Error(d.error||'Lỗi');
    // Load vocab for highlighting — use today's date properly (previously a template string bug sent the literal JS code)
    let vocWords=[];
    try{{
      const today=new Date().toISOString().slice(0,10);
      const vr=await fetch('/api/day?date='+today);
      const vd=await vr.json();
      vocWords=(vd.vocab||[]).filter(v=>v.article_url===url);
    }}catch(ve){{}}
    let h='<h1>'+esc(d.title||'')+'</h1>';
    if(d.images&&d.images[0])h+='<img src="'+esc(d.images[0].src)+'" onerror="this.style.display=\\'none\\'">';
    const ps=d.paragraphs||[],vs=d.paragraphs_vi||[];
    const isVN=artCat==='vietnam';
    let clusterNum=0;
    for(let i=0;i<ps.length;i++){{
      const p=ps[i]||{{}},v=vs[i]||null;
      const hd=(p.tag==='h2'||p.tag==='h3')?'h2':'div';
      const paraVocabs=vocWords.filter(vc=>{{
        const pi=(vc.paragraph_index==null)?-1:vc.paragraph_index;
        return pi===i||pi===-1;
      }});
      const numbered=paraVocabs.map(vc=>({{...vc, _num: ++clusterNum}}));
      const enHtml=hlText(esc(p.text||''), numbered, false);
      const viHtml=v?hlText(esc(v.text||''), numbered, true):'';
      if(isVN){{
        h+='<div class="pr"><'+hd+' class="pe">'+enHtml+'</'+hd+'></div>';
      }}else{{
        h+='<div class="pr"><'+hd+' class="pe">'+enHtml+'</'+hd+'>';
        if(v&&v.text)h+='<div class="pv">'+viHtml+'</div>';
        h+='</div>';
      }}
    }}
    h+='<p style="margin-top:24px;text-align:center;"><a href="'+esc(url)+'" target="_blank">🔗 Mở bài gốc</a> | <a href="/">← Về trang chủ</a></p>';
    document.getElementById('c').innerHTML=h;
  }}catch(e){{
    document.getElementById('c').innerHTML='<div class="err">⚠️ '+esc(e.message)+'<br><br><a href="'+esc(url)+'" target="_blank">🔗 Mở trong trình duyệt</a></div>';
  }}
}}
function esc(s){{return(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}}
function escRe(s){{return s.replace(/[.*+?^${{}}()|[\\]\\\\]/g,'\\\\$&');}}
function hlText(text, vocabs, useTranslated){{
  if(!vocabs.length)return text;
  const matches=[];
  for(const v of vocabs){{
    const rawWord=useTranslated?(v.translated_text||''):(v.original_text||'');
    if(!rawWord||rawWord.trim().length<2)continue;
    const escWord=esc(rawWord.trim());
    const re=new RegExp(escRe(escWord),'i');
    const m=text.match(re);
    if(m&&m.index>=0)matches.push({{start:m.index,end:m.index+m[0].length,vocab:v}});
  }}
  if(!matches.length)return text;
  matches.sort((a,b)=>a.start-b.start);
  const clean=[];let lastEnd=0;
  for(const m of matches){{if(m.start>=lastEnd){{clean.push(m);lastEnd=m.end;}}}}
  let out='';let pos=0;
  for(const m of clean){{
    out+=text.substring(pos,m.start);
    const cls=m.vocab.type==='note'?'vocab-note':'vocab-hl';
    const tip=esc(m.vocab.translated_text||m.vocab.original_text||'');
    out+='<span class="'+cls+'" title="'+tip+'">'+text.substring(m.start,m.end)+'<sup class="vocab-num">['+m.vocab._num+']</sup></span>';
    pos=m.end;
  }}
  out+=text.substring(pos);
  return out;
}}
load();
</script></body></html>'''
            self._html(reader_html)
        elif path=='/api/day':
            date=q.get('date',datetime.now().strftime('%Y-%m-%d'))
            self._json({'articles':db.get_articles(date),'notes':db.get_note(date),'vocab':db.get_vocab_by_date(date),'sessions':db.get_sessions(date),'date':date})
        elif path=='/api/reader':
            url=q.get('url','')
            if not url:self._json({'success':False,'error':'No URL'});return
            # Check DB cache (skip garbage cached results)
            cached=db.get_cached_content(url)
            if cached:
                cached.setdefault('paragraphs', [])
                cached.setdefault('paragraphs_vi', [])
                cached.setdefault('images', [])
                # Skip if cached result is garbage
                if cached.get('paragraphs') and len(cached['paragraphs']) > 0:
                    title = cached.get('title','').lower()
                    if 'google search' not in title and 'google' not in title[:20]:
                        cached['success'] = True
                        self._json(cached);return
                # Delete garbage cache
                try:
                    with db.conn() as c: c.execute('DELETE FROM article_cache WHERE url=?',(url,))
                except: pass

            content=fetcher.fetch_article_content(url)
            paras = content.get('paragraphs') or []
            clean_paras = [{'text':p['text'],'tag':p.get('tag','p')} for p in paras if isinstance(p,dict) and p.get('text')]

            # Detect garbage (Google Search page, empty content)
            is_garbage = False
            title = content.get('title','')
            if 'google' in title.lower()[:20] or 'search' in title.lower()[:20]:
                is_garbage = True
            if not clean_paras:
                is_garbage = True

            # Fallback: use article description from DB
            if is_garbage or not content.get('success'):
                art_row = None
                try:
                    with db.conn() as c:
                        art_row = c.execute('SELECT * FROM articles WHERE url=? LIMIT 1',(url,)).fetchone()
                except: pass
                if art_row:
                    art = dict(art_row)
                    fallback_title = art.get('title','')
                    fallback_paras = []
                    desc = art.get('description','')
                    desc_vi = art.get('description_vi','')
                    if desc:
                        fallback_paras.append({'text': desc, 'tag': 'p'})
                    fallback_vi = []
                    if desc_vi:
                        fallback_vi.append({'text': desc_vi, 'tag': 'p'})
                    elif desc:
                        try: fallback_vi = translator.translate_paragraphs(fallback_paras)
                        except: fallback_vi = [{'text':'','tag':'p'}]

                    content = {
                        'title': fallback_title,
                        'paragraphs': fallback_paras,
                        'paragraphs_vi': fallback_vi,
                        'images': [],
                        'url': url,
                        'success': True,
                        'fallback': True,
                        'fallback_msg': 'Không tải được toàn bộ bài viết (trang có thể bị chặn). Hiển thị tóm tắt từ RSS.'
                    }
                    self._json(content);return
                else:
                    error_msg = content.get('error','') or 'Không tải được bài viết và không có dữ liệu RSS.'
                    self._json({'success':False,'error':error_msg,'url':url,'paragraphs':[],'paragraphs_vi':[],'images':[],'title':''});return

            content['paragraphs'] = clean_paras
            if clean_paras:
                try:
                    vi = translator.translate_paragraphs(clean_paras)
                    content['paragraphs_vi'] = vi if vi and len(vi)==len(clean_paras) else [{'text':'','tag':'p'}]*len(clean_paras)
                except:
                    content['paragraphs_vi'] = [{'text':'','tag':'p'}]*len(clean_paras)
            else:
                content['paragraphs_vi'] = []
            if content.get('success') and clean_paras:
                try:db.save_cached_content(url,content)
                except:pass
            self._json(content)
        elif path=='/api/config':self._json(load_config())
        elif path=='/api/dates':self._json(db.get_available_dates())
        elif path=='/api/export/excel':
            date=q.get('date',datetime.now().strftime('%Y-%m-%d'));a=db.get_articles(date);n=db.get_note(date);v=db.get_vocab_by_date(date);cfg=load_config()
            d=exporter.export_excel_day(a,n,date,cfg.get('port',8765),vocab=v);self._file(d,f'news_{date}.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        elif path=='/api/export/word':
            date=q.get('date',datetime.now().strftime('%Y-%m-%d'));a=db.get_articles(date);n=db.get_note(date);v=db.get_vocab_by_date(date)
            d=exporter.export_word_day(a,n,date,vocab=v);self._file(d,f'news_{date}.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        elif path=='/api/export/vocab':
            date=q.get('date',datetime.now().strftime('%Y-%m-%d'));v=db.get_vocab_by_date(date);cfg=load_config()
            d=exporter.export_vocabulary_excel(v,cfg.get('port',8765));self._file(d,f'vocab_{date}.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        else:self.send_error(404)

    def do_POST(self):
        if self._require_auth(): return
        p=urllib.parse.urlparse(self.path);path=p.path
        if path=='/api/fetch':
            b=self._body();date=b.get('date',datetime.now().strftime('%Y-%m-%d'))
            use_wayback=b.get('use_wayback',None)  # None=auto, True=force, False=skip
            today=datetime.now().strftime('%Y-%m-%d')
            if date>today:self._json({'added':0,'message':'Không thể cập nhật ngày tương lai'});return
            # Calculate days ago for better UX messaging
            from datetime import datetime as _dt
            try:
                days_ago=(_dt.strptime(today,'%Y-%m-%d')-_dt.strptime(date,'%Y-%m-%d')).days
            except:days_ago=0
            label_parts=['Thủ công']
            if date<today:label_parts.append('(cũ)')
            if use_wayback is True:label_parts.append('[Wayback]')
            added=scheduler.run_now(date,' '.join(label_parts),use_wayback=use_wayback)
            msg=''
            if date<today and added==0:
                if use_wayback is True:
                    msg=f'Wayback Machine không có snapshot cho {date}. Thử các nguồn khác hoặc ngày khác.'
                elif days_ago>7:
                    msg=f'Không tìm thấy tin cho {date} ({days_ago} ngày trước). Thử bấm "🕰️ Lịch sử (Wayback)" để tìm từ archive.org.'
                else:
                    msg=f'Không tìm thấy tin mới cho {date} ({days_ago} ngày trước). Các bài có thể đã được lưu trước đó.'
            self._json({'added':added,'message':msg,'wayback_used':use_wayback is True})
        elif path=='/api/notes':
            b=self._body();db.save_note(b['date'],b['content']);self._json({'ok':True})
        elif path=='/api/vocab':
            b=self._body();text=b.get('text','');vt=b.get('type','translate');date=b.get('date',datetime.now().strftime('%Y-%m-%d'))
            try: pi=int(b.get('paragraph_index', -1))
            except: pi=-1
            translated=''
            if vt in ('translate','note'):
                try:translated=translator.translate(text)
                except:translated=text
            vid=db.save_vocab(date,text,translated,vt,b.get('url',''),b.get('title',''),pi)
            self._json({'id':vid,'translated':translated})
        elif path=='/api/rate':
            b=self._body();db.update_article_importance(b['id'],b['importance']);self._json({'ok':True})
        elif path=='/api/read':
            b=self._body();db.mark_read(b['id']);self._json({'ok':True})
        elif path=='/api/config':
            b=self._body();save_config(b);self._json({'ok':True})
        else:self.send_error(404)

    def do_DELETE(self):
        if self._require_auth(): return
        p=urllib.parse.urlparse(self.path);q=dict(urllib.parse.parse_qsl(p.query))
        if p.path=='/api/vocab':db.delete_vocab(int(q['id']));self._json({'ok':True})
        else:self.send_error(404)

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

if __name__=='__main__':
    cfg=load_config();port=cfg.get('port',8765)
    scheduler.start()
    auth_on = bool((os.environ.get('AUTH_USER') or cfg.get('auth_user','')) and
                   (os.environ.get('AUTH_PASS') or cfg.get('auth_pass','')))
    print(f"[NewsReader v4.3] http://localhost:{port}")
    print(f"[Timezone] {os.environ.get('TZ','(system default)')} — giờ hiện tại: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[Auth] {'BẬT (Basic Auth)' if auth_on else 'TẮT — chỉ nên dùng trong mạng LAN'}")
    print(f"[Scheduler] 23:50 + {cfg.get('extra_fetches',[])}")
    server=ThreadedHTTPServer(('0.0.0.0',port),Handler)
    try:server.serve_forever()
    except KeyboardInterrupt:print("\nĐã dừng.");server.server_close()
