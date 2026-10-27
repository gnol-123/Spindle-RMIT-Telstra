-- Scope report: a professional Scoping Brief (time, cost, data, feasibility,
-- risks) and a Scope Report skill for the Project Scoping agent's HTML report.
-- Apply after telstra_design.sql. Re-runnable.
begin;

insert into public.tool_presets (slug, tool_type_id, name, description, config, sort_order)
values
  (
    'scoping_brief',
    (select id from public.tool_types where slug = 'skill'),
    'Scoping Brief',
    'The structure of a good scope document.',
    jsonb_build_object(
      'description', 'Load before writing or revising a project scope.',
      'text', $t$Write scope.md as these sections, in order, each as short as it can be.

1. Goal
One sentence: the outcome the user gets, not the feature.

2. Non-goals
What this deliberately does not do. At least three. Then "Not decided yet": items that are neither in nor out. This is the most useful section.

3. User journey
3 to 5 steps of the first version, from the user's side.

4. Deliverables
Concrete things that will exist when done. Each must be checkable: a URL, a file, a passing test, a document.

5. Requirements
MoSCoW: Must, Should, Could, Won't. Must is 60% of effort or less, so Should and Could act as buffer.

6. Data inventory
Table: Data | Used for | Comes from | Owner | Sensitivity | Status.
Status is one of: Have, Need access, We build it, Doesn't exist.

7. Work packages
One row per package, estimated in person-weeks: best, likely, worst.
Expected = (best + 4 x likely + worst) / 6. Show the working.
Table: Package | Best | Likely | Worst | Expected | People | Waits on | Start week (likely, worst) | Calendar weeks (likely, worst) | End week (likely, worst).
People = how many work on it. Waits on = the packages that must finish first. Calendar weeks = person-weeks / people, for likely and worst. Likely start = the latest likely end of what it waits on; worst start = the latest worst end of what it waits on (0 if nothing). End = start + calendar weeks.

8. Team
- Person-weeks by role.
- Team size: distinct people across all packages.
- Calendar weeks to pilot: likely = the latest likely end; worst = the latest worst end; best = likely x (total best pw / total likely pw). Check: the last likely end in section 7 equals this likely figure.
- The blocking step: the package with the latest likely end. It sets the end date.

9. Cost
Expected person-weeks x 5 x day rate, plus infrastructure and licences. Give best, expected and worst.
Name the blended AU day rate and its source. Search for a current published AU contractor rate guide. If you find none, use $950/day and label it "assumption".

10. Milestones
Deliverables grouped in the order they unblock each other. Name what each milestone unblocks and give its target week.

11. Dependencies
Things outside this scope it needs: accounts, data, decisions, other work.

12. Feasibility (TELOS)
Technology, Cost to build and run, Law and privacy, Operations (Telstra assets and channels), Schedule.
- Technology: give a TRL 1 to 9 for each key piece of technology.
- Score each check 1 to 5 with DVF Assessment's rubric.
- Overall Feasibility = the weakest check, with confidence.

13. Risk register
4 to 8 risks, highest likelihood x impact first; the first is the top risk. Each has likelihood 1 to 5, impact 1 to 5, a named owner role and a mitigation.

14. Stakeholders
Who is affected, the intended audience, and who signs off.

15. Success criteria
Measurable. A number and a way to check it.

16. Open questions
What you had to guess. Ask these before inventing answers.

Rules:
- No adjectives where a number will do.
- A deliverable that cannot be checked is a wish, rewrite it.
- If the user's ask is larger than one scope, say so and propose the split before scoping the first piece.
- Every estimate is a range. Early estimates are typically -25% to +75% off; say so once.
- Every dollar figure states its day rate. Every day rate states its source or says "assumption".$t$
    ),
    20
  ),
  (
    'scope_report',
    (select id from public.tool_types where slug = 'skill'),
    'Scope Report',
    'The scope report template and how to publish it.',
    jsonb_build_object(
      'description', 'Load after scope.md is written, to turn it into report.html and publish it beside the chat.',
      'text', $t$Turn your finished scope.md into report.html: a professional Telstra-style scope report in light mode, for a Telstra innovation lab team deciding what to build, how long it takes, what it costs, what it needs and what could stop it. The markdown comes first. The report is a tuned view of it: no new claims.

How it reads: the first screen answers the whole question in one sentence. Each band down the page goes one level deeper. The working and sources come last.

Write for two readers on one page. The top must make sense to someone with no technical or project background; the bottom must satisfy an expert checking your estimates.
- Top (hero, What we're building): everyday words, short sentences, no jargon or acronyms. Say "must have" before "MoSCoW", "how ready the technology is" before "TRL". If a term must appear, its plain meaning goes first and the term follows.
- Middle (Plan and cost to Risks): plain words with the standard terms named once, each claim with its number and citation.
- Bottom (inside <details>, the estimate table, sources): full expert detail. Formulas with every input, the day rate and its source, the scoring rubric, confidence reasoning. Precise terms are fine here.
- Band labels and section headings use plain words. Never open a section with an acronym.
- Test the top: would a new graduate in any team get the answer and the reason without asking you? If not, rewrite it.

Rules
- Use the template below as it is. Keep the style block, the header, the Spindle script and the footer unchanged. Fill every {{placeholder}}, repeat blocks as needed, and delete blocks you have nothing for. Never add colours, fonts, libraries, images, or external scripts and styles.
- Repeat the element or group just before each <!-- repeat --> once per item.
- Headings state the takeaway as a sentence ("Legal sign-off sets the end date"), not a topic ("Timeline").
- Citations are real, clickable links. Every number and claim carries one: <a class="cite" href="FULL_URL">Publisher, Mon YYYY</a> <span class="grade g-A">A</span>. The href is the exact page URL you fetched or found in search, copied character for character and starting with https://. Never link a search results page, and never link a homepage when the claim came from a specific page. No URL for a claim means you write "unverified" instead of a link. Your own estimates need no link: scope.md's working is their source.
- The template's <base target="_blank"> makes every link open in a new tab. Links that jump within the page get target="_self".
- No text may overlap another label, dot or line. Before writing an SVG, list each label's x, y and rough width (7 units per character at 12px) and move any that collide. Keep every mark at least 15 units inside the viewBox edge.
- No tile or card row at the top and no score bars. The hero sentence carries the numbers.
- Cut small text the reader can infer: no caption, sub-line or source line that only repeats what the heading or visual already shows. Citations stay wherever a number or claim needs one.
- Every estimate is a range. Every dollar figure states its day rate, and every day rate states its source or says "assumption".
- The same number reads the same everywhere: hero, timeline, cost bar and estimate table all match scope.md.
- Expected cost = expected (three-point) person-weeks × 5 × day rate + infrastructure and licences. Best cost = the sum of best person-weeks × 5 × day rate + infrastructure; worst cost the same with worst. The hero, cost bar and estimate table total all use these.
- Load Plain Writing before you write the prose.

Colours (already defined in the template): ink #0A0F24, Telstra blue #0D54FF, deep blue #0A2FA8, soft blue #E8EEFF, mid blue #B9CCFF for worst-case tails, track #EEF1F6, green #0A8A4A good, gold #B7791F caution and the blocker, red #D0021B bad, grey #9AA3B5 context, tints #E3F4EA, #FBF1DE, #FCE6E8, amber #F44E1A for the Spindle mark only. Scores 4 to 5 use green, 3 uses gold, 1 to 2 use red.

Scope report sections, in order (the scope.md sections each draws on are in brackets)
- Hero (Goal, Team, Cost, Feasibility, Risk register): the answer as one sentence, with <em> highlights on the time and the cost and <em class="warn"> on the blocker. The blocker is the top risk (risk A: highest likelihood × impact). Reword the sentence to fit the facts (when Feasibility is 2/5 or lower, lead with the blocker), but keep the three highlights. One line under it: feasibility score and confidence, person-weeks and day rate, cost range, time range.
- Band 1, What we're building (User journey, Deliverables, Non-goals): the journey strip (F), then In / Out / Not decided yet as three columns. In = Deliverables, Out = Non-goals, Not decided yet = the "Not decided yet" list.
- Band 2, Plan and cost (Work packages, Team, Milestones, Cost): the timeline (G), then the cost range bar (H) beside person-weeks by role (I).
- Band 3, What we need (Requirements, Data inventory): the MoSCoW board (J), then the data table (K).
- Band 4, Can we build it, in detail (Feasibility): TELOS rows (L) beside a TRL meter for each key piece of technology (M).
- Band 5, Risks (Risk register): the 5 x 5 risk grid (N) beside each risk's owner and plan.
- Band 6, The working (Work packages, Cost, Success criteria, Stakeholders, Dependencies, Open questions, Feasibility, the assumptions ledger): the estimate table (O), open by default, then the collapsed sections.
- Sources: every source, linked and graded, best grade first.

Template
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{Idea name}} | Scope report</title>
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
.hero .big{margin:6px 0 0;font-size:30px;line-height:1.35;font-weight:600;letter-spacing:-.015em;max-width:860px}
.big em{font-style:normal;background:rgba(255,255,255,.18);border-radius:6px;padding:0 8px;font-weight:800}
.big em.warn{background:#FBF1DE;color:var(--gold)}
.hero .foot{margin-top:16px;font-size:13px;opacity:.85}
main{max-width:1000px;margin:0 auto;padding:0 32px 56px}
.good{color:var(--green)}.mid{color:var(--gold)}.bad{color:var(--red)}.blue{color:var(--blue)}
.level{display:flex;align-items:center;gap:10px;margin:64px 0 10px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:700}
main>.level:first-child{margin-top:40px}
.level .dots{display:flex;gap:4px}.level .dots i{width:8px;height:8px;border-radius:50%;background:var(--line)}.level .dots i.on{background:var(--blue)}
.level:after{content:"";flex:1;height:1px;background:var(--line)}
section{margin-top:28px}.level+section{margin-top:0}
h2{font-size:21px;letter-spacing:-.01em;line-height:1.25;margin:0 0 14px}.sub{color:var(--muted);font-size:13px;margin:-10px 0 14px}
.card{border:1px solid var(--line);border-radius:10px;padding:18px;background:#fff}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
.grid3{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
.card h3{font-size:16px;margin:0 0 8px;line-height:1.3}
.cite{font-size:12px;white-space:nowrap}
.grade{display:inline-block;font-size:10px;font-weight:800;border-radius:4px;padding:1px 6px;vertical-align:1px}
.g-A{background:#E3F4EA;color:var(--green)}.g-B{background:var(--blue-soft);color:var(--blue)}.g-C{background:#FBF1DE;color:var(--gold)}.g-D{background:#FCE6E8;color:var(--red)}
.journey{display:flex;flex-wrap:wrap}
.step{flex:1;min-width:150px;margin:0 22px 10px 0;padding:14px 16px;background:var(--soft);border:1px solid var(--line);border-radius:10px;position:relative}
.step:last-child{margin-right:0}
.step:not(:last-child):after{content:"→";position:absolute;right:-19px;top:40%;color:var(--blue);font-weight:800}
.step .n{width:24px;height:24px;border-radius:50%;background:var(--blue);color:#fff;font-size:12px;font-weight:800;display:flex;align-items:center;justify-content:center;margin-bottom:8px}
.step b{display:block;font-size:14px}.step span{font-size:13px;color:var(--muted)}
.col h3{display:flex;align-items:center;gap:8px}.col ul{margin:0;padding-left:18px;font-size:14px}.col li{margin-bottom:4px}
.tag{font-size:11px;font-weight:800;padding:2px 8px;border-radius:4px;letter-spacing:.04em;text-transform:uppercase}
.t-in{background:#E3F4EA;color:var(--green)}.t-out{background:#FCE6E8;color:var(--red)}.t-tbd{background:#FBF1DE;color:var(--gold)}
.range{position:relative;height:56px;margin:8px 4px 0}
.range .track{position:absolute;top:22px;left:0;right:0;height:10px;background:#EEF1F6;border-radius:5px}
.range .band{position:absolute;top:22px;right:0;height:10px;background:#B9CCFF;border-radius:5px}
.range .base{position:absolute;top:14px;width:4px;height:26px;margin-left:-2px;background:var(--blue);border-radius:2px}
.range .lab{position:absolute;top:42px;font-size:12px;color:var(--muted);transform:translateX(-50%);white-space:nowrap}
.range .lab.b{top:-4px;color:var(--blue);font-weight:800;font-size:13px}
.range .lab.w{right:0;transform:none}
.bars div{display:grid;grid-template-columns:170px 1fr 40px;align-items:center;gap:10px;font-size:13px;margin-bottom:6px}
.bars i{display:block;height:12px;border-radius:6px;background:#9AA3B5}.bars i.hi{background:var(--blue)}
.moscow{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}
.moscow .col{border-radius:10px;padding:12px 14px;border:1px solid var(--line)}
.moscow .col h3{font-size:13px;text-transform:uppercase;letter-spacing:.06em;margin:0 0 8px}
.m-must{background:var(--blue-soft)}.m-should{background:var(--soft)}.m-wont{border-style:dashed}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{background:var(--soft);font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.st{font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;white-space:nowrap}
.st-have{background:#E3F4EA;color:var(--green)}.st-ask{background:#FBF1DE;color:var(--gold)}.st-build{background:var(--blue-soft);color:var(--blue)}.st-none{background:#FCE6E8;color:var(--red)}
.telos .row{display:grid;grid-template-columns:130px 44px 1fr;gap:12px;align-items:start;padding:10px 0;border-bottom:1px solid var(--line);font-size:14px}.telos .row:last-child{border:0}
.score{font-weight:800}
.trl{display:flex;gap:3px;margin:6px 0 2px}.trl i{flex:1;height:10px;border-radius:2px;background:#EEF1F6}.trl i.on{background:var(--blue)}
.trlrow{font-size:13px;margin-bottom:12px}.trlrow b{font-size:14px}
details{margin-top:12px;border:1px solid var(--line);border-radius:10px;padding:10px 16px}
summary{cursor:pointer;font-weight:600;color:var(--blue)}
.formula{font-family:ui-monospace,Consolas,monospace;font-size:13px;background:var(--soft);padding:10px 12px;border-radius:8px;margin:10px 0}
.risklist{font-size:13px}.risklist div{margin-bottom:10px}
.rail{position:fixed;right:18px;bottom:24px;display:none;flex-direction:column;gap:12px;font-size:11px}
.rail a{display:flex;align-items:center;gap:8px;color:var(--muted);text-decoration:none}
.rail a:before{content:"";width:8px;height:8px;border-radius:50%;background:var(--line)}
.rail a:hover{color:var(--blue)}.rail a:hover:before{background:var(--blue)}
@media(min-width:1260px){.rail{display:flex}}
footer{margin-top:56px;padding-top:16px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}
@media(max-width:700px){header,.hero,main{padding-left:16px;padding-right:16px}.hero .big{font-size:24px}header .meta{display:none}.bars div{grid-template-columns:120px 1fr 32px}.step{flex-basis:100%;margin-right:0}.step:not(:last-child):after{content:none}.telos .row{grid-template-columns:1fr auto}.telos .row span:last-child{grid-column:1/-1}}
</style></head><body>
<header>
  <canvas id="spindle" aria-hidden="true"></canvas>
  <div class="brand"><b>Spindle</b><small>Telstra Muru-D · Innovation research</small></div>
  <div class="meta">Scope report<br>{{D Mon YYYY}}</div>
</header>
<nav class="rail"><a href="#l1" target="_self">The answer</a><a href="#l2" target="_self">What we're building</a><a href="#l3" target="_self">Plan and cost</a><a href="#l4" target="_self">What we need</a><a href="#l5" target="_self">Can we build it</a><a href="#l6" target="_self">Risks</a><a href="#l7" target="_self">The working</a></nav>
<section class="hero" style="margin-top:0" id="l1">
  <div class="kicker">Project scope · {{Idea name}}</div>
  <h1 class="big">We can build this in <em>about {{likely weeks to pilot}} weeks</em> with a team of {{team size, in words}}, for <em>roughly {{expected cost, e.g. $160k}}</em>. The one thing that could stop it is <em class="warn">{{the blocker, in plain words}}</em>{{optional: ", so" and the first step against it}}.</h1>
  <div class="foot">Feasibility {{score}}/5, {{high|medium|low}} confidence · {{expected}} person-weeks at {{$950}}/day, {{rate source name, or "assumption"}} · {{best cost}} to {{worst cost}} · {{best}} to {{worst}} weeks</div>
</section>
<main>
  <div class="level" id="l2"><span class="dots"><i class="on"></i><i></i><i></i><i></i><i></i><i></i></span>What we're building</div>
  <section>
    <h2>{{Takeaway: what the first version does for the user}}</h2>
    <div class="journey">
      <div class="step"><div class="n">{{1}}</div><b>{{Step, at most 5 words}}</b><span>{{One line, optional}}</span></div><!-- repeat -->
    </div>
  </section>
  <section>
    <h2>{{Takeaway: what is in, and what waits}}</h2>
    <div class="grid3">
      <div class="card col"><h3><span class="tag t-in">In</span></h3><ul><li>{{Deliverable}}</li><!-- repeat --></ul></div>
      <div class="card col"><h3><span class="tag t-out">Out</span></h3><ul><li>{{Non-goal}}</li><!-- repeat --></ul></div>
      <div class="card col"><h3><span class="tag t-tbd">Not decided yet</span></h3><ul><li>{{Undecided item}}</li><!-- repeat --></ul></div>
    </div>
  </section>

  <div class="level" id="l3"><span class="dots"><i class="on"></i><i class="on"></i><i></i><i></i><i></i><i></i></span>Plan and cost</div>
  <section>
    <h2>{{Takeaway: when the pilot lands; name the blocking step if it is not the hero's blocker}}</h2>
    <div class="card">{{Timeline SVG, pattern G below}}</div>
  </section>
  <section>
    <h2>{{Takeaway: the expected cost and its range}}</h2>
    <p class="sub">{{expected}} person-weeks at {{$950}}/day, {{rate source as a cite link, or "assumption"}}, plus {{$8k}} of {{infrastructure and licences, in plain words}}.</p>
    <div class="grid2">
      <div class="card">
        <div class="range"><div class="track"></div><div class="band" style="left:{{best%}}"></div><div class="base" style="left:{{expected%}}"></div>
          <div class="lab b" style="left:{{expected%}}">{{$160k}} expected</div><div class="lab" style="left:{{best%}}">{{$100k}} best</div><div class="lab w">{{$250k}} worst</div></div>
      </div>
      <div class="card"><h3>Person-weeks by role</h3>
        <div class="bars"><div><span>{{Role}}</span><i style="width:{{width}}%"></i><span>{{9}}</span></div><!-- repeat --></div>
      </div>
    </div>
  </section>

  <div class="level" id="l4"><span class="dots"><i class="on"></i><i class="on"></i><i class="on"></i><i></i><i></i><i></i></span>What we need</div>
  <section>
    <h2>{{Takeaway: how many must-haves, and whether the pilot survives without the rest}}</h2>
    <div class="moscow">
      <div class="col m-must"><h3 class="blue">Must have</h3><ul><li>{{Requirement}}</li><!-- repeat --></ul></div>
      <div class="col m-should"><h3>Should have</h3><ul><li>{{Requirement}}</li><!-- repeat --></ul></div>
      <div class="col"><h3>Could have</h3><ul><li>{{Requirement}}</li><!-- repeat --></ul></div>
      <div class="col m-wont"><h3 class="bad">Won't have (now)</h3><ul><li>{{Requirement}}</li><!-- repeat --></ul></div>
    </div>
  </section>
  <section>
    <h2>{{Takeaway: which data we have, and which to chase}}</h2>
    <div class="card" style="padding:0;overflow:auto">
      <table><tr><th>Data</th><th>Used for</th><th>Comes from</th><th>Sensitivity</th><th>Status</th></tr>
        <tr><td>{{Dataset}}</td><td>{{What it is used for}}</td><td>{{Where it comes from}}</td><td>{{Sensitivity}}</td><td><span class="st st-{{have|ask|build|none}}">{{Have|Need access|We build it|Doesn't exist}}</span></td></tr><!-- repeat -->
      </table>
    </div>
  </section>

  <div class="level" id="l5"><span class="dots"><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i></i><i></i></span>Can we build it, in detail</div>
  <section>
    <h2>{{Takeaway: what is ready, and which check is weakest}}</h2>
    <div class="grid2">
      <div class="card telos">
        <div class="row"><b>{{Technology|Cost to build and run|Law and privacy|Operations|Schedule}}</b><span class="score {{good|mid|bad}}">{{4}}/5</span><span>{{One line, with its citation}}</span></div><!-- repeat -->
      </div>
      <div class="card"><h3>How ready each piece of technology is, 1 (idea) to 9 (proven in market)</h3>
        <div class="trlrow"><b>{{Piece of technology}}</b> · TRL {{6}}<div class="trl"><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i></i><i></i><i></i></div></div><!-- repeat -->
      </div>
    </div>
  </section>

  <div class="level" id="l6"><span class="dots"><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i></i></span>Risks</div>
  <section>
    <h2>{{Takeaway: how many risks are red, and the one to act on first}}</h2>
    <div class="grid2">
      <div class="card">{{Risk grid SVG, pattern N below}}</div>
      <div class="card risklist"><div><b>{{A}} {{Risk}}.</b> Owner: {{role}}. Plan: {{mitigation}}.</div><!-- repeat --></div>
    </div>
  </section>

  <div class="level" id="l7"><span class="dots"><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i><i class="on"></i></span>The working</div>
  <section>
    <h2>How the estimate was built</h2>
    <details open><summary>Effort by work package (three-point estimate)</summary>
      <div class="formula">expected = (best + 4 × likely + worst) ÷ 6 · cost = person-weeks × 5 days × {{$950}}/day</div>
      <div style="overflow:auto"><table><tr><th>Work package</th><th>Best</th><th>Likely</th><th>Worst</th><th>Expected (pw)</th><th>Cost</th></tr>
        <tr><td>{{Work package}}</td><td>{{3}}</td><td>{{4}}</td><td>{{6}}</td><td>{{4.2}}</td><td>{{$20k}}</td></tr><!-- repeat -->
        <tr><td>{{Infrastructure and licences}}</td><td colspan="4">{{What it covers}}</td><td>{{$8k}}</td></tr>
        <tr><th>Total</th><th>{{sum}}</th><th>{{sum}}</th><th>{{sum}}</th><th>{{sum}}</th><th>{{expected cost}}</th></tr>
      </table></div>
    </details>
    <details><summary>Success criteria</summary><ul><li>{{Criterion: the number, and how we check it}}</li><!-- repeat --></ul></details>
    <details><summary>Stakeholders and who signs off</summary><ul><li>{{Who, and their part}}</li><!-- repeat --></ul></details>
    <details><summary>Assumptions ledger</summary>{{The assumptions ledger table from scope.md}}</details>
    <details><summary>Dependencies outside this project</summary><ul><li>{{Dependency}}</li><!-- repeat --></ul></details>
    <details><summary>Open questions</summary><ul><li>{{Question}}</li><!-- repeat --></ul></details>
    <details><summary>Feasibility scoring and confidence</summary><p>{{Each TELOS check's score and reason, the rubric, why the weakest check sets Feasibility, and the confidence reasoning.}}</p></details>
  </section>

  <section id="sources">
    <h2>Sources</h2>
    <ol><li><a href="{{https://exact/page}}">{{Title, Publisher, D Mon YYYY}}</a> <span class="grade g-{{A}}">{{A}}</span></li></ol>
  </section>

  <footer>Spindle · Telstra Muru-D · Prepared by the Project Scoping agent on {{D Mon YYYY}} · Full findings: <a href="scope.md" target="_self">scope.md</a> · Estimates are ranges.</footer>
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

Patterns. F, H to M and O are in the template; G and N are below. Keep the formulas.

F. Journey strip: 3 to 5 steps from User journey, numbered 1 up.

G. Timeline: one row per work package, in start order. Labels sit in the column x 0 to 170: at most 24 characters. Read each row's likely start and End week (likely, worst) straight from the Work packages table; never derive new ones. Let W = the latest worst end across all rows, rounded up to a multiple of 4; week w sits at x = 180 + w × (560 / W). With n rows, row i (from 0) has its bar at y = 40 + 34i and its label at y = 52 + 34i. Each bar starts at the likely start. The solid #0D54FF bar runs to the likely end; the #B9CCFF tail behind it runs to the worst end. The blocking row (Team's blocking step) is #B7791F with a #FBF1DE tail and a bold gold label, and keeps its start-order position. The last likely end equals the hero's weeks to pilot. Gridlines every 4 weeks (every 8 past 60 weeks). Milestones are diamonds at y 20 at x = 180 + (milestone target week) × (560 / W), with the label at x + 12; if a label (about 6 units per character) would reach the next diamond or x 745, put it on the left instead (text-anchor="end", x - 12), and if that collides too, shorten it.
<svg viewBox="0 0 760 {{82 + 34n}}" width="100%" role="img" aria-label="Timeline">
  <g stroke="#EEF1F6"><line x1="{{x}}" y1="34" x2="{{x}}" y2="{{28 + 34n}}"/><!-- repeat --></g>
  <text x="0" y="{{52 + 34i}}" font-size="12" fill="#0A0F24">{{Work package}}</text>
  <rect x="{{start x}}" y="{{40 + 34i}}" width="{{(worst end - start) × 560 / W}}" height="16" rx="8" fill="#B9CCFF"/><rect x="{{start x}}" y="{{40 + 34i}}" width="{{(likely end - start) × 560 / W}}" height="16" rx="8" fill="#0D54FF"/><!-- repeat -->
  <text x="0" y="{{52 + 34i}}" font-size="12" fill="#B7791F" font-weight="700">{{Blocking package}}</text>
  <rect x="{{start x}}" y="{{40 + 34i}}" width="{{(worst end - start) × 560 / W}}" height="16" rx="8" fill="#FBF1DE"/><rect x="{{start x}}" y="{{40 + 34i}}" width="{{(likely end - start) × 560 / W}}" height="16" rx="8" fill="#B7791F"/>
  <path d="M{{x}} 20 l6 6 -6 6 -6 -6z" fill="#0A0F24"/><text x="{{x + 12}}" y="30" font-size="11" fill="#0A0F24">{{Milestone}}</text><!-- repeat -->
  <g transform="translate(0,{{34n}})" font-size="11" fill="#5A6275">
    <text x="180" y="44" text-anchor="middle">wk 0</text><text x="{{x}}" y="44" text-anchor="middle">{{4}}</text><!-- repeat -->
    <rect x="180" y="57" width="20" height="10" rx="5" fill="#0D54FF"/><text x="206" y="66">likely</text>
    <rect x="262" y="57" width="20" height="10" rx="5" fill="#B9CCFF"/><text x="288" y="66">worst case</text>
    <rect x="368" y="57" width="20" height="10" rx="5" fill="#B7791F"/><text x="394" y="66">sets the end date</text>
  </g>
</svg>

H. Cost range bar: positions are % of the worst case: best% = best ÷ worst × 100, expected% = expected ÷ worst × 100. The band runs from best to the right end, where the worst label sits.

I. Person-weeks by role: one row per role from Team, largest first. Width = the role's person-weeks ÷ the largest × 100. Only the largest bar keeps class="hi" (blue); the rest are grey. Roles at most 24 characters.

J. MoSCoW board: from Requirements, items under 8 words each.

K. Data table: from Data inventory. Status classes: Have = st-have, Need access = st-ask, We build it = st-build, Doesn't exist = st-none.

L. TELOS rows: all five checks in Feasibility's order. Score class: good 4 to 5, mid 3, bad 1 to 2. The hero's Feasibility score equals the lowest of the five.

M. TRL meter: one row per key piece of technology from Feasibility. 9 segments; the first TRL of them get class="on".

N. Risk grid: likelihood L and impact I run 1 to 5. Cell (L, I) has its top-left at x = 60 + (L-1) × 50, y = 20 + (5-I) × 50, and its dot at the centre (x + 25, y + 25). The cells are already filled: #FCE6E8 when L × I is 15 or more, #FBF1DE when 8 to 14, otherwise #EEF1F6. Dots use the same bands: red #D0021B, gold #B7791F, grey #9AA3B5. Letter the dots A, B, C in the risk list's order, highest L × I first. When two risks share a cell, dots are 24 units wide, so put the first at x + 13 and the second at x + 37 (both at y + 25). A third goes at x + 25, y + 38, with the first two raised to y + 15.
<svg viewBox="0 0 340 320" width="100%" style="max-width:340px" role="img" aria-label="Risk grid">
  <g stroke="#fff" stroke-width="2">
    <rect x="60" y="20" width="50" height="50" fill="#EEF1F6"/><rect x="110" y="20" width="50" height="50" fill="#FBF1DE"/><rect x="160" y="20" width="50" height="50" fill="#FCE6E8"/><rect x="210" y="20" width="50" height="50" fill="#FCE6E8"/><rect x="260" y="20" width="50" height="50" fill="#FCE6E8"/>
    <rect x="60" y="70" width="50" height="50" fill="#EEF1F6"/><rect x="110" y="70" width="50" height="50" fill="#FBF1DE"/><rect x="160" y="70" width="50" height="50" fill="#FBF1DE"/><rect x="210" y="70" width="50" height="50" fill="#FCE6E8"/><rect x="260" y="70" width="50" height="50" fill="#FCE6E8"/>
    <rect x="60" y="120" width="50" height="50" fill="#EEF1F6"/><rect x="110" y="120" width="50" height="50" fill="#EEF1F6"/><rect x="160" y="120" width="50" height="50" fill="#FBF1DE"/><rect x="210" y="120" width="50" height="50" fill="#FBF1DE"/><rect x="260" y="120" width="50" height="50" fill="#FCE6E8"/>
    <rect x="60" y="170" width="50" height="50" fill="#EEF1F6"/><rect x="110" y="170" width="50" height="50" fill="#EEF1F6"/><rect x="160" y="170" width="50" height="50" fill="#EEF1F6"/><rect x="210" y="170" width="50" height="50" fill="#FBF1DE"/><rect x="260" y="170" width="50" height="50" fill="#FBF1DE"/>
    <rect x="60" y="220" width="50" height="50" fill="#EEF1F6"/><rect x="110" y="220" width="50" height="50" fill="#EEF1F6"/><rect x="160" y="220" width="50" height="50" fill="#EEF1F6"/><rect x="210" y="220" width="50" height="50" fill="#EEF1F6"/><rect x="260" y="220" width="50" height="50" fill="#EEF1F6"/>
  </g>
  <g font-size="12" font-weight="700" fill="#fff" text-anchor="middle">
    <circle cx="{{x + 25}}" cy="{{y + 25}}" r="12" fill="{{#D0021B|#B7791F|#9AA3B5}}"/><text x="{{x + 25}}" y="{{y + 29}}">{{A}}</text><!-- repeat -->
  </g>
  <text x="185" y="295" text-anchor="middle" font-size="12" fill="#5A6275">How likely →</text>
  <text x="30" y="145" text-anchor="middle" font-size="12" fill="#5A6275" transform="rotate(-90 30 145)">How bad →</text>
</svg>

O. Estimate table: one row per work package, then infrastructure and licences, then the totals. The totals match the hero and the cost bar.

Publish
1. write_file report.html in your own directory, next to scope.md.
2. read_file it back and check: no {{ left; no class="tile"; every a.cite href starts with https:// and is a real page you used; every section heading is a sentence; no colours outside the palette.
3. next_free_port, then run_command in the background: python3 -m http.server <port> --bind 0.0.0.0 --directory <your own directory>.
4. publish_preview with title "Scope report", that port, and path "/report.html".
5. In your reply, give the preview link, the Feasibility score with its confidence, and the time and cost ranges.$t$
    ),
    83
  )
on conflict (slug) do update set
  tool_type_id = excluded.tool_type_id,
  name = excluded.name,
  description = excluded.description,
  config = excluded.config,
  sort_order = excluded.sort_order;

update public.agent_types set system_prompt = $prompt$You are a project scoping assistant for Telstra's innovation lab. Convert the user's raw idea into a scoped plan and judge whether Telstra can build it.

Load Scoping Brief and DVF Assessment first. Cover everything Scoping Brief lists. Assess Feasibility in Scoping Brief's TELOS section, scoring each check with DVF Assessment's rubric; the weakest check is the Feasibility score Market Research uses, with confidence. DVF's Telstra assets fall under Operations, its dependencies and time to MVP under Schedule, its cost under Cost to build and run. Search to check feasibility claims, and cite what you find.

Deliver two files in your own directory:
1. scope.md: the full scope, the Feasibility assessment, the assumptions ledger, and sources with full URLs.
2. report.html: load Scope Report and build the report from scope.md, and publish it with publish_preview.

When asked to revise against research findings, update both files and republish, then list what changed and why.

Your reply: the goal, time to pilot and cost with ranges, the Feasibility score and confidence, the report link, and the open questions that matter most. Short. Ask for a specific detail only when you cannot proceed on a stated assumption; otherwise assume, say so, and deliver.$prompt$
where slug = 'project_scoping';

update public.agent_types set default_presets = array[
  'brave_search', 'web_fetch',
  'brainstorming', 'scoping_brief', 'dvf_assessment', 'assumptions_ledger',
  'source_grading', 'scope_report', 'plain_writing', 'workspace_memory'
] where slug = 'project_scoping';

-- Backfill Scope Report onto existing scoping agents. Same CTE shape as telstra_design.sql.
-- Slot 2: idea_assessment.sql's backfill uses slots 0 and 1.
with wanted as (
  select
    gen_random_uuid() as tool_id,
    n.id              as agent_id,
    n.project_id,
    n.owner_id,
    n.position_x,
    n.position_y,
    p.tool_type_id,
    p.name            as preset_name,
    p.config          as preset_config
  from public.nodes n
  join public.agent_types a on a.id = n.agent_type_id
  join public.tool_presets p on p.slug = 'scope_report' and p.is_active
  where n.kind = 'agent'
    and a.slug = 'project_scoping'
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
    w.position_x - 520, w.position_y + 2 * 90,
    'ready', 'Skill ready.', now()
  from wanted w
  returning id
)
insert into public.edges (project_id, owner_id, source_node_id, target_node_id, kind)
select w.project_id, w.owner_id, w.tool_id, w.agent_id, 'tool'
from wanted w
where w.tool_id in (select id from created)
on conflict (source_node_id, target_node_id, kind) do nothing;

-- Push the text to existing copies. Visual Report repeats idea_assessment.sql's
-- push (already current, so it matches nothing); harmless, kept as a backstop.
-- ponytail: overwrites hand edits to these skills; scope by an edited flag if users customise them.
update public.nodes n
set config = p.config
from public.tool_presets p
where n.kind = 'tool'
  and n.tool_type_id = p.tool_type_id
  and n.name = p.name
  and p.slug in ('scoping_brief', 'scope_report', 'visual_report')
  and n.config is distinct from p.config;

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
