---
name: ta-trend-systems
description: A-share trend indicator guidance for multi-period moving averages, MACD, Bollinger Bands, trendlines, and regime filters. Use when designing, reviewing, or tuning trend-following rules and signal confirmation in A-share context.
---

# TA Trend Systems

## Overview

Provide concise, A-share-specific rules for trend indicators and parameter adaptation.

## Moving Averages (MA/EMA)

- Use multi-period sets: short 5/10, mid 20/60, long 120/250.
- Prefer EMA over SMA for high-turnover small caps to reduce lag.
- Interpret alignment states: bullish stack, bearish stack, or entanglement.
- Require multi-layer resonance: short MA cross above mid MA, mid MA rising, long MA in bullish stack.

## MACD

- Avoid default 12/26/9 in high-vol A-shares; treat it as too slow.
- Consider faster params like 8/17/9 and accept more false signals.
- Prioritize divergence and histogram slope change over simple zero-cross.
- Apply regime filter: ADX>25 favors MACD trend signals; ADX<20 down-weight or pause.

## Bollinger Bands

- Adjust for A-share volatility: shorter lookback (10) and wider bands (2.5-3) if needed.
- Use squeeze (bandwidth contraction) as a breakout precondition.
- Distinguish trend runs along bands versus mean-reverting touches.

## Trendline And Support/Resistance

- Confirm breakouts on close, not intraday spikes.
- Treat >=3% close beyond key levels with volume expansion as higher quality.

## Signal Quality Rules

- Avoid single-indicator decisions.
- Require volume confirmation or multi-indicator agreement before entry.
