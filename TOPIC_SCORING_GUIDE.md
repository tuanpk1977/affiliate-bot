# Topic Scoring Guide

This guide explains how the topic scoring engine evaluates affiliate and content opportunities.

## Scoring factors

Each topic is scored on the following 20 factors, normalized from 0 to 100:

1. Trend Score
2. Search Intent
3. SEO Opportunity
4. Competition Level
5. Affiliate Value
6. Buyer Intent
7. CPC Potential
8. Evergreen Potential
9. Freshness
10. Social Share Potential
11. Reddit Discussion Potential
12. Quora Potential
13. LinkedIn Potential
14. YouTube Potential
15. Website Internal Linking Opportunity
16. Brand Fit
17. Difficulty
18. Estimated Traffic
19. Estimated Conversion

## Score composition

The overall topic score is computed using weighted feature values from `data/topic_scoring_rules.json`.
The engine also derives sub-scores for:

- `traffic_score`
- `revenue_score`
- `seo_score`

These sub-scores help prioritize different publish objectives.

## Recommendations

The decision engine classifies topics into:

- `High Priority`
- `Strong Candidate`
- `Opportunity`
- `Watch`
- `Skip`

Thresholds are defined in `data/topic_scoring_rules.json`.

## Content decisions

After scoring, the engine chooses a recommended publish path:

- `Website Only`
- `YouTube Only`
- `Website + YouTube`
- `Website + Shorts`
- `Social Only`
- `Skip`

The decision is based on total score, video potential, social potential, traffic strength, revenue potential, and search intent.

## Video prioritization

The video engine chooses one of:

- `No video`
- `Short`
- `Long review`
- `Comparison`
- `Tutorial`
- `Demo`

It uses YouTube potential, difficulty, buyer intent, and social momentum.

## Social score estimation

The social estimator returns a predicted engagement score for:

- Facebook
- LinkedIn
- Reddit
- Quora
- X
- Hashnode
- Dev.to
- Medium

These scores are derived from topic-level indicators like social share potential, freshness, brand fit, and business relevance.

## Dashboard readiness

The scoring output includes JSON structures that can feed dashboards for:

- `today_best_topics`
- `top_revenue_topics`
- `highest_seo_score`
- `highest_social_score`
- `video_candidates`
- `skipped_topics`

## Usage

Run the scoring script:

```powershell
python scripts/score_topics.py --input data/topic_demo_inputs.json --output data/topic_demo_output.json
```

Optional outputs:

- `--plan-output data/topic_demo_plan.json`
- `--dashboard-output data/topic_demo_dashboard.json`

## Rule customization

Edit `data/topic_scoring_rules.json` to adjust:

- global field weights
- category weights for traffic, revenue, and SEO
- recommendation thresholds
