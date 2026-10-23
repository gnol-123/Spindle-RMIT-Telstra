# DVF (Desirability, Viability, Feasibility) scoring on evidence

Research date: 2026-10-23. Scope: origin, rubrics, evidence-strength scales, scoring mechanics, AI desk-research limits, experiment benchmarks, public scorecards. Written for an LLM market research agent at muru-D.

## 1. Origin and canonical definitions (incl. 4th lens)

### Takeaway
DVF comes from IDEO / Tim Brown's design thinking (HBR, June 2008). Strategyzer turned it into an evidence-based risk system mapped to the Business Model Canvas (BMC) and added a 4th lens, **Adaptability**: the environment (competition, market, trends, macro). That is the only 4th lens with a published, scored rubric behind it. Ethics/Responsibility lenses exist only as informal variants.

### Cited Findings
- Brown defines design thinking as matching "people's needs with what is technologically feasible and what a viable business strategy can convert into customer value and market opportunity" (HBR, June 2008, sole author Tim Brown): [Brown 2008 PDF copy](https://www.student.cs.uwaterloo.ca/~cs449/w18/IDEO_Brown_2008.pdf)
- *Change by Design* (Brown) lists the three criteria: feasibility (can it be built), desirability (do people want it), viability (can it be sustained). Commentators note Brown treats desirability as the foundational lens: [timnovate summary](https://timnovate.com/2022/04/03/change-by-design-feasibility-viability-desirability/); [IDEO Change by Design page](https://designthinking.ideo.com/resources/change-by-design)
- The claim that "IDEO conceptualized DVF in the early 2000s" rests on secondary sources only (e.g. UXPin). No primary IDEO document dates the triad: [UXPin](https://www.uxpin.com/studio/?p=15119)
- Strategyzer (Bland, *Testing Business Ideas*, 2019/2020) uses four hypothesis types. Desirability: "Does the market want this idea?" Feasibility: "Can we deliver at scale?" Viability: "Is the idea profitable enough?" Adaptability: "Can the idea survive and adapt in a changing environment?" (Bland, 4 Aug 2020): [Strategyzer, Assumptions Mapping](https://strategyzer.com/library/how-assumptions-mapping-can-focus-your-teams-on-running-experiments-that-matter)
- BMC mapping in the Strategyzer Innovation Project Scorecard. Desirability = Customer Segments, Value Proposition, Channels, Customer Relationships. Feasibility = Key Resources, Key Activities, Key Partners. Viability = Revenue Streams, Cost Structure. Adaptability = Business Environment Canvas (Industry Forces, Market Forces, Key Trends, Macro-Economic Forces): [Strategyzer scorecard PDF (CSULB copy)](https://www.csulb.edu/sites/default/files/document/innovation_project_scorecard.pdf); [Viki, Strategyzer, 10 Jun 2019](https://strategyzer.com/library/innovation-project-scorecard-evidence-trumps-opinion)
- Note: Strategyzer puts **Channels and Customer Relationships under desirability**, not viability. Many simplified versions omit this.
- The Canadian public service "mission model canvas" maps DVF onto canvas fields too. Desirability = value proposition, buy-in, beneficiaries. Viability = budget/cost/impact. Feasibility = partners, activities, resources: [Canada School of Public Service, Mission Canvas](https://ecolecanada.gc.ca/tools/jobaids/pdfs/mission-canvas-eng.pdf)
- Assumptions mapping lineage: Gothelf and Seiden (*Lean UX*) originated it, and Bland adapted it: [Barking Iguana](https://barkingiguana.com/writing/the-workshop-assumption-mapping/)
- A search for an established "Responsibility/Ethics/Integrity" 4th lens returned no authoritative framework. Mainstream DVF sources use 3 lenses, and Strategyzer adds Adaptability: [Bucknell DVF](https://bucknell.edu/desirability-viability-feasibility-framework); [Ramotion](https://www.ramotion.com/blog/desirability-feasibility-viability/)

### Inferences
- For muru-D (Telstra), Adaptability is the defensible 4th lens. It covers competitor/incumbent response, regulatory shifts (ACMA, privacy, AI regulation), and tech trends. Desk research can actually assess it, so it plays to an AI agent's strength.
- Strategyzer's Adaptability "Key Trends" item already folds regulatory risk in. A separate Ethics lens would duplicate it unless muru-D wants a hard responsible-tech gate. If it does, implement that as a pass/fail gate, not a scored lens.
- The current agent's 3-lens model misses Strategic Fit (a separate Strategyzer section) and Opportunity Size. Both are first-class sections in the scorecard, not sub-items of viability.

### Gaps
- No primary IDEO source dates the DVF triad or credits it to a specific person.
- No authoritative source found for "Integrity" or "Responsibility" as a 4th DVF lens. Treat these as informal variants.

## 2. Concrete sub-criteria per lens

### Takeaway
The best public sub-criteria are Strategyzer's scorecard items (13 risk items plus 3 strategic-fit items plus opportunity size). Overlay them with quantitative viability thresholds: LTV:CAC > 3, CAC payback < 12 months (Skok), SaaS gross margin ~75-80%. Feasibility should use TRL for deep-tech ideas.

### Cited Findings
**Strategyzer Innovation Project Scorecard, verbatim items (0 no evidence / 5 some evidence / 10 strong evidence)**: [scorecard PDF](https://www.csulb.edu/sites/default/files/document/innovation_project_scorecard.pdf)
- Strategic Fit (0 no alignment to 10 strong alignment): Vision/Culture/Image ("aligned to our company's vision, culture and image"); Innovation Guidance; Leadership Support ("has support from a key sponsor(s)").
- Desirability: Customer Segment ("critical customer segments have the jobs, pains, and gains relevant for selling our value proposition"); Value Proposition ("resonates with our critical customer segments"); Channels ("found the best channel(s) to reach and acquire"); Customer Relationship ("right relationships to retain customers and repeatedly earn from them").
- Feasibility: Key Resources ("right technologies and resources"); Key Activities ("right capabilities to handle the most critical activities"); Key Partners ("found the right key partners who are willing to work with us").
- Viability: Revenues ("We know how much our customers are willing to pay us and how they will pay"); Costs ("We know our costs for creating and delivering the value proposition").
- Adaptability: Industry Forces (competitors, emerging players); Market Forces (critical issues, shifts, economic value of addressable market); Key Trends (technology, regulatory, cultural, societal); Macro-Economic Forces.
- Opportunity: "We understand the financial potential of our idea", anchored value < $100k / $10M+ / $100M+.

**Viability benchmarks**
- LTV:CAC: "The best SaaS businesses have a LTV to CAC ratio that is higher than 3". CAC payback: profitability is "anemic if the time to recover CAC extends beyond 12 months" (David Skok, SaaS Metrics 2.0, undated, rewrite circa 2020): [forEntrepreneurs](https://www.forentrepreneurs.com/saas-metrics-2/)
- 2025 actuals (Aleph x Benchmarkit, 342 SaaS/AI-native cos, FY2025 data): median CLTV:CAC 4.1x, top quartile 7.8x, bottom quartile 1.1x: [Aleph](https://getaleph.com/answers/cltv-cac-ratio-saas-2026). Aggregators conflict: SaaS Capital 2025 median 2.1:1, OpenView 3.2:1 (both unverified at source): [Stealth Agents](https://stealthagents.com/research/startup-ltv-to-cac-ratio-benchmarks-2026)
- CAC payback: Benchmarkit median 18 months in 2024, up from 14 months the year before: [Rework](https://resources.rework.com/fr/libraries/pipeline-management/ltv-cac-ratio); Aleph ~20 months median for 2025, leaders < 12: [Aleph payback](https://www.getaleph.com/answers/cac-payback-period-saas-2026)
- Gross margin: 2025 median software gross margin 80% (top quartile > 86%), usage-only pricing ~62%: [Aleph](https://www.getaleph.com/answers/saas-gross-margin-2026). KeyBanc 2025, $5-50M ARR: 71-74% (via aggregator): [Stealth Agents](https://stealthagents.com/research/startup-gross-margin-benchmarks-2026). Rule of thumb: > 75% is good for SaaS: [Stripe](https://stripe.com/en-se/resources/more/saas-gross-margin-explained-what-it-is-and-why-it-is-important)
- AI-native: Bessemer 2025 "Supernovas" average ~25% gross margin early (some negative), "Shooting Stars" ~60%: [SaaStr](https://www.saastr.com/have-ai-gross-margins-really-turned-the-corner-the-real-math-behind-openais-70-compute-margin-and-why-b2b-startups-are-still-running-on-a-treadmill)
- Marketplaces 30-45% early / 50-65% at scale; hardware/IoT 38-52% (attributed to Bessemer State of the Cloud 2025, **unverified secondary**): [Stealth Agents](https://stealthagents.com/research/startup-gross-margin-benchmarks-2026)

**Feasibility: TRL**
- NASA TRL runs 1 (basic research) to 9 ("flight proven" in a successful mission). TRL 2 = speculative application with little or no experimental proof. TRL 3 = active R&D begins. TRL 8 = tested and "flight qualified": [NASA](https://www.nasa.gov/directorates/spacetech/spinoff/feature/technology-readiness-levels). TRL 4 = component validation in lab, TRL 7 = full prototype tested in operational environment: [KTN Innovation Canvas](https://www.innovationcanvas.ktn-uk.org/resources/technology-readiness-levels-trl). ESA uses ISO 16290 because agencies interpret TRL differently: [ESA](https://m.esa.int/Enabling_Support/Space_Engineering_Technology/Shaping_the_Future/Technology_Readiness_Levels_TRL)
- Blank calls TRL "imperfect" and "subjective" but says it gives a shared language: [Blank 2013](https://steveblank.com/2013/11/25/its-time-to-play-moneyball-the-investment-readiness-level/)

**Stage-Gate (Cooper) criteria**
- Gates mix must-meet knockouts (binary; one "No" kills, e.g. strategic fit) with should-meet weighted criteria summed into an attractiveness score. Typical should-meet items: strategic fit, market attractiveness, competitive advantage, technical feasibility, financial return/ROI, each scored 1-10: [Rework](https://resources.rework.com/libraries/project-management/stage-gate-process); [HubSpot FR](https://blog.hubspot.fr/marketing/methode-stage-gate?facet2=pdf). Stage-Gate International now uses a risk-adjusted financial model plus a "Value-Based Scorecard": [resumelens](https://www.resumelens.org/blog/project-management/stage-gate-process) (secondary)

### Inferences
- Proposed sub-criteria for the agent, each scored separately:
  - **D**: problem severity, frequency, current spend/workaround, switching intent, reachable channel, retention driver.
  - **V**: WTP and pricing model, gross margin vs. business-model benchmark, LTV:CAC and payback (modelled), opportunity size (Strategyzer anchors), strategic fit with Telstra.
  - **F**: TRL (if tech-heavy), regulatory/licensing path, team capability, partner dependency, time/cost to MVP.
  - **A**: competitor/incumbent response, trend tailwinds/headwinds, macro.
- Margin benchmarks must be by business model. A blanket 70%+ threshold would wrongly fail marketplaces, hardware, and AI-heavy usage businesses.
- For early-stage ideas, LTV:CAC and payback are always modelled, never observed. The agent should label them "assumption" and cap confidence (see section 3).

### Gaps
- Stage-Gate International's official Value-Based Scorecard items and weights were not accessible. Cooper's NewProd factor weights were not verified.
- Marketplace and hardware margin figures come only from an aggregator. Verify against Bessemer before using them as hard thresholds.
- No Australian-specific unit-economics benchmarks were found.

## 3. Evidence-strength scales and score caps

### Takeaway
Practice scores **evidence, not opinion**. Strategyzer rates evidence 0-5. What people *say* (interviews, surveys) can never score above 2. Only what they *do* (clicks, sign-ups, deposits, sales) reaches 3-5. Strength rises with proximity to a real purchase, real-world (not lab) setting, and size of customer commitment. Confidence then scales with the number of data points and independent experiments.

### Cited Findings
- Strategyzer: a 0-5 evidence scale. Levels 1-2 = what people say, 3-5 = what they do. Volume does not change the category: five interviews and a million interviews score the same: [Strategyzer, business project success](https://www.strategyzer.com/library/business-project-succcess) (via search summary)
- An interview's evidence score "will never exceed a 2". A landing page asking for an email is "very weak/light" evidence; a deposit is stronger. Real-world settings beat lab settings. The top benchmark is a covert/mock sale where "Customers will believe they are buying the real thing". The Innovation Project Scorecard rates risk "from 0 to 5" on evidence type and quantity (Lucy Luo, Strategyzer, 6 May 2021): [Strategyzer](https://strategyzer.com/library/business-testing-is-your-hypothesis-really-validated)
- Data-point count affects confidence but not strength: 100 interviews give more confidence than 5 yet remain weak. 50 deposits give far more confidence than 5: [Luo 2021](https://strategyzer.com/library/business-testing-is-your-hypothesis-really-validated)
- Validation is "a judgment call" on a spectrum. Leaders should ask "what evidence has been collected and how confident they feel about that evidence" rather than "is it validated?": [Luo 2021](https://strategyzer.com/library/business-testing-is-your-hypothesis-really-validated)
- Osterwalder: two experiment dimensions, Speed and Strength. "The evidence gets stronger the closer you get to a real world buying example." Interviews and surveys are "valuable, but weak". Simulated sales give strong evidence. Start cheap in exploration, use "longer and more solid experiments" in validation (21 Mar 2017): [Strategyzer](https://strategyzer.com/library/how-strong-is-your-innovation-evidence)
- The Strategyzer Experiment Library plots experiments on two axes: Say to Do, and Low-stakes action to Real-world commitment: [Strategyzer, Design experiments](https://www.strategyzer.com/programs/design-experiments-prepare-to-test-your-business-idea-part-2)
- Scorecard (Viki 2019) grades the amount of evidence on three tiers: "no evidence, evidence from one experiment or evidence from multiple experiments". Multiple experiments are "likely to be picking up a strong signal rather than noise": [Strategyzer](https://strategyzer.com/library/innovation-project-scorecard-evidence-trumps-opinion)
- Assumptions mapping evidence axis: "observable evidence, qualitative or quantitative". "It's not about who is the loudest or who gets paid the most": [Bland 2020](https://strategyzer.com/library/how-assumptions-mapping-can-focus-your-teams-on-running-experiments-that-matter)
- Strategyzer Innovation Metrics: track only 4 metrics per exploration project (Risk/uncertainty, Potential/expected profitability, Time, Cost). The RISK metric shows "how much the team has de-risked an idea so far, and how much risk still remains". Hypotheses without recent evidence need experiments: [Strategyzer, innovation board](https://www.strategyzer.com/library/how-should-your-innovation-board-make-decisions); [Strategyzer, guesswork](https://www.strategyzer.com/library/taking-the-guesswork-out-of-innovation)
- The Test Card has these fields: hypothesis, test, metric, success criterion ("We are right if..."). The Learning Card has these fields: observation, learning, decision: [Miro community](https://community.miro.com/ideas/test-and-leaning-cards-templates-10650)
- The Mom Test (Fitzpatrick). Compliments, fluff (generic/hypothetical claims), and ideas are bad data. Ask about specific past behaviour. Real signal is commitment and advancement (next meeting, sign-up): [Unusual VC](https://www.unusual.vc/rob-fitzpatricks-mom-test/); [mtlynch review](https://mtlynch.io/book-reports/the-mom-test/). Commitment currencies are time, reputation, and money, ranked roughly beta join (moderate) < intro to boss (strong) < pilot with stated WTP (very strong). This ranking is a **third-party interpretation**: [Koji](https://www.koji.so/docs/mom-test-methodology)
- Blank's Investment Readiness Level (IRL, Nov 2013) is modelled on NASA TRL. It aggregates customer interviews (~10/week, ~100 over 10 weeks) and validated/invalidated hypotheses across all 9 BMC boxes into one score. It is "part of" the go/no-go decision and does not replace judgment: [Blank 2013](https://steveblank.com/2013/11/25/its-time-to-play-moneyball-the-investment-readiness-level/); [Blank 2014](https://steveblank.com/2014/07/01/how-investors-make-better-decisions-the-investment-readiness-level/)
- Teresa Torres' Opportunity Solution Tree: outcome, opportunities, solutions, assumption tests. Compare solutions by testing their underlying assumptions. Prioritise opportunities, not solutions: [Product Talk](https://www.producttalk.org/glossary-discovery-opportunity-solution-tree/); [Chameleon](https://www.chameleon.io/blog/opportunity-solution-tree)

### Inferences
- Map the agent's source grades to a hard evidence cap per lens (adapting Strategyzer 0-5 to the agent's 1-5):
  - Desk research only (market reports, competitor sites, news, analyst data): max 2/5 for Desirability and Viability. Third-party data shows a market exists, not that *these* customers want *this* offer.
  - Reported behaviour from secondary sources (reviews/complaints volume, search demand, competitor revenue/traction, public pricing): max 3/5.
  - Founder's own primary say-data (interviews, surveys): max 2 under Strategyzer's rule, regardless of N.
  - Low-stakes do-data (landing page CTR, waitlist, fake door): 3.
  - Commitment do-data (LOI, deposit, pre-order, paid pilot): 4.
  - Repeat purchase or retention at real price: 5.
- So "5 = strong positive from A/B sources" is miscalibrated for an AI desk-research agent. A/B *source quality* (credible publisher) is not *evidence strength* (behaviour and commitment). The agent conflates the two. Keep source reliability as a separate axis (an Admiralty-style A-F) feeding confidence, and let evidence type cap the score.
- Confidence should derive from (a) number of independent sources/experiments (Strategyzer: one vs multiple), (b) recency, and (c) source agreement. Confidence should not be a free-text judgment.
- Feasibility and Adaptability are the lenses where desk research can legitimately reach high scores: TRL of existing components, regulatory text, competitor landscape.

### Gaps
- The exact verbatim wording of each level 0-5 on Strategyzer's current evidence scale was not retrievable. The *Testing Business Ideas* PDF was not accessible.
- The IRL 1-9 level labels render as an image on Blank's blog and could not be verified verbatim. A commonly reproduced version runs: 1 first-pass BMC, 2 market size/competition, 3 problem/solution fit, 4 low-fi MVP, 5 product/market fit, 6 high-fi MVP, 7 channel validation, 8 metrics that matter, 9 business model validated. **Unverified**, so confirm before quoting.
- No source found for formal "innovation accounting" (Ries) thresholds beyond the general validated-learning concept.

## 4. Scoring mechanics: weighted vs gated vs weakest-link, combining score and confidence, inter-rater reliability

### Takeaway
Practice combines **gates** (must-meet knockouts, e.g. strategic fit, legal), **evidence-based risk scores per lens**, and **stage-appropriate thresholds**. Strategyzer has no single composite. It shows the risk profile per lens plus Potential, Time, and Cost. Weakest-link is defensible for DVF because a fatal flaw in any lens kills the idea, but it should run on the risk-adjusted score with confidence, not the raw score. Rater agreement on idea quality is only moderate, so anchored rubrics and elimination-style screening help.

### Cited Findings
- Stage-Gate: must-meet = binary knockouts, any "No" kills. Should-meet = weighted 1-10 scores summed: [Rework](https://resources.rework.com/libraries/project-management/stage-gate-process); [HubSpot FR](https://blog.hubspot.fr/marketing/methode-stage-gate?facet2=pdf)
- Strategyzer innovation boards track four metrics (Risk, Potential, Time, Cost). Stronger evidence means more risk reduced. The scorecard aligns with discovery, validation, and acceleration stages: [Strategyzer](https://www.strategyzer.com/library/how-should-your-innovation-board-make-decisions); [Strategyzer](https://www.strategyzer.com/library/taking-the-guesswork-out-of-innovation)
- The scorecard separates Strategic Fit (alignment, 0-10), Risk Reduction (evidence, 0-10 per item), and Opportunity (value <$100k / $10M+ / $100M+). These are three different axes, not summed: [scorecard PDF](https://www.csulb.edu/sites/default/files/document/innovation_project_scorecard.pdf)
- Bayer adapted the scorecard for innovation sprint teams and trained leaders to judge pitches on evidence: [Viki 2019](https://strategyzer.com/library/innovation-project-scorecard-evidence-trumps-opinion)
- Assumptions mapping prioritises important plus no-evidence ("top-right"). The order is desirability, feasibility, viability, then adaptability. The test of importance: "which hypothesis, if proven wrong will cause our business idea to fail": [Bland 2020](https://strategyzer.com/library/how-assumptions-mapping-can-focus-your-teams-on-running-experiments-that-matter). Some versions draw it top-left; the quadrant is the same: [Barking Iguana](https://barkingiguana.com/writing/the-workshop-assumption-mapping/)
- Inter-rater reliability: a consumer innovation contest study reports ICC(2,k) 0.70 for an aggregated 6-item quality scale, but individual items only 0.59-0.66: [HAL-HEC](https://hal-hec.archives-ouvertes.fr/hal-02953039) (via search summary). Crowd raters are less reliable than experts and rate more generously: [Exordo OUI 2016](https://programme.exordo.com/oui2016/delegates/presentation/87)
- "Bag of lemons" elimination was ~33% more accurate than Likert rating for filtering ideas with ~1/3 rater time. Crowds were ~60% more accurate at eliminating bad ideas than at picking good ones (2015): [HKBU IIB](https://www.comp.hkbu.edu.hk/~iib/2015/Dec/article2/iib_vol16no1_article2.pdf)
- Confidence-weighted aggregation of crowd judgments reduces the risk of discarding high-quality ideas, at the cost of slightly more misclassified low-quality ones (ICIS 2021): [AISeL](https://aisel.aisnet.org/icis2021/sharing_econ/sharing_econ/10)
- LLMs and crowds can evaluate ideas in complex domains against expert juries. Contest specialisation hurt crowd performance but not LLM performance (Group Decision and Negotiation, 2025): [MIT DSpace](https://dspace.mit.edu/handle/1721.1/162165) (via search summary)

### Inferences
**Gap analysis vs the current muru-D agent**
1. **Score conflates "how good" with "how proven."** Split each lens into a *signal* (direction: positive/negative/mixed) and an *evidence level* (0-5, capped by evidence type, section 3). Today "5 = strong positive A/B" makes a well-sourced desk report look validated.
2. **Missing Adaptability lens and missing Strategic Fit gate.** Add Adaptability, scored like the other lenses. Make Telstra strategic fit a must-meet gate (vision, innovation thesis, sponsor) per Strategyzer and Stage-Gate.
3. **Missing Opportunity size axis.** Strategyzer scores it separately with $ anchors. Link this to the TAM/SAM/SOM work instead of burying it in viability.
4. **Weakest-link verdict needs a confidence rule.** A low score with low confidence means "unknown": test it (Pilot to test). A low score with high confidence means "known bad": Rethink or Park. Suggested matrix:
   - all lenses at signal >= positive and evidence >= 3: **Pursue**
   - any lens unknown or weak-evidence but no negative signal: **Pilot to test**
   - any lens negative with medium-or-higher confidence and fixable: **Rethink**
   - must-meet gate fail, or negative with high confidence on desirability: **Park**
5. **No anchored descriptors per level.** Every 1-5 per sub-criterion needs a written anchor ("3 = third-party behavioural data, e.g. >=2 competitors with disclosed paying customers in AU"). Anchors are the main lever for rater consistency (item-level ICC ~0.6 without them).
6. **Assumptions lack testable form.** Use Bland's "We believe that..." phrasing plus a Test Card: metric, success threshold set *before* the test, cost, time, expected evidence level. Tag each assumption D/V/F/A. Rank by importance (fails the idea if wrong) x evidence (none to strong). Order D first.
7. **Experiments lack evidence-level targets.** Each proposed experiment should state which evidence level it would reach (e.g. fake door = 3, LOI = 4) and the pass threshold, so a "Pilot to test" verdict maps to a concrete next gate.
8. **Stage-appropriate thresholds.** At discovery, expect evidence 1-2 everywhere; a "Pursue" should not be possible from desk research alone. Cap the max verdict at "Pilot to test" when no lens has do-evidence.
9. **LLM rater drift.** Use elimination prompts ("which lens most likely kills this?") plus multi-sample self-consistency, and report disagreement as lower confidence.

### Gaps
- No published inter-rater reliability study of DVF scorecards specifically was found.
- No public source gives Strategyzer's numeric thresholds for moving between discovery, validation, and acceleration.

## 5. What AI desk research can and cannot establish, plus experiments and pass benchmarks

### Takeaway
Desk research can establish market existence, competitor landscape, pricing anchors, regulatory path, tech maturity, and trends: most of Feasibility and Adaptability, part of Viability. It cannot establish that target customers want *this* offer or will pay *this* price. Those need do-evidence from primary experiments. Experiment benchmarks are practitioner rules of thumb, not standards: set thresholds before running.

### Cited Findings
- Strategyzer: evidence strength rises with proximity to a real purchase. Pharma-type industries that cannot simulate sales must get as close to buying behaviour as possible: [Osterwalder 2017](https://strategyzer.com/library/how-strong-is-your-innovation-evidence)
- Landing-page CTA click-through: >10% strong, 5-10% promising, <3% weak. Email sign-ups at 20-30% of CTA clickers signal serious interest: [echai.ventures](https://echai.ventures/startingup/validate-idea/how-to-run-a-landing-page-fake-door-test) (practitioner)
- Under 2% conversion is "noise, not validation". A "notify me" button on a hyped category page may hit 8-15%: [Causo 2026](https://hub.causo.ai/guides/fake-door-smoke-testing-validate-demand-2026) (practitioner)
- "Even a great landing" converts at 2-5% (founder report): [Indie Hackers](https://www.indiehackers.com/post/use-the-fake-door-test-to-validate-your-saas-product-before-building-it-709eadf520)
- Signal ladder: notify-me (weak) < email plus qualifying questions such as budget/current tool (medium) < card capture or paid pre-order (strong). Waitlist-to-customer conversion is 2-5% for cold traffic. Cap ad spend at $500-2,000 per test. Sample 200-500 requests or 1-2 weeks: [knowledgelib.io](https://knowledgelib.io/business/customer-validation/demand-signal-testing/2026) (practitioner)
- False-positive case: 2,847 sign-ups drove a funding decision, then only 3% converted at launch: [Future Foundry via echai](https://echai.ventures/startingup/from/future-foundry)
- Strategyzer: a landing-page email is "very weak/light"; deposits are stronger; a covert sale is strongest: [Luo 2021](https://strategyzer.com/library/business-testing-is-your-hypothesis-really-validated)
- Blank's Lean LaunchPad / I-Corps standard: ~10 customer interviews per week, ~100 over 10 weeks: [Blank 2013](https://steveblank.com/2013/11/25/its-time-to-play-moneyball-the-investment-readiness-level/)

### Inferences
| Lens | AI desk research can establish (max evidence level) | Needs primary research |
|---|---|---|
| Desirability | Problem exists (complaints, forums, reviews), segment size, incumbents' traction, search demand (max 2-3) | Severity for *this* segment, switching intent, response to this value prop (interviews to 2; fake door/LOI to 3-4) |
| Viability | Price anchors from competitors, business-model margin benchmarks, market size, CAC proxies by channel (max 2-3) | WTP (pricing test, pre-sale), real CAC (paid ads test), retention |
| Feasibility | TRL of components, available vendors/APIs, regulatory requirements (ACMA, Privacy Act), comparable build times (max 3-4) | Team capability, partner willingness (LOI from partner), integration with Telstra systems |
| Adaptability | Competitors, funding in space, trends, regulation pipeline, macro (max 3-4) | Incumbent response is speculative, so rarely testable |

- Suggested experiment library for the agent, with evidence level and default pass threshold:
  - Problem interviews x 10-15 using Mom Test rules: level 2. Pass: >= 60% describe a recent specific instance plus a current workaround/spend. **No source; set as internal default.**
  - Fake door / landing page: level 3. Pass: CTA CTR >= 5% (strong >10%) from targeted traffic.
  - Qualified waitlist (budget/tool questions): level 3. Pass: >= 20-30% of clickers complete.
  - LOI / pilot agreement (B2B): level 4. Pass: >= 3 LOIs from target-segment buyers. **No source.**
  - Pre-sale / deposit: level 4-5.
  - Concierge / Wizard of Oz paid pilot: level 4-5. Pass: repeat use or conversion to paid.
- For muru-D, Telstra's customer base and channels make B2B LOIs and pilot sign-ups unusually cheap experiments. The agent should prefer them.

### Gaps
- No authoritative, dated, peer-reviewed benchmark for fake-door or landing-page validation conversion rates was found. All numbers are practitioner rules of thumb from 2024-2026 blogs. Unbounce-style landing page benchmark reports (marketing pages, not validation tests) were not retrieved.
- No sourced pass thresholds found for interviews, LOI counts, or concierge tests.
- The *Testing Business Ideas* per-experiment cost/time/strength ratings were not accessible.

## 6. Public DVF scorecards from corporates and Australian accelerators

### Takeaway
The only robust public DVF scorecard is Strategyzer's Innovation Project Scorecard, used and adapted by Bayer. No public DVF scorecard was found from Telstra/muru-D, Bosch, Mastercard, Deutsche Telekom, or Australian accelerators.

### Cited Findings
- Strategyzer Innovation Project Scorecard: full items and anchors in section 2: [scorecard PDF](https://www.csulb.edu/sites/default/files/document/innovation_project_scorecard.pdf)
- Bayer adapted it for innovation sprint teams and trained leaders to evaluate on evidence: [Viki 2019](https://strategyzer.com/library/innovation-project-scorecard-evidence-trumps-opinion)
- A search for "Bosch + Strategyzer scorecard" found no source linking Bosch to the scorecard. The only Bosch "risk score" hits were unrelated cyber ratings: [search: Strategyzer scorecard](https://strategyzer.com/library/innovation-project-scorecard)
- Canada School of Public Service mission model canvas: a public-sector DVF mapping: [CSPS](https://ecolecanada.gc.ca/tools/jobaids/pdfs/mission-canvas-eng.pdf)
- No Australian government DVF template was found. The closest are an OECD OPSI-listed Australian public sector innovation lab guide (DesignGov-based) and the Australian Government Discovery/Alpha/Beta/Live service design stages, which do not use DVF labels: [OECD OPSI Australia](https://oecd-opsi.org/toolkit-country-territory/australia/page/2); [AGA, Innovation and PoC](https://architecture.digital.gov.au/node/126)
- Blank's IRL was adapted per segment (e.g. medical devices) by a VC for a UCSF life-sciences cohort and used by an angel to screen applicants: [Blank 2014](https://steveblank.com/2014/07/01/how-investors-make-better-decisions-the-investment-readiness-level/) (via search summary)

### Inferences
- muru-D should treat the Strategyzer scorecard as the reference rubric and localise it: a Telstra strategic-fit gate, AU regulatory items, and opportunity anchors in AUD tied to the TAM/SAM/SOM outputs.
- For deep-tech or regulated ideas (health, telco infrastructure), add TRL and an IRL-style stage label so the verdict reflects maturity, not just attractiveness.

### Gaps
- No public scorecard from Telstra/muru-D, Bosch, Mastercard, Deutsche Telekom, Startmate, Cicada Innovations, or CSIRO ON. These may exist internally. Contact the programs directly.
- Bosch is often cited anecdotally as a Strategyzer client, but no source was found here confirming its scorecard use.
