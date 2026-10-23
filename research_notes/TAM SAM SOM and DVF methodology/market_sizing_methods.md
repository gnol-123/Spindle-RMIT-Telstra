# Professional market sizing (TAM/SAM/SOM) for early-stage startup ideas

Scope: how VCs, accelerators and strategists size markets, and where the muru-D agent's current method (unit line, top-down with filters, bottom-up buyers x adoption x price, 2x triangulation, low/base/high, SOM from competitor share or channel reach) falls short. Researched 2026-10-23. Note on source quality: primary VC-firm guidance (Sequoia, a16z, YC, Bessemer) and consulting texts (Bain, McKinsey, HBR, Kotler) did not surface in search; most method detail below comes from Gurley, Damodaran/Cornell, ABS, Bass/Rogers literature and one strong practitioner guide (Stratrix). Practitioner blogs are flagged as such.

## 1. Definitions of TAM, SAM, SOM and where they disagree

### Takeaway
Working definitions converge: TAM = annual revenue if every potential customer bought at a realistic price; SAM = the part your product, channels and geography can serve today; SOM = the part of SAM you can win within a stated period. The real disagreements are (a) whether TAM is today's spend or a future expanded market, (b) whether SAM means "can serve" or "choose to target", and (c) that SOM has no standard time horizon.

### Cited Findings
- TAM: "annual revenue available if every potential customer bought at a realistic price"; SAM: "the part of TAM that your product, channels and geography can serve today"; SOM: "the part of SAM you can realistically win within a stated period" ([Stratrix, The Strategist's Craft, c. 2025-26](https://www.stratrix.com/craft/tam-sam-som)).
- Common secondary definitions: TAM = total demand if every potential customer bought; SAM = portion of TAM a company "can realistically target and serve based on its business model, capabilities, and geographic reach" ([Startup Savant](https://startupsavant.com/startup-marketing/understanding-tam-sam-and-som); [pitchdrive glossary](https://www.pitchdrive.com/glossary/tam-vs-sam)). Note this blends "can serve" and "target".
- Steve Blank's framework (secondhand): treats TAM as 100% of the market and says sizing SAM is "more an art than a science"; his Startup Owner's Manual defines four market types (excerpt truncated before listing them) ([UX Planet summary](https://uxplanet.org/ux-design-for-startups-understanding-and-calculating-the-market-a0976cee607b)).
- "Your TAM is NOT the size of the problem" (Steve Barsh, DreamIt angel) ([Slidebean](https://ar.slidebean.com/blog/what-is-tam)).
- TAM as today's spend vs future market: Damodaran (June 2014) sized Uber's TAM as the global taxi and limo market, about $100B, growing to about $183B by 2024 ([Jimmy's Journal summary](https://jimmysjournal.substack.com/p/how-to-define-the-total-addressable?r=3463sv); [Stratrix](https://www.stratrix.com/craft/tam-sam-som)). Gurley (July 2014) argued "The past can be a poor guide for the future if the future offering is materially different than the past" and sized an expanded market ([Gurley, Above the Crowd, 2014-07-11](https://abovethecrowd.com/2014/07/11/how-to-miss-by-a-mile-an-alternative-look-at-ubers-potential-market-size/)).
- Stratrix's resolution: keep today's TAM honest and put "market-expansion theses on a separate line with their own test"; adding adjacent markets to today's TAM is an error ([Stratrix](https://www.stratrix.com/craft/tam-sam-som)).
- SOM horizon: Stratrix's worked example uses SOM "after three years" ([Stratrix](https://www.stratrix.com/craft/tam-sam-som)); no source found giving a universal standard.

### Inferences
- The agent should define SAM strictly as "servable today with current product, channel, geography and pricing" and keep "segments we choose to target first" (beachhead) as a separate, explicit filter. Mixing the two is the main definitional ambiguity in secondary sources.
- The agent should always state SOM with a horizon (default: year 3 revenue, matching the Stratrix example and typical seed/Series A planning windows) and as revenue, not as a percentage.
- Two TAM lines are better than one: "TAM today (current spend replaced)" and "Expansion TAM (if thesis X holds)", each with its own evidence.

### Gaps
- Primary definitions from Sequoia, a16z, YC, Bain, McKinsey, HBR and Damodaran's own TAM glossary were not retrieved; the claim that they disagree on SAM wording could not be verified directly.

## 2. Methods: top-down, bottom-up, value-based, analogue, new-market sizing; when to use which

### Takeaway
Pros make bottom-up (customer count x units x realized price) the primary estimate and use top-down only as a ceiling/sanity check. For categories that do not yet exist, anchoring on the incumbent spend pool understates the market (Gurley on Uber); the fix is to size substitution pools and price-elasticity-driven expansion, then test them against observed user behaviour.

### Cited Findings
- Recommended stack: "Build bottom-up (customers x units x price) as the main estimate; use top-down as a ceiling and sanity check"; count customers from official statistical sources; "price per unit at realized prices, matching the unit to the count (seat, site or firm)"; "apply SAM filters one at a time, each with a stated reason, keeping them MECE" ([Stratrix](https://www.stratrix.com/craft/tam-sam-som)).
- Worked bottom-up example (fictional field-service software at $1,200 per technician per year): US BLS SOC 49-9021 about 440,900 technicians in 2025, 68% at plumbing/HVAC contractors; TAM about $359.8M; SAM filtered on Census CBP 2022 establishments of 10-99 employees (12,938 + 8,184 + 2,495 = 23,617 establishments), SAM about $181M; SOM about $5.2M ARR after three years (about 2.9% of serviceable accounts) ([Stratrix](https://www.stratrix.com/craft/tam-sam-som)).
- Unit discipline: "CBP counts establishments, not firms. Adjust for multi-unit firms or state the bias"; "Price per user means counting users, not headcount" ([Stratrix](https://www.stratrix.com/craft/tam-sam-som)).
- Simple bottom-up formula as pitched: "180,000 mid-market companies in the US with 200-2,000 employees. Our ACV is $24,000. TAM = 180,000 x $24,000 = $4.3B" ([Pitch Deck Guide](https://pitchdeckguide.com/tam-sam-som-pitch-deck/), practitioner blog).
- Top-down is quicker but less reliable, especially for new markets; it narrows a published total by geography, customer size, product fit ([Waveup](https://waveup.com/blog/top-down-and-bottom-up-market-size-calculation), practitioner blog). Stanford Biodesign advises running both directions because results "can vary widely" ([Stanford Biodesign example PDF](https://biodesignguide.stanford.edu/wp-content/uploads/2022/07/Top-Down-and-Bottom-Up-Market-Sizing-Example.pdf)).
- New-market sizing, Uber case. Damodaran: $100B TAM, 10% max share, $5.9B value. Gurley's expansion drivers: shorter predictable pickups, coverage, cashless payment, two-way ratings; price cuts from higher driver utilisation with high price elasticity ("lowering the price of car-for-hire transportation will increase the usage"); new use cases (suburbs, rental-car replacement, drink-driving avoidance, ferrying kids/parents, transit supplement); car-ownership substitution estimated as 1B cars x $6,000/yr (AAA $9,000 cut 33%) = about $6T globally, US about 25% ([Gurley 2014](https://abovethecrowd.com/2014/07/11/how-to-miss-by-a-mile-an-alternative-look-at-ubers-potential-market-size/)).
- Gurley's method for the range: expanded car-for-hire market at 3-6x historical, plus 2.5-12.5% of ownership costs, giving about $450B to $1.3T; implied share for a 25x outcome about 56% (bear) or 20% ("more likely") ([Gurley 2014](https://abovethecrowd.com/2014/07/11/how-to-miss-by-a-mile-an-alternative-look-at-ubers-potential-market-size/)).
- Gurley's evidence base: 2009 research put SF taxi/limo spend near $120M; Kalanick said Uber SF revenue was a "healthy multiple" of that; SF car-ownership market near $22B; SF black cars about 600 at Uber launch; fleet growth 20% month-on-month in late 2012. Validation method: ask users how their spend changed vs taxi spend two years earlier ([Gurley 2014](https://abovethecrowd.com/2014/07/11/how-to-miss-by-a-mile-an-alternative-look-at-ubers-potential-market-size/)).
- Gurley's cautionary analogue: a 1980 cellular forecast of 900,000 subscribers was "less than 1%" of the actual figure ([Gurley 2014](https://abovethecrowd.com/2014/07/11/how-to-miss-by-a-mile-an-alternative-look-at-ubers-potential-market-size/)).
- Hindsight: Uber Q4 2024 Mobility gross bookings $22,798M (SEC 8-K, 2025-02-05), roughly a quarter of Damodaran's annual TAM in one quarter, though gross bookings are not the same measure as taxi revenue ([Stratrix](https://www.stratrix.com/craft/tam-sam-som)). Commentators generally side with Gurley that Damodaran anchored on "how the world used to work" ([Playing for Doubles](https://playingfordoubles.beehiiv.com/p/uber-tam-a-case-study-whats-really)).
- Gurley's own caveats: precision is not accuracy, small assumptions swing outputs, and he disclosed his bias as Uber board member/investor ([Gurley 2014](https://abovethecrowd.com/2014/07/11/how-to-miss-by-a-mile-an-alternative-look-at-ubers-potential-market-size/)).
- "Larval market" (attributed to Paul Graham): small but growable market; YC reportedly accepts small starting markets with a clear path to scale ([Gurubase, unofficial](https://gurubase.io/g/ycombinator/y-combinator-evaluate-market-size-potential-startups-funding)); unverified against PG's original wording.
- "TAM onion": start from a spearhead market and expand outward ([Sutton, VC 101](https://sutton.substack.com/p/venture-capital-101-market-sizing)).

### Inferences
- Decision rule for the agent: existing category with countable buyers and observable prices -> bottom-up primary, top-down ceiling. Re-segmented market -> bottom-up on the sub-segment, top-down only on the parent category. New category -> substitution-pool sizing (what spend/time/workaround it replaces), plus an explicit price-elasticity or new-use-case expansion line, each flagged as thesis.
- Value-based sizing (price ceiling = share of value created for the buyer, e.g. hours saved x loaded wage) fits as a price check inside bottom-up: realized price should sit below the value created. Gurley's AAA cost-of-ownership calculation is a demand-side version of this.
- Demand-side vs supply-side: Gurley's argument is demand-side (buyer behaviour and spend pools); Damodaran's original was effectively supply-side (incumbent industry revenue). The agent's "published total narrowed by filters" is supply-side and will under-size disruptive ideas and over-size niche ones.

### Gaps
- No primary source found defining "value theory" as a named third method (search returned nothing specific); treat it as a price-ceiling check, not a standalone method, until sourced.
- No sourced guidance found on Fermi estimation protocols or formal analogue/comparables selection beyond Gurley's cellular example.

## 3. Building a credible SOM: penetration, diffusion, sales capacity, funnel benchmarks

### Takeaway
Pros build SOM from the go-to-market engine (reps or channel capacity x win rate x deal size, net of churn) and then check it against category diffusion curves and the pipeline it requires. "X% of SAM" without a mechanism is the classic weak SOM. There is no standard year-3 share; one rigorous worked example lands at about 2.9% of serviceable accounts.

### Cited Findings
- "Build SOM from sales capacity, win rate and churn, then check the pipeline it requires"; "No standard SOM percentage exists" ([Stratrix](https://www.stratrix.com/craft/tam-sam-som)).
- Worked SOM: about $5.2M ARR after three years, about 2.9% of serviceable accounts ([Stratrix](https://www.stratrix.com/craft/tam-sam-som)).
- Bass diffusion pooled parameters from a meta-analysis of 213 applications in 15 articles: p (innovation) = 0.03, q (imitation) = 0.38 (Sultan, Farley and Lehmann, Journal of Marketing Research 27, Feb 1990, pp. 70-77) ([Foresight for Development, secondary](https://foresightfordevelopment.org/library/download-file/46-1392/54); [Columbia Business School listing](https://business.columbia.edu/faculty/research/meta-analysis-applications-diffusion-models)). Verify against original JMR tables before hard-coding.
- q/p ratio varies across countries with income inequality (Gini) and Hofstede culture dimensions ([Stremersch and Van den Bulte, Erasmus working paper](https://repub.eur.nl/pub/1012/ERS%20077%20Stremersch%20van%20den%20Bulte.pdf)).
- Rogers adopter categories: innovators 2.5%, early adopters 13.5%, early majority 34%, late majority 34%, laggards 16% ([PMC article](https://pmc.ncbi.nlm.nih.gov/articles/PMC3772073); [CFI](https://corporatefinanceinstitute.com/learn/resources/economics/diffusion-of-innovation)). Moore's "chasm" sits between early adopters and the early majority ([Benchmark Six Sigma forum, non-scholarly](https://www.benchmarksixsigma.com/forum/topic/36597-diffusion-of-innovations-theory/)).
- Sales capacity inputs (secondary, conflicting): Bridge Group 2025 SDR report (primary): SDR ramp 3.0 months, lowest since 2010; 60% of SDRs at quota, lowest in study history ([Bridge Group 2025](https://www.bridgegroupinc.com/research/2025-sdr-models-metrics-report-the-bridge-group)). AE ramp attributed to Bridge Group 2024: 4.7 months ([Stealth Agents](https://stealthagents.com/research/cost-of-hiring-an-account-executive-2026)) vs 7.2 months, up from 5.3 in 2020 ([Starr Conspiracy](https://www.thestarrconspiracy.com/insights/benchmarks/b2b-go-to-market-strategy-benchmarks-2024)) vs 3.2 months undated ([Alexander Jarvis](https://www.alexanderjarvis.com/what-is-sales-ramp-up-time-in-saas/)). AE quota attainment median 40-55% ([Boomerang](https://www.getboomerang.ai/glossaries/quota-attainment-benchmarks-2026), citation possibly mislabelled).
- Gurley's critique of SOM caps: disputed Damodaran's 10% max share because strong user incentives (faster pickup, lower price) and network effects concentrate share ("Geographic density is the new network effect", quoting David Sacks) ([Gurley 2014](https://abovethecrowd.com/2014/07/11/how-to-miss-by-a-mile-an-alternative-look-at-ubers-potential-market-size/)).

### Inferences
- Bass curve with the pooled p = 0.03, q = 0.38 (cumulative share of eventual market potential, all vendors combined; computed from F(t) = (1 - e^-(p+q)t) / (1 + (q/p) e^-(p+q)t)): year 1 about 3.6%, year 2 about 8.5%, year 3 about 15%, year 5 about 33%, year 7 about 55%, year 10 about 81%; peak adoption around year 6.2. So by year 3 a typical new category has only reached about the innovators + early adopters slice (16% in Rogers). A startup's year-3 SOM is its share of that 15%, not of SAM. These parameters come mostly from consumer durables; treat as an order-of-magnitude prior, not a forecast.
- Recommended SOM build for the agent (B2B): SOM_y3 = sum over months of (ramped reps x monthly quota x attainment) or (channel reach x conversion x ACV), minus churn; then check (a) SOM / SAM accounts, (b) required pipeline = new bookings / win rate, (c) SOM <= category adoption at year 3 x plausible vendor share. For B2C: reach (paid/organic/partner) x funnel conversion x ARPU x retention.
- The agent's "SOM anchored to competitor share" is a reasonable cross-check (a peer's share at a similar age shows what is achievable) but not a build; it ignores the startup's own capacity and the time to get there. Channel reach is closer to correct but needs conversion and churn.
- For muru-D specifically, Telstra distribution (if genuinely available) is a channel-reach input that should be stated with its own conversion assumption, not assumed.

### Gaps
- No primary Bridge Group AE report retrieved; AE ramp and attainment numbers conflict across secondaries. A claim that AE attainment fell from 66% (2022) to 51% (2024) appeared in a search summary without a traceable URL; unverified.
- No sourced benchmark for typical startup year-3 market share across a cohort; no sourced funnel conversion benchmarks (visitor to lead, lead to customer) from a primary source.
- No Australia-specific Bass parameters found.

## 4. Sensitivity analysis and ranges

### Takeaway
Rigorous sizing identifies the few assumptions that drive the output and tests them; the Uber case shows a 25x swing from two inputs (market definition and max share). Sources found do not give a standard low/base/high method or tornado/Monte Carlo practice for startup TAM.

### Cited Findings
- Gurley: valuation models look precise while depending heavily on a few assumptions; Damodaran's assumptions could be off by 25x ([Gurley 2014](https://abovethecrowd.com/2014/07/11/how-to-miss-by-a-mile-an-alternative-look-at-ubers-potential-market-size/)).
- Gurley's ranges are built from bounded multipliers on each driver (3-6x expansion of car-for-hire; 2.5-12.5% capture of ownership spend) rather than one blanket +/- percentage ([Gurley 2014](https://abovethecrowd.com/2014/07/11/how-to-miss-by-a-mile-an-alternative-look-at-ubers-potential-market-size/)).
- Triangulation tolerance: "If bottom-up and top-down differ by more than 2-3x, one contains a bad assumption" ([Stratrix](https://www.stratrix.com/craft/tam-sam-som)); a practitioner blog uses 8x ([Tomba](https://tomba.io/blog/how-to-calculate-tam-sam-som)); another flags $10B vs $500M as a must-fix gap ([Growigami](https://growigami.com/blog/tam-sam-som-saas)).
- Damodaran/Cornell recommend "skeptical" DCF models built on critical estimates of market size and number of competitors ([Cornell via Slope of Hope](https://slopeofhope.com/?p=182173)).

### Inferences
- Low/base/high should come from ranging each driver (buyer count, price, adoption, share) at sourced bounds, not from multiplying the base by 0.5x/2x. The output range is then the product of driver ranges, and the agent should report which driver contributes most (a text tornado: swing in SOM when each input moves low->high, others at base).
- The agent's 2x triangulation rule is at the strict end of the 2-3x Stratrix band, which is fine; the weakness is what happens on disagreement. It should name the diverging assumption and fix it, not average the two.
- Monte Carlo is overkill for an LLM-generated early-stage note; a driver-level tornado is sufficient and more legible.

### Gaps
- No primary source found on how VCs or consultants formally choose low/base/high (e.g. P10/P50/P90) or use Monte Carlo for startup TAM.

## 5. Common errors VCs and analysts flag

### Takeaway
The recurring errors are: inflated top-down totals from too-broad category codes or analyst reports, "1% of a huge market" SOMs, mismatched units (employees as seats, establishments as firms), list instead of realized price, adjacent markets folded into today's TAM, stale or mixed years/geographies, and ignoring that all competitors' implied shares must fit inside the market.

### Cited Findings
- Using the widest industry code: NAICS 238 would give a "TAM" about 16x the honest figure (CBP 2022: NAICS 238 had 510,803 establishments vs 109,601 for NAICS 238220) ([Stratrix](https://www.stratrix.com/craft/tam-sam-som)).
- Further errors: counting employees as seats; list instead of realized price; adding adjacent markets to today's TAM; SOM as a share of TAM ("win just 1%") without a sales mechanism; untraceable totals; mixed years or geographies ([Stratrix](https://www.stratrix.com/craft/tam-sam-som)).
- "1% of a huge market" implies the founder hasn't worked out how to win customers ([Flipsnack](https://blog.flipsnack.com/how-to-calculate-tam-sam-som), practitioner blog). TAM quietly including markets the product cannot serve is "the most common inflation"; a 2021 analyst figure in a 2026 deck reads as neglect; SOM often contradicts the deck's own revenue plan ([BD Emerson](https://www.bdemerson.com/article/tam-sam-som), practitioner blog).
- Big market delusion (Cornell and Damodaran, Financial Analysts Journal 76(2), 2020, Viewpoint, not peer reviewed): overconfidence among entrepreneurs and VCs leads to collective overpricing of companies in "big markets", downplaying competition, rapid overcrowding, then correction; cases: 1990s online retail, online advertising, cannabis ([RePEc](https://ideas.repec.org/a/taf/ufajxx/v76y2020i2p15-25.html); [CFA Institute](https://rpc.cfainstitute.org/research/financial-analysts-journal/2020/0015198x-2020-1730655)).
- Damodaran's sum-of-shares test: estimate market size for a target year; back out the revenue each player's valuation requires; sum and compare. Online ads, Aug 2015: imputed 2025 revenues of listed firms $523B vs optimistic 2025 market $466B (implied 112% share before private firms); Facebook alone needed $129,318M in 2025. Cannabis, Oct 2018: market caps over $48B, more than 20x revenues, vs 2024 forecasts of $70-150B. He criticises "nonsensical notions of what accessible means to get to large numbers" and says to test assumptions with people who don't share your optimism ([Damodaran blog, 2019-12](https://aswathdamodaran.blogspot.com/2019/12/the-market-is-huge-revisiting-big.html?m=0)).
- "We've never seen small TAM, SAM, SOM numbers on a market size slide" (Max Meyer, Blackbird) ([Overnight Success, 2025-09-25](https://www.overnightsuccess.vc/p/what-blackbird-wants-in-an-early-stage-pitch-deck)).

### Inferences
- Add a "sum of shares" check to the agent: list named competitors with estimated revenue, add the proposed SOM, and confirm the total does not exceed SAM in the horizon year.
- Spend vs revenue pool: Uber's gross bookings vs taxi revenue mismatch (Stratrix) is an instance of the general rule that the agent must size the revenue the startup can book (take rate x GMV for marketplaces), not total customer spend.
- Category market reports (high CAGR, broad definitions) should only feed the top-down ceiling, always with publisher, year, geography and currency stated, and never be the basis of SOM.

### Gaps
- No primary VC-authored list of sizing errors (Sequoia, a16z, Bessemer) was found; "double counting" across segments is implied by Stratrix's MECE rule but not separately sourced.

## 6. How accelerators and VCs evaluate a sizing slide (incl. Australian firms)

### Takeaway
Australian top-tier VCs (Blackbird) treat the standard TAM/SAM/SOM slide as low-signal because everyone shows big numbers; they look for a large, painful problem shared by many customers, evidence of customer love (revenue first), and a team with an earned secret. What earns trust is traceable logic, not the headline.

### Cited Findings
- Blackbird (Rick Baker, Partner; Max Meyer, Investment Principal), Sept 2025: TAM/SAM/SOM "in isolation... doesn't add value"; show scale through a "big, hair on fire problem for a large number of customers"; Uber and DoorDash as cases where the problem existed before the market; "the purest form of love is revenue"; traction "through numbers using charts"; team with "an earned secret about the world"; "The bolder the vision, the more excited we become"; early exit plans signal low ambition ([Overnight Success, 2025-09-25](https://www.overnightsuccess.vc/p/what-blackbird-wants-in-an-early-stage-pitch-deck)).
- Common thresholds (practitioner, unverified): TAM $1B+ with defensible SAM $200-500M as rough venture-scale threshold; $5B+ TAM expected at Series A and later ([Pitch Deck Guide](https://pitchdeckguide.com/tam-sam-som-pitch-deck/)); TAM over $1B for typical venture-backed business ([startupfundraising.com](https://startupfundraising.com/library/articles/how-to-capture-the-market-size-in-a-pitch-deck)).
- Investors judge the logic more than the number; an unfiltered "$2T global market" loses credibility ([Whitepage Studio](https://www.whitepage.studio/blog/market-size-slide-pitch-deck), practitioner blog).
- YC (secondary): prefers bottom-up because it shows you know who customers are and how you reach them ([Storydoc](https://www.storydoc.com/blog/y-combinator-application-guide)); accepts small "larval" markets with a path to scale ([Gurubase](https://gurubase.io/g/ycombinator/y-combinator-evaluate-market-size-potential-startups-funding)).

### Inferences
- For a muru-D agent, the sizing output should lead with the bottom-up unit line (who exactly buys, how many in Australia, at what realized price), then the problem-severity evidence, and treat TAM as context. This matches Blackbird's stated preference and YC's bottom-up preference.
- A credible slide answers "why this number?" for every input with a named source and year.

### Gaps
- No public guidance found from muru-D, Startmate, Square Peg or Cut Through Venture on market sizing slides.
- No primary YC Startup School lesson on market sizing retrieved.

## 7. Worked examples and Australia-specific inputs

### Takeaway
The best worked examples (Stratrix field-service SaaS; Gurley's Uber) share a pattern: official counts of the buying unit, realized price per that unit, MECE filters each justified, SOM from capacity over a stated horizon, expansion as a separate thesis. For Australia, the ABS Counts of Australian Businesses (CABEE) is the default buyer-count source for B2B.

### Cited Findings
- Stratrix field-service SaaS example (TAM about $359.8M -> SAM about $181M -> SOM about $5.2M ARR at year 3), using BLS occupational counts and Census CBP establishment counts by size band, arithmetic checked ([Stratrix](https://www.stratrix.com/craft/tam-sam-som)).
- Gurley's Uber build (Section 2) as the reference example of demand-side new-market sizing ([Gurley 2014](https://abovethecrowd.com/2014/07/11/how-to-miss-by-a-mile-an-alternative-look-at-ubers-potential-market-size/)).
- ABS CABEE: 2,814,778 actively trading businesses at 30 June 2026, of which 996,203 employing (first net increase in employing businesses since 2021-22) ([ABS CABEE Jul2022-Jun2026](https://www.abs.gov.au/statistics/economy/business-indicators/counts-australian-businesses-including-entries-and-exits/jul2022-jun2026)). Prior year: 2,729,648 at 30 June 2025, 994,178 employing; 2024-25 entry rate 16.4%, exit rate 13.9% ([ABS CABEE Jul2020-Jun2024 / methodology Jul2021-Jun2025](https://www.abs.gov.au/methodologies/counts-australian-businesses-including-entries-and-exits-methodology/jul2021-jun2025)).
- Breakdowns by industry and employment size are available via the ABS CABEE release ([ABS](https://www.abs.gov.au/statistics/economy/business-indicators/counts-australian-businesses-including-entries-and-exits/sort)).

### Inferences
- About 1.82M (64.6%) of Australian actively trading businesses are non-employing (computed from ABS June 2026 figures). A B2B tool aimed at "SMEs" that counts all 2.8M businesses is counting mostly sole traders and dormant-ish ABNs; the agent should default to employing businesses in the relevant ANZSIC division and size band unless the product is explicitly for sole traders.
- Entry/exit rates of 16.4%/13.9% mean the buyer base churns materially each year; for SOM, new-business formation is a recurring acquisition pool, and customer churn has a structural floor from business exits.
- Australian analogues to Stratrix's US sources: ABS CABEE (vs Census CBP), ABS Labour Force occupation data (vs BLS), with AUD and financial year (July-June) stated. CABEE counts are ABN-based; the establishment vs firm distinction in CBP should be checked for CABEE before use.
- Currency/year hygiene: global reports in USD must be converted to AUD at a stated rate and year, and a global figure must be scaled to Australia with a stated method (e.g. GDP share or category-specific data), not assumed.

### Gaps
- Not verified whether CABEE counts enterprises, ABNs or establishments (affects multi-unit adjustment).
- No Australian consumer worked example found; ABS household and population data sources were not researched.
- No Australia-specific penetration or adoption benchmarks found.

## Summary of gaps and fixes in the current agent method (synthesised from the above)

### Takeaway
The current pipeline is directionally right but has four structural weaknesses: adoption is mixed into the TAM line, SOM is anchored to others' shares instead of the startup's own capacity, ranges are not driver-based, and there is no competitor sum-of-shares or expansion-thesis separation.

### Cited Findings
- Capacity-based SOM, MECE filters, realized price, unit matching, expansion on a separate line, 2-3x triangulation: [Stratrix](https://www.stratrix.com/craft/tam-sam-som).
- Sum-of-shares test against market size: [Damodaran 2019](https://aswathdamodaran.blogspot.com/2019/12/the-market-is-huge-revisiting-big.html?m=0).
- Incumbent-spend anchoring under-sizes new categories: [Gurley 2014](https://abovethecrowd.com/2014/07/11/how-to-miss-by-a-mile-an-alternative-look-at-ubers-potential-market-size/).

### Inferences
- Fix 1: Bottom-up TAM = buyers x units per buyer x realized annual price (no adoption term). Adoption/penetration belongs in SOM.
- Fix 2: SOM = capacity build (reps/channel x conversion x ACV, minus churn) over 3 years, cross-checked against (a) Bass-implied category adoption (about 15% of potential at year 3), (b) a comparable competitor's share at the same age, (c) sum of competitor shares <= SAM.
- Fix 3: Ranges from sourced bounds on each driver; report the top 1-2 drivers by swing.
- Fix 4: On triangulation failure (>2x), name and fix the divergent assumption; never average.
- Fix 5: Separate "Expansion TAM" line for new-category ideas, with the specific behaviour-change evidence that would confirm it.
- Fix 6: Australia defaults: ABS CABEE employing businesses by ANZSIC and size band, AUD, financial year, every input sourced with publisher and year.

### Gaps
- None of these fixes were validated against muru-D's own judging criteria, which were not found publicly.
