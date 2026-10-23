# Australian Market-Sizing Data Sources for an LLM Research Agent (Brave search + page fetch)

Research date: 2026-10-23. Items marked "verified" were fetched or seen in search results this session. Items marked "unverified" come from prior knowledge and need a check before being hard-coded into the agent.

## Official statistics: ABS and other federal/state sources

### Takeaway
ABS is the backbone: Counts of Australian Businesses (8165) gives buyer counts by industry and size, refreshed August 2026, as a plain XLSX the agent can fetch. The ABS Data API (SDMX) needs no key and returns CSV/JSON. The Household Expenditure Survey is stale (2015-16) with no scheduled successor, so household spend has to come from other ABS series or commercial sources.

### Cited Findings
**ABS Counts of Australian Businesses, incl. Entries and Exits (cat. 8165, "CABEE")**
- Latest release 18 Aug 2026, reference period Jul 2022 to Jun 2026. Next release 18 Dec 2026 ([ABS 8165 latest](https://www.abs.gov.au/statistics/economy/business-indicators/counts-australian-businesses-including-entries-and-exits/latest-release)).
- At 30 June 2026: 2,814,778 actively trading businesses, of which 996,203 were employing (about 35%). Non-employing is about 1.82m by subtraction ([ABS 8165](https://www.abs.gov.au/statistics/economy/business-indicators/counts-australian-businesses-including-entries-and-exits/latest-release)).
- 2025-26: net +85,130 (3.1%), entries 460,461 (16.9%), exits 375,331 (13.8%). Non-employing +4.8%, employing +0.2% (first net rise since 2021-22). 28,127 survivors moved from employing to non-employing ([ABS 8165](https://www.abs.gov.au/statistics/economy/business-indicators/counts-australian-businesses-including-entries-and-exits/latest-release)).
- Direct XLSX: `https://www.abs.gov.au/statistics/economy/business-indicators/counts-australian-businesses-including-entries-and-exits/jul2022-jun2026/8165DC01.xlsx` (Tables 1-16, August). Tables 17-20 and data cubes 2-11 come out in December ([ABS 8165](https://www.abs.gov.au/statistics/economy/business-indicators/counts-australian-businesses-including-entries-and-exits/latest-release)).
- Scope: actively trading businesses in the market sector. Excludes RBA, general government and non-profit institutions serving households. Source is the ABS Business Register (ABR + ATO data). The count "differs from the total number of entities with an ABN" ([ABS 8165](https://www.abs.gov.au/statistics/economy/business-indicators/counts-australian-businesses-including-entries-and-exits/latest-release); [methodology](https://www.abs.gov.au/methodologies/counts-australian-businesses-including-entries-and-exits-methodology/jul2022-jun2026)).

**ABS Data API (SDMX)**
- Base URL `https://data.api.abs.gov.au/rest/`, GET only. The old host `api.data.abs.gov.au` was replaced in the 29 Nov 2024 update ([ABS Data API user guide](https://www.abs.gov.au/about/data-services/application-programming-interfaces-apis/data-api-user-guide)).
- No API key: "freely accessible without the need for an API key" ([ABS Data API user guide](https://www.abs.gov.au/about/data-services/application-programming-interfaces-apis/data-api-user-guide)).
- Formats: XML (default), `format=jsondata`, `format=csv`, `format=structurespecificdata`. Query pattern `/rest/data/{dataflow}/{datakey}?startPeriod=...`. Example in the guide: `.../rest/data/jv/all?startPeriod=2020&format=jsondata` (the guide has a typo, `data.api..abs`). No published rate limit ([ABS Data API user guide](https://www.abs.gov.au/about/data-services/application-programming-interfaces-apis/data-api-user-guide)). OpenAPI spec: [api.gov.au](https://api.gov.au/assets/APIs/abs/DataAPI.openapi.html).
- Verified: `https://data.api.abs.gov.au/rest/dataflow/ABS?detail=allstubs` returns the dataflow list, but the response is about 790k characters, so a fetch tool sees only the first chunk. Visible IDs include `ABORIGINAL_POP_PROJ` and the 2016 Census `ABS_C16_*` tables ([ABS dataflow list](https://data.api.abs.gov.au/rest/dataflow/ABS?detail=allstubs)).

**ABS Characteristics of Australian Business (8167, technology use)**
- 2024-25 edition released 25 June 2026. First release on a redesigned biennial framework that merges the innovation and digital activity modules ([ABS 8167 2024-25](https://www.abs.gov.au/statistics/industry/technology-and-innovation/characteristics-australian-business/2024-25)).
- 12% of businesses used AI (1% in 2022-23). 32% received orders online. 59% reported supply chain disruption. Search snippet suggests about 21% had a cyber incident; not confirmed on the page ([ABS 8167 2024-25](https://www.abs.gov.au/statistics/industry/technology-and-innovation/characteristics-australian-business/2024-25)). 2021-22: 22% cyber incident, 70% had preventive measures ([ABS 8167 2021-22](https://abs.gov.au/statistics/industry/technology-and-innovation/characteristics-australian-business/2021-22)).

**ABS Household Expenditure Survey (6530)**
- Latest published results cover 2015-16. The 2026-27 forward work program change notice (31 Aug 2026) lists the HES summary as "not currently scheduled", timing to be confirmed ([ABS forward work program changes 2026-27](https://www.abs.gov.au/about/our-organisation/corporate-reporting/abs-corporate-plan/2026-27/changes-forward-work-program); [ABS 6530](https://www.abs.gov.au/AUSSTATS/abs@.nsf/MF/6530.0)).
- The 2023-24 Survey of Income and Housing was reportedly not released because of collection problems ([MacroBusiness, Aug 2025](https://www.macrobusiness.com.au/2025/08/australias-economic-statistics-fly-blind)). Secondary source.
- The ABS Monthly Household Spending Indicator exists as a current alternative ([ABS MHSI methodology](https://www.abs.gov.au/methodologies/monthly-household-spending-indicator-methodology)).

**ABS Australian Industry (8155)**
- Annual income, expenses, profit and capex by industry, released within 11 months of financial year end. ABS consulted (May to Nov 2024) on dropping some mining detail and the industry value-added tables ([ABS consultation](https://consult.abs.gov.au/industry-statistics/australian-industry-publication-changes)). 2024-25 release date not confirmed this session.

**Census / TableBuilder**
- Registering with an organisation email gives free Census TableBuilder Basic; organisation members also get TableBuilder Pro free ([ABS TableBuilder](https://www.abs.gov.au/statistics/microdata-tablebuilder/tablebuilder)). TableBuilder needs a login, so it is out of reach for a fetch-only agent.
- QuickStats, Community Profiles and DataPacks are free web products ([ABS Census page, older](https://www.abs.gov.au/websitedbs/censushome.nsf/home/tablebuilder)). A "Guest" TableBuilder tier was described in older ABS material; current status unconfirmed ([ABS TableBuilder overview PDF](https://www.abs.gov.au/ausstats/abs@.nsf/6630eff525d4cdc1ca25763e0075754f/430a8c5f1214d173ca2581440078919a/$FILE/ATTC516L.pdf/TableBuilder%20Overview.pdf)).

**ATO Taxation Statistics**
- 2023-24 edition published 17 June 2026. Company tables (Table 11 income items, Table 12 expenses) compare 2022-23 and 2023-24 ([ATO company stats 2023-24](https://www.ato.gov.au/about-ato/research-and-statistics/in-detail/taxation-statistics/taxation-statistics-2023-24/statistics-in-taxation-statistics-2023-24/company-statistics-for-taxation-statistics-2023-24)).
- Full datasets are Excel files on data.gov.au, linked under each ATO table. Detailed tables are generally revised for the previous 2 years ([ATO navigating taxstats](https://www.ato.gov.au/about-ato/research-and-statistics/in-detail/taxation-statistics/taxation-statistics-2023-24/navigating-taxation-statistics-2023-24)).
- Companies paid 22.7% ($144.6bn) of total tax collections in 2023-24 ([ATO media release](https://www.ato.gov.au/media-centre/2023-24-taxation-statistics-released)).

**ACMA Communications and Media in Australia**
- Series pages: [acma.gov.au/communications-and-media-australia](https://www.acma.gov.au/communications-and-media-australia). Recent: "How we use the internet" (Feb 2026), "How we communicate" (Feb 2026, nine-year trend), "How we watch and listen to content" (Mar 2026), "Trends and developments in telecommunications 2024-25" (Feb 2026), "Trends and developments in viewing and listening 2024-25" (Mar 2026, PDF, consumer surveys 2017 to 2025, adults 18+) ([ACMA how we communicate](https://www.acma.gov.au/publications/2026-02/report/communications-and-media-australia-how-we-communicate); [ACMA viewing PDF](https://www.acma.gov.au/sites/default/files/2026-03/Trends%20and%20developments%20in%20viewing%20and%20listening%202024-25.pdf)).
- News Media in Australia 2025 (biennial): 2,864 professional news outlets across nine platforms in 2024 ([TV Blackbox](https://tvblackbox.com.au/page/2025/03/29/acma-launches-first-report-under-new-media-diversity-framework/)). Secondary source.
- ACMA and eSafety share an annual report ([ACMA and eSafety annual report 2024-25](https://www.acma.gov.au/sites/default/files/2025-10/ACMA%20and%20eSafety%20annual%20report%202024-25.pdf)).

### Inferences
- For B2B buyer counts the agent should default to 8165 employing businesses by ANZSIC division and employment-size band, not total businesses. About 65% of the 2.8m are non-employing (sole traders, holding entities, trusts), which inflates any "SMB" TAM if left in.
- 8165 does not use the GST threshold as its cutoff; it counts ABS Business Register units. Unverified from memory: the turnover bands start at "zero to less than $50k", and that low band holds many dormant-ish entities. An SMB SaaS estimate should drop it or flag it.
- The agent can fetch the 8165 XLSX by URL, but a generic HTML-to-markdown fetch tool may not parse XLSX. Use the ABS Data API with `format=csv` for the same data (dataflow ID for CABEE not confirmed this session; it has to be found from the dataflow list).
- The full dataflow list is too large for one fetch. Better: search `site:abs.gov.au "Data API"` + topic, or cache a list of known IDs in the agent config. Unverified, from memory: `CPI` (Consumer Price Index), `ERP_Q` (estimated resident population), `LF` (labour force), `RT` (retail trade), `HSI_M` (household spending indicator), `ABS_REGIONAL_ASGS2021`. Each needs to be checked against the list before going into code.
- Household spend: with HES stale, combine the Monthly Household Spending Indicator (spend by category) with ERP household counts, then use the 2015-16 HES category shares indexed by CPI as a fallback. Label the fallback as low confidence.
- Credibility grades (proposed): ABS, ATO, regulators = A (official census or administrative). ACMA surveys = A- (sampled survey, adults 18+ only). Secondary press summaries of official data = B until the primary is fetched.

### Gaps
- Not verified this session: Australian Industry 8155 2024-25 release date and URL; ABS population projections (3222) latest edition; RBA, Treasury, Productivity Commission, AIHW, Austrade, Tourism Research Australia, Jobs and Skills Australia, data.gov.au API (CKAN), state portals (data.nsw.gov.au, data.vic.gov.au, data.qld.gov.au). From memory, data.gov.au runs CKAN with a public `/api/3/action/package_search` endpoint; unverified.
- CABEE SDMX dataflow ID not confirmed.
- Exact 8165 table names (by ANZSIC class x employment size x turnover) not listed on the release page.
- eSafety: no market-sizing dataset identified.

## Sector regulators and registries with counts

### Takeaway
Regulators publish practitioner, participant and entity counts on a quarterly or annual cycle. Ahpra and NDIS were verified this session. The rest are listed from memory and still need checking.

### Cited Findings
- Ahpra publishes quarterly registration data per national board as well as annual reports; quarterly reports have run since April 2016 ([Ahpra statistics](https://ahpra.gov.au/About-AHPRA/What-We-Do/Statistics.aspx)).
- Pharmacy Board March 2026 quarter: a record 42,941 registered pharmacists, data released 18 May 2026 ([AJP](https://ajp.com.au/news/older-pharmacists-dropping-rego/)). Secondary source.
- NDIS Quarterly Report, June 2026 (Q4 2025-26): 782,013 participants at 30 June 2026, including 162,781 children under 9. March 2026: 774,456 participants ([NDIS quarterly report](https://www.ndis.gov.au/media/8806/download)).
- NDIS supplements and downloadable data (by state, service district, support type, SDA) are on the NDIS data site. The March 2026 supplement notes a new computer system affected some data ([NDIS data and research](https://dataresearch.ndis.gov.au/media/4533/download)).

### Inferences
- Pattern for the agent: search "<regulator> quarterly statistics <year>" with Brave, then fetch the PDF or XLSX. Regulator counts are administrative and complete (grade A), but they count registrants, not active buyers. Many Ahpra registrants are non-practising or hospital-employed, and NDIS participants are end users while plan managers or providers may be the real buyers.
- NDIS download links use opaque `/media/NNNN/download` IDs that change each quarter, so search before every fetch. Don't hard-code them.

### Gaps
- Not verified this session (candidate sources from memory): APRA (authorised deposit-taking institution and insurer statistics, quarterly, apra.gov.au), ASIC (company registrations, insolvency stats), ACARA My School and the ACARA National Report on Schooling data portal (school counts and enrolments), Department of Education (higher education student data, uCube), Clean Energy Regulator (small-scale installations by postcode, monthly), AIHW (health workforce, hospitals), ACNC Charity Register (data.gov.au CSV), Tourism Research Australia (IVS/NVS), Jobs and Skills Australia (occupation employment).
- No current Ahpra dashboard URL confirmed.

## Commercial publishers: paywalls, leakage and reliability

### Takeaway
Commercial sources are mostly gated. Statista shows titles and free stats but hides premium values behind login. An IBISWorld industry page fetched this session returned only site chrome with no figures. Press-released summaries (Cut Through Venture, Deloitte, PwC, Telsyte, Roy Morgan) are the realistic way in for an agent, and should be cited as secondary.

### Cited Findings
- Statista tiers: Basic free (free statistics only, premium hidden behind "Log in or register to access precise data"); Starter $199/month billed annually; Professional $1,399/month for up to 5 users, adding reports and market insights. The stated starting price for premium is $2,388 USD per year ([Statista statistic page](https://www.statista.com/statistics/1552548/jellycat-website-visits)). Discovery tier (10 premium stats per month) is only available in DE, CH, AT, US, CA and MX ([Statista FAQ](https://www.statista.com/accounts/discovery-faq)).
- IBISWorld: fetching `https://www.ibisworld.com/au/industry/software-publishing/` returned navigation and marketing only, with no market size, growth, business counts or players ([IBISWorld AU page](https://www.ibisworld.com/au/industry/software-publishing/)). University guides describe IBISWorld as covering Australia, with exportable tables, and accessible only through a subscription login ([Portsmouth library guide](https://library.port.ac.uk/subject/page1239.html); [U Arkansas guide](https://libguides.uark.edu/IBISWorld)).

### Inferences
- IBISWorld's public AU pages used to show a market-size teaser in the snippet. Whether that still holds is unknown (the URL tried may also be wrong). Brave snippets of IBISWorld pages may still carry "market size is $X in 2026"; the agent should treat any IBISWorld figure from a snippet as grade B- and record it as such.
- Euromonitor, Gartner, IDC, Frost & Sullivan: fully paywalled. Their figures reach the public only through press releases and vendor quotes, which are usually global and seldom Australia-specific. Grade B, and always check the scope (AU vs APAC vs global).
- Telsyte (AU tech market studies), Roy Morgan (consumer surveys, publishes free press-release findings), Deloitte Access Economics (commissioned reports, often free PDFs) and the PwC Australian Entertainment & Media Outlook (headline figures in free press releases, full data paid) are the most useful Australia-specific commercial sources an agent can reach. Commissioned reports carry sponsor bias: grade B.

### Gaps
- Access terms not verified for Euromonitor, Gartner, IDC, Frost & Sullivan, Roy Morgan, Telsyte, Deloitte Access Economics or PwC Outlook 2025-2029.
- No Australian university library guide (UNSW, Melbourne, Monash) was retrieved. The search returned only overseas guides. A UWA ABS guide exists ([UWA library ABS guide](https://guides.library.uwa.edu.au/datastatistics/ABS)) but was not read.

## Company-level, funding and competitor data

### Takeaway
For startup funding, Cut Through Venture's annual and quarterly reports are the reference. The 2025 report shows $5.1bn across 390 deals. Company revenue comes from ASX annual reports and segment notes. Crunchbase, PitchBook and Dealroom are largely gated.

### Cited Findings
- Cut Through Venture and Folklore Ventures, State of Australian Startup Funding 2025: $5.1bn across 390 deals, up 24% year on year, the third-largest year on record. Q4 2025 was about $2bn, the strongest quarter since 2021 ([Forbes Australia](https://www.forbes.com.au/news/investing/australias-startup-funding-jumps-to-5-1-billion-in-2025-as-ai-takes-the-lead/)).
- AI-built companies took 61% of funding (over $1bn to AI-native startups). Fintech $868m, hardware/robotics/IoT $297m. Top 20 deals were 58% of the total. Deals with a female founder fell from 28% to 24% ([Forbes Australia](https://www.forbes.com.au/news/investing/australias-startup-funding-jumps-to-5-1-billion-in-2025-as-ai-takes-the-lead/); [SmartCompany](https://www.smartcompany.com.au/startupsmart/australia-startups-2025-funding-report/)).
- 77% of investors reported portfolio layoffs and 46% reported shutdowns ([SmartCompany](https://www.smartcompany.com.au/startupsmart/australia-startups-2025-funding-report/)). These figures come from secondary coverage; the 165-page report itself was not fetched.

### Inferences
- ASX: announcements and annual reports are free PDFs (from memory, `asx.com.au/markets/trade-our-cash-market/announcements.{TICKER}`; unverified). Segment revenue in the annual report notes (AASB 8) is the best free check on incumbent revenue. Grade A for the company, but segments are defined by management and are seldom a clean market slice.
- Crunchbase, PitchBook and Dealroom profile pages show partial data publicly (headline funding total, last round). Snippets are usable at grade B; full data needs paid access.
- Pricing pages (vendor `/pricing`), G2 and Capterra review counts, and LinkedIn employee counts (shown in search snippets, e.g. "X employees on LinkedIn") are fetchable or visible in snippets. G2 and LinkedIn often block plain fetches. Use these as directional signals (grade C), not as market size.
- SimilarWeb free pages show traffic ranges for big domains. Fetching them is often blocked by bot protection.

### Gaps
- Fetchability of ASX, Crunchbase, Dealroom, G2, LinkedIn and SimilarWeb with a plain page fetch was not tested this session.
- Cut Through Venture's own report URL and its quarterly cadence for 2026 were not confirmed.

## Demand signals and price data (desirability)

### Takeaway
Nothing in this group was verified this session. All points below are prior knowledge, flagged for testing. Search-volume and community signals should be treated as relative demand evidence (grade C), not as buyer counts.

### Cited Findings
- No sources retrieved this session for Google Trends, Keyword Planner, Reddit, Whirlpool, ProductReview.com.au or app store review counts.

### Inferences
- Google Trends gives only a relative 0 to 100 index, and the explore page is rendered by JavaScript, so a plain fetch probably returns nothing useful. Keyword Planner needs a Google Ads login. Neither is a good fit for a fetch-only agent. Brave snippets of third-party keyword tools may expose rough volumes (grade C-).
- Whirlpool (telco and broadband forums, relevant to Telstra-adjacent startups), ProductReview.com.au (review counts per brand) and Reddit (r/australia, r/AusFinance, r/smallbusiness via search) can be fetched or seen in snippets. Use them for pain-point evidence and rough adoption signals, not volumes.
- App store review and rating counts are visible on public App Store and Google Play listing pages and work as a proxy for installed base.

### Gaps
- Not tested: which of these pages a plain fetch tool can render, and whether Reddit blocks unauthenticated fetches in 2026.

## Currency and inflation handling

### Takeaway
Use RBA exchange rate tables for FX and ABS CPI (quarterly and monthly) to bring older AUD figures to current dollars. RBA tables are CSV/XLSX at stable URLs, and CPI is in the ABS Data API. Neither link was opened directly this session.

### Cited Findings
- Third-party tools describe RBA statistical tables as CSVs at predictable URLs, e.g. `https://www.rba.gov.au/statistics/tables/csv/f11.1-data.csv`. Descriptions of what F11 covers versus F11.1 (monthly from 1983 vs daily) conflict between sources, so check the RBA index ([Apify RBA actor](https://apify.com/mrjerry/rba-statistics); [rba-mcp on Glama](https://glama.ai/mcp/servers/Bigred97/rba-mcp)).
- Some historical RBA exchange-rate tables have no official table numbers; the readrba R package assigns its own ([readrba docs](https://search.r-project.org/CRAN/refmans/readrba/html/read_rba.html)). Historical CSVs are described as poorly structured ([npm author note](https://www.npmjs.com/~brendtos)).

### Inferences
- Authoritative index (from memory, unverified): `https://www.rba.gov.au/statistics/historical-data.html#exchange-rates`; current F11 at `https://www.rba.gov.au/statistics/tables/#exchange-rates`.
- Conversion rule: convert a USD figure at the average rate for the source's reference year (not today's spot rate), then inflate with AUD CPI. Inflating with US CPI and then converting at today's rate gives a different answer. Pick one method and record it.
- CPI: ABS 6401 quarterly All Groups index (unverified API dataflow ID `CPI`). The ABS moved to a complete monthly CPI in late 2025 (prior knowledge, unverified).

### Gaps
- RBA F11 and CPI CSV URLs and the ABS CPI dataflow ID were not fetched this session.
- Whether the ABS full monthly CPI replaced the quarterly headline as planned was not confirmed.
