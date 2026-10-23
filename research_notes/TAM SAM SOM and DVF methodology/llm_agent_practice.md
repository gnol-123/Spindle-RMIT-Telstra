# LLM agents for market research and quantitative estimation: state of practice (Oct 2026)

Scope: evidence for designing muru-D's market research agent (Brave search + page fetch + optional sandboxed code runner; outputs TAM/SAM/SOM, DVF scorecard, cited HTML report). Items marked [prior knowledge] are well-known papers cited from memory with their canonical arXiv URL. I did not re-fetch them this session.

## 1. LLM accuracy at Fermi estimation, market sizing and forecasting; effect of retrieval/tools

### Takeaway
Point estimates from LLMs on Fermi problems are rough, and their stated uncertainty is badly overconfident: nominal 99% intervals cover the truth about 65% of the time. Retrieval plus aggregation brings LLM forecasting close to human crowds. No benchmark measures LLM accuracy at TAM sizing specifically.

### Cited Findings
- FermiEval (Oct 2025): across several modern models, nominal 99% confidence intervals on Fermi questions contain the true answer only 65% of the time on average. Conformal widening of the intervals restores ~99% coverage and cuts the Winkler interval score by 54%. The authors call the cause a "perception tunnel": models act as if they sample from a truncated slice of their own distribution and ignore the tails ([arXiv 2510.26995](https://arxiv.org/abs/2510.26995)).
- Older baseline (2021, pre-frontier models, flagged as old): Kalyan et al. built REALFP (~928 real Fermi problems) and SYNTHFP (10k templated). Fine-tuned LMs were off by about two orders of magnitude on average. Each item ships with supporting facts and an executable explanation program, which makes it a usable eval scaffold. Three settings: perfect context, distractor context, full recall ([arXiv 2110.14207](https://arxiv.org/pdf/2110.14207); [AI2 dataset](https://allenai.org/data/fermi)).
- Halawi et al. (NeurIPS 2024): a retrieval-augmented system (search, generate several forecasts, aggregate), tested on questions published after the models' knowledge cutoff, gets close to the competitive human forecaster crowd on average and beats it in some settings ([NeurIPS 2024 paper](https://proceedings.neurips.cc/paper_files/paper/2024/file/5a5acfd0876c940d81619c1dc60e7748-Paper-Conference.pdf); [code](https://github.com/dannyallover/llm_forecasting)).
- Schoenegger, Tuminauskaite, Park, Tetlock (Science Advances, Nov 2024): the mean of 12 LLMs over 31 binary questions was statistically indistinguishable from a crowd of 925 humans. LLM forecasts showed acquiescence bias, with mean predictions significantly above 50% although outcomes split roughly evenly. Showing GPT-4 and Claude 2 the human median improved their accuracy 17-28%, but a plain average of human and machine forecasts did better still ([PMC full text](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11800985/)).
- HBS working paper (Brand & Israeli, 2023, flagged as old): LLM-generated market research estimates sometimes match human studies but are often inaccurate, and occasionally point the wrong way ([HBS WP 23-062](https://www.hbs.edu/ris/Publication%20Files/23-062_1f58623a-ee21-44b9-a262-276047bc5543.pdf)).
- Practitioner vendors say LLM-only scans "can hallucinate or give exaggerated numbers". Preuve withholds TAM figures from its free tier for that reason. This is a vendor claim, not a measurement ([Preuve](https://preuve.ai/blog/market-size-calculator)).
- Vendor guidance: top-down sizing tends to overestimate, bottom-up is grounded in verifiable customer counts; every number needs a traceable source or gets labelled a hypothesis ([HG Insights](https://hginsights.com/blog/market-sizing-the-complete-guide-to-calculating-tam-sam-som-and-building-a-data-driven-growth-strategy/); [Ainna](https://ainna.ai/resources/faq/ai-market-research)).
- Anthropic research system: on BrowseComp, token usage alone explained 80% of performance variance. Token usage, tool-call count and model choice together explained 95%. A multi-agent setup (Opus 4 lead, Sonnet 4 subagents) beat single-agent Opus 4 by 90.2% on an internal research eval ([Anthropic engineering](https://www.anthropic.com/engineering/multi-agent-research-system)).

### Inferences
- Treat model-stated ranges as too narrow by default. Widen them in code (e.g. multiply the log-range by a fixed factor tuned on a small Fermi eval) rather than trusting "low/high" as emitted.
- Retrieval helps mainly by replacing recalled inputs (population, price, penetration) with sourced ones. The decomposition itself is where LLMs are reasonable. Design the pipeline so each Fermi factor is a retrieved, quoted number.
- More search budget measurably helps (BrowseComp variance), so cap by cost, not by a low fixed call count.

### Gaps
- No independent benchmark of LLM TAM/SAM/SOM accuracy against known market sizes turned up. Australian-market-specific evidence: none found.
- Full-text error magnitudes for FermiEval point estimates (vs interval coverage) not retrieved.

## 2. Known failure modes

### Takeaway
Citation unreliability is the most heavily measured failure: 10-60% of citations do not support their claims, depending on system and mode. Close behind: optimism and acquiescence bias, anchoring on numbers in context, overconfident intervals, and a preference for SEO/content-farm sources.

### Cited Findings
- **Citations that don't support claims.** DeepResearch Bench (Jun 2025) FACT metric: Gemini-2.5-Pro Deep Research averaged 111 supported citations per task at 81.44% citation accuracy. Perplexity Deep Research had the highest accuracy (90.24%) with fewer citations. Method: split the report into statement-URL pairs, fetch each page via Jina Reader, and have a judge LLM decide binary support ([arXiv 2506.11763](https://arxiv.org/html/2506.11763v1); [repo](https://github.com/Ayanami0730/deep_research_bench)).
- DeepTRACE (Venkit et al., ICLR 2026): citation accuracy across generative search and deep research systems ranged 40-80%. Perplexity/You.com search modes had 23-47% unsupported claims. Perplexity's deep research mode reached a 97.5% unsupported-statement ratio in some tests, and the authors suggest it drew on parametric knowledge rather than retrieved pages. Deep research modes were also highly one-sided on debate queries. Figures vary between paper versions ([arXiv 2509.04499](https://arxiv.org/abs/2509.04499); [ICLR PDF](https://proceedings.iclr.cc/paper_files/paper/2026/file/ad08767706825033b99122332293033d-Paper-Conference.pdf)).
- **Hallucinated or misattributed URLs.** Tow Center/CJR (Mar 2025), 8 AI search tools: over 60% of responses had incorrect citations. Perplexity was wrong 37% of the time, ChatGPT Search 67%, Grok 3 94%. The tools fabricated links, cited syndicated copies, rarely declined to answer, and premium tiers were *more* confidently wrong. Per-tool numbers come from secondary coverage ([CJR](https://www.cjr.org/tow_center/we-compared-eight-ai-search-engines-theyre-all-bad-at-citing-news.php); [eWeek](https://www.eweek.com/de/news/ai-chatbot-citation-problem/)).
- **Low-quality source preference.** Anthropic saw its research agents "preferring SEO-optimized content farms over authoritative sources like academic PDFs". Adding source-quality heuristics to the prompts fixed it. Other observed failures: endless searching for sources that don't exist, overly long and specific queries that return little, and duplicated work across subagents ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)).
- **Majority-vote "accuracy".** GPT Researcher's only accuracy mechanism is aggregating 20+ sources and favouring the most frequently reported information. It has no reviewer or verifier agent ([GPT Researcher repo](https://github.com/assafelovic/gpt-researcher)). For market sizing this amplifies report-mill figures, since many press releases syndicate the same number. Inference, but consistent with CJR's finding that tools cite syndicated copies.
- **Optimism bias.** OptimismBench (Jul 2026) elicits P(success) and P(failure) for each scenario, and the gap gives a signed bias score. 14 of 16 models from 8 providers were optimistic; only Anthropic's frontier tier leaned pessimistic. Post-training sets the sign of the bias. The tilt survived prompt, temperature, perspective and self-debiasing ablations, and "downstream pipelines inherit the tilt by default" ([arXiv 2607.26981](https://arxiv.org/abs/2607.26981)).
- Acquiescence bias in forecasts: mean LLM probabilities sat significantly above 50% ([Schoenegger et al. 2024](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11800985/)).
- Kleinert & Urbig (Entrepreneurship Theory & Practice, 2026): GPT-4, the oldest model tested, performed worst at evaluating startups and gave "unrealistically positive assessments". Newer GPT and Gemini models did better. Outputs depend on recall and framing; sycophancy is flagged as a risk (abstract via search snippet; full text was 403) ([SAGE](https://journals.sagepub.com/doi/10.1177/10422587261430320)).
- Debate overconfidence: in 60 three-round policy debates among ten LLMs, models started at 72.9% average confidence against a rational 50% baseline ([arXiv 2505.19184](https://export.arxiv.org/pdf/2505.19184)).
- **Anchoring.** SynAnchors (May 2025): anchoring is common across LLMs, works at shallow layers, and is not removed by conventional mitigations; reasoning helps somewhat ([arXiv 2505.15392](https://arxiv.org/pdf/2505.15392)). In a pricing scenario, GPT-4o had an anchoring index of 13.12%, GPT-4.5 5.67%, three other models none ([CogInfoCom 2025](https://papers.sze.hu/research-portal/publications/10.1109/CogInfoCom66819.2025.11200816)). ACL 2026: anchoring susceptibility tracks model confidence rather than accuracy, high anchors pull harder than low ones, and post-training shifts the effect ([ACL 2026 short.16](https://aclanthology.org/2026.acl-short.16/)).
- **False precision.** Covered by FermiEval's overconfident intervals above ([arXiv 2510.26995](https://arxiv.org/abs/2510.26995)).

### Inferences
- First-number anchoring is real. Collect several independent figures *before* any estimate is formed. Don't let the first fetched report-mill number sit in context while the agent builds the bottom-up model.
- Expect an optimistic DVF scorecard by default. Bias direction depends on the model, so measure it once for the chosen model (OptimismBench method: ask both "probability this succeeds" and "probability this fails"; the gap is the bias).
- Unit, currency and year errors: no dedicated 2024-2026 study found. They are a known class: USD vs AUD, global vs ANZ, base-year vs forecast-year market values, CAGR compounding.

### Gaps
- No quantified study of how much syndicated report-mill numbers (MarketsandMarkets, Allied, etc.) dominate LLM market-sizing outputs.
- No 2024-2026 measurement of LLM arithmetic error rates specifically inside agentic report writing.
- OpenAI Deep Research citation accuracy is not in the DeepResearch Bench snippet I retrieved. Check the leaderboard.

## 3. Mitigations with evidence

### Takeaway
The best-supported mitigations: (a) a separate citation pass that re-fetches every cited page and checks claim support; (b) independent multiple estimates aggregated in code; (c) arithmetic executed in code; (d) post-hoc widening of intervals. Red-team and debate passes have mixed evidence: they help evaluation accuracy but do not reliably fix calibration.

### Cited Findings
- **Separate citation agent.** Anthropic's research system runs a dedicated CitationAgent after research to attach each claim to a source location ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)). Most open pipelines (STORM, GPT Researcher) "cite as you write", with verification left outside the generator, per a single non-authoritative third-party claim ([stanford-oval/storm](https://github.com/stanford-oval/storm)).
- **Re-fetch and judge.** DeepResearch Bench's FACT and DeepTRACE both verify by re-fetching the URL and asking a judge LLM whether the page text supports the statement. The same method serves as a runtime guard ([DeepResearch Bench](https://arxiv.org/html/2506.11763v1); [DeepTRACE](https://arxiv.org/abs/2509.04499)). "Claim-level auditability" is argued as the design target for deep research agents ([arXiv 2602.13855](https://arxiv.org/html/2602.13855v1)).
- **Quote extraction.** Anthropic's guidance on reducing hallucinations: extract word-for-word quotes first and ground the answer in them; let the model say "I don't know"; retract any claim it can't support with a quote [prior knowledge] ([Anthropic docs](https://docs.anthropic.com/en/docs/test-and-evaluate/strengthen-guardrails/reduce-hallucinations)).
- **Chain-of-Verification** (Dhuliawala et al., Meta, 2023, older): draft, plan verification questions, answer them *independently* of the draft, then revise. This reduced hallucinations on list and QA tasks [prior knowledge] ([arXiv 2309.11495](https://arxiv.org/abs/2309.11495)).
- **Arithmetic in code.** PAL (Gao et al., 2022, older): the LLM writes a program and the interpreter computes, beating chain-of-thought on math benchmarks [prior knowledge] ([arXiv 2211.10435](https://arxiv.org/abs/2211.10435)). Fermi datasets ship executable explanation programs, so decomposition-as-code is native to the task ([Kalyan et al.](https://arxiv.org/pdf/2110.14207)).
- **Multiple estimates, then aggregation.** A 12-LLM mean matched a 925-human crowd ([Schoenegger et al.](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11800985/)). Halawi's system generates several forecasts and aggregates them ([NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/file/5a5acfd0876c940d81619c1dc60e7748-Paper-Conference.pdf)). Self-consistency (sampling many reasoning paths and taking the majority/median) is the older baseline [prior knowledge] ([arXiv 2203.11171](https://arxiv.org/abs/2203.11171)).
- **Calibration fixes.** Conformal interval widening gives ~99% coverage and a 54% better Winkler score. Log-probability elicitation and quantile adjustment were also proposed ([FermiEval](https://arxiv.org/abs/2510.26995)). Prompting alone is weak: self-debiasing did not remove optimism tilt ([OptimismBench](https://arxiv.org/abs/2607.26981)), and conventional strategies did not remove anchoring ([SynAnchors](https://arxiv.org/pdf/2505.15392)).
- **Devil's advocate / debate.** DEBATE (one agent ordered to criticise the others) beat prior state of the art on NLG-evaluation meta-benchmarks SummEval and TopicalChat ([arXiv 2405.09935](https://www.arxiv.org/abs/2405.09935)). Debate success depends mostly on base reasoning strength and diversity, structural tweaks add little, and majority pressure suppresses independent correction ([arXiv 2511.07784](https://arxiv.org/abs/2511.07784v1)). Confidence-modulated debate beat vanilla multi-agent debate and majority vote on six QA benchmarks ([ACL Findings 2026](https://aclanthology.org/2026.findings-acl.1694/)). I found no study showing a red-team pass reduces overconfidence in estimates.
- **Source-quality heuristics in the prompt.** These fixed the content-farm preference ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)). GPT Researcher filters passages by relevance scoring, with BM25 as fallback ([repo](https://github.com/assafelovic/gpt-researcher)).

### Inferences (actionable pipeline for search + fetch + code runner)
1. Store every number as a structured record: `{value, unit, currency, geography, year, quote, url, source_type}`. Reject records without a verbatim quote from a fetched page.
2. Verification pass: re-fetch each URL (or reuse the cached fetch) and check that the quote string appears and that the claim matches the quote. Drop or flag failures. Cheap string match first, LLM judge second.
3. Do all arithmetic (TAM = units x price, FX to AUD, CAGR rollforward, SAM/SOM shares) in the code runner from the records. The model never types a computed number into the report.
4. Build at least two independent estimates: top-down from published reports, bottom-up from counts x price. Ideally several sampled bottom-up decompositions. Report the median and range; widen the range in code. Put a large top-down vs bottom-up gap in the report as a flag, rather than averaging it away.
5. Anchoring guard: run the bottom-up estimate in a context that does *not* contain the report-mill headline number.
6. Source tiering in the prompt: government/ABS, regulator, company filings and primary surveys above analyst press releases (GlobeNewswire/PR Newswire report-mill syndication). Dedupe syndicated copies of one number to a single source.
7. Bear case: a separate pass with fresh context, told to find disconfirming evidence and the strongest failure reasons, with its own citations. Evidence it helps calibration is weak; evidence it helps evaluation quality is moderate.

### Gaps
- No head-to-head study of "forced quote extraction" vs no quotes on market-number accuracy specifically.
- Premortem prompting for LLMs: no empirical study found.

## 4. Existing products and open-source tools

### Takeaway
Open-source deep-research agents (GPT Researcher, STORM) use plan, parallel search and summarise, then write, with citations attached during writing and no independent verification. Commercial idea validators (ValidatorAI etc.) have no independent accuracy evidence, and their scores reportedly cluster high.

### Cited Findings
- GPT Researcher: a planner generates research questions; a crawler agent per question gathers and summarises sources, tracking each one; a publisher merges everything into a report of 2,000+ words (5-6 pages in multi-agent mode; PDF/Docx/MD). It aggregates "over 20 sources" and favours frequently reported facts. Context filter: Jev relevance scoring, BM25 fallback. Its own benchmark claims 73% vs 46% relevant passages over embeddings, on 28 tasks. Deep mode recurses through a tree of subtopics. No reviewer agent ([repo](https://github.com/assafelovic/gpt-researcher)).
- STORM (Stanford OVAL): two stages. Pre-writing does perspective-guided question asking plus simulated writer-expert conversations grounded in retrieved sources, and produces an outline. Writing produces a cited article from the outline. Co-STORM adds a moderator, QA agents and a human user around a shared mind map ([stanford-oval/storm](https://github.com/stanford-oval/storm); [PyPI](https://pypi.org/project/knowledge-storm)).
- Anthropic Research: an orchestrator (Opus 4) plans and keeps the plan in memory because context beyond 200k tokens is truncated. It spawns 3-5 parallel subagents, and a CitationAgent runs at the end. Effort scales with query: 1 agent and 3-10 calls for simple facts, 2-4 subagents and 10-15 calls each for comparisons, 10+ subagents for complex research. Multi-agent runs use ~15x the tokens of chat ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)).
- ValidatorAI: free idea scoring with a "viability score". Claims behavioural data from 300k+ founders (self-reported). Thin user reviews (4.7/5 from 2 reviews on one listing) ([Techjockey](https://www.techjockey.com/us/detail/validator-ai)). A competitor (interested party) cites ValidatorAI data showing 54.2% of users scored 80-89, i.e. scores cluster high ([BigIdeasDB](https://bigideasdb.com/validatorai-alternative)).
- SparkToro TAM feature combines its own audience dataset with LLM requests. The vendor says it can't guarantee every estimate is good ([SparkToro](https://sparktoro.com/blog/total-addressable-market-tam-size-is-now-in-sparktoro-reports/)).
- SSFF (2024): a multi-agent LLM framework for predicting startup success, built for explainability ([arXiv 2405.19456](https://arxiv.org/pdf/2405.19456)).

### Inferences
- None of the open-source pipelines verify numbers. muru-D's differentiator should be the number ledger plus re-fetch verification plus code arithmetic, not more search.
- High-clustering scores (ValidatorAI) are the failure to avoid in the DVF scorecard. Anchor rubric levels to concrete evidence thresholds, not adjectives.

### Gaps
- No independent analyst reviews of output quality for IdeaBuddy, Crayon or AlphaSense found in this pass; searches returned vendor and listing pages only.
- OpenAI/Gemini Deep Research internal pipeline details not retrieved.

## 5. LLM-as-judge for idea/startup evaluation

### Takeaway
LLM judges agree only moderately with experts, run more lenient than experts, favour longer proposals and novel framing, and older models are unrealistically positive about startups. On founder-outcome prediction (VCBench), LLMs reportedly beat VC precision baselines, with methodological caveats.

### Cited Findings
- VCBench (Sep 2025, Oxford + Vela Research): 9,000 anonymised founder profiles (US, founded 2010-2018), 9% labelled successful (exit/IPO >$500M or raised >$500M within 8 years). Baseline precision: market index 1.9%, YC 3.2%, tier-1 VCs 5.6%. Nine LLMs reportedly beat these baselines. A critic says the anonymisation lacks ablations, and the 9% base rate is inflated vs the real 1.9% ([arXiv 2509.14448](https://arxiv.org/pdf/2509.14448); [HF dataset](https://huggingface.co/datasets/vela-research/VCBench); [review](https://www.themoonlight.io/en/review/vcbench-benchmarking-llms-in-venture-capital)).
- Kleinert & Urbig (ETP 2026): LLM startup evaluations vary by model; GPT-4 was weakest and unrealistically positive, newer GPT/Gemini better; results are sensitive to recall and framing ([SAGE](https://journals.sagepub.com/doi/10.1177/10422587261430320)).
- Business-idea judges (Apr 2026, 105 researchers): current LLM judges cannot reliably reproduce proposal-stage expert preferences across five dimensions, and favoured the longer proposal in most decisive comparisons. Experts themselves disagree a lot, which motivates personalised over aggregate judges ([arXiv 2604.22517](https://arxiv.org/pdf/2604.22517)).
- Si et al. (2024, 100+ NLP researchers): LLM ideas were rated more novel than expert ideas but slightly weaker on feasibility. LLM-as-judge correlated poorly with human experts ([arXiv 2409.04109](https://arxiv.org/pdf/2409.04109)).
- Leniency: in merchant-risk assessment, LLM judges scored on average 0.46 points higher than a 26-expert consensus ([arXiv 2602.05110](https://arxiv.org/pdf/2602.05110)).
- HindSight (2026): LLM judges reward novelty of framing over real future impact. Use them for fast screening, paired with outcome-based validation ([arXiv 2603.15164](https://arxiv.org/pdf/2603.15164)).
- Evaluator sycophancy under user rebuttal is documented ([arXiv 2509.16533](https://arxiv.org/pdf/2509.16533)).
- Optimism tilt varies by model and is inherited downstream ([OptimismBench](https://arxiv.org/abs/2607.26981)).

### Inferences
- The DVF scorecard should be evidence-gated: each Desirability/Viability/Feasibility score cites the records that justify it, and a score is capped if evidence is missing.
- Don't show the founder's pitch framing to the scoring pass verbatim (framing sensitivity). Score from the extracted evidence ledger.
- Length bias: compare like-for-like report lengths if the judge ranks ideas against each other.

### Gaps
- No study comparing LLM DVF-style scores with accelerator selection decisions or later outcomes for Australian startups.

## 6. Evaluating the agent

### Takeaway
Use (a) citation precision via statement-URL re-fetch plus a judge (FACT/DeepTRACE style); (b) a small (~20) real-query set with a single-call 0-1 rubric judge plus human spot checks; (c) numeric accuracy on Fermi or known-market items, measured as log-error and interval coverage.

### Cited Findings
- Anthropic started evals with ~20 real-usage queries, since large effect sizes show up in small sets. Rubric: factual accuracy, citation accuracy, completeness, source quality, tool efficiency. A single LLM call producing a 0.0-1.0 score plus pass/fail matched humans best, and multiple judges were less consistent. Human testers caught hallucinations on unusual queries and source-selection bias that automation missed ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)).
- FACT metrics: citation accuracy (share of statement-URL pairs supported) and effective citations (supported citations per task) ([DeepResearch Bench](https://arxiv.org/html/2506.11763v1)). DeepResearch Bench II reportedly replaces FACT with InfoRecall, which measures whether reports retrieve the relevant facts (recall) ([arXiv 2512.01948](https://arxiv.org/pdf/2512.01948); unverified detail).
- DeepTRACE builds a citation matrix (statement x source) and a factual-support matrix, which catches both fabricated citations and evidence the system missed. It also measures one-sidedness and overconfidence ([DeepTRACE](https://arxiv.org/abs/2509.04499)).
- Interval scoring: coverage at nominal level plus Winkler score, as in FermiEval ([arXiv 2510.26995](https://arxiv.org/abs/2510.26995)). Fermi test items with gold answers and programs: REALFP/SYNTHFP ([AI2](https://allenai.org/data/fermi)).
- Directional bias audit: P(success) vs P(failure) gap ([OptimismBench](https://arxiv.org/abs/2607.26981)).
- Founder-outcome benchmark with precision vs VC baselines: [VCBench](https://huggingface.co/datasets/vela-research/VCBench).

### Inferences
- Known-size test set: pick ~20 ANZ markets where a primary-source figure exists (ABS, IBISWorld-cited government data, listed-company segment revenue) and score log10 error of TAM plus whether the interval covers the figure. Hide the answer source from the agent's search (blocklist that domain) to avoid leakage.
- Citation metrics per report: precision = supported pairs / all pairs; quote-match rate (exact substring found on the re-fetched page); share of numbers traceable to primary vs report-mill sources.
- Re-run each eval item several times. Agent variance is high, so compare medians.

### Gaps
- No public dataset of startup ideas with ground-truth TAM/SAM/SOM found.
- No published inter-rater agreement for human graders on market-sizing reports.
