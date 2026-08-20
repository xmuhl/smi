"""网络采集硬超时护栏（R13-P3-01 修订）。

背景：2026-08-18 close-snapshot 在 GitHub runner 上因数据源无响应挂起
60 分钟整（零输出）直至撞 timeout-minutes 被取消，当日数据缺失。
akshare 的多数接口内部不设请求超时，单点挂起会无限占用任务窗口。
R12 的线程方案（future.result(timeout)）只停止等待、不能终止底层调用，
且 _orphanify_executor 依赖的私有 API 按 CPython 语义不生效（运行中线程
禁止改 daemon；_threads_queues 的键是 worker Thread 而非 executor），
R13 复核确认其为 P1：挂死风险仍在。

设计（R13-P3-01 [FIX]，加 Windows spawn 兜底）：
- net_guard(timeout, retries, backoff)：把被装饰的采集函数放进独立子
  进程执行；timeout 到达后 terminate→kill 确定性终止子进程，彻底释放
  socket/mini_racer 等底层资源，不依赖 concurrent.futures 私有实现；
- 平台：POSIX 用 fork（GitHub ubuntu-latest 生产路径，开销小）；
  Windows 无 fork，用 spawn 子进程兜底（被装饰函数必须是模块级可
  pickle 函数——本项目全部采集入口均为模块级函数且懒加载 akshare，
  满足约束；不可 pickle 时 fail-closed 抛 GuardedCallError，绝不静默
  退化为不可终止线程）；
- 全程串行（重试在上一次超时终止后才开始）：THS 指数/汇总接口内部用
  py_mini_racer（V8），并发会进程级崩溃（见 sectors.py 实测记录）。
  因此凡 THS/mini_racer 路径的采集（raw_archive 全部、sectors、
  fund_flow）必须 retries=0——重试会产生并发子进程，禁止；
- 结果经 pickle 文件原子传回父进程；子进程异常优先保留原异常对象，
  异常不可序列化时退化为 GuardedCallError（保留类型/消息/traceback）；
- 采集函数是只读 GET，重试幂等；最终失败抛 GuardTimeoutError/原异常/
  GuardedCallError，由各模块既有的 fail-closed 捕获路径转为
  ERROR/SKIP，绝不伪造数据。
"""

from __future__ import annotations

import functools
import multiprocessing
import os
import pickle
import tempfile
import time
import traceback
from typing import Any, Callable


class GuardTimeoutError(RuntimeError):
    """护栏超时：隔离子进程已被终止。"""


class GuardedCallError(RuntimeError):
    """隔离调用失败且无法安全还原原异常对象（或平台/可序列化约束不满足）。"""


def _write_payload(path: str, payload: tuple[str, Any]) -> None:
    """将子进程结果原子写入临时结果文件。"""
    tmp_path = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tmp_path, "wb") as fh:
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


def _child_entry(
    result_path: str,
    fn: Callable,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    """隔离子进程入口。"""
    try:
        value = fn(*args, **kwargs)
        payload: tuple[str, Any] = ("ok", value)
    except BaseException as exc:  # noqa: BLE001
        payload = ("error", exc)

    try:
        _write_payload(result_path, payload)
    except BaseException:  # noqa: BLE001 原结果/异常不可 pickle 时退化
        fallback = (
            "error_text",
            {
                "type": type(payload[1]).__name__ if payload[0] == "error" else "ResultSerializationError",
                "message": str(payload[1]) if payload[0] == "error" else repr(type(payload[1])),
                "traceback": traceback.format_exc(),
            },
        )
        _write_payload(result_path, fallback)


def _terminate_process(process: multiprocessing.Process) -> None:
    """确定性终止隔离子进程（terminate → kill 两级）。"""
    try:
        if not process.is_alive():
            process.join(timeout=0)
            return

        process.terminate()
        process.join(timeout=2.0)

        if process.is_alive():
            process.kill()
            process.join(timeout=2.0)
    finally:
        # 释放进程句柄（Windows 上句柄不释放会让 pid 探测失真）
        try:
            process.close()
        except (ValueError, OSError):
            pass


def _pick_context(fn: Callable) -> multiprocessing.context.BaseContext:
    """选择进程启动方式：POSIX 优先 fork，否则 spawn（要求 fn 可 pickle）。"""
    if os.name == "posix":
        try:
            return multiprocessing.get_context("fork")
        except ValueError:
            pass  # 极少数 POSIX 构建无 fork，退化 spawn
    # spawn 子进程按限定名重新 import fn 所在模块：闭包/lambda/局部函数
    # 不可 pickle，直接 fail-closed，绝不退化为不可终止的线程方案。
    try:
        pickle.dumps(fn, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as exc:
        raise GuardedCallError(
            f"{getattr(fn, '__name__', fn)!r} is not picklable; net_guard "
            "spawn worker (Windows/无 fork 平台) 要求被装饰函数为模块级函数。"
            "禁止静默退化为不可终止线程。"
        ) from exc
    return multiprocessing.get_context("spawn")


def _run_once_hard_timeout(
    fn: Callable,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    timeout: float,
) -> Any:
    """在可杀死子进程中执行一次调用。"""
    if timeout <= 0:
        raise ValueError("timeout must be > 0")

    ctx = _pick_context(fn)

    with tempfile.TemporaryDirectory(prefix="smi-netguard-") as tmp_dir:
        result_path = os.path.join(tmp_dir, "result.pkl")

        process = ctx.Process(
            target=_child_entry,
            args=(result_path, fn, args, kwargs),
            daemon=False,
        )
        process.start()
        process.join(timeout=timeout)

        if process.is_alive():
            _terminate_process(process)
            raise GuardTimeoutError(
                f"{fn.__name__} exceeded {timeout}s; worker process terminated"
            )

        exit_code = process.exitcode
        process.join(timeout=0)

        if not os.path.exists(result_path):
            raise GuardedCallError(
                f"{fn.__name__} worker exited with code {exit_code} "
                "without a result payload"
            )

        with open(result_path, "rb") as fh:
            kind, payload = pickle.load(fh)

        if kind == "ok":
            return payload

        if kind == "error":
            if isinstance(payload, BaseException):
                raise payload
            raise GuardedCallError(
                f"{fn.__name__} returned an invalid exception payload: {payload!r}"
            )

        if kind == "error_text":
            info = payload if isinstance(payload, dict) else {}
            raise GuardedCallError(
                f"{fn.__name__} isolated call failed/serialization failed: "
                f"{info.get('type', 'UnknownError')}: "
                f"{info.get('message', '')}"
            )

        try:
            process.close()
        except (ValueError, OSError):
            pass

        raise GuardedCallError(
            f"{fn.__name__} returned unknown guard payload kind: {kind!r}"
        )


def net_guard(
    timeout: float = 180.0,
    retries: int = 1,
    backoff: float = 15.0,
) -> Callable:
    """给联网采集函数增加可终止的硬时限与有限重试。

    timeout  单次尝试最长执行秒数（到点终止子进程）
    retries  失败后的额外尝试次数（0 = 不重试；THS/mini_racer 必须 0）
    backoff  重试前等待秒数
    """
    if retries < 0:
        raise ValueError("retries must be >= 0")
    if backoff < 0:
        raise ValueError("backoff must be >= 0")

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 测试专用直通（仅 collector/tests/conftest.py 设置）：
            # 单测依赖进程内 monkeypatch/sys.modules 替换，子进程隔离会让
            # mock 失效并触发真实联网。生产/采集 workflow 严禁设置该变量——
            # 设置即失去硬超时护栏。
            if os.environ.get("SMI_NETGUARD_MODE") == "inline":
                return fn(*args, **kwargs)

            last_error: BaseException | None = None

            for attempt in range(retries + 1):
                if attempt:
                    time.sleep(backoff)

                try:
                    return _run_once_hard_timeout(
                        fn=fn,
                        args=args,
                        kwargs=kwargs,
                        timeout=timeout,
                    )
                except BaseException as exc:  # noqa: BLE001
                    last_error = exc

            assert last_error is not None
            raise last_error

        return wrapper

    return decorator
