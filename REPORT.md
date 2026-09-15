# r/AmITheJerk: a verdict-labeled, category-labeled dataset

## 1. The subreddit

r/AmITheJerk runs the same ritual as r/AmItheAsshole: a poster narrates a conflict they were part of,
asks whether they were in the wrong, and commenters return a verdict. The vocabulary is its own —
commenters answer **YTJ** ("you're the jerk") or **NTJ** ("not the jerk") rather than AITA's YTA/NTA.
That difference is the point of collecting it. This dataset is one arm of a comparison across the
"judge me" subreddits (r/AmItheAsshole, r/AITAH, r/AmIWrong, r/AmIOverreacting and others), built to
ask whether the verdict wording a community adopts shifts the judgment it reaches on otherwise
comparable situations — in short, whether the question does the judging.

## 2. Collecting the posts

Posts were collected from **Reddit's official API**, paging the subreddit's submission listings
newest-first until no further history was returned. The file is therefore the subreddit's complete
qualifying history rather than a capped sample — collection stopped because the listings were
exhausted, not because a row target was hit. Retrieved posts span **August 2023 to August 2026**. For
each retained post, its top-level comments were fetched, filtered to non-removed comments, sorted by
score, and the best three kept.

A post was dropped during collection if it was not a text ("self") post, if it carried an image,
gallery or video attachment, if its body was `[removed]`, `[deleted]` or empty, or if it had no
usable top-level comment left for a judge to react to:

| stage | posts |
|---|---|
| retrieved from the subreddit | 32,433 |
| dropped: image / gallery / video | −5,691 |
| dropped: removed, deleted or empty body | −1,996 |
| dropped: no usable comments | −1,576 |
| **collected** | **23,170** |

**No usernames, author IDs, or other author-identifying fields were collected or stored.** All text
comes from already-public posts; nothing private, quarantined or removed is included.

**Text cleaning.** Post titles and bodies are stripped of emoji and pictographs (including flags,
skin-tone modifiers and zero-width-joined sequences), of the invisible characters that survive
copy-paste — zero-width spaces and joiners, bidi marks, byte-order marks, soft hyphens, variation
selectors — and of the U+FFFD replacement characters left wherever an earlier encoding step lost a
byte; non-breaking spaces become ordinary spaces. This touched 1,176 titles and bodies. Ordinary
English punctuation is deliberately preserved: the corpus contains roughly 125,000 curly apostrophes
along with em dashes, ellipses, accented letters and currency symbols, and removing those would turn
"don't" into "dont". A residue remains that cleaning cannot fix: twelve posts are written in
homoglyphs, with Latin letters swapped for Cyrillic, Armenian and Lisu lookalikes to evade filters
(one reads `ꓮꓲꓔꓙ fоr dіѕtаոсіոց mуѕеꓲf`). Stripping those characters would leave gibberish, so the
posts are kept as they are and are best excluded by anyone working at the character level.

## 3. Reading the community's verdict

The point of the dataset is the community's judgment, so a post is only useful if its commenters
actually rendered one. Each post's three stored comments were scanned for verdict signals: the
subreddit's own **YTJ** / **NTJ**, the imported AITA tags **YTA** / **NTA** / **ESH** / **NAH**, and
the spelled-out forms commenters use instead of tagging ("you are the jerk", "not a jerk", "you're
not an asshole"). A comment votes for whichever verdict it mentions most; the post takes the majority
across its comments, with the highest-scoring comment breaking ties; a comment mentioning two
verdicts equally abstains.

Two distinctions matter for precision. Lowercase "nah" is *not* counted — in this corpus it is
ordinary speech ("nah bro u gotta go"), so only the capitalized **NAH** tag counts, while a phrase
like "nah, you're not the jerk" still registers through the spelled-out patterns. `INFO:` comments
are requests for detail, not verdicts, and are ignored.

**12,197 of the 23,170 posts (52.6%) carry an explicit verdict**; the other 10,973 were dropped. The
posts lost here are not junk — comments like *"You're not a charity, and her acting shocked is peak
audacity"* plainly imply a verdict — but they never state one, and inferring it would mean guessing
rather than recording what the community said.

| verdict | posts | share |
|---|---|---|
| NTJ — not the jerk | 9,909 | 81.2% |
| YTJ — you're the jerk | 2,179 | 17.9% |
| ESH — everyone sucks here | 89 | 0.7% |
| NAH — no assholes here | 20 | 0.2% |

The headline result is the imbalance: **posters are told they are not the jerk 82% of the time**, a
4.6-to-1 ratio. People bring conflicts they expect to be vindicated over, and the community obliges.

## 4. Labeling the surviving posts with three LLM judges

Each remaining post was assigned one of ten categories describing the *area* of the conflict —
`family`, `romantic_relationships`, `friendships`, `money_possessions`, `events_celebrations`,
`school`, `strangers_public`, `housing_neighbors`, `work`, `parenting_children` — by LLM judges
working from a single fixed prompt. Because several categories can plausibly fit one post, the prompt
carries an explicit precedence ladder (a dispute centered on an event beats the relationship
involved; a dispute mainly about money beats both, and so on), and each judge also returns a
**secondary category** for posts that straddle two areas, plus a confidence rating.

To keep only labels that are stable rather than coin-flips, every post was judged by **three models
from three different providers — Claude, OpenAI and DeepSeek** — each labeling the corpus
independently. A post was kept only where **at least two of the three judges chose the same primary
category**; that majority category became its label, and its secondary category and confidence were
voted the same way among the judges backing it. Posts where all three judges disagreed were dropped,
along with reposts (identical title and body) and the few posts no majority could categorize — 723
posts in total. Using three independent models removes the labels that rest on one model's
idiosyncratic reading of a borderline post, most often at the boundaries the precedence ladder
adjudicates: friendships↔school, family↔money_possessions, family↔housing_neighbors.

**Human validation.** A human annotator independently re-labeled a 5% sample (~900 posts) of the
high-confidence labels. Agreement with the model's primary category was **Cohen's κ = 0.96**, and
when a match on either the primary or the secondary category was accepted, agreement was **perfect
(1.00)** — every disagreement in the sample was a post whose true category the model had already
recorded as its second choice.

### The pipeline end to end

| step | posts remaining | lost at this step |
|---|---|---|
| retrieved from the subreddit | 32,433 | — |
| after dropping media, empty and comment-less posts | 23,170 | −9,263 |
| after dropping posts with no verdict in the comments | 12,197 | −10,973 |
| after the three-judge category consensus and dedup | **11,474** | −723 |

The result is **`data_files/verdict_categorized_posts.csv` — 11,474 posts**, each carrying both what the community
decided and what the conflict was about:

| category | posts | | category | posts |
|---|---|---|---|---|
| family | 2,420 | | school | 1,056 |
| friendships | 1,799 | | work | 726 |
| romantic_relationships | 1,667 | | housing_neighbors | 703 |
| money_possessions | 1,145 | | strangers_public | 688 |
| events_celebrations | 1,071 | | parenting_children | 199 |

9,837 of the labels are high confidence and 4,496 posts carry a secondary category.

## 5. Columns stored

| column | description |
|---|---|
| `row_id` | Index of the post in the collected file, stable across the whole pipeline. |
| `title` | The question as the poster asked it. |
| `content` | The full body text — the poster's account of the situation. Never empty. |
| `link` | Permanent Reddit URL of the post. |
| `upvotes` | Score (upvotes minus downvotes) at scrape time. |
| `upvote_ordinal` | The score binned into six ordered traction bands (see below). |
| `comments` | Total comments Reddit reported at scrape time. |
| `comment1`–`comment3` | The three highest-scoring top-level comments, non-removed. |
| `community_prediction` | The verdict the commenters reached: `YTJ`, `NTJ`, `ESH` or `NAH`. Never empty in this file. |
| `category` | The agreed category, one of the ten above. |
| `secondary_category` | A second category when the post straddles two areas, otherwise `none`. |
| `confidence` | The judges' confidence in the category: `high`, `medium` or `low`. |

Post scores are heavily skewed — a median of 9 against a maximum of 23,146 — so raw `upvotes` behave
badly as a continuous variable. `upvote_ordinal` bins them into six log-scaled, ordered bands:

| band | posts | share | | band | posts | share |
|---|---|---|---|---|---|---|
| `0` | 1,501 | 13.1% | | `20-99` | 2,392 | 20.8% |
| `1-4` | 3,264 | 28.4% | | `100-999` | 1,385 | 12.1% |
| `5-19` | 2,695 | 23.5% | | `1000+` | 237 | 2.1% |

Attention is not spread evenly across conflict types (χ²(45) = 1,257, p < 0.001, Cramér's V = 0.148):
median score runs from 24 for `work` and 20 for `money_possessions` down to 3 for `school` and 4 for
`strangers_public`. Nor is vindication — the NTJ rate ranges from **88% for `work`** disputes down to
**67% for `parenting_children`** and 72% for `romantic_relationships`, so how likely a poster is to be
told they were in the right depends materially on what the fight was about.
