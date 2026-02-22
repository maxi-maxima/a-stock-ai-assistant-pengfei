import numpy as np
import pandas as pd

_INDEX = None


def _clean_code(code):
    if not code:
        return ""
    code = str(code).upper()
    if "." in code:
        code = code.split(".")[0]
    return code


def _code_like(code, prefix):
    return code.startswith(prefix)


def _as_series(x, index=None):
    if isinstance(x, pd.Series):
        return x
    if index is None:
        index = _INDEX
    if isinstance(x, (list, tuple, np.ndarray, pd.Index)):
        try:
            if index is not None and len(x) == len(index):
                return pd.Series(x, index=index)
        except Exception:
            pass
    if index is not None:
        return pd.Series([x] * len(index), index=index)
    return pd.Series([x])


def _to_bool(series):
    if isinstance(series, pd.Series):
        return series.fillna(False).astype(bool)
    return bool(series)


def ref(series, n):
    series = _as_series(series)
    if isinstance(n, (int, np.integer)):
        return series.shift(int(n))
    if isinstance(n, float) and not np.isnan(n):
        return series.shift(int(n))
    n_series = _as_series(n, series.index).astype(float)
    s = series.to_numpy()
    n_arr = n_series.to_numpy()
    out = np.full(len(s), np.nan)
    for i in range(len(s)):
        ni = n_arr[i]
        if np.isnan(ni):
            continue
        ni = int(ni)
        if ni < 0:
            continue
        j = i - ni
        if j >= 0:
            out[i] = s[j]
    return pd.Series(out, index=series.index)


def refb(series, n):
    series = _as_series(series)
    return ref(series.astype(float), n) > 0.5


def ma(series, n):
    return series.ewm(span=int(n), adjust=False).mean()


def count(cond, n):
    cond = _to_bool(cond)
    if isinstance(n, (int, np.integer)):
        return cond.rolling(int(n)).sum()
    n_series = _as_series(n, cond.index).astype(float)
    c = cond.to_numpy()
    n_arr = n_series.to_numpy()
    out = np.zeros(len(c))
    for i in range(len(c)):
        ni = n_arr[i]
        if np.isnan(ni) or ni <= 0:
            out[i] = 0
            continue
        ni = int(ni)
        start = max(0, i - ni + 1)
        out[i] = c[start:i + 1].sum()
    return pd.Series(out, index=cond.index)


def every(cond, n):
    cond = _to_bool(cond)
    if isinstance(n, (int, np.integer)):
        if int(n) <= 0:
            return pd.Series([False] * len(cond), index=cond.index)
        return cond.rolling(int(n)).min().fillna(False).astype(bool)
    n_series = _as_series(n, cond.index).astype(float)
    c = cond.to_numpy()
    n_arr = n_series.to_numpy()
    out = np.zeros(len(c), dtype=bool)
    for i in range(len(c)):
        ni = n_arr[i]
        if np.isnan(ni) or ni <= 0:
            out[i] = False
            continue
        ni = int(ni)
        start = max(0, i - ni + 1)
        out[i] = bool(c[start:i + 1].all())
    return pd.Series(out, index=cond.index)


def hhv(series, n):
    if isinstance(n, (int, np.integer)):
        return series.rolling(int(n)).max()
    n_series = _as_series(n, series.index).astype(float)
    s = series.to_numpy()
    n_arr = n_series.to_numpy()
    out = np.full(len(s), np.nan)
    for i in range(len(s)):
        ni = n_arr[i]
        if np.isnan(ni) or ni <= 0:
            continue
        ni = int(ni)
        start = max(0, i - ni + 1)
        out[i] = np.nanmax(s[start:i + 1])
    return pd.Series(out, index=series.index)


def llv(series, n):
    if isinstance(n, (int, np.integer)):
        return series.rolling(int(n)).min()
    n_series = _as_series(n, series.index).astype(float)
    s = series.to_numpy()
    n_arr = n_series.to_numpy()
    out = np.full(len(s), np.nan)
    for i in range(len(s)):
        ni = n_arr[i]
        if np.isnan(ni) or ni <= 0:
            continue
        ni = int(ni)
        start = max(0, i - ni + 1)
        out[i] = np.nanmin(s[start:i + 1])
    return pd.Series(out, index=series.index)


def barslast(cond):
    cond = _to_bool(cond)
    last_idx = None
    out = np.full(len(cond), np.nan)
    for i, v in enumerate(cond.to_numpy()):
        if v:
            last_idx = i
            out[i] = 0
        else:
            if last_idx is None:
                out[i] = np.nan
            else:
                out[i] = i - last_idx
    return pd.Series(out, index=cond.index)


def barslastcount(cond):
    cond = _to_bool(cond)
    out = np.zeros(len(cond))
    cnt = 0
    for i, v in enumerate(cond.to_numpy()):
        if v:
            cnt += 1
            out[i] = cnt
        else:
            cnt = 0
            out[i] = 0
    return pd.Series(out, index=cond.index)


def cross(a, b):
    a = _as_series(a, b.index if isinstance(b, pd.Series) else None)
    b = _as_series(b, a.index)
    a_prev = a.shift(1)
    b_prev = b.shift(1)
    return (a_prev <= b_prev) & (a > b)


def exist(cond, n):
    return count(cond, n) > 0


def _round_half_up(x, digits=2):
    factor = 10 ** digits
    return np.floor(x * factor + 0.5) / factor


def ztprice(prev_close, limit):
    return _round_half_up(prev_close * (1 + limit), 2)


def _bool_last(series):
    if isinstance(series, pd.Series) and len(series) > 0:
        return bool(series.iloc[-1])
    return False


def _num_last(series):
    if isinstance(series, pd.Series) and len(series) > 0:
        try:
            val = series.iloc[-1]
            if pd.isna(val):
                return None
            return float(val)
        except Exception:
            return None
    return None


def check(df, debug=False):
    if df is None or len(df) < 100:
        return False, "insufficient_data"
    required = {"open", "close", "high", "low", "vol"}
    if not required.issubset(set(df.columns)):
        return False, "missing_columns"

    global _INDEX
    _INDEX = df.index
    code = _clean_code(df.attrs.get("ts_code", ""))
    sh = _code_like(code, "00") or _code_like(code, "60")
    sz = _code_like(code, "30") or _code_like(code, "68")
    ss = _code_like(code, "4") or _code_like(code, "8")
    if sh:
        x1 = 0.1
    elif sz:
        x1 = 0.2
    elif ss:
        x1 = 0.3
    else:
        x1 = 100

    O = df["open"].astype(float)
    C = df["close"].astype(float)
    H = df["high"].astype(float)
    L = df["low"].astype(float)
    V = df["vol"].astype(float)

    ZF = 100 * (C / ref(C, 1) - 1)
    ZT = (C == H) & (C >= ztprice(ref(C, 1), x1))
    DT = (C == L) & (ZF < -9)
    LBTS = barslastcount(ZT)
    ZB = (C < H) & (H >= ztprice(ref(C, 1), x1))
    SYX = 100 * (H - np.maximum(C, O)) / ref(C, 1)
    ST = 100 * (np.abs(C - O)) / ref(C, 1)
    XYX = 100 * (np.minimum(C, O) - L) / ref(C, 1)
    JZF = 100 * (O / ref(C, 1) - 1)
    V5 = ma(V, 5)
    V10 = ma(V, 10)
    BL = V > 2 * ref(V, 1)
    VJ = V < ref(V, 1)
    VS = V > ref(V, 1)

    ZTY = (~ZT) & (C > O) & VS & refb(ZT & (count(ZT, 5) == 1) & (ST > 7), 1)
    ZTYN = barslast(ZTY)

    cond_stsb_a = (ST > 8) & ZT & (count(ZT, 10) == 1) & (~((JZF > 1) & (XYX == 0)))
    cond_stsb_b = refb(ST > 5, 1)
    cond_stsb_bv = (C > ref(np.maximum(C, O), 1)) & refb(
        (XYX < 1.5)
        & (hhv(SYX, 10) < 6)
        & (hhv(LBTS, 30) < 4)
        & (refb(BL == 0, 1))
        & (every(VS, 3) == 0),
        1,
    )
    cond_stsb_b = np.where(cond_stsb_b, cond_stsb_bv, True)
    cond_stsb_c = (BL & refb(C < O, 1)) if sz else True
    STSB = cond_stsb_a & cond_stsb_b & cond_stsb_c

    N1 = barslast(STSB)
    T1 = cross(ref(O, N1), C) & every((C < O) & VJ & (~ZT) & (~ZB) & (ST < 5), N1 - 1) & refb(
        C < O, N1 - 1
    ) & refb(count(ZT & (C == O), 20) == 0, 1)

    N2 = barslast(T1)
    TTA = (N1 == 6) & refb(C < O, 1) & refb(JZF > 0, N1 - 1)
    TTB = (N1 == 5) & refb(JZF > 0, N1 - 1)
    TTC = (N1 == 4) & refb(C < O, N1 + 1)
    TT = TTA | TTB | TTC

    TTD = refb(
        (ST < 18)
        & (count(every((C == O) & (JZF < -9), 2), 20) == 0)
        & (~((ST > 5) & (SYX > 3) & (XYX > 3)))
        & VS,
        N1 - 1,
    )
    TTE = refb((~(BL & (C > O))) & (~((XYX > 3 * ST) & (C > O) & (N2 > 1))), 1)
    TTF = (count(refb(ST == 0, 1) & (C < ref(C, 1)), N2) == 0) & np.where(
        N2 > 30, count(BL, N1) > 0, True
    )
    TT1 = TTD & TTE & TTF

    TTG = (
        ~((JZF < 0) & (SYX > 5) & (XYX > 3) & (ST > 1))
        & np.where(VJ, refb(BL, 2), True)
        & np.where(
            (JZF > 1) & (ST > 5) & (V / ref(V, 1) > 1.15) & refb(BL, 1),
            (C < ref(C, 1))
            & refb(BL == 0, 2)
            & (V / ref(V, 1) > 1.2)
            & (XYX < 5)
            & sh,
            True,
        )
    )
    TTH = (
        np.where(SYX > 5, BL, True)
        & (~(VS & refb(BL, 1)))
        & (~((JZF > 4) & BL))
        & np.where(
            count(ZTY, 20) > 0,
            refb((V == llv(V, ZTYN)) & (C > ref(O, ZTYN + 1)), 1),
            True,
        )
    )

    TJ1 = (SYX < 3) & (every(ST > 3, 2) == 0) & refb(ST < 9, 1)
    TJ2 = ~(((llv(L, N2) / ref(L, N2) - 1) * 100 < -20) & ss)
    TJ3 = np.where(N2 <= ref(N1, N2), (N2 == 2) & refb(L, 1).eq(llv(L, N1)) & TT, True)
    TJ4 = (count(H > ref(H, N2), N2 - 1) == 1) | (count(H > ref(H, N2), N2 - 1) > 5)
    TJ5 = np.where(N1 - N2 == 2, TT1, True) & refb(TTG, N1 - 1) & refb(TTH, N1 + 1)
    TJ6 = refb(every((C > O) & (ST > 4), 4) & (V < ref(hhv(V, 3), 1)), N1) == 0
    TJ7 = refb(every(VJ, 3) & (count(BL & (C > O), 10) > 0), N1) == 0
    TJ8 = refb(ref(hhv(LBTS, 30) > 5, 30), N1) == 0
    LYTS = barslastcount(C > O)
    TJ9 = refb(count(VJ & (C < O) & refb((LYTS > 6) & refb(VJ, LYTS), 1), 15) == 0, N1)
    TJ10 = refb(count((JZF < -9) & (XYX == 0) & (count(every(ZT, 2), 10) > 0), 40) == 0, N1)
    TJ = TJ1 & TJ2 & TJ3 & TJ4 & TJ5 & TJ6 & TJ7 & TJ8 & TJ9 & TJ10

    XG1 = cross(H, ref(H, N2)) & (count(cross(H, ref(H, N2)), N2) == 1) & every((~ZT) & (~ZB), N2) & TJ

    TZ1 = (
        (~ss)
        & ZT
        & (count(ZT, 20) == 1)
        & (ST > 8)
        & (count(ZB, 5) == 0)
        & refb((BL == 0) & (hhv(LBTS, 20) < 2) & (hhv(LBTS, 60) < 3), 1)
        & (L < ref(hhv(H, 3), 1))
    )
    TZ2 = refb(TZ1, 1) & (C < O) & (V > 1.05 * ref(V, 1)) & (JZF < 5.1) & (SYX < 5) & np.where(
        refb(JZF > 3, 1), C < ref(O, 1), True
    )
    TZ3 = (
        refb(TZ2, 3)
        & refb((H < ref(H, 1)) & (JZF > -4), 2)
        & every(
            (V < ref(V, 1))
            & (L < ref(L, 1))
            & (H > ref(L, 1))
            & (np.minimum(C, O) < ref(np.minimum(C, O), 1)),
            3,
        )
        & np.where(V > ref(V, 4), refb(BL == 0, 4), True)
        & np.where(
            refb(every(VJ, 3), 5),
            refb(ST < 1.5, 5) & refb(C < O, 5) & refb(np.where(C > O, C < ref(C, 1), True), 1) & (ST < 4),
            True,
        )
        & refb(JZF < 2, 2)
    )
    NN1 = barslast(TZ1)
    NN2 = barslast(TZ3)
    TZ4 = (NN1 > NN2) & (NN2 > 0) & cross(V10, V5) & (count(cross(V10, V5), NN1) == 1) & refb(
        count(ZT, NN1) == 0, 1
    )
    TZA = TZ4 & ZT & refb(VJ & (C > O), 1)
    TZB = TZ4 & (NN2 == 1) & refb((C < O) & refb(C > O, 1), NN1 + 1) & (ST < 3) & refb(JZF > -2, 4)
    TZC = TZ4 & (NN2 == 3) & refb(C > O, 1) & refb(SYX < 5, 5) & refb(SYX < 3, 1) & (ST < 2) & np.where(
        sz, every(VJ, 6), every(VJ, 6) | refb(JZF < 0, 6)
    )
    TZD = TZ4 & (NN2 > 3) & sz & (C == llv(C, NN1))
    TZE = TZ4 & (NN2 == 2) & sz & every(VJ & (L < ref(L, 1)), 5) & refb(C < O, 4)
    TZF = (
        TZ4
        & (NN2 == 2)
        & sh
        & (ref(V, 4) > ref(V, 6))
        & refb((C < O) & (C > ref(O, 2)), 4)
        & refb(C < O, 2)
        & refb((XYX < 3) & exist(C > O, 5), 1)
        & (C > O)
        & refb(~every(C < O, 2), 7)
    )
    TZG = (
        TZ4
        & (NN2 == 2)
        & sh
        & (ref(V, 4) > ref(V, 6))
        & refb((C < O) & (C < ref(O, 2)), 4)
        & every(VJ & (H <= ref(H, 1)), 5)
        & refb(JZF > 1, 6)
    )
    TZH = (
        TZ4
        & (NN2 == 2)
        & sh
        & (ref(V, 4) < ref(V, 6))
        & refb(C > O, 4)
        & refb((C > ref(O, 2)) & (SYX < 5), 4)
        & np.where(refb(C > O, 3), llv(C, 5) < ref(O, 6), True)
        & (every(C < ma(C, 60), 3) == 0)
        & (every(JZF >= 0, 4) == 0)
    )
    TZI = (
        TZ4
        & (NN2 == 2)
        & sh
        & (ref(V, 4) < ref(V, 6))
        & refb(C < O, 4)
        & refb(JZF <= 0, 5)
        & refb((JZF > 0) & (C > ref(O, 2)), 4)
        & refb((C < ref(H, 1)) & (ZF > -5), 1)
        & (refb((O > ref(H, 1)) & (JZF > 1), 6) == 0)
    )
    TZJ = (
        TZ4
        & (NN2 == 2)
        & sh
        & (ref(V, 4) < ref(V, 6))
        & refb(C < O, 4)
        & refb(JZF > 0, 5)
        & refb(np.where(ST > 3, refb(BL, 1), True), 7)
        & refb((L < ref(H, 1)) & np.where(count(ZB, 10) > 0, C < hhv(H, 10), True), 6)
        & (llv(C, 5) > ref(O, 6))
        & (hhv(LBTS, 100) < 3)
        & refb((C < ref(C, 1)) & (SYX < 2) & (XYX < 2), 5)
        & (ST < 3)
        & (hhv(XYX, 5) < 3)
        & refb(H < ref(C, 2), 4)
    )
    TZK = (
        TZ4
        & (NN2 == 2)
        & sh
        & (ref(V, 4) < ref(V, 6))
        & refb(C < O, 4)
        & refb(JZF > 0, 5)
        & refb(np.where(ST > 3, refb(BL, 1), True), 7)
        & refb((L < ref(H, 1)) & np.where(count(ZB, 10) > 0, C < hhv(H, 10), True), 6)
        & np.where(
            (llv(C, 5) < ref(O, 6)) & VJ,
            refb(barslastcount(C > O) == 2, 1) | every(C <= O, 6) | refb(barslastcount((C < O) & (ST < 3)) == 2, 1),
            (llv(C, 5) < ref(O, 6)) & (V > ref(V, 1)) & refb(hhv(ST, 4) > 6, 1),
        )
    )

    TB1 = (
        (~ss)
        & ZT
        & (count(ZT, 20) == 1)
        & (ST > 8)
        & (count(ZB, 5) == 0)
        & refb(BL & (hhv(LBTS, 20) < 2) & (hhv(LBTS, 60) < 3), 1)
        & (L < ref(hhv(H, 3), 1))
    )
    TB2 = refb(TB1, 1) & (C < O) & (V > 1.05 * ref(V, 1)) & (JZF < 5.1) & (SYX < 5) & np.where(
        refb(JZF > 3, 1), C < ref(O, 1), True
    )
    TB3 = (
        refb(TB2, 3)
        & refb((H < ref(H, 1)) & (JZF > -4), 2)
        & every((V < ref(V, 1)) & (H < ref(H, 1)) & (H > ref(L, 1)) & (np.minimum(C, O) < ref(np.minimum(C, O), 1)), 3)
        & np.where(V > ref(V, 4), refb(BL == 0, 4), True)
        & np.where(
            refb(every(VJ, 3), 5),
            refb(ST < 1.5, 5) & refb(C < O, 5) & refb(np.where(C > O, C < ref(C, 1), True), 1) & (ST < 4),
            True,
        )
        & refb(JZF < 2, 2)
    )
    BNN1 = barslast(TB1)
    BNN2 = barslast(TB3)
    TB4 = (BNN1 > BNN2) & (BNN2 > 0) & cross(V10, V5) & (count(cross(V10, V5), BNN1) == 1) & refb(
        (count(ZT, BNN1) == 0) & BL, 1
    )

    XGA = TZA | TZB | TZC | TZD | TZE | TZF | TZG | TZH | TZI | TZJ | TZK | TB4
    TG = XG1 | XGA

    signal = _bool_last(TG)
    reason = "TDX_TG_XG1" if _bool_last(XG1) else ("TDX_TG_XGA" if _bool_last(XGA) else "")

    if not debug:
        return signal, reason

    debug_info = {
        "TG": signal,
        "XG1": _bool_last(XG1),
        "XGA": _bool_last(XGA),
        "XG1_parts": {
            "cross_H_refH": _bool_last(cross(H, ref(H, N2))),
            "count_cross_eq1": _bool_last(count(cross(H, ref(H, N2)), N2) == 1),
            "every_not_zt_zb": _bool_last(every((~ZT) & (~ZB), N2)),
            "TJ": _bool_last(TJ),
        },
        "XGA_parts": {
            "TZA": _bool_last(TZA),
            "TZB": _bool_last(TZB),
            "TZC": _bool_last(TZC),
            "TZD": _bool_last(TZD),
            "TZE": _bool_last(TZE),
            "TZF": _bool_last(TZF),
            "TZG": _bool_last(TZG),
            "TZH": _bool_last(TZH),
            "TZI": _bool_last(TZI),
            "TZJ": _bool_last(TZJ),
            "TZK": _bool_last(TZK),
            "TB4": _bool_last(TB4),
        },
        "state": {
            "N1": _num_last(N1),
            "N2": _num_last(N2),
            "NN1": _num_last(NN1),
            "NN2": _num_last(NN2),
            "BNN1": _num_last(BNN1),
            "BNN2": _num_last(BNN2),
            "TZ4": _bool_last(TZ4),
            "TJ": _bool_last(TJ),
            "TT1": _bool_last(TT1),
            "TTG": _bool_last(TTG),
            "TTH": _bool_last(TTH),
        },
    }
    return signal, reason, debug_info
