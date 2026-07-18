"""Inline CSS and JS for the self-contained HTML report — no external resources."""

from __future__ import annotations

STYLE = """
:root{--bg:#0d1117;--panel:#161b22;--panel2:#1c2430;--bd:#2d3440;--fg:#e6edf3;--mut:#8b949e;
--ac:#58a6ff;--gn:#3fb950;--yl:#d29922;--pu:#bc8cff;--cy:#39c5cf;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-sans-serif,system-ui,"Segoe UI",Roboto,sans-serif}
code,.mono{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
header{padding:20px 24px;border-bottom:1px solid var(--bd);background:var(--panel)}
h1{margin:0 0 4px;font-size:20px}
.meta{color:var(--mut);font-size:12px}.meta b{color:var(--fg)}
.layout{display:flex;min-height:calc(100vh - 80px)}
nav{width:220px;flex:none;border-right:1px solid var(--bd);background:var(--panel);padding:12px;
position:sticky;top:0;align-self:flex-start;height:calc(100vh - 80px);overflow:auto}
nav button{display:flex;justify-content:space-between;width:100%;text-align:left;background:none;
border:none;color:var(--fg);padding:9px 11px;border-radius:7px;cursor:pointer;font-size:13px;
margin-bottom:2px}
nav button:hover{background:var(--panel2)}
nav button.active{background:var(--ac);color:#04111f;font-weight:600}
nav .cnt{color:var(--mut);font-size:11px}nav button.active .cnt{color:#04111f}
main{flex:1;padding:20px 24px;overflow:auto}
.section{display:none}.section.active{display:block}
.search{width:100%;max-width:480px;padding:9px 12px;background:var(--panel2);
border:1px solid var(--bd);border-radius:8px;color:var(--fg);font-size:13px;margin-bottom:16px}
.search:focus{outline:none;border-color:var(--ac)}
.card{background:var(--panel);border:1px solid var(--bd);border-radius:10px;
padding:14px 16px;margin-bottom:10px}
.card.eff{border-left:3px solid var(--gn)}.card.shadow{opacity:.62}
.row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ref{font-weight:600;font-size:14px}.id{color:var(--mut);font-size:11px}
.desc{color:#c9d1d9;margin:7px 0 0;font-size:13px}
.path{color:var(--mut);font-size:11.5px;margin-top:6px;word-break:break-all}
.tags{margin-top:8px;display:flex;gap:5px;flex-wrap:wrap}
.tag{background:var(--panel2);border:1px solid var(--bd);border-radius:20px;padding:1px 9px;
font-size:11px;color:var(--cy)}
.pill{font-size:10.5px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;
padding:2px 8px;border-radius:5px}
.k-skill{background:#1f2d3d;color:var(--ac)}.k-agent{background:#2d1f3d;color:var(--pu)}
.k-command{background:#1f3d2a;color:var(--gn)}.k-hook{background:#3d2f1f;color:var(--yl)}
.k-tool{background:#3d1f2a;color:#ff7b9c}.k-mcp_server{background:#1f3a3d;color:var(--cy)}
.sc{background:var(--panel2);border:1px solid var(--bd);color:var(--mut)}
.eff-b{background:#16341f;color:var(--gn)}
.toolrow{font-size:12px;padding:6px 0;border-top:1px solid var(--bd)}
.toolrow:first-child{border-top:none}
.toolname{color:var(--cy);font-weight:600}.params{color:var(--mut)}
.preview{margin-top:8px;background:var(--bg);border:1px solid var(--bd);border-radius:6px;
padding:8px 10px;color:var(--mut);font-size:11.5px;white-space:pre-wrap;max-height:160px;
overflow:auto;display:none}
.card.open .preview{display:block}
.toggle{cursor:pointer;color:var(--ac);font-size:11px;background:none;border:none;padding:0;margin-top:6px}
.bigstat{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:18px}
.stat{background:var(--panel);border:1px solid var(--bd);border-radius:10px;padding:12px 16px;
min-width:110px}
.stat .n{font-size:24px;font-weight:700}.stat .l{color:var(--mut);font-size:12px}
.grp{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.5px;margin:18px 0 8px}
.empty{color:var(--mut);padding:24px;text-align:center}
.eventbar{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
.event{background:#3d2f1f;color:var(--yl);border-radius:5px;padding:2px 9px;font-size:11.5px}
.tblwrap{overflow-x:auto;margin-top:8px;-webkit-overflow-scrolling:touch}
table.tbl{width:100%;border-collapse:collapse;font-size:12px}
table.tbl th,table.tbl td{text-align:left;padding:5px 9px;border-bottom:1px solid var(--bd);
vertical-align:top}
table.tbl th{color:var(--mut);font-weight:600;font-size:10.5px;text-transform:uppercase;
letter-spacing:.4px;white-space:nowrap}
table.tbl td.num,table.tbl th.num{text-align:right;font-variant-numeric:tabular-nums;
white-space:nowrap}
table.tbl tr:last-child td{border-bottom:none}
table.tbl tr.total td{border-top:1px solid var(--bd);font-weight:700;color:var(--fg)}
table.tbl td.toolname{color:var(--cy);font-weight:600;white-space:nowrap}
.more{cursor:pointer;color:var(--ac);font-size:11.5px;background:none;border:1px solid var(--bd);
border-radius:6px;padding:3px 11px;margin-top:9px}
.more:hover{border-color:var(--ac)}
.popup-src{display:none}
#backdrop{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;z-index:40}
#backdrop.open{display:block}
#drawer{position:fixed;left:0;right:0;bottom:0;max-height:72vh;background:var(--panel);
border-top:1px solid var(--bd);border-radius:14px 14px 0 0;box-shadow:0 -10px 34px rgba(0,0,0,.5);
transform:translateY(101%);transition:transform .22s ease;z-index:50;display:flex;
flex-direction:column}
#drawer.open{transform:translateY(0)}
#drawer .dhead{display:flex;justify-content:space-between;align-items:center;padding:13px 18px;
border-bottom:1px solid var(--bd)}
#drawer .dtitle{font-weight:600;font-size:14px}
#drawer .dclose{cursor:pointer;background:none;border:none;color:var(--mut);font-size:24px;
line-height:1;padding:0 4px}
#drawer .dclose:hover{color:var(--fg)}
#drawer .dbody{overflow:auto;padding:6px 18px 20px}
@media(max-width:820px){
  .layout{flex-direction:column;min-height:0}
  nav{width:auto;height:auto;position:static;border-right:none;
      border-bottom:1px solid var(--bd);display:flex;flex-wrap:wrap;gap:4px;overflow:visible}
  nav button{width:auto;margin:0}
  main{padding:16px}
  .stat{min-width:88px;flex:1 1 88px}
  .bigstat{gap:8px}
}
"""

SCRIPT = """
const sections=document.querySelectorAll('.section');
const navs=document.querySelectorAll('nav button');
function show(v){
  sections.forEach(s=>s.classList.toggle('active',s.id==='sec-'+v));
  navs.forEach(b=>b.classList.toggle('active',b.dataset.v===v));
}
navs.forEach(b=>b.addEventListener('click',()=>show(b.dataset.v)));
document.querySelectorAll('.search').forEach(inp=>{
  inp.addEventListener('input',()=>{
    const q=inp.value.toLowerCase().trim();
    inp.closest('.section').querySelectorAll('.card[data-s]').forEach(c=>{
      c.style.display=(!q||c.dataset.s.includes(q))?'':'none';
    });
  });
});
const backdrop=document.getElementById('backdrop');
const drawer=document.getElementById('drawer');
const dtitle=drawer.querySelector('.dtitle');
const dbody=drawer.querySelector('.dbody');
function closeDrawer(){
  drawer.classList.remove('open');backdrop.classList.remove('open');dbody.replaceChildren();
}
document.querySelectorAll('.more').forEach(btn=>{
  btn.addEventListener('click',()=>{
    const src=btn.parentElement.querySelector('.popup-src');
    dtitle.textContent=btn.dataset.title||'Details';
    dbody.replaceChildren();
    if(src){for(const node of src.children)dbody.appendChild(node.cloneNode(true));}
    drawer.classList.add('open');backdrop.classList.add('open');
  });
});
backdrop.addEventListener('click',closeDrawer);
drawer.querySelector('.dclose').addEventListener('click',closeDrawer);
document.addEventListener('keydown',ev=>{if(ev.key==='Escape')closeDrawer();});
show('overview');
"""
