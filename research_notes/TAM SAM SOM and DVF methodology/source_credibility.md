# Source Credibility Grading and Provenance for Market Research Figures

Scope: how an LLM market research agent (web search + page fetch only) should grade sources and numbers, record where every figure came from, combine conflicting figures, and state confidence. Current agent scheme for comparison: A primary/current, B reputable secondary with sources named, C unsourced or >2 years old, D forums/marketing/undated; citation = claim (Grade, publisher, date, URL).

## 1. Established grading frameworks and what to borrow

### Takeaway
The strongest idea to borrow is the Admiralty Code's two separate axes: grade the source (track record, competence) and the specific claim (corroboration, consistency) independently. The current A-D scheme folds source type, sourcing, and age into one letter. ICD 203 adds a mandatory "describe source quality" standard and a fixed likelihood vocabulary. IPCC adds evidence x agreement as the basis for confidence. GRADE adds "start high, downgrade for named reasons". SIFT and lateral reading supply the verification procedure.

### Cited Findings
**Admiralty Code / NATO system (AJP-2.1)**
- Two-part rating: a letter for source reliability plus a number for information credibility, e.g. "B2" = usually reliable source, information probably true ([Wikipedia: Admiralty code](https://en.wikipedia.org/wiki/Admiralty_code)).
- Source reliability: A Reliable ("No doubt about the source's authenticity, trustworthiness, or competency. History of complete reliability"), B Usually reliable ("Minor doubts. History of mostly valid information"), C Fairly reliable ("Doubts. Provided valid information in the past"), D Not usually reliable ("Significant doubts"), E Unreliable ("History of invalid information"), F Reliability unknown ("Insufficient information to evaluate reliability") ([Wikipedia: Intelligence source and information reliability](https://en.wikipedia.org/wiki/Intelligence_source_and_information_reliability)).
- Information credibility: 1 Confirmed by independent sources ("Logical, consistent with other relevant information, confirmed by independent sources"), 2 Probably true ("consistent with other relevant information, not confirmed"), 3 Possibly true ("agrees with some relevant information, not confirmed"), 4 Doubtfully true ("Not logical but possible, no other information on the subject"), 5 Improbable ("contradicted by other relevant information"), 6 Difficult to say ("validity of the information can not be determined") ([Wikipedia](https://en.wikipedia.org/wiki/Intelligence_source_and_information_reliability)).
- Worked examples: confirmed info from reliable source = A1; unknown info from new source = F6; inconsistent info from a known liar = E5 ([Wikipedia](https://en.wikipedia.org/wiki/Intelligence_source_and_information_reliability)).
- Each axis is assessed in isolation so source reliability does not drive the accuracy grade; a D or F source can still supply information later confirmed ([Wikipedia: Admiralty code](https://en.wikipedia.org/wiki/Admiralty_code); [Pangea Research](https://pangearesearch.substack.com/p/the-admiralty-code-nato-6x6-system)).
- Devised by John Godfrey at the British Naval Intelligence Division in WWII; matrix cited to US Army FM 2-22.3. The NATO doctrine text itself is not public ([Wikipedia](https://en.wikipedia.org/wiki/Intelligence_source_and_information_reliability); [Wikipedia: Admiralty code](https://en.wikipedia.org/wiki/Admiralty_code)).

**US ICD 203 Analytic Standards (signed 2 Jan 2015, technical amendment 21 Jan 2022)** ([ODNI ICD 203 PDF](https://archive.dni.gov/files/documents/ICD/ICD-203.pdf))
- Nine tradecraft standards: (1) describe quality and credibility of sources, data, methods; (2) express and explain uncertainty; (3) distinguish underlying information from assumptions and judgments; (4) analysis of alternatives; (5) customer relevance; (6) clear logical argumentation; (7) explain change to or consistency of judgments; (8) accurate judgments; (9) effective visuals.
- Standard 1 lists source-quality factors: "accuracy and completeness, possible denial and deception, age and continued currency of information, and technical elements of collection as well as source access, validation, motivation, possible bias, or expertise." Recommends a "source summary statement" giving a holistic view of the source base and "which sources are most important to key analytic judgments."
- Standard 2 separates likelihood (of an event) from confidence (in the basis for the judgment). Confidence rests on "the quantity and quality of source material, and their understanding of the topic." Products should name causes of uncertainty and "identify indicators that would alter the levels of uncertainty."
- Likelihood terms (pick one row, do not mix): almost no chance / remote 01-05%; very unlikely / highly improbable 05-20%; unlikely / improbable 20-45%; roughly even chance / roughly even odds 45-55%; likely / probable 55-80%; very likely / highly probable 80-95%; almost certain / nearly certain 95-99%.
- Rule: products "must not combine a confidence level and a degree of likelihood ... in the same sentence."
- Standard 3: state assumptions explicitly "when they serve as the linchpin of an argument or when they bridge key information gaps", and explain implications if they prove wrong.

**IPCC AR5 uncertainty guidance (Mastrandrea et al., 2010)** ([IPCC AR5 Guidance Note](https://www.ipcc.ch/site/assets/uploads/2017/08/AR5_Uncertainty_Guidance_Note.pdf); mirror used: [stat.berkeley.edu copy](https://www.stat.berkeley.edu/users/aldous/157/Papers/ipcc_uncertainty-guidance-note.pdf))
- Evaluate evidence ("limited", "medium", "robust": type, amount, quality, consistency) and agreement ("low", "medium", "high"). "Evidence is most robust when there are multiple, consistent independent lines of high-quality evidence."
- High agreement + robust evidence: give confidence or quantified uncertainty. Only one of the two: assign if possible, else state summary terms (e.g. "robust evidence, medium agreement"). Low agreement + limited evidence: summary terms only.
- Confidence uses five qualifiers: very low, low, medium, high, very high. "Confidence should not be interpreted probabilistically."
- Likelihood scale: virtually certain 99-100%, very likely 90-100%, likely 66-100%, about as likely as not 33-66%, unlikely 0-33%, very unlikely 0-10%, exceptionally unlikely 0-1%; optional extremely likely 95-100%, more likely than not >50-100%, extremely unlikely 0-5%. Boundaries are "fuzzy".
- "About as likely as not" should not be used to express lack of knowledge.
- Requires a "traceable account": description of "the type, amount, quality, and consistency of evidence and the degree of agreement", including "approaches to combining or reconciling multiple lines of evidence, conditional assumptions."
- Warns that estimates "can also become anchored on previous versions or values to a greater extent than is justified" and that experts underestimate structural uncertainty (competing conceptual frameworks).
- Survey of IPCC authors: interpretations only partly matched the defined intervals, and were wider under "medium" than "high" confidence ([USC summary of survey](https://sustainabilitysolutions.usc.edu/research_papers/confidence-levels-and-likelihood-terms-in-ipcc-reports-a-survey-of-experts-from-different-scientific-disciplines/)).

**GRADE (medicine)**
- Body of evidence starts at high certainty and is downgraded to moderate, low, or very low for concerns in five domains: risk of bias, inconsistency, indirectness, imprecision, publication bias ([PubMed: GRADE guidelines 19](https://pubmed.ncbi.nlm.nih.gov/29452223/); [Cochrane Handbook ch. 14](https://www.cochrane.org/zh-hant/authors/handbooks-and-manuals/handbook/current/chapter-14)).
- Indirectness = how closely population, intervention, comparison, outcome match the review question ([PubMed](https://pubmed.ncbi.nlm.nih.gov/29452223/)). Imprecision = width of the interval and whether it crosses a decision threshold ([MetricGate, commercial site](https://metricgate.com/docs/grade-evidence-quality/)).
- Non-randomised evidence can be upgraded on three further domains ([Cochrane Handbook ch. 14](https://www.cochrane.org/zh-hant/authors/handbooks-and-manuals/handbook/current/chapter-14)).

**CRAAP test**
- Currency, Relevance, Authority, Accuracy, Purpose; created by Sarah Blakeslee, CSU Chico Meriam Library, 2004 ([LAPC library guide](https://library.lapc.edu/evaluating-online-sources/craap-test); [OCO Learn](https://open.ocolearnok.org/ecokinformationliteracy/chapter/craap-test)).
- Purpose asks whether material aims to "inform, teach, sell, entertain, or persuade" ([ETBI library guide](https://library.etbi.ie/sources2/craap)).

**SIFT (Mike Caulfield) and lateral reading**
- SIFT: Stop; Investigate the source (expertise and agenda); Find better coverage; Trace claims, quotes, and media to original context. Spend only enough time on each move ([Writing Commons](https://writingcommons.org/section/information-literacy/information-evaluation/sift-stop-investigate-source-find-better-coverage-trace-claims/); [SFU Library](https://www.lib.sfu.ca/node/38957)).
- Wineburg and McGrew (2017): 10 professional fact checkers outperformed 10 PhD historians and 25 Stanford undergraduates at judging credibility. Checkers left the page to read what other sites said about it ("lateral reading"), practised click restraint, and reached "more warranted conclusions in a fraction of the time." Historians and students were misled by logos and domain names ([Stanford Daily](https://stanforddaily.com/2017/10/26/fact-checkers-more-likely-than-peer-expert-groups-to-identify-credible-information-determine-gse-researchers/); [Stanford PURL](https://purl.stanford.edu/yk133ht8603)).

### Inferences
- The current A-D scheme mixes three things in one letter: source type (A/B), sourcing transparency (B vs C), and staleness (C). A report-mill figure that names no inputs and a 3-year-old ABS census figure both land on C, though the census figure is far more trustworthy. Split into: Source grade (who), Claim grade (is this specific number corroborated), and an explicit data-as-of year.
- Suggested adaptation for the agent, keeping the Admiralty shape:
  - Source S-A: official statistics or audited primary (ABS, ATO, ASIC/ASX filings, regulator data, census, company annual reports). S-B: analyst firm or trade body with disclosed method and named inputs. S-C: large-catalogue report publisher or journalism re-quoting a report; method not disclosed. S-D: press-release wires, LinkedIn/Medium posts, vendor marketing, forums, AI-generated SEO pages. S-F: cannot judge.
  - Claim C-1: matched by an independent source (different owner, different method) within normalised scope. C-2: consistent with related data, unconfirmed. C-3: partially consistent. C-4: no other data available. C-5: contradicted by a primary anchor (e.g. exceeds census receipts by >2x for the same scope). C-6: cannot judge.
  - Example: "S-C/C-5" flags a report-mill number contradicted by census data; "S-A/C-6" is a primary figure for a market no-one else measures.
- From GRADE, borrow named downgrade reasons for each number: indirectness (global figure used for Australia, adjacent category, wrong year), inconsistency (spread across sources), imprecision (range crosses the go/no-go threshold), bias (vendor selling the market). Logging the reason is more useful to a reviewer than the letter.
- From ICD 203 Standard 3, tag every sentence in the output as either sourced fact, assumption, or judgment.
- SIFT "Trace" and lateral reading are the operational core for an agent: for each number, search the exact figure in quotes, find the originating report page, and search the publisher's name plus "methodology" or "criticism" before grading.
- A Bayesian framing (treat each source as evidence with a likelihood ratio given its track record) was in scope but not researched; the Admiralty two-axis grades and IPCC evidence x agreement give a practical qualitative stand-in.

### Gaps
- The NATO AJP-2.1 text is not public; descriptor wording above comes from FM 2-22.3 via Wikipedia.
- No scholarly critique of CRAAP was retrieved (one source only says it "was also criticized" without detail). Caulfield has argued checklist approaches are weaker than lateral reading, but this was not fetched in this session.
- No source found on Bayesian or likelihood-ratio source weighting applied to market sizing.
- GRADE Working Group primary pages (gradeworkinggroup.org) were not fetched; details come from Cochrane Handbook and PubMed abstract.

## 2. Market research "report mills": divergence, detection, treatment

### Takeaway
Large-catalogue publishers routinely disagree by 2-3x on the same market, mainly because of undisclosed scope, base year, and geography differences, and sometimes contradict themselves across their own pages. Treat their figures as low-grade, deduplicate syndicated copies and co-owned firms, normalise scope before comparing, and test against a primary anchor (census, filings, trade-body data). Use them as bounds or a cross-check, not as the headline.

### Cited Findings
**How far apart they are**
- Global pet grooming services, 2025, eight publishers: $3.6B (Fact.MR, services only) to $8.44B (The Business Research Company, includes product sales), 2.3x spread; forecast CAGRs agreed closely at 6.7-8.2%. Mordor and Straits gave $2.19B vs $1.12B for the US; Mordor showed two different 2026 US values on one page ($2.34B and $2.24B) ([Hyperresearch, J. Gibbs, updated 2026-09-24](https://hyperresearch.ai/guides/why-market-size-reports-disagree)). Note: Hyperresearch sells AI research tooling.
- Global digital health 2025: MarketsandMarkets $199.14bn, Global Market Insights $387.8bn, Fortune Business Insights $427.24bn, IMARC $573.3bn; high is almost 3x low ([Sectorial, updated 2026-10-06](https://sectorial.io/resources/blog/market-research-providers-compared)). Note: Sectorial sells competing market intelligence.
- Same-publisher contradictions: Mordor Intelligence, two UK reports with near-identical titles, $15.46bn vs $42.93bn for 2025; Precedence Research, two health insurance reports, $2.50bn vs $2.69 trillion; Global Market Insights press release giving $380 billion where its report page gives $161 million for 2022 (Sectorial's own text and source note disagree on the exact pairing) ([Sectorial](https://sectorial.io/resources/blog/market-research-providers-compared)).
- Self-storage: a vendor headline of $45.34B was 2.2x the 2022 Economic Census receipts ($20.62B, 18,465 establishments); IMARC gave $30.6B; Public Storage same-store revenue was flat 2023-2025 ($3,786.3M, $3,763.6M, $3,764.8M) while the vendor implied 4.3% growth ([Hyperresearch](https://hyperresearch.ai/guides/how-to-check-a-market-research-report)).
- Also: "trillion-dollar space economy by 2040" described as a zombie statistic tracing to one origin ([Ill-Defined Space, Substack](https://illdefinedspace.substack.com/p/space-zombie-statistics-the-industry)).

**Tiering of publishers (vendor opinion)**
- Tier 1 "Institutionally Validated": IBISWorld, Euromonitor, Mintel, MarketLine, Frost & Sullivan. Tier 2 "Large Catalogues, Mixed Credibility": Grand View Research, MarketsandMarkets, Mordor Intelligence, Global Market Insights, Allied Market Research, Fortune Business Insights, Precedence Research; none shows interview counts or sources behind its market size. Research and Markets is a reseller, so dependent on whoever wrote the report ([Sectorial](https://sectorial.io/resources/blog/market-research-providers-compared)).
- Non-independence: Mordor Intelligence owns a majority of Global Market Insights, so their figures are not independent checks ([Sectorial](https://sectorial.io/resources/blog/market-research-providers-compared)).

**Detection signals**
- Identical methodology text across many reports (Grand View on three, Fortune Business Insights on at least eight); no interview count or size source; unnamed team or stale "last updated" date (a Grand View UK report last updated March 2023); definitions or segments that change between sections or don't belong; identical growth rates across unrelated categories; currency or CAGR inconsistencies on one page; "infallible" methodology claims paired with no-accuracy-warranty disclaimers (Allied Market Research) ([Sectorial](https://sectorial.io/resources/blog/market-research-providers-compared)).
- Checks: free page should state definition, base year, forecast, CAGR, segments, method ("If the free page has no definition or method, the paid report rarely adds one"); pin base year and revenue scope; recompute CAGR (start x (1+CAGR)^years should equal forecast) and compare with incumbents' organic growth; reconcile with Census/BLS/public-company revenue as bounds; check implied revenue per unit (e.g. $/sq ft vs a listed operator); search the exact number in quotes; check who relies on it (filings and lender memos vs blogs) ([Hyperresearch](https://hyperresearch.ai/guides/how-to-check-a-market-research-report)).
- Narrative errors are a signal: the self-storage page dated the Extra Space / Life Storage merger to July 2024, while SEC filings show deregistration on 31 July 2023 ([Hyperresearch](https://hyperresearch.ai/guides/how-to-check-a-market-research-report)).
- Primary anchor example: US Census 2022 receipts for NAICS 812910 (Pet Care, except Veterinary) $10.11B across 24,655 establishments; excludes non-employer businesses, so it is a floor for its own scope ([Hyperresearch](https://hyperresearch.ai/guides/why-market-size-reports-disagree)).

**Circular citation, stale and re-dated numbers**
- "Syndicated copies are one source"; if a firm's press releases show different values for the same market "without a new edition date", ask which value the paid report uses ([Hyperresearch](https://hyperresearch.ai/guides/how-to-check-a-market-research-report)).
- Circular sourcing: "Blog cites blog, which cites blog, which eventually cites the first blog. The paper trail forms a circle and points directly at nothing" ([Layerproof](https://layerproof.app/blog/zombie-stats-presentations/)). Zombie statistic = a misleading figure "that keeps getting repeated no matter how often it has been refuted" ([Word Spy](https://wordspy.com/words/zombie-statistic)).
- Press-release wires get releases copied onto aggregator sites without editorial vetting ([ContentGrip](https://www.contentgrip.com/free-pr-distribution-services-tools/)).

**Spend vs revenue, scope confusion**
- Scope differences drive divergence: whether product sales count (Fact.MR excludes, Business Research Company includes), which animals and channels count, base years 2023-2026, one figure US-only ([Hyperresearch](https://hyperresearch.ai/guides/why-market-size-reports-disagree)).
- Gartner's IT spending forecast is built from analysis of sales by "over a thousand vendors" plus primary research, spans hardware, software, IT services, telecom; the enterprise forecast excludes consumer spending; 2026 headline $6.08 trillion, +9.8% ([Gartner press release, 22 Oct 2025](https://www.gartner.com/en/newsroom/press-releases/2025-10-22-gartner-forecasts-worldwide-it-spending-to-grow-9-point-8-percent-in-2026-exceeding-6-trillion-dollars-for-the-first-time)).

### Inferences
- Default grade for openPR, GlobeNewswire, EIN Presswire, LinkedIn Pulse copies of report-mill figures: S-D for the wire copy; trace to the publisher's own report page and grade that S-C. Never let the wire copy count as corroboration.
- Independence groups: before counting two sources as agreeing, check (a) same originating report, (b) common ownership (Mordor/GMI), (c) reseller relationship (Research and Markets). Record an `independence_group` per figure.
- Treatment rule: report-mill figures can set the plausible range and be cited as "published estimates range X to Y", but the headline TAM should come from a bottom-up build or a primary anchor where one exists. If a mill number exceeds the nearest primary anchor for the same scope by >2x, grade the claim C-5 and exclude it from any average.
- Staleness rule: record both `data_year` (the year the number measures) and `published_date`. Flag "re-dated" when a newer page carries an identical figure and CAGR to an older edition, or when the base year is older than the publication year by more than 2 years.
- Spend vs revenue: "spending" figures count buyer outlay (can include channel margin, taxes, multiple layers), while "revenue" or "market size" may mean vendor revenue at one layer. Gross merchandise value, transaction value, and revenue are often conflated. The agent should record `metric_type` and refuse to compare across types without conversion. (This is an inference; no source fetched defines Gartner's end-user spending vs vendor revenue basis.)
- Australian anchors to prefer for the muru-D agent: ABS (e.g. Australian Industry, Counts of Australian Businesses), ATO taxation statistics, IBISWorld Australia, ASX filings of listed incumbents. (Inference; not fetched in this session.)

### Gaps
- No independent journalism or academic study quantifying report-mill divergence across many markets was found. The two main sources (Hyperresearch, Sectorial) are 2026 commercial vendors with an interest in discrediting syndicated reports; their specific numbers are unverified.
- No source found that names openPR, EIN Presswire, or GlobeNewswire specifically as vectors for unreliable market figures.
- Could not confirm Gartner's exact definition of end-user spending vs vendor revenue (needs Gartner glossary or Market Databook).
- No systematic study of LLMs repeating report-mill numbers; only an unverifiable LinkedIn post.

## 3. Provenance recording

### Takeaway
Record provenance per number, not per document: the value with unit, scope and data year; the URL plus an archived snapshot; a verbatim excerpt; both grades; and, for derived numbers, the input IDs, the formula, and the assumptions. W3C PROV's Entity / Activity / Agent model maps directly onto "figure / calculation / publisher", and Cochrane-style evidence tables give the per-source row layout.

### Cited Findings
- W3C PROV-O core classes: Entity, Activity, Agent ([W3C IPAW 2012 slides](https://www.w3.org/2011/prov/wiki/images/archive/4/43/20120619203549%212012-06-ipaw-provo.ppt.pdf)). Relations: wasGeneratedBy (entity produced by activity), used (activity consumed entity), wasDerivedFrom (entity came from entity), wasAttributedTo / wasAssociatedWith (link to agents) ([CASRAI glossary](https://www.casrai.org/dictionary/term/prov-o)).
- Provenance between entities can be stated directly with wasDerivedFrom without naming the activity ([W3C PROV repo commit](https://dvcs.w3.org/hg/prov/rev/daf8d2a42852)). Derivation = "a transformation of an entity into another, an update ... or the construction of a new entity based on a pre-existing entity" ([HL7 FHIR mirror of W3C vocabulary](https://www.hl7.org/fhir/R4/codesystem-w3c-provenance-activity-type.json.html)).
- Qualified relations (e.g. prov:Usage) carry extra attributes such as time, location, role ([W3C blog](https://www.w3.org/blog/2012/the-prov-ontology-an-update)).
- Cochrane "Characteristics of included studies" tables use five standard entries per study (Methods, Participants, Interventions, Outcomes, Notes) plus up to three extra fields such as funding source ([Cochrane Handbook v5.1, 4.6.1](https://training-noproxy.cochrane.org/handbook/archive/v5.1/chapter_4/4_6_1_characteristics_of_included_studies.htm)); risk-of-bias judgements sit in a separate table ([Murray State guide](https://lib.murraystate.edu/systematicreviews/data)).
- Summary of Findings tables: one row per important outcome, max seven, each with a GRADE certainty rating ([Cochrane Handbook ch. 14](https://www.cochrane.org/zh-hant/authors/handbooks-and-manuals/handbook/current/chapter-14)).
- ICD 203 Standard 1 asks for source descriptors and a "source summary statement" stating "which sources are most important to key analytic judgments" ([ICD 203](https://archive.dni.gov/files/documents/ICD/ICD-203.pdf)). IPCC requires a "traceable account" per key finding ([IPCC AR5 note](https://www.ipcc.ch/site/assets/uploads/2017/08/AR5_Uncertainty_Guidance_Note.pdf)).

**Archiving (agent-usable)**
- Availability API: `https://archive.org/wayback/available?url=<url>[&timestamp=YYYYMMDDhhmmss]`, no auth, returns `archived_snapshots.closest` with `available`, `url`, `timestamp`, `status`, or `{"archived_snapshots":{}}` if none ([Internet Archive Wayback API](https://archive.org/help/wayback_api.php)).
- An October 2026 test found the availability API returned empty results for pages that CDX did list; use CDX as fallback ([DataImpulse](https://dataimpulse.com/blog/wayback-machine-api/)).
- Save Page Now 2 (`web.archive.org/save`) requires authentication (S3 keys via `authorization: LOW key:secret`) and is a two-step capture + status flow ([SPN2 API doc, Google Doc](https://docs.google.com/document/d/1Nsv52MvSjbLb2PCpHlat0gkzw0EvtSgpKHu4mk0MnrA/mobilebasic)); waybackpy notes it is "very unreliable" ([waybackpy source](https://codeclimate.com/github/akamhy/waybackpy/waybackpy/save_api.py/source)); some URLs are on a block list ([ArchiveTeam wiki](https://wiki.archiveteam.org/index.php/Internet_Archive/Save_Page_Now)).
- Archived URL form: `web.archive.org/web/<timestamp>/<url>` ([waybackpy on PyPI](https://pypi.org/project/waybackpy/3.0.0)).

### Inferences
- Proposed per-figure record (one row per number, JSON or table):
  - `id`, `value`, `unit`, `currency`, `metric_type` (revenue | spend | GMV | units | users | establishments), `geography`, `data_year`, `scope_definition` (verbatim from source where possible)
  - `quote` (verbatim excerpt containing the number, short), `source_url`, `archive_url` (or "none found"), `retrieved_at`
  - `publisher`, `author`, `published_date`, `origin_url` (where the trace ended), `trace_chain` (list of hops: wire copy -> report page -> stated input), `independence_group`
  - `source_grade` (S-A..S-F), `claim_grade` (C-1..C-6), `downgrade_reasons` (indirectness, staleness, inconsistency, no method, vendor bias)
- Derived numbers get their own record with `inputs` (list of ids), `formula` (e.g. `n_firms * adoption_rate * acv`), `assumptions` (each with its own id and rationale), `output_low/base/high`. This mirrors PROV: output Entity wasGeneratedBy a calculation Activity that used input Entities.
- From prior knowledge of the PROV-O spec (w3.org/TR/prov-o/, not fetched this session), PROV-O also has `prov:wasQuotedFrom`, `prov:hadPrimarySource`, and `prov:wasRevisionOf`; these map neatly to `quote`, `origin_url`, and re-dated editions. Verify before relying on exact names.
- Inline citation format suggestion, upgrading the current "(Grade, publisher, date, URL)": `A$1.2B (2024 revenue, AU, S-B/C-2, IBISWorld, pub 2025-03, [link], [archive])`, with the quote and chain kept in an evidence table appendix. The `data_year` vs `published_date` split is the key addition.
- Agent cost control: try the availability API first (no auth); record "no archive" rather than block on SPN2. The quote field is the cheapest verifiability win, since reviewers can Ctrl-F the excerpt on the live page.

### Gaps
- The W3C PROV-O Recommendation and PROV-DM pages were not fetched directly; relation definitions come from W3C slides, a W3C commit, CASRAI, and HL7.
- Cochrane Handbook Chapter 5 (data collection forms, dual independent extraction) was not retrieved.
- No source found on claim-level citation schemas specific to market research or LLM agents (e.g. formal "evidence table" standards for TAM work).

## 4. Combining multiple sources for one number

### Takeaway
Normalise first (same metric type, scope, geography, year, currency), collapse non-independent sources, drop figures contradicted by primary anchors, then combine. With several genuinely independent, comparable estimates, an equal-weight mean (trimmed mean at five or more) is a defensible default; otherwise report the range and lean on the most credible primary anchor. Always show the spread.

### Cited Findings
- Combining forecasts: equal weights are "a reasonable starting point, and a trimmed mean is desirable if you combine forecasts resulting from five or more methods"; use different weights only with good domain knowledge of which method is most accurate. Across 30 comparisons, equal-weight combinations cut ex ante error by about 12.5% on average (range 3-24%) ([Armstrong, Combining Forecasts, 2001](https://repository.upenn.edu/marketing_papers/34); [Wharton PDF](https://marketing.wharton.upenn.edu/wp-content/uploads/2020/07/96-JSA-Combining-Forecasts.pdf)).
- "Combining forecasts is most valuable when the individual forecasts are diverse in the methods used and the theories and data upon which they are based" ([SAS blog quoting Armstrong](https://blogs.sas.com/content/forecasting/2014/02/14/the-miracle-of-combining-forecasts)).
- Equal weighting "often outperforms more complex approaches which aim to estimate 'optimal' weights" ([PollyVote, Wharton](https://faculty.wharton.upenn.edu/wp-content/uploads/2016/10/the-pollyvote-forecast-for-the-2016-american-presidential-election_4.pdf)).
- IPCC: robust evidence = "multiple, consistent independent lines of high-quality evidence"; traceable account should include "approaches to combining or reconciling multiple lines of evidence" ([IPCC AR5 note](https://www.ipcc.ch/site/assets/uploads/2017/08/AR5_Uncertainty_Guidance_Note.pdf)).
- IPCC on ranges: when a range can be given, explain "the basis for the range given, noting factors that determine the outer bounds", state assumptions, and estimate structural uncertainty; when only an order of magnitude is known, say so and give confidence ([IPCC AR5 note](https://www.ipcc.ch/site/assets/uploads/2017/08/AR5_Uncertainty_Guidance_Note.pdf)).
- ICD 203 Standard 7: "Significant differences in analytic judgment ... should be fully considered and brought to the attention of customers" ([ICD 203](https://archive.dni.gov/files/documents/ICD/ICD-203.pdf)).
- Market example of why normalisation matters: CAGRs agreed (6.7-8.2%) while levels spread 2.3x, driven by scope ([Hyperresearch](https://hyperresearch.ai/guides/why-market-size-reports-disagree)). Census figures exclude non-employers, so they act as a floor for their scope ([Hyperresearch](https://hyperresearch.ai/guides/how-to-check-a-market-research-report)).
- GRADE inconsistency (unexplained heterogeneity) and imprecision (interval crossing a decision threshold) are explicit downgrade reasons ([Cochrane Handbook ch. 14](https://www.cochrane.org/zh-hant/authors/handbooks-and-manuals/handbook/current/chapter-14); [MetricGate](https://metricgate.com/docs/grade-evidence-quality/)).

### Inferences
- Triangulation procedure for the agent:
  1. Normalise each figure to the target metric_type, geography, year (roll forward/back with its own stated CAGR, logged as a derivation), currency (record FX rate and date).
  2. Collapse by independence_group; keep the earliest/originating figure.
  3. Discard or flag figures that breach a primary anchor (C-5).
  4. If 2+ independent comparable figures remain: report min, max, median; if 5+, also a trimmed mean. Weight by grade only if a clear quality gap exists (e.g. one S-A census-derived number vs S-C mills: use the S-A number as base, mills as context).
  5. Report spread ratio max/min. Heuristic: under 1.5x reasonably consistent; 1.5-3x substantial disagreement, explain by scope; over 3x treat as definitions not matching, do not combine.
  6. Prefer an agent-built bottom-up estimate (count x price) cross-checked against top-down figures; disagreement between the two is itself a finding to report.
- Uncertainty propagation for multiplicative TAM builds: carry low/base/high for each input. Multiplying all lows and all highs gives a conservative outer bound that over-widens; for more realistic ranges, the agent can state it took the product of bounds and call it an outer bound. (Monte Carlo is out of reach for a search-only agent unless it has code execution.)
- Never average across mismatched metric types (spend vs revenue vs GMV) or across a global and a national figure.

### Gaps
- No source found giving market-research-specific triangulation rules or spread thresholds; the 1.5x/3x thresholds above are a heuristic, not sourced.
- No source fetched on log-scale (geometric mean) averaging of market sizes, though order-of-magnitude spreads suggest it.

## 5. Communicating confidence in a final estimate

### Takeaway
Give a range with a base case, state confidence separately from likelihood, use a fixed vocabulary with numbers attached, explain what drives the uncertainty and what would change it, and say "unknown" or "insufficient evidence" plainly rather than using a mid-probability word.

### Cited Findings
- ICD 203: express likelihood with one fixed row of terms with percentage bands (remote 1-5% ... almost certain 95-99%); keep confidence ("high confidence") out of the same sentence as likelihood; explain causes of uncertainty and indicators that would change it ([ICD 203](https://archive.dni.gov/files/documents/ICD/ICD-203.pdf)).
- ICD 203 Standard 6: "present a clear main analytic message up front"; Standard 8: do not "avoid difficult judgments in order to minimize the risk of being wrong" ([ICD 203](https://archive.dni.gov/files/documents/ICD/ICD-203.pdf)).
- IPCC: confidence (very low to very high) is not a probability; when information allows, "it is preferable to specify the full probability distribution or a probability range (e.g., 90-95%) without using the terms"; "About as likely as not" must not express lack of knowledge; readers adjust interpretation by perceived consequences ([IPCC AR5 note](https://www.ipcc.ch/site/assets/uploads/2017/08/AR5_Uncertainty_Guidance_Note.pdf)).
- IPCC: present low or very low confidence findings only for areas of major concern, with reasons explained ([IPCC AR5 note](https://www.ipcc.ch/site/assets/uploads/2017/08/AR5_Uncertainty_Guidance_Note.pdf)).
- Verbal probabilities are more ambiguous than numbers. In a 924-participant study, correspondence with the ICD 203 bands rose to 66% (vs 32% control) only when numeric ranges were bracketed in the text ([PMC6469752, "Verbal probabilities: Very likely to be somewhat more confusing than numbers"](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6469752/)).
- IPCC author survey: even experts read the terms inconsistently, wider under "medium" confidence ([USC summary](https://sustainabilitysolutions.usc.edu/research_papers/confidence-levels-and-likelihood-terms-in-ipcc-reports-a-survey-of-experts-from-different-scientific-disciplines/)).

### Inferences
- Recommended output pattern per key figure: "Australian SMB payroll software TAM: A$X-Y M (base A$Z M, 2025 revenue). Confidence: medium (two independent sources agree within 1.4x; bottom-up build depends on an assumed adoption rate). Would change if: ABS business counts by size band differ from assumption."
- Always bracket numbers after verbal terms: "likely (55-80%)". Pick one vocabulary (ICD 203 suits business decisions; IPCC's "likely" = 66-100% conflicts with ICD's 55-80%, so do not mix them).
- Map evidence x agreement to confidence, IPCC style: robust evidence + high agreement = high; one weak = medium; both weak = low; no usable evidence = "unknown: insufficient evidence", with no number, or a wide order-of-magnitude bound labelled as such.
- Add an ICD-style source summary line per report: which 1-3 sources drive the headline, their grades, and the biggest weakness in the source base.
- For muru-D decision makers, the useful question is whether the range crosses the decision threshold (GRADE imprecision idea): if the whole range clears the "venture-scale" bar, low precision does not matter; if it straddles it, say so explicitly.

### Gaps
- No source fetched on how investors or accelerator committees specifically prefer confidence to be shown (ranges vs scenarios vs probabilities).
- ICD 206 (sourcing requirements, source descriptors) was referenced by ICD 203 but not fetched.

Agent operational notes from this session: dni.gov / odni.gov ICD PDFs redirect to archive.dni.gov; ipcc.ch PDFs returned HTTP 403 to the fetch tool (mirror at stat.berkeley.edu worked); fetched PDFs may come back as binary and need text extraction.
