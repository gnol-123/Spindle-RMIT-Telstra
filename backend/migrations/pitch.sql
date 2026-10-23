-- Scrutinizer (pitch + limitations decks) and the temporary evaluator.
-- Decks share the Visual Report look from idea_assessment.sql: light,
-- Telstra blue, Spindle mark. Apply after orchestrator.sql. Re-runnable.
begin;

-- Skill text is copied onto each box at creation, so remember the old text
-- and refresh boxes still holding it once the preset is updated below.
create temp table _old_pitch_scrutiny on commit drop as
  select config from public.tool_presets where slug = 'pitch_scrutiny';

insert into public.tool_presets (slug, tool_type_id, name, description, config, sort_order)
values (
  'pitch_scrutiny',
  (select id from public.tool_types where slug = 'skill'),
  'Pitch Scrutiny',
  'How to build an honest pitch deck and limitations deck, in the Telstra-style slide template.',
  jsonb_build_object(
    'description', 'Load before building the pitch deck or the limitations deck.',
    'text', $t$Two decks, one standard of evidence, one look. They are for a Telstra innovation lab team deciding whether an idea is worth pursuing.

Gather first
- The scoping brief and market research reach you as context. The research agent's report.html and research.md sit in its directory of the shared sandbox; reuse its numbers, citations and verdict vocabulary.
- The UX prototype is prototype.html in the UX agent's directory. The code and screenshots are in the coding agent's directory of the coding environment; screenshots are in its screenshots/ folder.
- No screenshots: take them yourself with the browser tools against the coding agent's preview URL. No browser tools either: link the preview URL instead and say so.

How the decks read: shallow to deep
Every deck moves through three layers, marked on each slide with data-layer. The nav bar shows the layer, so the reader always knows how deep they are.
- Overview (first 2 to 3 slides): the answer in 30 seconds. Everyday words, no acronyms, one big visual or number per slide. A new graduate in any team gets the point without asking.
- Evidence (middle slides): one claim per slide, one visual that proves it, a citation under it. Standard terms named once, plain meaning first: "Customers we could realistically win (SOM)".
- Detail (last 1 to 3 slides): full working for an expert checking you. Tables, formulas with every input, scoring rubric, sources. Long tables go inside <details>.

Pitch deck, deck.html, 9 to 12 slides
Overview
1. Title: product name, one-line promise, verdict pill.
2. The problem in one picture: a big stat on who has it and how often, with one human line (a quote or a scenario).
3. The product at a glance: the best screenshot large, three plain benefits beside it.
Evidence
4. How it works: three to four steps (steps pattern), screenshots where they help.
5. How many people could buy it: nested circles (pattern B) and the bottom-up formula chips.
6. Who else does this and why we win: positioning map (pattern D), real competitors only.
7. How it makes money: price, cost to serve, the unit economics as formula chips.
8. Why now and why Telstra: two cards, each with a dated fact.
9. The ask: what we need, and the first experiment with its pass mark.
Detail
10. Evidence table: claim | number | source | grade, in <details>. Then sources.

Limitations deck, limitations.html, 9 to 12 slides
Overview
1. Title: "Should we build <product>?", verdict pill, one sentence answer.
2. The verdict in 30 seconds: verdict scale (pattern F), confidence, the single biggest reason.
3. Every risk on one picture: risk map (pattern G), each risk named in plain words under it.
Evidence
4 to 8. One risk per slide, worst first: market, competition, technical, adoption, cost and unit economics, legal or regulatory if any. Takeaway heading, one visual (risk bars, a stat, a competitor price comparison), the evidence, and what would reduce it.
9. What would kill it: kill criteria table: signal | kill if | check by.
10. What would change our mind: the three facts, each with how to find it out.
Detail
11. Full risk register in <details> (risk | likelihood | impact | evidence | mitigation), how you scored, and sources.

Verdict
Use the research report's scale: Pursue, Pilot to test, Rethink, Park. Add a confidence (low, medium, high). If yours differs from the research verdict, say why on the verdict slide.

Evidence
- Every number cites its source: <a class="cite" href="FULL_URL">Publisher, Mon YYYY</a> <span class="grade g-B">B</span>. The href is the exact page URL you or the research agent used, starting with https://. No source: write "unverified".
- Name real competitors from the research. Never invent one.
- A strength in the pitch deck that the limitations deck undercuts must be addressed in both.

Writing
- Slide headings state the takeaway as a sentence ("Every rival charges under $40 a month"), not a topic ("Pricing").
- At most 5 short lines of text per slide. The visual carries the point.
- Each slide has <aside class="notes"> with 2 to 4 sentences of speaker notes. Hidden on screen; they drive narration later.
- Load Plain Writing before you write the prose.

Template rules
- Use the template below as it is for both decks. Keep the style block, header, nav, the Spindle script and the slide script unchanged. Fill every {{placeholder}}, repeat slides as needed, delete blocks you have nothing for.
- Light mode only. Never add colours, fonts, libraries, images other than the screenshots, or external scripts and styles. Never use the Telstra logo; the Spindle mark is the brand. This template overrides any look the design skills suggest.
- Copy the screenshots next to the decks and reference them with relative paths.
- Colours (defined in the template): ink #0A0F24, Telstra blue #0D54FF for what matters, deep blue #0A2FA8, soft blue #E8EEFF, grey #9AA3B5 for context, green #0A8A4A good, gold #B7791F caution, red #D0021B bad, amber #F44E1A for the Spindle mark only.
- Charts are hand-drawn inline SVG from the patterns below, viewBox with width="100%". Label values on the chart. Every chart has a source line under it.

Template
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{Product}} | {{Pitch deck or Limitations}}</title>
<base target="_blank">
<style>
:root{--ink:#0A0F24;--muted:#5A6275;--line:#E3E6EE;--soft:#F5F7FB;--blue:#0D54FF;--deep:#0A2FA8;--blue-soft:#E8EEFF;--green:#0A8A4A;--gold:#B7791F;--red:#D0021B}
*{box-sizing:border-box}html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{margin:0;min-height:100vh;display:flex;flex-direction:column;background:#fff;color:var(--ink);font:16px/1.55 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--blue)}a:hover{text-decoration:none}
header{display:flex;align-items:center;gap:12px;padding:12px 32px;border-bottom:1px solid var(--line)}
#spindle{width:56px;height:35px;flex:none}.brand b{display:block;letter-spacing:-.01em}.brand small{color:var(--muted);font-size:11px}
header .meta{margin-left:auto;font-size:12px;color:var(--muted);text-align:right}
#bar{height:3px;width:0;background:var(--blue);transition:width .3s}
main{flex:1;display:flex}
[data-slide]{flex:1;min-width:0;width:100%;max-width:1100px;margin:0 auto;padding:40px 48px;display:flex;flex-direction:column;justify-content:center;animation:in .35s ease}
[data-slide][hidden]{display:none}
@keyframes in{from{transform:translateY(8px)}}
.cover{background:radial-gradient(ellipse at 90% 10%,var(--blue-soft),#fff 60%);max-width:none;padding-left:max(48px,calc((100% - 1004px)/2))}
.kicker{font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--blue)}
h1{font-size:46px;line-height:1.1;letter-spacing:-.02em;margin:8px 0 18px;max-width:880px}
h2{font-size:30px;line-height:1.2;letter-spacing:-.015em;margin:6px 0 8px;max-width:900px}
h3{font-size:16px;margin:0 0 8px;line-height:1.3}
.sub{color:var(--muted);margin:0 0 22px;max-width:760px}.lead{font-size:20px;max-width:720px;margin:16px 0 0}
.pill{display:inline-block;font-weight:800;font-size:12px;letter-spacing:.06em;text-transform:uppercase;padding:6px 14px;border-radius:999px}
.pill.pursue{background:#E3F4EA;color:var(--green)}.pill.pilot{background:var(--blue-soft);color:var(--blue)}.pill.rethink{background:#FBF1DE;color:var(--gold)}.pill.park{background:#FCE6E8;color:var(--red)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
.tile{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px 16px;box-shadow:0 2px 10px rgba(10,15,36,.07)}
.tile .l{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.tile .v{font-size:28px;font-weight:800;line-height:1.2;margin-top:2px}.tile .s{font-size:12px;color:var(--muted)}
.good{color:var(--green)}.mid{color:var(--gold)}.bad{color:var(--red)}
.card{border:1px solid var(--line);border-radius:10px;padding:18px;background:#fff}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;align-items:center}
.stat{font-size:64px;font-weight:800;color:var(--blue);line-height:1;letter-spacing:-.02em}
.src{font-size:12px;color:var(--muted);margin-top:10px}
.cite{font-size:12px;white-space:nowrap}
.grade{display:inline-block;font-size:10px;font-weight:800;border-radius:4px;padding:1px 6px;vertical-align:1px}
.g-A{background:#E3F4EA;color:var(--green)}.g-B{background:var(--blue-soft);color:var(--blue)}.g-C{background:#FBF1DE;color:var(--gold)}.g-D{background:#FCE6E8;color:var(--red)}
.chips{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:14px}
.chip{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:8px 12px}.chip b{display:block;font-size:18px}
.chip.total{background:var(--blue);border-color:var(--blue);color:#fff}
.shot{display:block;width:100%;border:1px solid var(--line);border-radius:10px;box-shadow:0 8px 30px rgba(10,15,36,.10)}
.steps{list-style:none;counter-reset:s;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}
.steps li{counter-increment:s;border-top:3px solid var(--blue);padding-top:14px}
.steps li:before{content:counter(s);display:grid;place-items:center;width:30px;height:30px;border-radius:50%;background:var(--blue);color:#fff;font-weight:800;margin-bottom:10px}
.steps b{display:block}.steps span{font-size:14px;color:var(--muted)}
blockquote{margin:0;padding:12px 16px;border-left:4px solid var(--blue);background:var(--soft);border-radius:0 8px 8px 0}
ul.plain{margin:0;padding-left:20px}ul.plain li{margin-bottom:6px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{background:var(--soft);font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
details{margin-top:12px;border:1px solid var(--line);border-radius:10px;padding:10px 16px;max-height:60vh;overflow:auto}
summary{cursor:pointer;font-weight:600;color:var(--blue)}
aside.notes{display:none}
.fine{margin-top:24px;font-size:12px;color:var(--muted)}
nav{display:flex;align-items:center;gap:10px;padding:10px 32px;border-top:1px solid var(--line);font-size:13px;color:var(--muted)}
nav .layer{margin-right:auto;font-weight:700;letter-spacing:.06em;text-transform:uppercase;font-size:11px;color:var(--blue)}
nav button{font:inherit;color:var(--ink);background:#fff;border:1px solid var(--line);border-radius:8px;padding:6px 14px;cursor:pointer}
nav button:hover{border-color:var(--blue);color:var(--blue)}nav button:disabled{opacity:.4;cursor:default}
@media(max-width:700px){header,nav{padding-left:16px;padding-right:16px}[data-slide],.cover{padding:24px 16px;justify-content:flex-start}h1{font-size:30px}h2{font-size:23px}.stat{font-size:44px}header .meta{display:none}}
@media print{header,nav,#bar{display:none}main{display:block}[data-slide],[data-slide][hidden]{display:flex;min-height:100vh;break-after:page;animation:none}details{max-height:none}}
</style></head><body>
<header>
  <canvas id="spindle" aria-hidden="true"></canvas>
  <div class="brand"><b>Spindle</b><small>Telstra Muru-D · Innovation research</small></div>
  <div class="meta">{{Pitch deck or Limitations}}<br>{{D Mon YYYY}}</div>
</header>
<div id="bar"></div>
<main>

  <section data-slide data-layer="Overview" class="cover">
    <div class="kicker">{{Pitch deck or Limitations}}</div>
    <h1>{{Product name, or "Should we build <product>?"}}</h1>
    <div><span class="pill {{pursue|pilot|rethink|park}}">{{Verdict}}</span></div>
    <p class="lead">{{One sentence: the promise, or the answer and the main reason.}}</p>
    <aside class="notes">{{2 to 4 sentences.}}</aside>
  </section>

  <section data-slide data-layer="Overview">
    <div class="kicker">{{Short label}}</div>
    <h2>{{Takeaway sentence}}</h2>
    <div class="grid2">
      <div><div class="stat">{{1 in 4}}</div><p>{{What the number means, in plain words.}}</p>
        <div class="src"><a class="cite" href="{{https://exact/page}}">{{Publisher, Mon YYYY}}</a> <span class="grade g-{{B}}">{{B}}</span></div></div>
      <blockquote>{{A quote or a one-line scenario.}}</blockquote>
    </div>
    <aside class="notes">{{2 to 4 sentences.}}</aside>
  </section>

  <section data-slide data-layer="Evidence">
    <div class="kicker">{{Short label}}</div>
    <h2>{{Takeaway sentence}}</h2>
    <p class="sub">{{What the visual shows, and the date}}</p>
    <div class="card">
      {{SVG from a pattern below, or <img class="shot" src="screenshots/x.png" alt="...">}}
      <div class="src">Source: <a class="cite" href="{{https://exact/page}}">{{Publisher, Mon YYYY}}</a> <span class="grade g-{{A}}">{{A}}</span></div>
    </div>
    <aside class="notes">{{2 to 4 sentences.}}</aside>
  </section>

  <section data-slide data-layer="Detail">
    <div class="kicker">Detail</div>
    <h2>{{Takeaway sentence}}</h2>
    <details open><summary>{{Show the full table}}</summary>
      <table><tr><th>{{Column}}</th><th>Source</th></tr>
        <tr><td>{{Value}}</td><td><a class="cite" href="{{https://exact/page}}">{{Publisher, Mon YYYY}}</a> <span class="grade g-{{C}}">{{C}}</span></td></tr></table>
    </details>
    <details><summary>Sources</summary>
      <ol><li><a href="{{https://exact/page}}">{{Title, Publisher, D Mon YYYY}}</a> <span class="grade g-{{A}}">{{A}}</span></li></ol>
    </details>
    <p class="fine">Spindle · Telstra Muru-D · Prepared by the Scrutinizer agent on {{D Mon YYYY}} · Sources graded A to D.</p>
    <aside class="notes">{{2 to 4 sentences.}}</aside>
  </section>

</main>
<nav><span class="layer" id="layer"></span><button id="prev" aria-label="Previous slide">←</button><span id="count"></span><button id="next" aria-label="Next slide">→</button></nav>
<script>
(()=>{const S=[...document.querySelectorAll("[data-slide]")],L=document.getElementById("layer"),C=document.getElementById("count"),B=document.getElementById("bar"),P=document.getElementById("prev"),N=document.getElementById("next");let i=0;
function go(k){i=Math.max(0,Math.min(S.length-1,k));S.forEach((s,j)=>s.hidden=j!==i);L.textContent=S[i].dataset.layer||"";C.textContent=(i+1)+" / "+S.length;B.style.width=(i+1)/S.length*100+"%";P.disabled=i===0;N.disabled=i===S.length-1;history.replaceState(null,"","#"+(i+1))}
P.onclick=()=>go(i-1);N.onclick=()=>go(i+1);
addEventListener("keydown",e=>{if(e.key===" "&&e.target.closest("button,summary,a"))return;if(["ArrowRight","PageDown"," "].includes(e.key)){e.preventDefault();go(i+1)}if(["ArrowLeft","PageUp"].includes(e.key)){e.preventDefault();go(i-1)}});
let x0=null;addEventListener("touchstart",e=>x0=e.touches[0].clientX,{passive:true});addEventListener("touchend",e=>{if(x0===null)return;const d=e.changedTouches[0].clientX-x0;if(Math.abs(d)>50)go(i+(d<0?1:-1));x0=null});
go((parseInt(location.hash.slice(1))||1)-1)})();
</script>
<script>
(()=>{const cv=document.getElementById("spindle"),ctx=cv.getContext("2d"),T=1.5,S=2,Q=.7;let w,h;
function size(){const r=cv.getBoundingClientRect(),d=devicePixelRatio||1;w=r.width;h=r.height;cv.width=w*d;cv.height=h*d;ctx.setTransform(d,0,0,d,0,0)}
function draw(t){ctx.clearRect(0,0,w,h);const cy=h/2,R=h*.38,ph=t/1000*1.6,n=Math.floor(w/S),pts=[];
for(let i=0;i<=n;i++){const u=i/n,r=R*Math.pow(Math.sin(Math.PI*u),.8);for(let k=0;k<2;k++){const th=u*T*Math.PI*2-ph+k*Math.PI;pts.push([i*S,cy+r*Math.cos(th),Math.sin(th)])}}
pts.sort((a,b)=>a[2]-b[2]);ctx.fillStyle="#F44E1A";ctx.globalAlpha=.18;for(let i=0;i<=n;i+=2)ctx.fillRect(i*S-Q,cy-Q,2*Q,2*Q);
for(const[x,y,z]of pts){const s=(2+(z+1)*1.25)*Q;ctx.globalAlpha=.25+(z+1)*.375;ctx.fillRect(x-s/2,y-s/2,s,s)}ctx.globalAlpha=1}
size();if(matchMedia("(prefers-reduced-motion: reduce)").matches)draw(0);else{const loop=t=>{draw(t);requestAnimationFrame(loop)};requestAnimationFrame(loop)}})();
</script>
</body></html>

Building blocks. Copy the shape, replace the numbers, keep the colours.

Tiles (Overview slides): <div class="tiles"><div class="tile"><div class="l">{{Do people want it?}}</div><div class="v good">{{4/5}}</div><div class="s">{{High confidence}}</div></div></div>
Screenshot beside benefits: <div class="grid2"><img class="shot" src="screenshots/home.png" alt="{{what it shows}}"><ul class="plain"><li>{{Benefit}}</li></ul></div>
Steps: <ol class="steps"><li><b>{{Step}}</b><span>{{What happens}}</span></li></ol>
Formula chips: <div class="chips"><div class="chip"><b>62,000</b>firms</div>×<div class="chip"><b>12%</b>adopt</div>×<div class="chip"><b>$1,080</b>a year</div>=<div class="chip total"><b>$8.0M</b>a year</div></div>

A. Score or risk bars: one row each, 120 units per point (5 = 600 of the 730 track). Fill green 4 to 5, gold 3, red 1 to 2 for scores. For risk severity flip it: red 4 to 5, gold 3, grey 1 to 2. Sort worst first.
<svg viewBox="0 0 760 130" width="100%" role="img" aria-label="Risk severity">
  <g font-size="14" fill="#0A0F24">
    <text x="0" y="24" font-weight="700">People may not switch 4/5 <tspan font-weight="400" fill="#5A6275">Adoption</tspan></text><text x="730" y="24" text-anchor="end" fill="#5A6275">Medium confidence</text>
    <rect x="0" y="34" width="730" height="18" rx="9" fill="#EEF1F6"/><rect x="0" y="34" width="480" height="18" rx="9" fill="#D0021B"/>
    <text x="0" y="84" font-weight="700">Rivals can copy it fast 3/5 <tspan font-weight="400" fill="#5A6275">Competition</tspan></text><text x="730" y="84" text-anchor="end" fill="#5A6275">High confidence</text>
    <rect x="0" y="94" width="730" height="18" rx="9" fill="#EEF1F6"/><rect x="0" y="94" width="360" height="18" rx="9" fill="#B7791F"/>
  </g>
</svg>

B. Market size, nested circles. Not to scale: say so in the sub line.
<svg viewBox="0 0 420 300" width="100%" style="max-width:420px" role="img" aria-label="Market size">
  <circle cx="210" cy="150" r="140" fill="#E8EEFF"/><circle cx="210" cy="192" r="96" fill="#B9CCFF"/><circle cx="210" cy="238" r="50" fill="#0D54FF"/>
  <text x="210" y="42" text-anchor="middle" font-size="13" fill="#0A2FA8" font-weight="700">Everyone $1.2B</text><text x="210" y="60" text-anchor="middle" font-size="11" fill="#5A6275">TAM</text>
  <text x="210" y="122" text-anchor="middle" font-size="13" fill="#0A2FA8" font-weight="700">We can reach $410M</text><text x="210" y="140" text-anchor="middle" font-size="11" fill="#0A2FA8">SAM</text>
  <text x="210" y="236" text-anchor="middle" font-size="14" fill="#fff" font-weight="800">We win $24M</text><text x="210" y="254" text-anchor="middle" font-size="11" fill="#fff">SOM, by year 3</text>
</svg>

D. Positioning map: the two axes that matter in this market, rivals in grey with names and prices, our spot in blue.
<svg viewBox="0 0 900 300" width="100%" role="img" aria-label="Competitor map">
  <line x1="60" y1="260" x2="880" y2="260" stroke="#C9CEDA"/><line x1="60" y1="20" x2="60" y2="260" stroke="#C9CEDA"/>
  <text x="470" y="290" font-size="12" fill="#5A6275" text-anchor="middle">{{x axis}} →</text>
  <text x="24" y="140" font-size="12" fill="#5A6275" text-anchor="middle" transform="rotate(-90 24 140)">{{y axis}} →</text>
  <circle cx="150" cy="210" r="11" fill="#9AA3B5"/><text x="168" y="214" font-size="12" fill="#0A0F24">Rival A $29</text>
  <circle cx="700" cy="80" r="14" fill="#0D54FF"/><text x="720" y="85" font-size="14" font-weight="700" fill="#0D54FF">{{Product}}</text>
</svg>

F. Verdict scale: four segments, Park to Pursue. The chosen one is solid, the others faded. The marker sits over the chosen segment's centre: x = 93 + position x 190 (Park 0, Rethink 1, Pilot to test 2, Pursue 3).
<svg viewBox="0 0 760 110" width="100%" role="img" aria-label="Verdict: Pilot to test">
  <g opacity=".22"><rect x="0" y="44" width="186" height="18" rx="9" fill="#D0021B"/><rect x="190" y="44" width="186" height="18" rx="9" fill="#B7791F"/><rect x="570" y="44" width="186" height="18" rx="9" fill="#0A8A4A"/></g>
  <rect x="380" y="44" width="186" height="18" rx="9" fill="#0D54FF"/>
  <path d="M463 24 L483 24 L473 38 Z" fill="#0A0F24"/><text x="473" y="14" text-anchor="middle" font-size="12" font-weight="700" fill="#0A0F24">Our verdict</text>
  <g font-size="13" text-anchor="middle" fill="#5A6275"><text x="93" y="86">Park</text><text x="283" y="86">Rethink</text><text x="473" y="86" font-weight="700" fill="#0D54FF">Pilot to test</text><text x="663" y="86">Pursue</text></g>
</svg>
(The triangle's points are x - 10, x + 10 and x.)

G. Risk map: likelihood 1 to 5 left to right, x = 60 + (likelihood - 1) x 110. Impact 1 to 5 bottom to top, y = 320 - (impact - 1) x 75. Red top-right is "act now". Dot colour by likelihood x impact: 15 or more red, 8 to 14 gold, under 8 grey. Number dots R1, R2 ... and list them under the map in plain words.
<svg viewBox="0 0 520 370" width="100%" style="max-width:560px" role="img" aria-label="Risk map">
  <rect x="280" y="20" width="220" height="150" fill="#FCE6E8"/><text x="490" y="40" font-size="12" fill="#D0021B" font-weight="700" text-anchor="end">Act now</text>
  <line x1="60" y1="320" x2="500" y2="320" stroke="#C9CEDA"/><line x1="60" y1="20" x2="60" y2="320" stroke="#C9CEDA"/>
  <text x="280" y="350" text-anchor="middle" font-size="12" fill="#5A6275">How likely →</text>
  <text x="24" y="170" text-anchor="middle" font-size="12" fill="#5A6275" transform="rotate(-90 24 170)">How bad if it happens →</text>
  <circle cx="390" cy="95" r="14" fill="#D0021B"/><text x="390" y="100" text-anchor="middle" font-size="11" fill="#fff" font-weight="700">R1</text>
  <circle cx="280" cy="170" r="14" fill="#B7791F"/><text x="280" y="175" text-anchor="middle" font-size="11" fill="#fff" font-weight="700">R2</text>
  <circle cx="170" cy="245" r="14" fill="#9AA3B5"/><text x="170" y="250" text-anchor="middle" font-size="11" fill="#fff" font-weight="700">R3</text>
</svg>

Kill criteria: <table><tr><th>Signal</th><th>Kill if</th><th>Check by</th></tr><tr><td>{{Waitlist sign-ups from a $2k ad test}}</td><td>{{Under 3% of visitors}}</td><td>{{Week 2}}</td></tr></table>

Other numbers: horizontal bars sorted largest first, grey with the important one in blue, for comparing; a line for trends over time.

Check, then serve
1. write_file deck.html and limitations.html in your own directory.
2. read_file each back and check: no {{ left; every slide has data-layer and a notes aside; every a.cite href starts with https:// and is a real page; every heading is a sentence; slide count in range; no colours outside the palette; screenshots referenced exist.
3. next_free_port, then run_command in the background: python3 -m http.server <port> --bind 0.0.0.0 --directory <your directory>.
4. publish_preview twice on that port: path /deck.html titled "<Product> pitch deck", path /limitations.html titled "<Product> limitations".

Reply with both URLs, the verdict and confidence, and the three facts. Nothing else.$t$
  ),
  70
)
on conflict (slug) do update set
  tool_type_id = excluded.tool_type_id,
  name         = excluded.name,
  description  = excluded.description,
  config       = excluded.config,
  sort_order   = excluded.sort_order;

-- Refresh boxes the user never edited. Edited text is left alone.
update public.nodes n
set config = n.config || p.config
from public.tool_presets p, _old_pitch_scrutiny o
where p.slug = 'pitch_scrutiny'
  and n.kind = 'tool'
  and n.tool_type_id = p.tool_type_id
  and n.config->>'text' = o.config->>'text';

insert into public.agent_types (slug, name, description, system_prompt, model, sort_order, default_presets)
values
  (
    'scrutinizer',
    'Scrutinizer',
    'Judges the product fairly and builds a pitch deck and a limitations deck.',
    $prompt$You are a product analyst for Telstra's innovation lab who has seen many launches fail. You are given a product idea, its scoping brief, market research, a UX prototype and a working prototype with screenshots. Judge it honestly and fairly: argue the strongest real case for it and the strongest real case against it, with the same rigour. No cheerleading, no doom for its own sake. Every market number traces to the research; anything you cannot trace is marked "unverified". Load the Pitch Scrutiny skill before you build anything and use its slide template: light, Telstra blue, the Spindle mark, starting simple and getting more detailed slide by slide. Deliver two HTML decks, published as previews, and a short reply with both URLs, your verdict (Pursue, Pilot to test, Rethink or Park) with confidence, and the three facts that would most change it.$prompt$,
    'deepseek-v4.1-flash',
    50,
    array['brave_search', 'web_fetch', 'pitch_scrutiny', 'plain_writing', 'workspace_memory']
  ),
  (
    'evaluator',
    'Evaluator',
    'Checks one agent''s delivery against its brief. Created and removed by the orchestrator.',
    $prompt$You are an evaluator. You check one agent's delivery against the criteria you are given, and nothing else. Verify claims where you can: read the files it says it wrote, open the preview or deck URLs, check that numbers have sources. Do not redo the work and do not add scope. PASS if the delivery meets every criterion well enough for the next stage to build on; FAIL otherwise. Reply in exactly this shape and nothing more:

VERDICT: PASS or FAIL
FIXES:
1. <one concrete, checkable fix>

At most 5 fixes, most important first. On PASS write "FIXES: none".$prompt$,
    'deepseek-v4.1-flash',
    90,
    array['web_fetch']
  )
on conflict (slug) do update set
  name            = excluded.name,
  description     = excluded.description,
  system_prompt   = excluded.system_prompt,
  sort_order      = excluded.sort_order,
  default_presets = excluded.default_presets;

-- Same guard as parity.sql: an unknown preset slug silently drops a box.
do $$
declare
  missing text[];
begin
  select array_agg(distinct s) into missing
  from public.agent_types a, unnest(a.default_presets) s
  where not exists (select 1 from public.tool_presets p where p.slug = s);
  if missing is not null then
    raise exception 'default_presets reference unknown presets: %', missing;
  end if;
end $$;

commit;
