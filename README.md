# News triage: can a free LLM tell which headlines move a stock?

Every few hours this repository collects English news headlines about 40 large European companies, asks a free LLM (Gemini, free tier) to label each one, and commits the labels. Every evening it checks the labels against what the shares actually did.

Built by [Saul González](https://sagonz126.github.io) as part of a public research portfolio. Nothing here is investment advice.

## Why forward-only

Testing an LLM on old headlines is easy and usually wrong: the model may already know from its training data how the story ended. So this project only labels headlines as they arrive, and every label is committed to git before the market closes on the day it is scored. The commit history is the proof.

## The labels

For each headline the model says, from the headline alone:

| Field | Values |
| --- | --- |
| relevant | Is it really about this company, with information shareholders care about? |
| reports_price_move | Does the headline already report the share move? These are excluded from scoring. |
| direction | up, down or none, relative to the European market |
| size | noise (under 1 normal day's move), notable (1 to 2), big (over 2) |
| vol_up | Should volatility rise over the next week? |
| confidence | 0 to 1 |

The prompt is in `prompts/label_v1.txt`. It is never edited: a change becomes `label_v2`, and results are reported per version.

## How it is scored

- **Outcome:** the stock's return minus the STOXX Europe 600 return on the reaction day (the first close after the headline was seen), divided by the stock's own volatility over the previous 60 days.
- **Unit:** one company on one reaction day. If several headlines hit the same day, the one the model rated biggest counts.
- **Metrics:** size accuracy, move precision (when the model says "notable" or "big", how often the stock moved more than one normal day), move recall (of the days that moved, how many the model flagged), and direction accuracy on the days that moved.
- **Baselines:** "always no move", and a simple keyword list (`triage/baseline.py`). Most days are noise, so "always no move" wins on raw accuracy; precision and recall are where the model has to earn its keep.
- **Two samples:** all scored days, and only days where the label was committed before that day's close.
- **Human check:** a random sample of 100 headlines is labelled by hand, blind to the model and to prices.

## Limits, stated up front

- Headlines come from GDELT, which sees most stories minutes to hours after they break. The market often reacts first. This measures how well the model reads news, not a trading strategy.
- Market-adjusted returns assume a beta of one.
- GDELT matching is noisy (Shell, SAP, ABB are common words); the "relevant" field is there to filter, and its error rate is part of the result.

## Layout

```
universe.csv              companies, Yahoo tickers, exchange time zones and closes, GDELT queries
prompts/label_v1.txt      the labelling prompt
triage/fetch_news.py      GDELT headlines -> data/headlines/
triage/label.py           Gemini labels  -> data/labels/
triage/prices.py          Yahoo Finance closes, abnormal returns -> data/prices/
triage/score.py           results/results.json and results/scored_days.csv
.github/workflows/        schedules: fetch and label 4x a day, score after the European close
```

## Run it yourself

Fork, add a free Gemini key from aistudio.google.com as the repository secret `GEMINI_API_KEY`, and enable Actions.
