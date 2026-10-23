-- Idea assessment: TAM/SAM/SOM market sizing, a DVF scorecard, and a
-- Telstra-styled HTML report on top of each stage's markdown. Market Research
-- owns sizing, desirability and viability; Project Scoping owns feasibility.
-- Apply after realtime_edges.sql. Re-runnable.
begin;

-- ---------------------------------------------------------------------------
-- The skills. Dollar-quoted so apostrophes, $ signs and newlines are literal.
-- ---------------------------------------------------------------------------
insert into public.tool_presets (slug, tool_type_id, name, description, config, sort_order)
values
  (
    'market_sizing',
    (select id from public.tool_types where slug = 'skill'),
    'Market Sizing',
    'How to size TAM, SAM and SOM two ways and show the working.',
    jsonb_build_object(
      'description', 'Load before estimating how big a market is: TAM, SAM, SOM, revenue potential.',
      'text', $t$Size the market twice, from opposite ends, and show every input. A market size nobody can check is a guess with a dollar sign.

0. Define the unit first
Write one line: "<who pays> pays <what> for <what>, per year, in <geography>." Default geography is Australia unless the idea says otherwise. All money in AUD for a stated year; when you convert, state the rate and its date.

1. The three layers
- TAM: annual revenue if every possible buyer of this kind of product in the geography bought it. The category, not just our version.
- SAM: the part of TAM this offer can actually serve: the segment it is built for, the channels Telstra can sell through, the regulation it fits.
- SOM: what we could realistically win within 3 years.

2. Top-down
Start from a published total (industry report, official statistics, a listed company's segment revenue). Narrow it with filters, one per line: "x 38% are small businesses (ABS 2025, A)". Each filter has a source and grade, or is marked as your assumption.

3. Bottom-up
Number of buyers x share who would adopt x annual price.
- Buyers: counts from official statistics (ABS business counts, population, households) or public customer numbers.
- Price: real prices from competitors' pricing pages, dated. Annualise monthly prices.
- Adoption: from a comparable product's actual penetration if you can find one; otherwise state it as an assumption.

4. Triangulate
Compare the two base cases for SAM.
- Within 2x of each other: say they agree and lead with bottom-up.
- More than 2x apart: name the input that explains the gap and say which method you trust. Still lead with bottom-up unless you can show its inputs are weaker.

5. Ranges, always
Give low, base and high for TAM, SAM and SOM. Move only the one or two least certain inputs between low and high, and say which ones. A single number with no range does not go in the report.

6. SOM must be anchored
Anchor SOM to something real: a named competitor's share after a similar number of years, or how many customers Telstra's channel could reach and convert per year. Never "if we get 1% of the market". If you cannot anchor it, say SOM is unknown and what evidence would settle it.

Output, in this order:
- The unit line.
- A table: Layer | Low | Base | High | Method.
- A table of inputs: Input | Value | Source (publisher, date, full URL) | Grade.
- Each formula written out with its numbers: "62,000 firms x 12% x $1,080 = $8.0M".
- One sentence on whether the two methods agree.

Rules: no number without a source or an "assumption" label. Prefer A and B sources. Quote dates. Never round a guess into false precision: $8M, not $8,035,200.$t$
    ),
    80
  ),
  (
    'dvf_assessment',
    (select id from public.tool_types where slug = 'skill'),
    'DVF Assessment',
    'How to judge desirability, viability and feasibility on evidence, not opinion.',
    jsonb_build_object(
      'description', 'Load before judging whether an idea is worth pursuing: desirability, viability, feasibility, verdict, riskiest assumptions.',
      'text', $t$Judge an idea on three lenses. Score what the evidence shows, not what you believe. Opinion is not evidence.

Who covers what
- Project Scoping covers Feasibility.
- Market Research covers Desirability and Viability, then assembles the full scorecard and verdict, taking Feasibility from the scoping agent's context. If that context is missing, do a short Feasibility pass yourself and label it "provisional".

Desirability: do people want this?
- Who has the problem, how often, and how badly. What they do about it today: workarounds, what they spend, which products they use.
- Demand signals: competitors with real traction (customers, revenue, funding), review volume and complaints, search interest, forum threads, surveys.
- A loud forum thread is a lead to follow (grade D), not proof.

Viability: does it make money for Telstra?
- Willingness to pay: what buyers already pay for comparable products, from pricing pages.
- The market size from Market Sizing: SAM and SOM base and range.
- Revenue model and rough unit economics: price, cost to serve, acquisition cost if findable.
- Strategic fit: does it use Telstra's strengths (network, retail and business channels, customer base, brand, enterprise relationships) and fit where Telstra is heading?
- Adaptability: competitors that are moving, regulation, technology shifts that could close the window.

Feasibility: can Telstra build and deliver it?
- Technology: does the core technology exist and work today? Name it.
- Telstra assets: which existing capabilities, platforms or partners it relies on.
- Dependencies: data, partners, approvals, other teams.
- Regulation and privacy: ACMA rules, the Privacy Act, sector rules (health, finance, critical infrastructure) that apply.
- Cost and time to an MVP a real customer could use, as a rough range.

Scoring, per lens
Score: what the evidence says.
- 5: strong positive signal from A or B sources.
- 4: positive signal, mostly B sources.
- 3: mixed, or positive but only C sources.
- 2: negative signal, or nothing better than D sources.
- 1: strong evidence against.
Confidence: how good the evidence is. High (several A or B sources that agree), Medium (some B, some C), Low (mostly C or D, or sources disagree).
A score of 4 or 5 with Low confidence must say so in the sentence that states it.

Verdict: the weakest lens decides, not the average.
- Pursue: every lens 4 or more, no Low confidence.
- Pilot to test: no lens below 3, but at least one 3 or one Low confidence. Name the experiment that would settle it.
- Rethink: any lens at 2. Say what would have to change.
- Park: any lens at 1, or two lenses at 2.

Riskiest assumptions
List 5 to 8 assumptions the idea depends on. For each: the lens (D, V or F), importance 1 to 5 (how badly the idea fails if it is false), evidence 1 to 5 (how much you actually know). High importance with low evidence is where to test first. For the top three, propose a cheap experiment: what to do, the metric, the pass mark, rough cost and time. Example: "Landing page with a $49/month price, 2 weeks, $2k of ads; pass if 3% of visitors join the waitlist."

Output, in this order:
- Scorecard table: Lens | Score /5 | Confidence | One-line reason with citations.
- Verdict and the reason in two sentences.
- Assumptions table: # | Assumption | Lens | Importance | Evidence | Experiment (top three only).$t$
    ),
    81
  ),
  (
    'visual_report',
    (select id from public.tool_types where slug = 'skill'),
    'Visual Report',
    'The Telstra-style HTML report template and how to publish it.',
    jsonb_build_object(
      'description', 'Load after research.md is written, to turn it into the research report.html and publish it beside the chat.',
      'text', $t$Turn your finished research.md into report.html: a professional Telstra-style report in light mode, for a Telstra innovation lab team deciding whether an idea is worth pursuing. The markdown comes first. The report is a tuned view of it: no new claims.

How it reads: the first screen answers "should we pursue this, and why?" in 30 seconds. Each section down the page goes one level deeper. Sources come last.

Write for two readers on one page. The top must make sense to someone with no business or research background; the bottom must satisfy an expert researcher checking your working.
- Top third (hero, tiles, first visuals): everyday words, short sentences, no jargon or acronyms. Say "how many people could buy this" before "TAM", "would people want it, would it make money, can we build it" before "DVF". If a term must appear, its plain meaning goes first and the term follows in small text: "Customers we could realistically win (SOM)".
- Middle (findings, competitors, assumptions): plain words with the standard terms named once, each claim with its number and citation.
- Bottom (inside <details>, inputs tables, method notes, sources): full expert detail. Formulas with every input, both sizing methods and why they agree or differ, scoring rubric, confidence reasoning, source grades. Precise terms are fine here.
- Tile labels and section headings use plain words. Never open a section with an acronym.
- Test the top third: would a new graduate in any team get the answer and the reason without asking you? If not, rewrite it.

Rules
- Use the template below as it is. Keep the style block, the header, the Spindle script and the footer unchanged. Fill every {{placeholder}}, repeat blocks as needed, and delete blocks you have nothing for. Never add colours, fonts, libraries, images, or external scripts and styles.
- Headings and chart titles state the takeaway as a sentence ("Every rival prices under $40 a month"), not a topic ("Pricing").
- Citations are real, clickable links. Every number and claim carries one: <a class="cite" href="FULL_URL">Publisher, Mon YYYY</a> <span class="grade g-A">A</span>. The href is the exact page URL you fetched or found in search, copied character for character and starting with https://. Never link a search results page, and never link a homepage when the claim came from a specific page. No URL for a claim means you write "unverified" instead of a link.
- The template's <base target="_blank"> makes every link open in a new tab. Links that jump within the page get target="_self".
- Visuals are yours to choose. For each point, ask what picture would make a non-expert get it fastest, then draw that, as inline SVG or HTML and CSS. The patterns below are a starter kit, not a menu. Good choices beyond them: a step-by-step journey or flow (how a customer uses it), before and after, a 100-dot grid ("7 in 100 cafes"), a scale comparison against something familiar, a value chain showing who pays whom, a map of Australia by state, a simple annotated sketch of the product, a ranked list with bars, a quote card from a real customer review.
- Whatever you draw: use a viewBox with width="100%" so it scales, label values on the visual itself, use only the palette colours (grey #9AA3B5 for context, Telstra blue #0D54FF for what matters), and put a source line under anything that shows a number. Never distort a number to make a picture work.
- No text may overlap another label, dot or line. Before writing an SVG, list each label's x, y and rough width (7 units per character at 12px) and move any that collide. Keep every mark at least 15 units inside the viewBox edge.
- One visual per finding. A finding with no number worth drawing gets a big stat, a quote or a small diagram, not a decorative chart. Vary the visuals: three bar charts in a row is a dull report.
- Long tables and detail go inside <details> so the page stays short.
- Load Plain Writing before you write the prose.

Colours (already defined in the template): ink #0A0F24, Telstra blue #0D54FF, deep blue #0A2FA8, soft blue #E8EEFF, green #0A8A4A good, gold #B7791F caution, red #D0021B bad, grey #9AA3B5 context, amber #F44E1A for the Spindle mark only. Scores 4 to 5 use green, 3 uses gold, 1 to 2 use red.

Research report sections (Market Research)
1. Hero: idea name, verdict pill (Pursue, Pilot to test, Rethink, Park), two sentences on why.
2. Tiles: "Do people want it?", "Will it make money?", "Can we build it?" as score/5 with confidence, plus "Market we could serve" with the SAM base and range.
3. DVF bars (pattern A), titled in plain words, with the lens names under each bar.
4. Market size: nested circles (pattern B) beside the bottom-up formula chips, plus one line on whether top-down and bottom-up agree. Inputs table and method notes in <details>.
5. Key findings: 3 to 5 cards, each with a takeaway title, one visual and a citation.
6. Competitors: positioning map (pattern D) on the two axes that matter most in this market, with the competitor table in <details>.
7. Riskiest assumptions: assumptions map (pattern C), then the top three with their experiments.
8. What we still don't know.
9. Sources: every source, linked and graded, best grade first.

Template
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{Idea name}} | Research report</title>
<base target="_blank">
<style>
:root{--ink:#0A0F24;--muted:#5A6275;--line:#E3E6EE;--soft:#F5F7FB;--blue:#0D54FF;--deep:#0A2FA8;--blue-soft:#E8EEFF;--green:#0A8A4A;--gold:#B7791F;--red:#D0021B}
*{box-sizing:border-box}html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{margin:0;background:#fff;color:var(--ink);font:15px/1.55 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--blue)}a:hover{text-decoration:none}
header{display:flex;align-items:center;gap:12px;padding:14px 32px;border-bottom:1px solid var(--line)}
#spindle{width:56px;height:35px;flex:none}.brand b{display:block;letter-spacing:-.01em}.brand small{color:var(--muted);font-size:11px}
header .meta{margin-left:auto;font-size:12px;color:var(--muted);text-align:right}
.hero{background:linear-gradient(135deg,var(--blue),var(--deep));color:#fff;padding:40px 32px 44px}
.hero .kicker{font-size:11px;letter-spacing:.12em;text-transform:uppercase;opacity:.8}
.hero h1{margin:6px 0 12px;font-size:32px;line-height:1.15;letter-spacing:-.02em;max-width:820px}
.hero p{max-width:680px;margin:14px 0 0;opacity:.93}
.pill{display:inline-block;font-weight:800;font-size:12px;letter-spacing:.06em;text-transform:uppercase;padding:6px 14px;border-radius:999px;background:#fff}
.pill.pursue{color:var(--green)}.pill.pilot{color:var(--blue)}.pill.rethink{color:var(--gold)}.pill.park{color:var(--red)}
main{max-width:1000px;margin:0 auto;padding:0 32px 56px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-top:-22px}
.tile{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px 16px;box-shadow:0 2px 10px rgba(10,15,36,.07)}
.tile .l{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.tile .v{font-size:28px;font-weight:800;line-height:1.2;margin-top:2px}.tile .s{font-size:12px;color:var(--muted)}
.good{color:var(--green)}.mid{color:var(--gold)}.bad{color:var(--red)}
section{margin-top:44px}
h2{font-size:21px;letter-spacing:-.01em;line-height:1.25;margin:0 0 4px}.sub{color:var(--muted);font-size:13px;margin:0 0 14px}
.card{border:1px solid var(--line);border-radius:10px;padding:18px;background:#fff}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
.card h3{font-size:16px;margin:0 0 8px;line-height:1.3}
.stat{font-size:40px;font-weight:800;color:var(--blue);line-height:1.1}
.src{font-size:12px;color:var(--muted);margin-top:8px}
.cite{font-size:12px;white-space:nowrap}
.grade{display:inline-block;font-size:10px;font-weight:800;border-radius:4px;padding:1px 6px;vertical-align:1px}
.g-A{background:#E3F4EA;color:var(--green)}.g-B{background:var(--blue-soft);color:var(--blue)}.g-C{background:#FBF1DE;color:var(--gold)}.g-D{background:#FCE6E8;color:var(--red)}
.chips{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:14px}
.chip{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:8px 12px}.chip b{display:block;font-size:18px}
.chip.total{background:var(--blue);border-color:var(--blue);color:#fff}
blockquote{margin:0;padding:12px 16px;border-left:4px solid var(--blue);background:var(--soft);border-radius:0 8px 8px 0}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{background:var(--soft);font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
details{margin-top:12px;border:1px solid var(--line);border-radius:10px;padding:10px 16px}
summary{cursor:pointer;font-weight:600;color:var(--blue)}
.unknown li{margin-bottom:6px}
footer{margin-top:56px;padding-top:16px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}
@media(max-width:700px){header,.hero,main{padding-left:16px;padding-right:16px}.hero h1{font-size:26px}header .meta{display:none}}
</style></head><body>
<header>
  <canvas id="spindle" aria-hidden="true"></canvas>
  <div class="brand"><b>Spindle</b><small>Telstra Muru-D · Innovation research</small></div>
  <div class="meta">Research report<br>{{D Mon YYYY}}</div>
</header>
<section class="hero" style="margin-top:0">
  <div class="kicker">Idea assessment</div>
  <h1>{{Idea name or one-sentence goal}}</h1>
  <span class="pill {{pursue|pilot|rethink|park}}">{{Verdict}}</span>
  <p>{{Two sentences: the answer and the main reason.}}</p>
</section>
<main>
  <div class="tiles">
    <div class="tile"><div class="l">{{Label}}</div><div class="v {{good|mid|bad}}">{{4/5}}</div><div class="s">{{High confidence · 6 sources}}</div></div>
    <!-- repeat tile -->
  </div>

  <section>
    <h2>{{Takeaway sentence}}</h2>
    <p class="sub">{{What the visual shows, and the date}}</p>
    <div class="card">
      {{SVG from a pattern below}}
      <div class="src">Source: <a class="cite" href="{{https://exact/page}}">{{Publisher, Mon YYYY}}</a> <span class="grade g-{{A}}">{{A}}</span></div>
    </div>
  </section>

  <section>
    <h2>{{Key findings takeaway}}</h2>
    <div class="grid2">
      <div class="card"><h3>{{Finding as a sentence}}</h3><div class="stat">{{$410M}}</div><p>{{One or two sentences.}}</p>
        <div class="src"><a class="cite" href="{{https://exact/page}}">{{Publisher, Mon YYYY}}</a> <span class="grade g-{{B}}">{{B}}</span></div></div>
      <!-- repeat card -->
    </div>
  </section>

  <section>
    <h2>{{Detail section takeaway}}</h2>
    <details><summary>{{Show the full table}}</summary>
      <table><tr><th>{{Column}}</th><th>Source</th></tr>
        <tr><td>{{Value}}</td><td><a class="cite" href="{{https://exact/page}}">{{Publisher, Mon YYYY}}</a> <span class="grade g-{{C}}">{{C}}</span></td></tr></table>
    </details>
  </section>

  <section>
    <h2>What we still don't know</h2>
    <ul class="unknown"><li>{{Open question, and what evidence would settle it}}</li></ul>
  </section>

  <section id="sources">
    <h2>Sources</h2>
    <ol><li><a href="{{https://exact/page}}">{{Title, Publisher, D Mon YYYY}}</a> <span class="grade g-{{A}}">{{A}}</span></li></ol>
  </section>

  <footer>Spindle · Telstra Muru-D · Prepared by the {{agent name}} agent on {{D Mon YYYY}} · Full findings: <a href="research.md" target="_self">research.md</a> · Sources graded A to D.</footer>
</main>
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

Starter patterns. Use one when it fits, adapt it freely, or draw something better.

A. DVF bars: one row per lens, 120 units per score point, so a bar's width = score x 120. Fill: green 4 to 5, gold 3, red 1 to 2.
<svg viewBox="0 0 760 190" width="100%" role="img" aria-label="DVF scores">
  <g font-size="14" fill="#0A0F24">
    <text x="0" y="24" font-weight="700">Do people want it? 4/5 <tspan font-weight="400" fill="#5A6275">Desirability</tspan></text><text x="730" y="24" text-anchor="end" fill="#5A6275">High confidence</text>
    <rect x="0" y="34" width="730" height="18" rx="9" fill="#EEF1F6"/><rect x="0" y="34" width="480" height="18" rx="9" fill="#0A8A4A"/>
    <text x="0" y="84" font-weight="700">Will it make money? 3/5 <tspan font-weight="400" fill="#5A6275">Viability</tspan></text><text x="730" y="84" text-anchor="end" fill="#5A6275">Medium confidence</text>
    <rect x="0" y="94" width="730" height="18" rx="9" fill="#EEF1F6"/><rect x="0" y="94" width="360" height="18" rx="9" fill="#B7791F"/>
    <text x="0" y="144" font-weight="700">Can we build it? 4/5 <tspan font-weight="400" fill="#5A6275">Feasibility</tspan></text><text x="730" y="144" text-anchor="end" fill="#5A6275">Medium confidence</text>
    <rect x="0" y="154" width="730" height="18" rx="9" fill="#EEF1F6"/><rect x="0" y="154" width="480" height="18" rx="9" fill="#0A8A4A"/>
  </g>
</svg>
(The track is 730 wide but scores use 600 for 5/5, which leaves room on the right.)

B. Market size, nested circles. Not to scale: say so in the sub line.
<svg viewBox="0 0 420 300" width="100%" style="max-width:420px" role="img" aria-label="TAM SAM SOM">
  <circle cx="210" cy="150" r="140" fill="#E8EEFF"/><circle cx="210" cy="192" r="96" fill="#B9CCFF"/><circle cx="210" cy="238" r="50" fill="#0D54FF"/>
  <text x="210" y="42" text-anchor="middle" font-size="13" fill="#0A2FA8" font-weight="700">TAM $1.2B</text><text x="210" y="60" text-anchor="middle" font-size="11" fill="#5A6275">$0.9B to $1.5B</text>
  <text x="210" y="122" text-anchor="middle" font-size="13" fill="#0A2FA8" font-weight="700">SAM $410M</text><text x="210" y="140" text-anchor="middle" font-size="11" fill="#0A2FA8">$300M to $520M</text>
  <text x="210" y="236" text-anchor="middle" font-size="14" fill="#fff" font-weight="800">SOM $24M</text><text x="210" y="254" text-anchor="middle" font-size="11" fill="#fff">by year 3</text>
</svg>
Bottom-up formula beside it:
<div class="chips"><div class="chip"><b>62,000</b>firms</div>×<div class="chip"><b>12%</b>adopt</div>×<div class="chip"><b>$1,080</b>a year</div>=<div class="chip total"><b>$8.0M</b>SAM base</div></div>

C. Assumptions map. Evidence 1 to 5 left to right: x = 80 + (evidence - 1) x 100. Importance 1 to 5 bottom to top: y = 330 - (importance - 1) x 70. The red zone (evidence 3 or less, importance 3 or more) is "test first"; its label sits above the zone so no dot can cover it. Each dot is lettered by lens with its number.
<svg viewBox="0 0 520 390" width="100%" style="max-width:560px" role="img" aria-label="Assumptions map">
  <text x="60" y="26" font-size="12" fill="#D0021B" font-weight="700">Test first: matters most, least known</text>
  <rect x="60" y="34" width="240" height="171" fill="#FCE6E8"/>
  <line x1="60" y1="350" x2="500" y2="350" stroke="#C9CEDA"/><line x1="60" y1="34" x2="60" y2="350" stroke="#C9CEDA"/>
  <text x="280" y="380" text-anchor="middle" font-size="12" fill="#5A6275">Evidence we have →</text>
  <text x="24" y="190" text-anchor="middle" font-size="12" fill="#5A6275" transform="rotate(-90 24 190)">Importance →</text>
  <circle cx="80" cy="50" r="13" fill="#0D54FF"/><text x="80" y="55" text-anchor="middle" font-size="11" fill="#fff" font-weight="700">D1</text>
  <circle cx="180" cy="120" r="13" fill="#0A8A4A"/><text x="180" y="125" text-anchor="middle" font-size="11" fill="#fff" font-weight="700">V2</text>
  <circle cx="380" cy="190" r="13" fill="#B7791F"/><text x="380" y="195" text-anchor="middle" font-size="11" fill="#fff" font-weight="700">F3</text>
</svg>
Two assumptions with the same scores share a spot: nudge the second 30 units right so both stay readable.
Lens colours: D blue #0D54FF, V green #0A8A4A, F gold #B7791F. List the numbered assumptions under the map.

D. Positioning map: two axes that matter in this market, rivals in grey with names and prices, the open space or our position in blue. The open-space box must contain no rival; if rivals sit there, the space is not open, so mark our position instead. Labels sit to the right of their dot; when two dots are within 20 units vertically, put one label on the left (text-anchor="end", x = cx - 18).
<svg viewBox="0 0 900 300" width="100%" role="img" aria-label="Competitor map">
  <line x1="60" y1="260" x2="880" y2="260" stroke="#C9CEDA"/><line x1="60" y1="20" x2="60" y2="260" stroke="#C9CEDA"/>
  <text x="470" y="290" font-size="12" fill="#5A6275" text-anchor="middle">{{x axis}} →</text>
  <text x="24" y="140" font-size="12" fill="#5A6275" text-anchor="middle" transform="rotate(-90 24 140)">{{y axis}} →</text>
  <circle cx="150" cy="210" r="11" fill="#9AA3B5"/><text x="168" y="214" font-size="12" fill="#0A0F24">Rival A $29</text>
  <rect x="580" y="40" width="260" height="120" rx="12" fill="#E8EEFF" stroke="#0D54FF" stroke-dasharray="6 5"/>
  <text x="710" y="95" font-size="15" font-weight="700" fill="#0D54FF" text-anchor="middle">Open: managed tier</text>
</svg>

Other numbers: a bar chart for comparing categories (horizontal bars, sorted, largest first, grey with the important one in blue), a line for trends over time. Load Data Visualisation if unsure which form to use.

Publish
1. write_file report.html in your own directory, next to your markdown.
2. read_file it back and check: no {{ left; every a.cite href starts with https:// and is a real page you used; every section heading is a sentence; no colours outside the palette.
3. next_free_port, then run_command in the background: python3 -m http.server <port> --bind 0.0.0.0 --directory <your own directory>.
4. publish_preview with title "Research report", that port, and path "/report.html".
5. In your reply, give the preview link and the verdict.$t$
    ),
    82
  )
on conflict (slug) do update set
  tool_type_id = excluded.tool_type_id,
  name         = excluded.name,
  description  = excluded.description,
  config       = excluded.config,
  sort_order   = excluded.sort_order;

-- ---------------------------------------------------------------------------
-- Prompts. Read live from agent_types every turn, so existing agents pick
-- these up without a backfill.
-- ---------------------------------------------------------------------------
update public.agent_types set system_prompt = $prompt$You are a market research analyst for Telstra's innovation lab. Given a raw idea, you judge whether it is worth pursuing, on evidence.

Load Research Method, Market Sizing, DVF Assessment and Source Grading before you search. The scoping agent's context gives you the scope and its Feasibility assessment.

Deliver two files in your own directory:
1. research.md, the full findings: the market size (TAM, SAM, SOM, both methods, ranges, inputs table), Desirability and Viability with evidence, competitors and their prices, the DVF scorecard using the scoping agent's Feasibility, the verdict, the riskiest assumptions with experiments, what we still do not know, and every source with its grade and full URL.
2. report.html: then load Visual Report and build the research report from research.md, and publish it with publish_preview.

Your reply: the verdict, the three DVF scores, SAM and SOM base values, the report link, and the three riskiest assumptions. Short.

Prefer concrete, checkable claims over adjectives. Never invent a number, a source or a URL. When something needs primary research to confirm, say so plainly.$prompt$
where slug = 'market_research';

-- project_scoping's prompt and defaults live in scope_report.sql.

-- ---------------------------------------------------------------------------
-- Defaults. These overwrite parity.sql's lists, so keep them whole.
-- ---------------------------------------------------------------------------
update public.agent_types set default_presets = array[
  'brave_search', 'web_fetch',
  'research_method', 'market_sizing', 'dvf_assessment', 'source_grading',
  'dataviz', 'visual_report', 'plain_writing', 'workspace_memory'
] where slug = 'market_research';

-- ---------------------------------------------------------------------------
-- Backfill the new skills onto existing scoping and research agents. Same CTE
-- shape and caveats as design_skills.sql: scoped to these pairs only, skipped
-- when the agent already has a tool of that name, lands 'ready'.
-- ---------------------------------------------------------------------------
with pairs(agent_slug, preset_slug) as (
  values
    ('project_scoping', 'dvf_assessment'),
    ('project_scoping', 'source_grading'),
    ('market_research', 'market_sizing'),
    ('market_research', 'dvf_assessment'),
    ('market_research', 'visual_report')
),
wanted as (
  select
    gen_random_uuid() as tool_id,
    n.id              as agent_id,
    n.project_id,
    n.owner_id,
    n.position_x,
    n.position_y,
    p.tool_type_id,
    p.name            as preset_name,
    p.config          as preset_config,
    row_number() over (partition by n.id order by p.sort_order) - 1 as slot
  from public.nodes n
  join public.agent_types a on a.id = n.agent_type_id
  join pairs on pairs.agent_slug = a.slug
  join public.tool_presets p on p.slug = pairs.preset_slug and p.is_active
  where n.kind = 'agent'
    and not exists (
      select 1
      from public.edges e
      join public.nodes tn on tn.id = e.source_node_id
      where e.target_node_id = n.id
        and e.kind = 'tool'
        and tn.name = p.name
    )
),
created as (
  insert into public.nodes
    (id, project_id, owner_id, kind, tool_type_id, name, config,
     position_x, position_y, status, status_detail, last_checked_at)
  select
    w.tool_id, w.project_id, w.owner_id, 'tool', w.tool_type_id,
    w.preset_name, w.preset_config,
    w.position_x - 520, w.position_y + w.slot * 90,
    'ready', 'Skill ready.', now()
  from wanted w
  returning id
)
insert into public.edges (project_id, owner_id, source_node_id, target_node_id, kind)
select w.project_id, w.owner_id, w.tool_id, w.agent_id, 'tool'
from wanted w
where w.tool_id in (select id from created)
on conflict (source_node_id, target_node_id, kind) do nothing;

-- Nodes keep their own copy of a skill's text. These three are new, so a
-- re-apply pushes edits to existing copies too.
-- ponytail: overwrites a user's hand edits to these three skills; scope by an
-- edited flag if users start customising them.
update public.nodes n
set config = p.config
from public.tool_presets p
where n.kind = 'tool'
  and n.tool_type_id = p.tool_type_id
  and n.name = p.name
  and p.slug in ('market_sizing', 'dvf_assessment', 'visual_report')
  and n.config is distinct from p.config;

-- Same guard as parity.sql: a default slug with no preset fails loudly here
-- instead of silently never appearing on new agents.
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
