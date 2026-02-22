---
name: trade-risk-discipline
description: Risk management and discipline guidance for A-share trading, including position sizing, stop-loss logic, risk-reward targets, and execution rules. Use when defining portfolio constraints or trading checklists.
---

# Trade Risk And Discipline

## Overview

Summarize practical risk controls and execution discipline for A-share trading.

## Position Sizing

- Set risk per trade to 2%-5% of capital based on volatility and liquidity.
- Compute size with max_loss = capital * risk_pct; size = max_loss / (entry - stop).

## Market-Regime Exposure

- Increase exposure in trend markets; reduce exposure in ranges.
- Policy-sensitive windows: reduce size and shorten holding periods.

## Stops And Exits

- Use technical stops: support breaks, trendline breaks, or neckline failures.
- Use ATR or fixed-percent stops for volatility adaptation.
- Use time stops when trades fail to progress within the planned window.

## Risk-Reward

- Require risk-reward >= 3:1 for average-quality signals.
- Allow lower RR only when multi-layer resonance is strong.

## Pyramiding And Trade Frequency

- Add only to winning positions; avoid averaging down.
- Limit daily/weekly trades to reduce overtrading costs.

## Discipline And Journaling

- Use a checklist before entry and a fixed post-trade review template.
- Log deviations between plan and execution; treat "no trade" as a valid outcome.
