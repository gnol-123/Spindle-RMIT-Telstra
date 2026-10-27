-- Idea assessment: TAM/SAM/SOM market sizing, a DVF scorecard, an evidence
-- ledger with code-computed sizing and quote checks, and a Telstra-styled HTML
-- report. Market Research owns sizing, desirability and viability; Project
-- Scoping owns feasibility. Source Grading here overrides defaults.sql.
-- Apply after realtime_edges.sql. Re-runnable.
begin;

-- ---------------------------------------------------------------------------
-- The skills. Dollar-quoted so apostrophes, $ signs and newlines are literal.
-- ---------------------------------------------------------------------------
insert into public.tool_presets (slug, tool_type_id, name, description, config, sort_order)
values
  (
    'source_grading',
    (select id from public.tool_types where slug = 'skill'),
    'Source Grading',
    'How to rate and cite what you found.',
    jsonb_build_object(
      'description', 'Load before presenting findings that rest on web sources.',
      'text', $t$Grade every source and every number you rely on. Two grades, kept separate: who published it, and whether this specific number holds up.

Source grade, A to D: who published it. This letter goes on every pill.
- A: official statistics, regulators, audited filings, the vendor's own pricing page, a dataset with a stated method.
- B: a named analyst, firm or survey with its method disclosed, or reputable press that names its primary source.
- C: secondary with no method shown, including report catalogues on their own pages, or older than two years on a fast-moving topic.
- D: press-release wires, LinkedIn posts, marketing copy, forums, content farms, undated pages, unknown publishers. Leads only, never the basis of a claim.

Claim grade, 1 to 6: does this specific number hold up. Judge it apart from the source.
- 1: confirmed by an independent group, or it is the primary record itself.
- 2: consistent with primary anchors, not independently confirmed.
- 3: plausible, unchecked.
- 4: doubtful: it conflicts with other figures, or its growth rate does not recompute.
- 5: contradicted: more than 2x a primary anchor for the same scope, or it recomputes wrong. Exclude it from calculations.
- 6: cannot judge.
In tables write both together, e.g. "B2". Pills show only the letter.

Downgrade reasons
Name each reason that applies, comma separated: scope (wrong geography or segment), stale, disagree, no-method, vendor-bias, metric (spend vs revenue vs GMV), syndicated.

Independence
Copies of one press release are one group. Co-owned publishers are one group (e.g. Mordor Intelligence and Global Market Insights). Count groups, not pages.

Combining figures
- Normalise first: metric, scope, geography, year, currency. Never average spend with revenue, or a global figure with a national one.
- Five or more independent comparable figures: use the trimmed mean (drop the highest and lowest).
- Fewer than five: report min, median, max and the max/min ratio.

Confidence, from evidence x agreement. Use it for every headline figure and every lens.
- High: 2 or more independent groups agree within 1.5x, and the inputs that drive the figure are A or B with claim grade 1 or 2.
- Low: only one group, or the driving inputs are C or D, or the spread is over 3x.
- Medium: everything else.
- No usable evidence: write "Unknown: insufficient evidence", not Low.

Each headline figure states: range, base, data year, currency, confidence with a one-line basis, and "Would change if ...".

Source summary
At the end, name the one to three sources the headline rests on, their grades, and the biggest weakness of the source base.

Cite as: claim (Grade, publisher, date, URL). A conclusion resting only on C and D sources says so in the sentence that states it.$t$
    ),
    23
  ),
  (
    'market_sizing',
    (select id from public.tool_types where slug = 'skill'),
    'Market Sizing',
    'How to size TAM, SAM and SOM bottom-up first, build SOM, and show the working.',
    jsonb_build_object(
      'description', 'Load before estimating how big a market is: TAM, SAM, SOM, revenue potential.',
      'text', $t$Size the market from the buyer up, check it from the top down, and show every input. A market size nobody can check is a guess with a dollar sign. Every input is a ledger row (Evidence Ledger), and sizing.py does all the arithmetic.

0. Define the unit first
Write one line: "<who pays> pays <what> for <what>, per year, in <geography>." Default geography is Australia unless the idea says otherwise.
- Money in AUD, for an Australian financial year (FY2025-26 runs 1 July 2025 to 30 June 2026).
- Record each input's data year (the year it measures) separately from its publish date.
- Foreign currency: convert at the RBA average rate for the source's data year. The rate is a ledger input.
- AUD from an older year: roll it forward with ABS CPI. The CPI values are ledger inputs.

1. The layers
- TAM today: every buyer of this kind of product x units per buyer x realised price. Realised price is what buyers actually pay, not list price. Size the category, not just our version. No adoption term in TAM.
- Units must match the price unit: seat, site, firm or household. A per-seat price times a count of firms is wrong.
- Expansion TAM (optional): new spend a new category creates beyond what buyers spend today. Example: Damodaran sized Uber against the taxi market; Gurley argued cheaper, faster rides would grow usage and replace some car ownership. Write it as a separate line with its own thesis and evidence. Never add it into TAM today.
- SAM: the part of TAM this offer can serve today. One filter per line: segment, channels, geography, regulation. Each filter has a ledger id or says "assumption". Filters must not overlap: never cut the same buyers twice.
- SOM: our revenue in year 3, from the build in step 5. Never a percentage of SAM.

2. Order: bottom-up first
Build bottom-up before you search for any market-size report or headline total. A headline seen first anchors everything after it. Only then run top-down, as a ceiling and a check.

3. Bottom-up
- Businesses: ABS Counts of Australian Businesses (cat. 8165), employing businesses by ANZSIC division and employment size band. Never all businesses: about 65% are non-employing at June 2026.
- People and households: ABS population, household counts, Census QuickStats.
- Regulated groups: regulator registers where they fit (Ahpra practitioners, NDIS participants, ACMA reports, APRA and ASIC registers).
- Price: competitors' pricing pages, dated. Annualise monthly prices. Use the tier the target buyer would choose.
- Formula: buyers x units per buyer x realised price.

4. Top-down
Take a published total and narrow it with the SAM filters, one per line.
- Market-report publishers (report catalogues and press-release wires) disagree 2-3x on the same market. Use them as bounds only, never as the base.
- Collapse syndicated copies and co-owned publishers into one group.
- Exclude any figure more than 2x a primary anchor for the same scope.

5. Build SOM
Revenue in year 3, built over 36 months, net of churn.
- B2B: ramped sales reps x quota x attainment, or channel reach x conversion x annual contract value.
- B2C: reach x funnel conversion x annual revenue per user x retention.
- Telstra distribution enters as a channel-reach input with its own conversion assumption. Never assume it.
- B2B churn floor: the ABS business exit rate, about 14% a year in 2025-26.
- Benchmarks like rep ramp time vary across sources: range them, don't pick one.

Cross-check SOM three ways. Report each as pass or fail, with the numbers.
a. Category diffusion: under pooled Bass parameters (p 0.03, q 0.38), a new category reaches about 3.6% of eventual adopters in year 1, 8.5% in year 2 and 15% in year 3, across all vendors together. SOM must be a share of that, not of SAM. The parameters come mostly from consumer durables: an order-of-magnitude check, not a forecast.
b. Peer: a named peer's revenue or customer count at the same age.
c. Sum of shares: named competitors' revenue plus our SOM must fit inside SAM. If it doesn't, the market can't hold everyone's plans (Damodaran's big market delusion).

6. Triangulate
Compare the bottom-up and top-down base cases for SAM.
- Within 2x: they agree. Lead with bottom-up.
- More than 2x apart: one holds a bad assumption. Name the input that explains the gap and fix it. Never average the two.

7. Ranges by driver
- Each input gets its own sourced low and high. Assumptions get wide ranges.
- All arithmetic runs in sizing.py (Evidence Ledger). Never type a computed number yourself.
- Report the tornado's top two drivers from sizing.md: the inputs that swing the result most.
- All lows together and all highs together are outer bounds. Label them "outer bound".

8. Decision line
Say whether the SOM range clears, misses or straddles the bar the brief gives. No bar given: place it on the Strategyzer opportunity scale (under $100k, $10M+, $100M+ revenue a year) and say which bar would change the verdict.

9. Where to get Australian numbers
- ABS 8165 Counts of Australian Businesses: employing businesses by ANZSIC division and size band, plus entries and exits. XLSX: download it in the sandbox. web_fetch cannot read XLSX or PDF and truncates at 20,000 characters.
- ABS Data API: https://data.api.abs.gov.au/rest/ with format=csv. No key needed.
- ABS 8167 Characteristics of Australian Business: share of businesses using a technology (cloud, AI, cyber security).
- ATO taxation statistics on data.gov.au: businesses and income by industry and size.
- ACMA communications reports: telco, internet and device use.
- Ahpra registration data: practitioner counts by profession and state.
- NDIS quarterly data: participants and payments. Links change: search first.
- RBA exchange rate tables (CSV): historical AUD rates.
- ABS CPI: the index for rolling old AUD forward.
- Household Expenditure Survey: latest is 2015-16 and has no successor. Anything built on it is Low confidence.
- IBISWorld and Statista are paywalled. A snippet figure is grade C at best.
Don't hardcode volatile figures other than those dated above. Fetch current ones.

Output, in this order:
- The unit line.
- Layer table: Layer | Low | Base | High | Method, copied from sizing.md.
- Expansion TAM line, if any, with its thesis.
- Each formula written out with its numbers from sizing.md: "62,000 firms x 1 site x $1,080 = $67M".
- The tornado's top two drivers.
- The three SOM cross-checks, pass or fail.
- Whether top-down and bottom-up agree.
- The decision line.
- Inputs table: Ledger id | Input | Low | Base | High | Source (publisher, date, full URL) | Grade (e.g. "B2"). Assumptions show "assumption" instead of a ledger id.

Rules: no number without a ledger id or an "assumption" label. Prefer A and B sources. Never round a guess into false precision: $8M, not $8,035,200.$t$
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

Each lens gets three things: a score 1-5, an evidence level 0-5, and a confidence.

Desirability: do people want this?
Look at: who has the problem, how often, how badly; what they do today (workarounds, spend, products used); competitors' traction (customers, revenue, funding); review volume and complaints; search interest; surveys.
- 5: strong pull: competitors with large, growing paying bases, buyers already pay for workarounds, and target buyers have committed (letters of intent, deposits, pilots).
- 4: clear demand: several competitors with real traction, the same complaint recurs across many reviews, buyers already spend on the problem.
- 3: some demand: the problem is real but signals are thin, mixed, or come from a different segment.
- 2: weak demand: few buyers spend on it today, signals are mostly opinion or forum noise, or competitors have struggled to sell.
- 1: evidence against: buyers tried and dropped similar products, competitors closed for lack of demand, or the problem is rare or minor.

Viability: does it make money for Telstra?
Look at: what buyers already pay for comparable products (pricing pages); SAM and SOM from Market Sizing; revenue model; unit economics (price, cost to serve, acquisition cost).
Adaptability, a named sub-check: competitor moves, regulation, technology shifts and macro forces that could close the window. Write one line on it.
- 5: buyers already pay prices that give unit economics at or above the benchmarks for this model, SOM clears the bar, and no adaptability risk threatens the window.
- 4: comparable prices show willingness to pay, modelled unit economics meet benchmarks for this model, SOM is near or above the bar.
- 3: money is possible but unproven: price or cost uncertain, SOM straddles the bar, or one adaptability risk could close the window.
- 2: economics look weak: likely price below cost to serve, SOM well below the bar, or a strong competitor or regulatory shift is under way.
- 1: evidence it can't make money: the price ceiling sits below cost to serve, the market is too small, or regulation blocks the model.

Viability benchmarks by business model. Label them as benchmarks, with the source:
- LTV:CAC above 3 and CAC payback under 12 months (Skok, forEntrepreneurs).
- 2025 median CAC payback about 20 months; median software gross margin 80% (Aleph x Benchmarkit).
- Early AI-native companies run about 25-60% gross margin (Bessemer via SaaStr).
- Pre-revenue ratios are always modelled: label them "assumption".
- Don't fail a marketplace or hardware idea on SaaS margins. Use benchmarks for its own model, or say none were found.

Feasibility: can Telstra build and deliver it?
Look at the five TELOS checks:
- Technology: the core technology, named, with its TRL 1-9 (1 idea, 4 lab prototype, 6 demonstrated in a relevant setting, 7 pilot in real use, 9 proven in market).
- Cost to build and run: rough range to an MVP a real customer could use, and to run it.
- Law and privacy: ACMA rules, the Privacy Act, sector rules (health, finance, critical infrastructure).
- Operations: Telstra assets, platforms, partners, data and teams it relies on.
- Schedule: dependencies, approvals and time to MVP.
Score the lens, or each TELOS check on its own, with these anchors:
- 5: ready: technology at TRL 8-9 in comparable products; Telstra already has the assets; no legal hurdle; cost and time fit a normal pilot.
- 4: mostly ready: TRL 7, a known build path; minor dependencies or approvals with a known process.
- 3: doable with work: TRL 5-6, or one key partner, approval, dataset or skill not yet secured, or cost and time at the edge of a pilot budget.
- 2: hard: TRL 3-4, major unknowns, a significant legal or privacy hurdle, or cost and time well beyond a pilot budget.
- 1: blocked: TRL 1-2, the law prohibits it, or a required asset or dataset doesn't exist.
Overall Feasibility is the weakest TELOS check.

Evidence level 0-5: what kind of evidence, say versus do
- 0: none, or opinion.
- 1: articles and reports about the market.
- 2: what people say: surveys, interviews, forum complaints, published survey results.
- 3: what people already do: competitor traction, review volume, search volume, prices buyers pay, fake door tests, waitlists.
- 4: commitments: letters of intent, deposits, paid pilots.
- 5: repeat paid use at the real price.
Desk research reaches 3 at most. More sources raise agreement, not the level.

Confidence
Use Source Grading's rule (evidence x agreement). Then cap it: Desirability and Viability cannot be High below evidence level 4. Feasibility can be High from public evidence: specs, regulation text, working comparables.
A score of 4 or 5 with Low confidence says so in the sentence that states it.

Telstra strategic fit gate: Pass, Fail or Unclear, with the reason.
Pass when it uses Telstra's network, retail or business channels, customer base, brand or enterprise relationships, and fits where Telstra is heading. Fail when it uses none of them or works against Telstra's direction. Unclear when you can't tell from the evidence.

Bias guard
- Score from research.md's evidence, not the founder's pitch.
- Before scoring, write the bear case: "Which lens most likely kills this, and why?" One paragraph.
- If the scores ignore something the bear case names, lower that lens's confidence.
- LLMs lean optimistic. When in doubt, score lower.

Verdict. Apply in order; the first rule that matches decides.
1. Gate Fail: Park.
2. A lens at 1 with Medium or High confidence, or two lenses at 2 with Medium or High confidence: Park.
3. One lens at 2 with Medium or High confidence: Rethink. Say what would have to change.
4. A lens at 1 or 2 with Low confidence means unknown, not bad: Pilot to test.
5. Pursue only when every lens is 4 or more, no confidence is Low, the gate is Pass, and Desirability evidence level is 4 or more.
6. Everything else: Pilot to test. Name the experiment.
"Unknown: insufficient evidence" counts as Low in these rules.
A desk-only pass never says Pursue.

Likelihood words
When you say how likely something is, use only these terms, with the number in brackets: remote (1-5%), very unlikely (5-20%), unlikely (20-45%), roughly even chance (45-55%), likely (55-80%), very likely (80-95%), almost certain (95-99%). Never put a confidence level and a likelihood term in the same sentence.

Riskiest assumptions
List 5 to 8. Each is written "We believe that ...", tagged D, V or F, with importance 1-5 (how badly the idea fails if it is false) and its evidence level now, 0-5. High importance with low evidence is where to test first.
The top three each get a Test Card:
- Test: what to do.
- Metric: what to measure.
- Pass threshold: set before the test runs.
- Rough cost and time.
- The evidence level a pass would reach.
Prefer B2B letters of intent and paid pilots: Telstra's channels make them cheap. Thresholds are internal defaults, say so. Example rule of thumb from practitioners: landing page CTA click-through above 10% is strong, under 3% is weak.

Output, in this order:
- Scorecard table: Lens | Score /5 | Evidence level | Confidence | One-line reason with ledger ids.
- Gate line: Pass, Fail or Unclear, and why.
- Bear case paragraph.
- Verdict and the reason in two sentences.
- Assumptions table: # | We believe that ... | Lens | Importance | Evidence level | Test Card (top three only).$t$
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
- Use the template below as it is. Keep the style block, the header, the Spindle script and the footer unchanged apart from their placeholders. Fill every {{placeholder}}, repeat blocks as needed, and delete blocks you have nothing for. Never add colours, fonts, libraries, images, or external scripts and styles.
- Never show a number that is not in sizing.md or ledger.csv. Copy it as printed there.
- Grade pills show the source letter only (A to D). Tables show the combined grade, e.g. "B2", and the ledger id, e.g. "L7".
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
2. Tiles: "Do people want it?", "Will it make money?", "Can we build it?" as score/5. Each sub-line gives confidence and evidence level in plain words: evidence level 0 "no evidence yet", 1 to 3 "desk research only", 4 "customer commitments", 5 "repeat paying customers". Example: "Medium confidence · desk research only". Then "Right fit for Telstra?" with Pass, Fail or Unclear (good, bad or mid) and the reason in a few words as its sub-line. Then "Market we could serve" with the SAM base and range.
3. DVF bars (pattern A), titled in plain words, with the lens names under each bar.
4. Market size: nested circles (pattern B) beside the bottom-up formula chips, plus one line on whether top-down and bottom-up agree. Then the biggest swing line, the three reality-check chips, and the Expansion TAM line if research.md has one (all under pattern B). Inputs table (Ledger | Input | Low | Base | High | Grade | Source) and method notes in <details>.
5. Key findings: 3 to 5 cards, each with a takeaway title, one visual and a citation.
6. Competitors: positioning map (pattern D) on the two axes that matter most in this market, with the competitor table in <details>.
7. Riskiest assumptions: assumptions map (pattern C), then the top three with their Test Cards.
8. What we still don't know.
9. Sources: every source, linked and graded, best grade first, with the ledger ids it supports.

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
    <div class="tile"><div class="l">{{Label}}</div><div class="v {{good|mid|bad}}">{{4/5}}</div><div class="s">{{Medium confidence · desk research only}}</div></div>
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
      <table><tr><th>Ledger</th><th>{{Column}}</th><th>Grade</th><th>Source</th></tr>
        <tr><td>{{L7}}</td><td>{{Value}}</td><td>{{C3}}</td><td><a class="cite" href="{{https://exact/page}}">{{Publisher, Mon YYYY}}</a> <span class="grade g-{{C}}">{{C}}</span></td></tr></table>
    </details>
  </section>

  <section>
    <h2>What we still don't know</h2>
    <ul class="unknown"><li>{{Open question, and what evidence would settle it}}</li></ul>
  </section>

  <section id="sources">
    <h2>Sources</h2>
    <ol><li><a href="{{https://exact/page}}">{{Title, Publisher, D Mon YYYY}}</a> <span class="grade g-{{A}}">{{A}}</span> {{L1, L4}}</li></ol>
  </section>

  <footer>Spindle · Telstra Muru-D · Prepared by the {{agent name}} agent on {{D Mon YYYY}} · Full findings: <a href="research.md" target="_self">research.md</a> · Sources graded A to D · Quotes verified on page: {{X}} of {{Y}}.</footer>
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
    <text x="0" y="24" font-weight="700">Do people want it? 4/5 <tspan font-weight="400" fill="#5A6275">Desirability</tspan></text><text x="730" y="24" text-anchor="end" fill="#5A6275">Medium confidence</text>
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
<div class="chips"><div class="chip"><b>62,000</b>firms</div>×<div class="chip"><b>1</b>site each</div>×<div class="chip"><b>$1,080</b>a year</div>=<div class="chip total"><b>$67M</b>TAM base</div></div>
Biggest swing, one line from the tornado's top two drivers:
<p class="sub">What moves the answer most: {{firms that need it}} ({{SOM $2M to $9M}}), then {{price}} ({{$4M to $6M}}).</p>
Reality checks on the year-3 estimate, one chip each, Pass in good, Fail in bad:
<div class="chips"><div class="chip"><b class="good">Pass</b>{{Fits how fast new products usually spread}}</div><div class="chip"><b class="bad">Fail</b>{{Above the nearest peer at the same age}}</div><div class="chip"><b class="good">Pass</b>{{Rivals plus us fit in the market}}</div></div>
Expansion TAM, only if research.md has one. A separate dashed line, never added into the circles:
<div class="chip" style="border-style:dashed;margin-top:10px">{{If cheaper access grows usage}}: {{$X to $Y}} more a year (Expansion TAM, not counted above)</div>

C. Assumptions map. Evidence level 0 to 5 left to right: x = 80 + evidence x 80. Importance 1 to 5 bottom to top: y = 330 - (importance - 1) x 70. The red zone (evidence level 2 or less, importance 3 or more) is "test first"; its label sits above the zone so no dot can cover it. Each dot is lettered by lens with its number.
<svg viewBox="0 0 520 390" width="100%" style="max-width:560px" role="img" aria-label="Assumptions map">
  <text x="60" y="26" font-size="12" fill="#D0021B" font-weight="700">Test first: matters most, least known</text>
  <rect x="60" y="34" width="220" height="171" fill="#FCE6E8"/>
  <line x1="60" y1="350" x2="500" y2="350" stroke="#C9CEDA"/><line x1="60" y1="34" x2="60" y2="350" stroke="#C9CEDA"/>
  <text x="280" y="380" text-anchor="middle" font-size="12" fill="#5A6275">Evidence we have, level 0 to 5 →</text>
  <text x="24" y="190" text-anchor="middle" font-size="12" fill="#5A6275" transform="rotate(-90 24 190)">Importance →</text>
  <circle cx="80" cy="50" r="13" fill="#0D54FF"/><text x="80" y="55" text-anchor="middle" font-size="11" fill="#fff" font-weight="700">D1</text>
  <circle cx="160" cy="120" r="13" fill="#0A8A4A"/><text x="160" y="125" text-anchor="middle" font-size="11" fill="#fff" font-weight="700">V2</text>
  <circle cx="400" cy="190" r="13" fill="#B7791F"/><text x="400" y="195" text-anchor="middle" font-size="11" fill="#fff" font-weight="700">F3</text>
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
2. read_file it back and check: no {{ left; every a.cite href starts with https:// and is a real page you used; every number appears in sizing.md or ledger.csv; every section heading is a sentence; no colours outside the palette.
3. next_free_port, then run_command in the background: python3 -m http.server <port> --bind 0.0.0.0 --directory <your own directory>.
4. publish_preview with title "Research report", that port, and path "/report.html".
5. In your reply, give the preview link and the verdict.$t$
    ),
    82
  ),
  (
    'evidence_ledger',
    (select id from public.tool_types where slug = 'skill'),
    'Evidence Ledger',
    'The per-number ledger, the sizing script and the quote check for market research.',
    jsonb_build_object(
      'description', 'Load before recording any number: the ledger, the sizing script, and the quote check.',
      'text', $t$Every number gets a receipt. You record it, code computes from it, and a script checks it is really on the page.

1. The ledger
Every number you will use goes into ledger.csv in your own directory (write_file). One row per figure. Columns, exactly in this order:
id,value,unit,currency,metric,geography,data_year,scope,quote,url,publisher,published,source_grade,claim_grade,downgrades,group,archive_url,verified
- id: L1, L2, L3 ...
- value: a plain number. 996203, not "996,203", "~1M" or "$1M".
- unit: firms, seats, AUD per month, %, and so on.
- currency: AUD, USD, or blank for counts.
- metric: count, price, revenue, spend, GMV, rate.
- data_year: the year the figure measures, e.g. FY2025-26 or 2024. Not the publish date.
- scope: the segment it covers, e.g. "employing businesses, ANZSIC M".
- quote: the exact sentence from the fetched page that contains the number, copied character for character.
- url: the exact page you fetched. published: its publish date, YYYY-MM-DD.
- source_grade A-D, claim_grade 1-6, downgrades: from Source Grading.
- group: the independence group. Copies and co-owned publishers share one group name.
- archive_url and verified: leave empty when you add the row.
Valid CSV: wrap any field that contains a comma or a double quote in double quotes, and double any double quote inside it.
No quote, no row. No row, the number doesn't go in the report.
Assumptions are not ledger rows. They live in sizing.py with ledger None.

2. Files you can't web_fetch
XLSX, PDF and CSV sources: download them in the sandbox with run_command (curl -L -o file URL) and read them with python. pip install openpyxl or pypdf if needed. web_fetch can't read them and truncates at 20,000 characters. For a row from a spreadsheet, quote the cell's row label and value as they appear.

3. Computation
Copy sizing.py below into your own directory. Fill INPUTS with ledger ids and assumptions, and fill model(). Run: python3 sizing.py > sizing.md
Every TAM, SAM, SOM, range, conversion and percentage in research.md and report.html comes from sizing.md. Never type a computed number. To change a number, change the ledger or sizing.py and run it again.

4. Verification
After research and before you write research.md: copy verify.py below into your own directory and run python3 verify.py. It writes verify.csv.
- found and found_loose: done. found_loose means it matched once punctuation and spacing were ignored.
- no_quote: add the quote, or drop the row.
- not_found: re-read the page with web_fetch. Fix the quote, or drop the row and everything built on it.
- fetch_failed: check the page with web_fetch yourself. Set verified to "checked_manual" only if you see the sentence.
Re-run until clean, then re-run sizing.py if any row changed.
State the result in research.md, e.g. "Quotes verified on page: 31 of 33; 2 checked by hand".

5. Citing
Cite ledger ids in research.md tables, e.g. "L7".

verify.py
"""Check each ledger quote appears on its source page. Usage: python3 verify.py [ledger.csv]"""
import csv, html, io, json, re, sys, zipfile
import urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
WAYBACK = "https://archive.org/wayback/available?url="
CAP = 10 * 1024 * 1024


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20) as r:
        return r.read(CAP), r.headers.get("Content-Type", "").lower()


def xlsx_text(data):
    out, z = [], zipfile.ZipFile(io.BytesIO(data))
    for n in z.namelist():
        if n == "xl/sharedStrings.xml" or n.startswith("xl/worksheets/sheet"):
            for el in ET.fromstring(z.read(n)).iter():
                tag = el.tag.rsplit("}", 1)[-1]
                if tag in ("t", "v") and el.text:
                    out.append(el.text)
                if tag == "c" and el.get("t") == "s":  # shared-string cell: v is an index, skip
                    for v in el:
                        v.text = None
    return " ".join(out)


def extract(url, data, ctype):
    """Return (text, None) or (None, (status, detail))."""
    path = urllib.parse.urlparse(url).path.lower()
    if "pdf" in ctype or path.endswith(".pdf"):
        try:
            import pypdf
        except ImportError:
            return None, ("binary_unchecked", "pip install pypdf")
        return " ".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(data)).pages), None
    if "spreadsheetml" in ctype or path.endswith(".xlsx"):
        return xlsx_text(data), None
    text = data.decode("utf-8", "replace")
    if "html" in ctype or path.endswith((".htm", ".html")):
        text = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1\s*>", " ", text)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return text, None


def norm(s):
    s = s.casefold().translate({0xA0: " ", 0x2009: " ", 0x202F: " ", 0x2018: "'", 0x2019: "'",
                                0x201C: '"', 0x201D: '"', 0x2013: "-", 0x2014: "-"})
    return re.sub(r"\s+", " ", s).strip()


def load(url):
    """-> (normalised text, None) or (None, (status, detail))."""
    try:
        text, err = extract(url, *get(url))
    except urllib.error.HTTPError as e:
        return None, ("fetch_failed", str(e.code))
    except Exception as e:
        return None, ("fetch_failed", type(e).__name__)
    return (norm(text), None) if err is None else (None, err)


def wayback(url):
    try:
        return json.loads(get(WAYBACK + urllib.parse.quote(url, safe=""))[0])["archived_snapshots"]["closest"]["url"]
    except Exception:
        return "none"


def check(quote, page):
    q = norm(quote)
    if not q:
        return "no_quote", ""
    detail = "" if re.search(r"\d", q) else "quote has no digits"
    if q in page:
        return "found", detail
    alnum = lambda s: re.sub(r"[\W_]+", "", s)
    return ("found_loose" if alnum(q) in alnum(page) else "not_found"), detail


def main(path="ledger.csv"):
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        cols, rows = rd.fieldnames, list(rd)
    urls = sorted({r["url"] for r in rows if r["url"]})
    with ThreadPoolExecutor(8) as ex:
        pages = dict(zip(urls, ex.map(load, urls)))
        snaps = dict(zip(urls, ex.map(wayback, urls)))
    report = []
    for r in rows:
        page, err = pages.get(r["url"], (None, ("fetch_failed", "no url")))
        status, detail = check(r["quote"], page) if err is None else err
        r["verified"] = status
        r["archive_url"] = r["archive_url"] or snaps.get(r["url"], "none")
        report.append({"id": r["id"], "url": r["url"], "status": status, "detail": detail})
    for fn, fields, data in ((path, cols, rows), ("verify.csv", ["id", "url", "status", "detail"], report)):
        with open(fn, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fields)
            w.writeheader()
            w.writerows(data)
    bad = [x for x in report if not x["status"].startswith("found")]
    n = lambda s: sum(x["status"] == s for x in report)
    print(f"verified {len(report) - len(bad)} of {len(report)} quotes ({n('not_found')} not_found, {n('fetch_failed')} fetch_failed)")
    for x in bad + [x for x in report if x["detail"] == "quote has no digits"]:
        print(f"  {x['id']}: {x['status']} {x['detail']}".rstrip())


if __name__ == "__main__":
    main(*sys.argv[1:2])

sizing.py
"""Market sizing skeleton. Edit INPUTS and model(), then: python3 sizing.py > sizing.md"""
import csv, itertools, math

# max caps a widened rate (shares, conversion, churn) at 1.
# ponytail: assumption ranges get a fixed widening (0.5x..1.5x), calibrate against an eval set later
INPUTS = {
    "firms":     dict(ledger="L1", low=None, base=None, high=None, note="target firms"),
    "seats":     dict(ledger=None, low=20, base=50, high=80, note="seats per firm"),
    "price":     dict(ledger="L2", low=None, base=None, high=None, note="AUD per seat per year, realised"),
    "sam_share": dict(ledger=None, low=0.2, base=0.3, high=0.4, max=1, note="share matching our segment"),
    "reach":     dict(ledger=None, low=0.01, base=0.02, high=0.03, max=1, note="share of SAM firms reached per year"),
    "conv":      dict(ledger=None, low=0.1, base=0.2, high=0.3, max=1, note="reached to customer"),
    "acv":       dict(ledger=None, low=20000, base=30000, high=40000, note="AUD annual contract value"),
    "churn":     dict(ledger=None, low=0.05, base=0.1, high=0.15, max=1, note="annual churn"),
}
COMPETITOR_REVENUE = []  # optional: annual revenue of named competitors inside the SAM


def model(x):
    tam = x["firms"] * x["seats"] * x["price"]
    sam = tam * x["sam_share"]
    new = x["firms"] * x["sam_share"] * x["reach"] * x["conv"]  # new customers per year
    cust = 0
    for _ in range(3):
        cust = cust * (1 - x["churn"]) + new
    return {"TAM": tam, "SAM": sam, "SOM": cust * x["acv"]}


def bass_cumulative(t, p=0.03, q=0.38):
    e = math.exp(-(p + q) * t)
    return (1 - e) / (1 + (q / p) * e)


def annualise(monthly):
    return monthly * 12


def fmt(n, usd=False):
    suf = ""
    for div, s in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= div:
            n, suf = n / div, s
            break
    return f"{'$' if usd else ''}{float(f'{n:.2g}'):g}{suf}"


def prepare():
    with open("ledger.csv", newline="", encoding="utf-8") as f:
        vals = {r["id"]: float(r["value"]) for r in csv.DictReader(f)}
    for v in INPUTS.values():
        if v["ledger"]:
            v["base"] = vals[v["ledger"]] if v["base"] is None else v["base"]
            v["low"] = v["base"] if v["low"] is None else v["low"]
            v["high"] = v["base"] if v["high"] is None else v["high"]
            v["tag"] = v["ledger"]
        else:
            lo, hi = v["base"] * 0.5, v["base"] * 1.5
            v["tag"] = "assumption, widened"
            v["low"], v["high"] = min(v["low"], lo), min(max(v["high"], hi), v.get("max", math.inf))


def table(head, body):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in body]


def main():
    prepare()
    names = list(INPUTS)
    base = {k: INPUTS[k]["base"] for k in names}
    ends = lambda k: (INPUTS[k]["low"], INPUTS[k]["high"])
    b = model(base)
    if len(names) <= 12:
        runs = [model(dict(zip(names, c))) for c in itertools.product(*map(ends, names))]
        note = f"Outer range: all 2^{len(names)} low/high combinations."
    else:
        runs = [model({**base, k: e}) for k in names for e in ends(k)]
        note = "More than 12 inputs: outer range is one-at-a-time extremes only."
    print("## Layers\n")
    print("\n".join(table(["Layer", "Outer low", "Base", "Outer high"],
          [[L, fmt(min(r[L] for r in runs), True), fmt(b[L], True), fmt(max(r[L] for r in runs), True)] for L in b])))
    print(f"\n{note}\n\n## Tornado (top 2 inputs per layer)\n")
    sw = {k: [model({**base, k: e}) for e in ends(k)] for k in names}
    for L in b:
        top = sorted(names, key=lambda k: abs(sw[k][1][L] - sw[k][0][L]), reverse=True)[:2]
        print(f"- {L}: " + "; ".join(f"{k} {fmt(sw[k][0][L], True)} / {fmt(sw[k][1][L], True)}" for k in top))
    print("\n## Inputs\n")
    print("\n".join(table(["Input", "Low", "Base", "High", "Ledger id or assumption"],
          [[k, fmt(v["low"]), fmt(v["base"]), fmt(v["high"]), v["tag"]] for k, v in INPUTS.items()])))
    print("\n## Cross-checks\n")
    ceil = bass_cumulative(3) * b["SAM"]
    print(f"- Bass year-3 ceiling {fmt(ceil, True)} vs SOM {fmt(b['SOM'], True)}: " + ("FLAG SOM exceeds ceiling" if b["SOM"] > ceil else "ok"))
    if COMPETITOR_REVENUE:
        tot = sum(COMPETITOR_REVENUE) + b["SOM"]
        print(f"- Competitors + SOM {fmt(tot, True)} vs SAM {fmt(b['SAM'], True)}: " + ("FLAG over SAM" if tot > b["SAM"] else "ok"))


if __name__ == "__main__":
    main()$t$
    ),
    83
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

Load Research Method, Evidence Ledger, Market Sizing, DVF Assessment and Source Grading before you search. The scoping agent's context gives you the scope and its Feasibility assessment.

Deliver these files in your own directory:
1. ledger.csv: every number you use, with its exact quote, URL and grades.
2. sizing.py and sizing.md: all sizing arithmetic, computed from the ledger.
3. verify.csv: the quote check from verify.py.
4. research.md, the full findings: the market size (TAM, SAM, SOM, Expansion TAM if any, both methods, ranges, the tornado's top two drivers, the three SOM cross-checks, inputs table with ledger ids), Desirability and Viability with evidence, competitors and their prices, the DVF scorecard with evidence levels using the scoping agent's Feasibility, the Telstra fit gate, the bear case, the verdict, the riskiest assumptions with Test Cards, what we still do not know, the verification line, the source summary, and every source with its grade and full URL.
5. report.html: then load Visual Report and build the research report from research.md, and publish it with publish_preview.

Your reply: the verdict; the three DVF scores with confidence; the gate; SAM and SOM base values with ranges; quotes verified X of Y; the report link; the three riskiest assumptions. Short.

Prefer concrete, checkable claims over adjectives. Never invent a number, a source or a URL. When something needs primary research to confirm, say so plainly.$prompt$
where slug = 'market_research';

-- project_scoping's prompt and defaults live in scope_report.sql.

-- ---------------------------------------------------------------------------
-- Defaults. These overwrite parity.sql's lists, so keep them whole.
-- ---------------------------------------------------------------------------
update public.agent_types set default_presets = array[
  'brave_search', 'web_fetch',
  'research_method', 'evidence_ledger', 'market_sizing', 'dvf_assessment', 'source_grading',
  'dataviz', 'visual_report', 'plain_writing', 'workspace_memory'
] where slug = 'market_research';

-- ---------------------------------------------------------------------------
-- Backfill the new skills onto existing scoping and research agents. Scoping
-- uses slots 0 and 1 (scope_report.sql takes slot 2); research uses 0 to 3. Same CTE
-- shape and caveats as design_skills.sql: scoped to these pairs only, skipped
-- when the agent already has a tool of that name, lands 'ready'.
-- ---------------------------------------------------------------------------
with pairs(agent_slug, preset_slug) as (
  values
    ('project_scoping', 'dvf_assessment'),
    ('project_scoping', 'source_grading'),
    ('market_research', 'market_sizing'),
    ('market_research', 'dvf_assessment'),
    ('market_research', 'visual_report'),
    ('market_research', 'evidence_ledger')
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

-- Nodes keep their own copy of a skill's text. A re-apply pushes edits to
-- existing copies of these skills.
-- ponytail: overwrites a user's hand edits to these skills, Source Grading
-- included on every agent; scope by an edited flag if users customise them.
update public.nodes n
set config = p.config
from public.tool_presets p
where n.kind = 'tool'
  and n.tool_type_id = p.tool_type_id
  and n.name = p.name
  and p.slug in ('market_sizing', 'dvf_assessment', 'visual_report',
                 'source_grading', 'evidence_ledger')
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
