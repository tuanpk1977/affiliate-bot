# Quality Score Engine

Score each article from 0 to 100 before it is treated as reviewable.

## Scoring

- structure: 15
- SEO readiness: 10
- human readability: 15
- EEAT and trust: 15
- HTML/public safety: 10
- consistency with blueprint: 10
- fingerprint similarity: 10
- internal/external linking: 5
- research/source quality: 10

## Passing Thresholds

Reviewable draft: 70+ with no hard blockers.

Strong draft: 82+ with only warning-level issues.

Publish candidate: must pass publish gate and human approval regardless of score.

## Automatic Fail

Score is capped at 50 if sources are weak. Score is capped at 40 if the article has duplicate paragraphs or missing FAQ where required. Score is zero for entity mismatch, fabricated sources, or public workflow marker leakage.
