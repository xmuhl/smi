"""多源降级：读取 config/sources.yaml，按优先级尝试数据源。

R5-P2-01 落地：sources.yaml 声明的 fallback 从此真正被消费。
调用方通过 try_sources() 依次尝试 primary/fallback 源，
任一源成功即返回，全部失败返回错误明细。
"""

from __future__ import annotations

from typing import Callable, TypeVar

from collector.config import load_yaml

T = TypeVar("T")


def source_order(
    kind: str,
    defaults: list[str],
) -> list[str]:
    """返回 sources.yaml 中 kind 的源优先级（primary + fallback，保序去重）。

    当配置文件缺失或字段异常时，回退到 defaults。
    """
    cfg = load_yaml("sources.yaml").get(kind, {})

    primary = cfg.get("primary")
    fallback = cfg.get("fallback")

    order: list[str] = []

    if isinstance(primary, str):
        order.append(primary)
    elif isinstance(primary, list):
        order.extend(str(item) for item in primary)

    if isinstance(fallback, list):
        order.extend(str(item) for item in fallback)
    elif isinstance(fallback, str):
        order.append(fallback)

    seen: set[str] = set()
    result: list[str] = []

    for item in [*order, *defaults]:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)

    return result


def try_sources(
    kind: str,
    defaults: list[str],
    call: Callable[[str], T],
) -> tuple[T | None, str | None, list[str]]:
    """按优先级调用 call(source)。

    第三个返回值始终保留前序源失败记录（R9-P3-02）：
    - 成功：返回成功值、成功源、此前失败列表（供 sourceWarnings 观测）；
    - 全失败：返回 None、None、完整失败列表。
    """
    errors: list[str] = []

    for source in source_order(kind, defaults):
        try:
            value = call(source)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source}: {exc}")
            continue

        return value, source, errors

    return None, None, errors
