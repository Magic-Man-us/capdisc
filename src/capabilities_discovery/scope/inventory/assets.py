"""Inline CSS and JS for the inventory's self-contained HTML render — no external resources."""

from __future__ import annotations

# How many characters of a capture's contents the HTML preview shows.
PREVIEW_CHARS = 600

INVENTORY_STYLE = """
:root{--bg:#0d1117;--panel:#161b22;--panel2:#1c2430;--bd:#2d3440;--fg:#e6edf3;--mut:#8b949e;
--ac:#58a6ff;--gn:#3fb950;--yl:#d29922;--pu:#bc8cff;--cy:#39c5cf;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-sans-serif,system-ui,"Segoe UI",Roboto,sans-serif}
header{padding:20px 24px;border-bottom:1px solid var(--bd);background:var(--panel)}
h1{margin:0 0 4px;font-size:20px}
.meta{color:var(--mut);font-size:12px}.meta b{color:var(--fg)}
main{padding:20px 24px}
.search{width:100%;max-width:480px;padding:9px 12px;background:var(--panel2);
border:1px solid var(--bd);border-radius:8px;color:var(--fg);font-size:13px;margin-bottom:16px}
.search:focus{outline:none;border-color:var(--ac)}
.card{background:var(--panel);border:1px solid var(--bd);border-radius:10px;
padding:14px 16px;margin-bottom:10px}
.card.eff{border-left:3px solid var(--gn)}.card.shadow{opacity:.62}
.row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ref{font-weight:600;font-size:14px}.id{color:var(--mut);font-size:11px}
.path{color:var(--mut);font-size:11.5px;margin-top:6px;word-break:break-all}
.pill{font-size:10.5px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;
padding:2px 8px;border-radius:5px}
.k-skill{background:#1f2d3d;color:var(--ac)}.k-agent{background:#2d1f3d;color:var(--pu)}
.k-command{background:#1f3d2a;color:var(--gn)}.k-hook{background:#3d2f1f;color:var(--yl)}
.sc{background:var(--panel2);border:1px solid var(--bd);color:var(--mut)}
.eff-b{background:#16341f;color:var(--gn)}
.preview{margin-top:8px;background:var(--bg);border:1px solid var(--bd);border-radius:6px;
padding:8px 10px;color:var(--mut);font-size:11.5px;white-space:pre-wrap;
max-height:160px;overflow:auto;display:none}
.card.open .preview{display:block}
.toggle{cursor:pointer;color:var(--ac);font-size:11px;background:none;border:none;padding:0;margin-top:6px}
.grp{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.5px;margin:18px 0 8px}
.empty{color:var(--mut);padding:24px;text-align:center}
.eventbar{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
.event{background:#3d2f1f;color:var(--yl);border-radius:5px;padding:2px 9px;font-size:11.5px}
"""

INVENTORY_SCRIPT = """
const search=document.querySelector('.search');
if(search){
  search.addEventListener('input',()=>{
    const q=search.value.toLowerCase().trim();
    document.querySelectorAll('.card[data-s]').forEach(c=>{
      c.style.display=(!q||c.dataset.s.includes(q))?'':'none';
    });
  });
}
"""
