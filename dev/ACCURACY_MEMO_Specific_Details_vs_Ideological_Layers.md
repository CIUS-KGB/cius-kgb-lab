# Accuracy memo (narrative): Specific Details vs Ideological Layers (AI vs Human)

This memo explains what the current accuracy charts imply, using the UI umbrella terms:

- **Specific Details** (SD) = the pipeline’s **content categories** (`human_category`, `llm_category`)
- **Ideological Layers** (IL) = the pipeline’s **framing strategies** (`human_framing`, `llm_framing`)

These are **presentation synonyms** only; the underlying stored labels remain canonical taxonomy strings (see `docs/agents/UI_LABEL_MAP.md`).

## 1) What we measured (and what we did not)

The results come from `docs/fixtures/comparison_results.json`, specifically:

- For each document: `comparison_by_doc[doc_id].aligned_rows`
- For each aligned segment: three booleans:
  - `category_match` (SD agreement)
  - `framing_match` (IL agreement)
  - `both_match` (SD and IL both agreed)

This is **agreement with a human label** on this aligned set of segments. It is not a claim about “truth” in a philosophical sense; it is a claim about reproducibility against the project’s expert-grounded coding scheme.

In the current fixture, there are **933 aligned segments** total.

## 2) The headline: strong partial agreement, moderate full agreement

Define \(N\) as the number of aligned segments, and define the three rates:

- \(\hat p_{SD} = \frac{\#\text{category\_match}}{N}\)
- \(\hat p_{IL} = \frac{\#\text{framing\_match}}{N}\)
- \(\hat p_{Both} = \frac{\#\text{both\_match}}{N}\)

From the fixture:

- \(N = 933\)
- **Specific Details agreed**: \(677 / 933 = 72.6\%\)
- **Ideological Layers agreed**: \(711 / 933 = 76.2\%\)
- **Both agreed**: \(547 / 933 = 58.6\%\)

This implies the system is often “right in at least one way” (SD or IL), but full agreement on both dimensions happens closer to **six in ten** segments than “near perfect”.

Therefore, the AI is best described as a **high-coverage assistant** (suggestions, triage, second coder) rather than a fully automated replacement for human coding at this stage.

## 3) The 4-outcome breakdown explains the 58.6% (and why it’s still the biggest slice)

Every segment lands in exactly one bucket:

| Bucket | Meaning | Count | Share |
| --- | --- | ---: | ---: |
| **Both agreed** | SD match AND IL match | 547 | 58.6% |
| **IL only** | IL match, SD mismatch | 164 | 17.6% |
| **SD only** | SD match, IL mismatch | 130 | 13.9% |
| **Neither** | SD mismatch AND IL mismatch | 92 | 9.9% |

This implies two important things at once:

1. **The most common single outcome is full agreement** (the green slice is the largest).
2. **Room for growth is real and structured**: most of the remainder is “one dimension right” (17.6% + 13.9% = 31.5%), and a smaller portion is “neither” (9.9%).

Therefore, the fastest path to better “Both agreed” is not necessarily to solve everything at once: it may be to convert “IL only” and “SD only” segments into “Both agreed”.

This is significant because it suggests the model is often close to the target taxonomy even when it misses; that typically responds well to clearer definitions, better few-shot examples, and targeted prompt/normalization changes.

## 4) How precise are these numbers? (uncertainty and significance)

### 4.1 Full agreement is ~59%, with a fairly tight confidence band

If we treat “Both agreed” as a binomial proportion over \(N\) segments, we can put error bars on it.

Using a **Wilson 95% confidence interval**:

- \(\hat p_{Both} = 0.586\)
- **95% CI** ≈ **[0.554, 0.617]**

This implies that, for similar data, the true full-agreement rate is plausibly in the **mid‑50s to low‑60s**, not an artifact of a tiny sample.

Therefore, the “~59%” claim is stable enough to be used as a baseline KPI for future iterations.

### 4.2 Is IL agreement truly higher than SD agreement?

Because SD and IL are evaluated on the same segments, we use a paired comparison.

Let:

- \(b\) = “SD only” (SD match, IL mismatch) = 130
- \(c\) = “IL only” (SD mismatch, IL match) = 164

McNemar’s test on discordant pairs yields:

- \(b+c = 294\)
- Exact two-sided p-value ≈ **0.054**

This implies **weak / borderline evidence** that IL is easier for the AI than SD on this fixture.

Therefore, it is reasonable to phrase this as: “IL agreement is slightly higher than SD agreement in this run,” but it is **not** strong enough to claim a decisive difference without more data or replication.

This is significant because it helps prioritization: if IL is genuinely easier, then improving SD confusions may be the higher-leverage path to increasing “Both agreed”.

## 5) What each visualization contributes to the story

All SVGs live in `dev/svg_accuracy_alignment_pack_2026-05-06/`.

### 5.1 The opener (the narrative chart)

- **`agreement_outcomes_100pct.svg`**

This implies, at a glance, that full agreement is the dominant outcome while still leaving a meaningful minority of segments in partial agreement or disagreement.

Therefore, this chart is the best single-slide summary of “positive outcome + room for growth”.

### 5.2 The topline rates (what % agree on each dimension)

- **`overall_alignment_rates.svg`**

This result lends to a careful claim: “agreement is high on each individual dimension, but drops when you require both at once.”

Therefore, “Both agreed” is the correct headline metric for strict automation; SD/IL alone are supporting metrics for diagnosis.

### 5.3 Where to look next (concentration by document and label)

- **`both_match_by_document_top12.svg`** (largest documents by volume)
- **`best_documents_by_full_agreement_top12.svg`** (where the AI is strongest)
- **`both_match_by_human_category.svg`** (by SD label)
- **`both_match_by_human_framing.svg`** (by IL label)

These imply that agreement is **not uniform**: some documents and labels are much easier than others.

Therefore, improvements should be targeted: fix high-volume weak spots first (impact), while learning from the strongest pockets (what’s already working).

### 5.4 What the AI confuses (mechanism)

- **`confusion_category.svg`** (SD confusion matrix)
- **`confusion_framing.svg`** (IL confusion matrix)
- **`top_category_divergences.svg`** (most frequent SD swaps)

These imply whether errors are random noise or systematic confusions between specific labels.

Therefore, they directly inform what to change next: taxonomy definitions, prompt examples, normalization rules, or possibly label redesign (if later pursued as a migration project).
