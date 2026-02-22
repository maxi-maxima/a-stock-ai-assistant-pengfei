---
name: ta-oscillators
description: A-share oscillator guidance for RSI, KDJ, CCI, and Williams %R, including divergence, threshold tuning, and regime-aware usage. Use when designing mean-reversion signals or filtering entries in range markets.
---

# TA Oscillators

## Overview

Provide concise rules for oscillators in A-shares, with emphasis on divergence and regime filters.

## RSI

- Avoid fixed 70/30 in strong trends; widen thresholds when momentum is strong.
- Use 80/20 in trend markets, 70/30 in ranges.
- Prefer divergence signals over raw threshold crossings.
- Confirm with volume or structure to avoid counter-trend traps.

## KDJ

- Treat KDJ as sensitive and expect overbought/oversold persistence in trends.
- Use only in range markets or as divergence confirmation.
- Treat J>100 or J<0 as short-term reversal warnings, not standalone signals.

## CCI And Williams %R

- Use wider thresholds in A-shares: CCI +/-150 or +/-200 for extremes.
- Combine multiple oscillators for higher confidence.
- Treat "multi-indicator resonance" as the trigger, not a single reading.

## Regime And Multi-Timeframe Filters

- Respect higher timeframe direction; do not fade strong trends.
- If ADX<20, favor oscillators; if ADX>25, down-weight them.
