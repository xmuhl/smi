"""网络采集超时护栏（R12-FIX-3；复核修订 P2-4）。

背景：2026-08-18 close-snapshot 在 GitHub runner 上因数据源无响应挂起
60 分钟整（零输出）直至撞 timeout-minutes 被取消，当日数据缺失。
akshare 的多数接口内部不设请求超时，单点挂起会无限占用任务窗口。

设计：
- net_guard(timeout, retries, backoff)：把被装饰的采集函数放进单工作
  线程执行，future.result(timeout) 强制时限；超时/异常按次数重试；
- 全程串行（重试在上一次超时放弃后才开始）：THS 指数/汇总接口内部用
  py_mini_racer（V8），多线程并发会进程级崩溃（见 sectors.py 实测记录）。
  因此凡 THS/mini_racer 路径的采集（raw_archive 全部、sectors、fund_flow）
  必须 retries=0——重试线程与孤儿线程并存同样构成并发，禁止；
- 超时后孤儿线程处理（P2-4）：CPython 的 concurrent.futures 在解释器
  退出时会 join 所有 executor 工作线程，孤儿挂起线程会阻塞进程退出
  （8-18 式结局：commit 步骤被跳过）。超时路径尽力把该线程 daemon 化并
  把 executor 从模块级 join 注册表摘除（私有 API，版本兼容失败时静默
  跳过、退化为旧行为）；daemon 线程不会阻塞 threading._shutdown；
- 采集函数是只读 GET，重试幂等；最终失败抛 GuardTimeoutError/原异常，
  由各模块既有的 fail-closed 捕获路径转为 ERROR/SKIP，绝不伪造数据。
"""

from __future__ import annotations

import concurrent.futures
import functools
import time
from typing import Any, Callable


class GuardTimeoutError(RuntimeError):
    """护栏超时：被包函数在时限内未返回。"""


def _orphanify_executor(executor: concurrent.futures.ThreadPoolExecutor) -> None:
    """超时放弃后，避免孤儿线程阻塞进程退出（尽力而为的私有 API 兼容）。"""
    try:
        for thread in tuple(executor._threads):  # noqa: SLF001
            thread.daemon = True
        concurrent.futures.thread._threads_queues.pop(  # noqa: SLF001
            executor, None
        )
    except Exception:  # noqa: BLE001 私有 API 变化时退化为旧行为
        pass


def net_guard(
    timeout: float = 180.0,
    retries: int = 1,
    backoff: float = 15.0,
) -> Callable:
    """给联网采集函数加硬时限与有限重试。

    timeout  单次尝试时限（秒）
    retries  超时/异常后的额外重试次数（0 = 不重试；THS/mini_racer 必须 0）
    backoff  重试前等待（秒）
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error: BaseException | None = None

            for attempt in range(retries + 1):
                if attempt:
                    time.sleep(backoff)

                executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=1,
                    thread_name_prefix=f"netguard-{fn.__name__}",
                )
                try:
                    future = executor.submit(fn, *args, **kwargs)
                    try:
                        return future.result(timeout=timeout)
                    except concurrent.futures.TimeoutError:
                        last_error = GuardTimeoutError(
                            f"{fn.__name__} exceeded {timeout}s "
                            f"(attempt {attempt + 1}/{retries + 1})"
                        )
                        _orphanify_executor(executor)
                    except BaseException as exc:  # noqa: BLE001 原样透传
                        last_error = exc
                finally:
                    executor.shutdown(wait=False)

            assert last_error is not None
            raise last_error

        return wrapper

    return decorator
