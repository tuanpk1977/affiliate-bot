# Content Engine V3 Blueprint

## Vision

Content Engine V3 should be designed to outperform existing Google results by optimizing for search competitiveness, intent match, content depth, authority signals, and conversion quality before drafting begins. The goal is not merely to write a better article, but to build a page that is more likely to win the SERP through superior structure, stronger topical coverage, better entity support, clearer buying guidance, and higher trust signals.

This blueprint is planning-only. No code, no modules, no deployment, and no publishing are introduced here.

---

## 1. Competitor Intelligence Engine

### Purpose

Before writing, the engine should understand the current search landscape so that the draft is built around what already wins.

### Flow

Google Results
↓
SERP Analysis
↓
Competitor Structure
↓
Content Gap Detection
↓
Winning Outline
↓
Writing
↓
Quality Gate

### Required inputs

- Target keyword or topic
- Seed intent label
- Top 10 Google results for the query
- Title, URL, and snippet for each result
- Page structure signals
- Estimated content length and section headings
- FAQ presence and quality
- Schema usage on competing pages
- Internal link patterns and hub usage
- E-E-A-T and trust cues
- Affiliate or commercial intent indicators
- Current freshness signals

### Outputs

- SERP snapshot summary
- Competitor ranking matrix
- Competitor structure profile
- Gap inventory
- Winning outline recommendation
- Draft brief with content priorities
- Quality gate scorecard

### Scoring

The competitor intelligence layer should score each competing page on:

- Relevance to the target keyword
- Intent alignment
- Structural completeness
- Topic coverage depth
- FAQ usefulness
- Entity richness
- Trust and authority signals
- Commercial usefulness
- Schema support
- Readability and UX quality

### Future modules

This engine should later be implemented as a dedicated intelligence layer with modules for:

- SERP fetch and extraction
- Competitor structure analysis
- Content gap detection
- Outline synthesis
- Competitive scoring

### Implementation phases

Phase 1
- Analyze top results only
- Extract headings, FAQs, schema hints, and basic structure
- Produce a simple competitive brief

Phase 2
- Add deeper gap analysis
- Compare coverage against the target intent
- Score weak points and missing sections

Phase 3
- Create full competitor intelligence output
- Feed results directly into outline and writer stages
- Add recommendation engine for winning page patterns

---

## 2. Keyword Cluster Engine

### Purpose

The engine should organize keywords into a topic cluster before drafting so the page can cover the full topic ecosystem rather than only the primary query.

### Cluster structure

- Parent Topic
  - The main topic or primary search theme
- Supporting Topics
  - Related narrower subtopics that strengthen topical depth
- Semantic Keywords
  - Conceptually related terms and synonyms
- Buyer Keywords
  - Commercial or purchase-intent terms such as best, top, review, pricing, alternatives
- Informational Keywords
  - Research-oriented questions and educational queries
- Comparison Keywords
  - Queries that compare alternatives, tools, plans, or approaches

### Expected behavior

The keyword cluster engine should group terms into a topic map that helps the writer answer the full user journey rather than only the main keyword.

### Planned inputs

- Primary keyword
- Seed topic
- Related search terms
- SERP query suggestions
- Existing content inventory
- Affiliate angles and buyer intent signals

### Planned outputs

- Cluster map
- Topic priority list
- Keyword coverage plan
- Suggested section themes
- Internal link targets

---

## 3. Search Intent Engine

### Purpose

The engine should detect the dominant search intent before it writes so the page format matches what the user actually wants.

### Supported intents

- Review
- Comparison
- Pricing
- Alternatives
- Tutorial
- Best
- Vs
- Use cases
- FAQ

### How intent changes article structure

#### Review
- Lead with a clear verdict
- Include strengths, weaknesses, and use cases
- Add trust and evidence signals
- Close with a recommendation

#### Comparison
- Open with a direct comparison frame
- Add feature-by-feature comparison table
- Highlight best fit by audience
- Include decision criteria

#### Pricing
- Lead with pricing clarity
- Show plan tiers, limitations, and value
- Add cost vs value framing
- Include affordability and ROI considerations

#### Alternatives
- Compare the target solution to other options
- Explain when each option is better
- Include decision matrix
- End with a practical recommendation

#### Tutorial
- Prioritize clear steps and implementation guidance
- Use numbered sections and action-oriented language
- Add screenshots, examples, or practical walkthroughs

#### Best
- Focus on shortlist and ranking logic
- Explain evaluation criteria
- Present a top-pick recommendation with reasoning

#### Vs
- Create a direct side-by-side format
- Emphasize differences, tradeoffs, and best use cases
- Include a concise verdict section

#### Use cases
- Organize content around what the tool is good for
- Show scenario-based examples
- Emphasize practical fit and outcomes

#### FAQ
- Lead with a simple summary answer
- Add question-based sections
- Address objections and common confusion
- Support with concise explanations

### Intent outputs

- Intent label
- Confidence score
- Recommended structure template
- Required sections
- CTA positioning

---

## 4. Competitor Gap Engine

### Purpose

The engine should identify where competing pages are weak and where a new page can win by covering missing or under-served topics.

### Gap scoring dimensions

- Missing topics
- Weak FAQ
- Missing entities
- Weak CTA
- Missing schema
- Weak internal links
- Weak EEAT
- Weak buying guide
- Weak comparison
- Weak pricing

### Scoring approach

Each dimension should receive a score based on:

- Presence on the top results
- Depth and quality of the signal
- Likelihood that this gap affects ranking or conversion
- Importance to the selected intent

### Example scoring logic

- Strong coverage = low gap risk
- Missing or shallow coverage = high gap opportunity
- Commercial intent pages with weak buying guidance = high priority opportunity
- Pages that lack FAQ or schema = clear structural gap

### Output

A prioritized gap report such as:

- High-priority gaps to cover
- Secondary opportunities to add
- Weaknesses that increase click risk
- Opportunities to improve trust and conversion

### Strategic use

The gap engine should directly inform:

- The outline
- The section hierarchy
- The FAQ section
- The CTA strategy
- The schema recommendation
- Internal link planning
- E-E-A-T content signals

---

## 5. Content Coverage Score

### Purpose

The system should score the planned or drafted page on how comprehensively it covers the topic and how strong it is as a competitive page.

### Scoring model

#### Coverage
- Topic completeness
- Subtopic inclusion
- Related question coverage
- Depth of explanation

#### Intent
- How well the page matches search intent
- Whether structure fits the query type

#### Authority
- Strength of expertise and topical depth
- Quality of evidence and framing
- Depth of product or topic understanding

#### Trust
- Transparency
- Accuracy
- Disclosure quality
- E-E-A-T support signals

#### Freshness
- Recentness of information
- Current pricing or feature references
- Timeliness of examples or guidance

#### Readability
- Clarity
- Scannability
- Concision
- Flow and structure

#### Commercial value
- Buyer guidance quality
- Conversion readiness
- CTA usefulness
- Purchase decision support

#### CTR
- Title appeal
- Snippet value
- Curiosity and relevance balance
- Expected click potential

#### Overall score
- Composite weighted score across all categories

### Suggested scoring bands

- 90–100: Excellent competitive page
- 80–89: Strong page with minor gaps
- 70–79: Acceptable but not winning
- Below 70: Needs major improvement

### Suggested use

The score should be used as a decision gate before publishing or before finalizing a draft for human review.

---

## 6. Future workflow

Topic
↓
Keyword Cluster
↓
SERP Analysis
↓
Competitor Intelligence
↓
Gap Detection
↓
Outline
↓
Writer
↓
Quality Gate
↓
Publisher

### Workflow intent

This workflow moves the system from keyword-first drafting to competitive, intent-aware page design. The engine should first understand the market, then build a page that can realistically beat the current top results.

### Design principle

The system should optimize for:

- Search competitiveness
- Intent precision
- Content depth
- Trust and authority
- Conversion usefulness
- SERP win probability

---

## Recommended implementation phases

### Phase 1 — Research layer
- Keyword clustering
- Intent detection
- Basic SERP extraction

### Phase 2 — Competitive layer
- Competitor structure analysis
- Gap scoring
- Outline generation

### Phase 3 — Drafting layer
- Content coverage planning
- Writer briefing
- Section and FAQ planning

### Phase 4 — Quality layer
- Coverage scoring
- Trust and authority scoring
- CTR scoring
- Overall gate

### Phase 5 — Publishing integration
- Publisher receives the optimized brief and final draft
- Quality gate becomes a pre-publish decision checkpoint

---

## Strategic outcome

A V3 content engine should be able to do more than generate an article. It should be able to produce a page that is strategically designed to outperform the current Google results by combining:

- competitor intelligence
- topic clustering
- search intent analysis
- gap detection
- coverage scoring
- authority and trust optimization
- stronger commercial usefulness

This blueprint is intentionally architecture-first and does not introduce implementation work.
