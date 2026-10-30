# Agent evaluation report

## Run and configuration

- Agent / code revision / model:
- Prompt URI and version:
- Tracking destination / experiment / run ID and URL:
- Dataset identity / version / selected record count:
- Scorer names / criteria / definitions and versions / judge models:
- Execution mode: rerun or precomputed
- MLflow / Python / application versions:
- Command / start time / elapsed time / exit status:
- Row-level artifact path (including all record/trace IDs):

## Outcome

State whether execution and scoring completed, then summarize quality separately.
A valid zero/False is a quality failure; an absent/error assessment is a scoring gap.

| Criterion | Selected / applicable rows | Scored | Passed / failed | Missing / skipped / errors | Metric and denominator |
| --- | --- | --- | --- | --- | --- |

Do not combine unrelated scorer means or invent letter grades. For nonbinary scales,
state the range and agreed acceptance threshold rather than deriving a pass rate.

## Evidence and limitations

- Representative failures: record/trace ID or URL, actual output, score, rationale.
- Failure patterns: affected-row count / denominator, frequency, and user impact.
- Infrastructure/scoring failures: affected rows, errors, dry-run disposition.
- Before/after comparisons: fixed dataset/judge versions, row-level regressions.
- Coverage and sample-size limits; untested user journeys or missing ground truth.
- Supported diagnosis versus hypotheses requiring investigation.
- Next action tied to observed evidence; blocked work and verification still needed.
