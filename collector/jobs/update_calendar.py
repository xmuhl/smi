"""根据经核验的交易所年度休市配置生成本地交易日快照。"""

from __future__ import annotations

import argparse

from collector.calendar import (
    build_calendar_from_rules,
    save_calendar,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build SMI annual trading calendar"
    )
    parser.add_argument(
        "--year",
        type=int,
        required=True,
    )
    args = parser.parse_args()

    dates = build_calendar_from_rules(args.year)

    if not dates:
        raise RuntimeError(
            f"calendar for {args.year} is empty"
        )

    save_calendar(
        args.year,
        dates,
        source=[
            f"SSE_{args.year}_OFFICIAL_CLOSURES",
            "LOCAL_GENERATED",
        ],
    )

    print(
        f"CALENDAR_WRITTEN year={args.year} "
        f"trading_days={len(dates)}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
