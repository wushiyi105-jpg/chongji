"""Web 入口:零依赖 http.server,单页 + JSON API。"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import agent, llm
from . import db as dbmod

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>宠记 · 宠物照护</title>
<style>
  :root{--bg:#fdf8f3;--card:#fff;--ink:#2b2520;--muted:#7d7268;--accent:#b5651d;--soft:#fbe9d7;
        --line:#efe3d6;--red:#b3261e;--green:#386641;--amber:#a15c00;--radius:16px}
  *{box-sizing:border-box}
  body{margin:0;font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink)}
  .wrap{max-width:940px;margin:0 auto;padding:32px 20px 80px}
  h1{font-size:26px;margin:0 0 4px} header p{color:var(--muted);margin:0 0 22px}
  .badge{display:inline-block;font-size:12px;padding:3px 10px;border-radius:999px;background:var(--soft);color:var(--accent);margin-left:8px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:20px;margin-bottom:18px;box-shadow:0 1px 2px rgba(43,37,32,.05)}
  label{display:block;font-size:13px;color:var(--muted);margin:0 0 6px}
  textarea,input{width:100%;padding:12px 14px;border:1px solid var(--line);border-radius:12px;font-size:14px;font-family:inherit;background:#fff}
  textarea{line-height:1.7}
  textarea:focus,input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--soft)}
  button{background:var(--accent);color:#fff;border:none;padding:12px 22px;border-radius:12px;font-size:15px;cursor:pointer}
  button:hover{filter:brightness(1.1)}
  .hint{color:var(--muted);font-size:12px;margin-top:8px}
  .spin{display:inline-block;width:16px;height:16px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:sp .7s linear infinite}
  @keyframes sp{to{transform:rotate(360deg)}}
  .result{display:none}.result.show{display:block}
  h3{font-size:15px;color:var(--muted);margin:20px 0 8px}
  .box{background:#fdfaf7;border-radius:10px;padding:12px 14px;margin:8px 0;font-size:14px;line-height:1.8}
  .item{border-left:3px solid var(--accent);padding:4px 0 4px 12px;margin:8px 0;font-size:14px}
  .ok{color:var(--green)}.bad{color:var(--red)}.warn{color:var(--amber)}
  .level{display:inline-block;padding:4px 12px;border-radius:999px;font-size:13px}
  ul{margin:6px 0 0 18px;padding:0}li{margin:6px 0;font-size:14px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>宠记 · 宠物照护<span class="badge" id="badge">…</span></h1>
    <p>告诉我是猫还是狗、多重、多大、哪里不对,给你每日喂食量、免疫日历和症状分级。</p>
  </header>
  <div class="card">
    <label>宠物情况</label>
    <textarea id="text" rows="6" placeholder="猫,4.2kg,2岁,已绝育,今天吐了两次,精神还行,上次 4.5kg"></textarea>
    <div style="margin-top:16px"><button id="btn">开始评估</button></div>
    <div class="hint">喂食量按 RER/DER 本地算;症状分级只做分流,不做诊断,红旗一律建议就医。</div>
  </div>
  <div class="result" id="res"></div>
</div>
<script>
const $=s=>document.querySelector(s);
function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function load(btn,on){btn.disabled=on;if(on){btn.dataset.label=btn.dataset.label||btn.textContent.trim();btn.innerHTML='<span class="spin"></span>';}else{btn.innerHTML=btn.dataset.label||btn.textContent;}}
$('#btn').onclick=async()=>{
  const el=$('#res');el.classList.remove('show');load($('#btn'),true);
  try{
    const p=await fetch('/api/care',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text:$('#text').value})});
    const r=await p.json(); if(r.error) throw new Error(r.error);
    let h='<div class="card"><div class="hint">'+(r.mode==='model'?'模型已连接':'离线模式')+(r.saved_id?' · 已入库 #'+r.saved_id:'')+'</div>';
    h+='<p style="font-size:16px;line-height:1.75">'+esc(r.verdict)+'</p>';
    h+='<h3>基本信息</h3><div>物种 '+esc(r.species?r.species.name:'未识别')+' · 体重 '+(r.weight||'—')+' kg · 月龄 '+(r.months===null?'—':r.months)+' · 阶段 '+esc(r.stage.name)+'</div>';
    if(r.plan){h+='<h3>喂食量</h3><div class="box">RER '+r.plan.rer+' kcal → DER '+r.plan.der+' kcal<br>'+
      '每日 '+r.plan.grams+' g,分 '+r.plan.meals+' 顿,每顿约 '+r.plan.per_meal+' g<br><span class="hint">'+esc(r.plan.formula)+'</span></div>';}
    if(r.trend){h+='<h3>体重趋势</h3><div>上次 '+r.trend.previous+' → 现在 '+r.trend.current+' kg ('+r.trend.change_pct+'%)</div>';
      if(r.trend.alert){h+='<div class="warn">'+esc(r.trend.alert)+'</div>';}}
    h+='<h3>症状分级</h3><span class="level" style="background:'+(r.triage.color==='red'?'#fee2e2':r.triage.color==='amber'?'#fef3c7':'#dcfce7')+'">'+esc(r.triage.level)+'</span><div class="hint" style="margin-top:6px">'+esc(r.triage.why)+'</div>';
    h+='<h3>免疫与驱虫</h3>';
    r.vaccines.forEach(v=>{h+='<div class="item"><b>'+esc(v.name)+'</b> '+esc(v.status)+' · 下次 '+esc(v.next||'—')+'<div class="hint">'+esc(v.note)+'</div></div>';});
    if(r.summary){h+='<h3>照护要点</h3><p>'+esc(r.summary)+'</p>';}
    if(r.care_tips.length){h+='<h3>日常建议</h3><ul>';r.care_tips.forEach(x=>h+='<li>'+esc(x)+'</li>');h+='</ul>';}
    if(r.risks.length){h+='<h3>必须注意</h3><ul>';r.risks.forEach(x=>h+='<li class="bad">'+esc(x)+'</li>');h+='</ul>';}
    h+='<h3>就诊带上</h3>';
    r.checklist.forEach(c=>{h+='<div class="'+(c.ok?'ok':'warn')+'">'+(c.ok?'✅':'❌')+' '+esc(c.item)+' —— '+esc(c.how)+'</div>';});
    h+='</div>'; el.innerHTML=h;
  }catch(e){el.innerHTML='<div class="card" style="color:#b3261e">请求失败:'+esc(e.message)+'</div>';}
  el.classList.add('show');load($('#btn'),false);
};
fetch('/api/status').then(r=>r.json()).then(s=>{const b=$('#badge');
  if(s.mock){b.textContent='离线模式';b.style.background='#fee2e2';b.style.color='#b3261e';}
  else{b.textContent=s.model||'模型已连接';b.style.background='#dcfce7';b.style.color='#386641';}
}).catch(()=>{});
</script>
</body></html>
"""


def _handler(db, cfg, force_mock):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, body, ctype, status=200):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status=200):
            self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8", status)

        def _read(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("gbk", errors="replace")
            return json.loads(text) if text else {}

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/status":
                mock = force_mock or not cfg.get("api_key")
                self._json({"mock": mock, "model": None if mock else cfg.get("model")})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            if urlparse(self.path).path != "/api/care":
                self._json({"error": "not found"}, 404)
                return
            try:
                body = self._read()
                r = agent.care(body.get("text", ""), config=cfg, db=db,
                               force_mock=force_mock, save=True)
                self._json(r)
            except llm.LLMError as e:
                self._json({"error": str(e)}, 400)
            except Exception as e:  # noqa: BLE001
                self._json({"error": str(e)}, 500)

        def log_message(self, *args):
            pass

    return Handler


def serve(host="127.0.0.1", port=8000, db_path=None, force_mock=False):
    db = dbmod.Database(db_path)
    cfg = llm.default_config()
    httpd = ThreadingHTTPServer((host, port), _handler(db, cfg, force_mock))
    mode = "离线模式(未配置 key)" if (force_mock or not cfg.get("api_key")) else "模型:%s" % cfg.get("model")
    print("🐾 宠记已启动:http://%s:%s  [%s]" % (host, port, mode))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
