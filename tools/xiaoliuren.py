#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
from datetime import datetime

from core.xiaoliuren import XiaoLiuRen


def main():
    xlr = XiaoLiuRen()
    if len(sys.argv) == 1:
        result = xlr.predict()
    elif len(sys.argv) >= 4:
        year = int(sys.argv[1])
        month = int(sys.argv[2])
        day = int(sys.argv[3])
        hour = int(sys.argv[4]) if len(sys.argv) > 4 else None
        minute = int(sys.argv[5]) if len(sys.argv) > 5 else 0
        dt = datetime(
            year,
            month,
            day,
            hour if hour is not None else 0,
            minute,
        )
        result = xlr.predict(dt)
    else:
        print("用法:")
        print("  python xiaoliuren.py                # 使用当前时间")
        print("  python xiaoliuren.py 2024 8 15 14 30 # 指定时间")
        sys.exit(1)

    print(xlr.format_result(result))


if __name__ == "__main__":
    main()
