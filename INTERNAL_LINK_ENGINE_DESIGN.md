# Internal Link Engine Design

## Objective

The internal link engine should plan and prioritize links between pages so that the site builds topical authority, improves crawlability, supports discoverability, and strengthens the relationship between informational, review, comparison, and money pages. The design is documentation-only and does not include implementation work.

---

## 1. Purpose of the engine

The engine should automatically identify where internal links should be added, which pages should link to which pages, and how those links should be weighted. Its goal is to create a site structure that helps both users and search engines understand the content hierarchy and topical relationships.

The engine should support:

- improving content discoverability
- strengthening topic clusters
- guiding users toward conversion-oriented pages
- distributing authority across related pages
- increasing contextual relevance of links

---

## 2. Core link planning model

The engine should work from a site map of content pages and classify each page by role.

### Page roles

- Related articles
- Cluster links
- Hub pages
- Money pages
- Review pages
- Comparison pages

Each page should receive a role and a link strategy based on its purpose and relationship to other pages.

---

## 3. Related articles

### Purpose

Related articles should connect pages that share a topic, subtopic, or user intent.

### Link behavior

The engine should identify related articles that:

- cover the same topic family
- answer adjacent questions
- support the same buyer journey
- are likely to be useful to the same reader

### Example link use cases

- a tutorial linking to a review page
- a comparison page linking to a buyer guide
- a review page linking to a beginner article

### Design rule

Related article links should feel natural and contextually relevant rather than forced.

---

## 4. Cluster links

### Purpose

Cluster links should connect pages that belong to the same topical cluster so that search engines can understand the broader topic ecosystem.

### Cluster structure

A cluster may include:

- a hub page
- several supporting articles
- review or comparison pages
- money pages
- FAQ or use-case pages

### Link behavior

The engine should connect supporting pages back to the hub and connect hub-related pages to one another where context supports it.

### Design rule

Cluster links should build topical depth while keeping the linking pattern simple and meaningful.

---

## 5. Hub pages

### Purpose

Hub pages should act as central entry points for a topic cluster.

### Role of a hub page

A hub page should:

- summarize the main topic
- introduce related subtopics
- link to core supporting articles
- signal the site’s topical authority
- guide the user toward the next best page

### Link behavior

Hub pages should receive links from supporting pages and should link out to the most important pages in the cluster.

### Design rule

Hub pages should not become overly broad or generic. They should remain focused on a clear topic theme.

---

## 6. Money pages

### Purpose

Money pages are the pages most closely tied to conversion or affiliate value.

### Role of a money page

A money page should:

- clearly present a product, service, or offer
- provide strong decision-support value
- link to supporting comparison or educational content
- receive links from related pages that build intent and trust

### Link behavior

The engine should support money pages by:

- linking to them from relevant review, comparison, and tutorial pages
- connecting them to related buying-guide or FAQ content
- helping them gain contextual authority from surrounding pages

### Design rule

Money pages should benefit from relevant context, not from excessive or low-quality link stuffing.

---

## 7. Review pages

### Purpose

Review pages should connect readers to surrounding context that helps them make a decision.

### Link behavior

Review pages should link to:

- comparison pages
- alternatives pages
- pricing pages
- beginner or overview pages
- related product or service pages

### Design rule

Review pages should help the reader compare and decide rather than simply redirect them to a purchase path.

---

## 8. Comparison pages

### Purpose

Comparison pages should connect users to the most relevant alternative options and decision-support content.

### Link behavior

Comparison pages should link to:

- the reviewed or compared products
- related review pages
- pricing pages
- buying-guide pages
- use-case pages

### Design rule

Comparison pages should make the decision process easier and should guide the user toward the most relevant next step.

---

## 9. Anchor text diversity

### Purpose

Anchor text should be varied so that links feel natural and avoid over-optimization.

### Anchor types

The engine should support multiple anchor strategies:

- exact-match anchors for clear relevance
- partial-match anchors for natural phrasing
- branded anchors for authority and trust
- descriptive anchors for clarity
- generic anchors where appropriate

### Design rule

Anchor text should reflect the surrounding content and the destination page’s purpose rather than repeating the same phrase excessively.

### Recommended diversity policy

- use exact-match anchors sparingly
- use descriptive anchors often
- blend branded and topical anchors naturally
- avoid repetitive keyword stuffing

---

## 10. Link scoring

### Purpose

The engine should score each potential link so it can prioritize the strongest opportunities.

### Suggested scoring dimensions

- topical relevance
- user intent match
- page authority contribution
- contextual fit
- conversion potential
- link distance within the cluster
- freshness of the destination page
- anchor quality
- risk of over-linking

### Example scoring categories

- Relevance: how closely the two pages relate
- Intent fit: whether the link supports the reader’s next step
- Authority value: whether the link helps strengthen the target page’s role
- Conversion value: whether the link helps move a user toward a money page
- Naturalness: whether the placement and anchor feel organic

### Output

The engine should produce a ranked list of link opportunities with:

- source page
- target page
- anchor text suggestion
- score
- rationale
- placement suggestion

---

## 11. Link placement strategy

### Recommended placement rules

- place links where the reader is already considering the related topic
- use contextual links inside body content whenever possible
- use supporting links in sections such as related reads, FAQs, or next steps
- avoid crowding the same paragraph with too many links
- ensure links are useful rather than decorative

### Design rule

The engine should prioritize usefulness and readability over sheer link volume.

---

## 12. Site architecture guidance

The engine should support a site structure where:

- hub pages connect clusters
- supporting articles reinforce topical depth
- review and comparison pages support buying decisions
- money pages receive contextual authority from related content

This creates a more coherent internal linking system and strengthens the site’s topical and commercial structure.

---

## 13. Expected outcome

A well-designed internal link engine should help the site:

- distribute authority across related pages
- improve topical relevance and crawlability
- guide users through a logical content journey
- improve the performance of review, comparison, and money pages
- support better long-term content architecture
