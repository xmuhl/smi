# SMI R13 送审复核报告 — Part 2（源码定点复核）

**文件名：** `SMI_R13_Review_Report_Part2.md`  
**复核日期：** 2026-08-20  
**复核对象：** `SMI_R13_source_20260820.zip`  
**限定范围：** 仅定点读取用户指定的 7 个文件，未遍历/审查其他源码文件：

1. `smi/config/tracks.yaml`
2. `smi/config/track-scoring.yaml`
3. `smi/collector/netguard.py`
4. `smi/tools/acceptance/accept.py`
5. `smi/.github/workflows/close-snapshot.yml`
6. `smi/.github/workflows/archive-raw.yml`
7. `smi/web/src/composables/useSnapshots.ts`

**工作区声明：** **未修改调用方本地工作区；未运行调用方项目测试；未更新 manifest；未重新打包。**  
本报告中的 `[FIX:]` 是可应用修订建议，不代表调用方文件已经被修改。

---

# 1. 总体结论

## 1.1 本步新增问题

| 编号 | 严重度 | 状态 | 摘要 |
|---|---|---|---|
| R13-P3-01 | **P1** | NOT_CLOSED | `netguard` 的“硬超时/孤儿线程退出保护”实际不能终止底层调用，且 `_orphanify_executor()` 的实现按 CPython 语义不会生效 |
| R13-P3-02 | P2 | NOT_CLOSED | acceptance 未校验 daily 文件名 ↔ snapshot.tradeDate，也未读取/核对 latest.json ↔ manifest 三指针身份 |
| R13-P3-03 | P2 | NOT_CLOSED | close-snapshot 发布自检只验证 `updatedAt >= jobStart`，不验证线上内容与本地构建产物/目标 tradeDate 身份一致 |
| R13-P3-04 | P2 | NOT_CLOSED | archive-raw 发布自检会跳过缺失的预期 JSONL，只要至少 1 个文件存在并匹配即可 PASS |
| R13-P3-05 | P3 | NOT_CLOSED | `useDailySnapshot.load()` 无请求序列保护，快速切换日期时旧请求可能覆盖新请求结果 |

**本步新增：P1=1 / P2=3 / P3=1。**

## 1.2 Part 1 两项结论经配置源码复核后的状态

| 编号 | 状态 | 源码复核结论 |
|---|---|---|
| R13-P2-01 | **NOT_CLOSED（确认）** | `tracks.yaml` 仍是 `poolSize: 8`、5 日成交额窗口、`requirePositiveInflow: true`；未见预热池、入/出池迟滞、历史就绪门禁等缓解配置 |
| R13-P2-02 | **NOT_CLOSED（确认）** | `track-scoring.yaml` 只有 `coverage_warn_pct: 80`，未见 target/hard-floor/DEGRADED 分层阈值；结合送审说明 71.4%→UNAVAILABLE 的线上事实，Part 1 对单阈值过紧的结论不变 |

> 限定：本步没有读取 `collector/calculators/tracks.py`，因此不能从实现内部证明 `coverage_warn_pct` 如何被消费；这里仅确认**配置层没有 Part 1 建议的缓解机制**，并结合送审说明已给出的线上决策事实判断。

## 1.3 已确认 CLOSED/正确的 R12 内容

- 四维权重 **25/35/25/15 配置正确且总和 100**：
  - 资金：10+10+5=25
  - 趋势：10+10+15=35
  - 情绪：8+8+9=25
  - 逻辑：8+7=15
- `close-snapshot.yml`：Node `22`。
- `archive-raw.yml`：Node `22`。
- 两个数据写 workflow 的 concurrency group 均为：
  `smi-data-write-${{ github.ref }}`
- 两者均为：
  `cancel-in-progress: false`
- 因此在**同一 ref** 上，close/archive 不会互相取消，后到任务排队等待，符合数据写串行化方向。

---

# 2. 文件级复核

# 2.1 `smi/config/tracks.yaml`

## 读取到的关键事实

- `configVersion: "3.0"`
- `effectiveFrom: "2026-08-20"`
- `selection.poolSize: 8`
- `selection.amountWindowDays: 5`
- `selection.requirePositiveInflow: true`
- 动态候选与 4 个种子赛道并存。
- 板块元数据不存在时明确 fail-closed，不伪造定性文案。
- THS 名称映射缺失时明确 UNAVAILABLE。
- `industry-universe` 快照作为资金/连续流入/红盘比例首选口径。

## 判断

方向上与 R12 方案一致；但没有看到以下机制：

- discovery/prewarm/scoring 三层池；
- 新候选历史预热；
- 连续两日/窗口式入池确认；
- 排名入池/出池双阈值；
- `WARMING_UP` 与 `FETCH_FAILED` 状态分离。

因此 **R13-P2-01 保持 NOT_CLOSED**，不重复另立代码级编号。

---

# 2.2 `smi/config/track-scoring.yaml`

## 四维权重核验

配置：

```text
资金：
turnover_rank 10
main_net_inflow 10
continuous_inflow_days 5
= 25

趋势：
ma_alignment 10
rps60 10
excess_return_20d 15
= 35

情绪：
limit_up 8
ladder_completeness 8
red_stock_ratio 9
= 25

逻辑：
core_catalyst 8
earnings_realization 7
= 15
```

总计 100，**与送审说明的 25/35/25/15 一致，CLOSED。**

## coverage 配置

仅看到：

```yaml
decision:
  pass_min: 75
  watch_min: 55
  coverage_warn_pct: 80
  secondary_missing_dimensions_allowed: 1
```

没有：

- `coverage_target_pct`
- `coverage_hard_floor_pct`
- `PARTIAL/DEGRADED` 区间
- 关键维度与非关键维度的独立门禁

因此 **R13-P2-02 保持 NOT_CLOSED**。

---

# 2.3 `smi/collector/netguard.py`

## R13-P3-01 — “硬超时”没有真正中止联网调用，孤儿线程退出修复实际失效

**严重度：P1**  
**状态：NOT_CLOSED**

### 定位

`netguard.py`：

- 68-75：`ThreadPoolExecutor` + `future.result(timeout=timeout)`
- 76-81：超时后调用 `_orphanify_executor`
- 35-44：`_orphanify_executor`
- 85：`executor.shutdown(wait=False)`

### 证据

实现核心为：

```python
future = executor.submit(fn, *args, **kwargs)
return future.result(timeout=timeout)
```

`Future.result(timeout)` 只停止**等待**，不会取消已经开始执行的 Python 线程。

随后 `_orphanify_executor()`：

```python
for thread in tuple(executor._threads):
    thread.daemon = True
concurrent.futures.thread._threads_queues.pop(executor, None)
```

这里存在两个确定性语义错误：

1. **运行中的 `threading.Thread` 不能再修改 daemon 属性。**
   `Thread.daemon` 在线程已启动后赋值会抛 `RuntimeError("cannot set daemon status of active thread")`。
   外层 `except Exception: pass` 会把该错误吞掉。

2. **`concurrent.futures.thread._threads_queues` 的键是 worker `Thread`，不是 executor。**
   因此即使执行到 `pop(executor, None)`，也不会删除对应 worker。

结果是：注释所声称的“daemon 化 + 从退出 join 注册表摘除”并未实际完成。

此外，即便能够让进程退出不等待，**仍然没有终止底层网络/mini_racer 调用**。超时线程仍可能：

- 继续持有 socket/session；
- 在主调用已返回后继续访问 C 扩展/V8；
- 与后续 collector 操作重叠；
- 对 `retries>0` 路径形成真正的并发孤儿调用。

这与文件注释中“全程串行”“超时强制时限”的安全目标不一致。

### 根因

把“调用方等待超时”误当成“被调用任务被终止”；并依赖 CPython 私有线程注册结构尝试补救，但实现对象类型和线程 daemon 生命周期均不成立。

### 影响

这是 R12 防止 2026-08-18 式 60 分钟挂死的关键护栏。当前实现仍可能在：

- 底层网络永久阻塞；
- THS/mini_racer 卡死；
- Python 解释器退出；

等阶段再次形成工作流长时间挂起或进程无法正常退出。

因此严重度定为 **P1**。

### 建议

真正的“hard timeout”需要**可杀死的隔离边界**：

1. 首选：底层 HTTP 客户端原生 connect/read timeout；
2. 对 AKShare/THS 等无法保证超时的黑盒调用，用**子进程**执行；
3. timeout 时 `terminate()`，必要时 `kill()`，然后 `join()`；
4. 不再依赖 `ThreadPoolExecutor` 私有 `_threads_queues`；
5. THS/mini_racer 保持 `retries=0`；
6. 子进程返回值必须可序列化；生产环境为 GitHub `ubuntu-latest`，可以显式使用 POSIX `fork`。

---

## [FIX:R13-P3-01]

**路径：** `smi/collector/netguard.py`  
**建议：完整替换该文件。**

```python
"""网络采集硬超时护栏。

设计目标：
1. timeout 到达后不仅停止等待，而且终止执行采集函数的隔离进程；
2. 不依赖 concurrent.futures / threading 私有退出实现；
3. THS / py_mini_racer 路径继续使用 retries=0；
4. 成功结果通过 pickle 文件返回父进程；
5. 子进程异常优先保留原异常对象；若异常不可序列化则退化为
   GuardedCallError，并保留异常类型、消息和 traceback。

注意：
- 当前生产 workflow 为 GitHub ubuntu-latest，本实现使用 POSIX fork。
- 若未来把真实采集运行环境迁移到 Windows，应另行设计 spawn-safe worker
  协议，不能静默退化回不可终止线程。
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
    """护栏超时：隔离进程已被终止。"""


class GuardedCallError(RuntimeError):
    """隔离调用失败且无法安全还原原异常对象。"""


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
    """隔离进程入口。"""
    try:
        value = fn(*args, **kwargs)
        payload: tuple[str, Any] = ("ok", value)
    except BaseException as exc:  # noqa: BLE001
        payload = ("error", exc)

    try:
        _write_payload(result_path, payload)
    except BaseException as serialization_exc:  # noqa: BLE001
        # 原结果/异常不可 pickle 时，只传递纯字符串诊断信息。
        fallback = (
            "error_text",
            {
                "type": type(serialization_exc).__name__,
                "message": str(serialization_exc),
                "traceback": traceback.format_exc(),
            },
        )
        _write_payload(result_path, fallback)


def _terminate_process(process: multiprocessing.Process) -> None:
    """确定性终止隔离进程。"""
    if not process.is_alive():
        process.join(timeout=0)
        return

    process.terminate()
    process.join(timeout=2.0)

    if process.is_alive():
        # Python 3.7+ multiprocessing.Process.kill
        process.kill()
        process.join(timeout=2.0)


def _run_once_hard_timeout(
    fn: Callable,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    timeout: float,
) -> Any:
    """在可杀死子进程中执行一次调用。"""
    if timeout <= 0:
        raise ValueError("timeout must be > 0")

    try:
        ctx = multiprocessing.get_context("fork")
    except ValueError as exc:
        raise GuardedCallError(
            "net_guard hard-timeout requires POSIX 'fork'; "
            "do not fall back to an unkillable worker thread"
        ) from exc

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
                f"{info.get('message', '')}\n"
                f"{info.get('traceback', '')}"
            )

        raise GuardedCallError(
            f"{fn.__name__} returned unknown guard payload kind: {kind!r}"
        )


def net_guard(
    timeout: float = 180.0,
    retries: int = 1,
    backoff: float = 15.0,
) -> Callable:
    """给联网采集函数增加可终止的硬时限与有限重试。

    timeout:
        单次尝试最长执行秒数。
    retries:
        失败后的额外尝试次数。
        THS / py_mini_racer 路径必须保持 0，避免业务语义上的重复调用。
    backoff:
        重试前等待秒数。
    """
    if retries < 0:
        raise ValueError("retries must be >= 0")
    if backoff < 0:
        raise ValueError("backoff must be >= 0")

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
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
```

### 应用后必须验证

至少增加以下确定性测试：

1. worker `sleep(timeout * 10)`：父调用在 timeout 附近返回 `GuardTimeoutError`；
2. timeout 后检查 worker PID 已不存在；
3. 连续 timeout 后 Python 进程能立即退出；
4. `retries=1`：第一次失败、第二次成功；
5. THS 模拟调用 `retries=0`：绝不产生第二个子进程；
6. DataFrame/常用 AKShare 返回类型可序列化；
7. 异常对象不可 pickle 时仍 fail-closed；
8. 删除 `_terminate_process()` 的 kill 分支后，故障测试必须 red。

---

# 2.4 `smi/tools/acceptance/accept.py`

## 已确认的正确行为

### margin 的 PENDING 与 FINAL 有显式区分

`check_margin()`：

- `status == "FINAL"`：执行正式余额/日期等规则；
- `status == "PENDING"`：
  - 要求 `tradeDate == manifest.latestCapturedDate`
  - 要求 `latestPublishedReference` 有效
  - 要求 `reference.dataDate < tradeDate`
  - 回读 reference 对应 daily 快照，并确认 margin 为 FINAL
- 其他非法状态进入 gap。

因此 **margin PENDING 没有简单压平为 ERROR**。

### 通用字段具备 per-state `skipStates`

`_validate_field_values()` 会读取标准中的 `skipStates`，状态豁免由标准驱动，而不是代码私自放宽。这一方向正确。

### 限定结论

`PARTIAL / UNAVAILABLE / ERROR` 对其它模块最终是否合法，依赖
`docs/acceptance/template-standard.json` 中的 `requiredStatus/skipStates`。
本步按用户限制没有读取该标准文件，因此这部分只能标为 **UNKNOWN**，不能伪称完全 CLOSED。

---

## R13-P3-02 — acceptance 缺少 daily/latest/manifest 顶层身份闭合

**严重度：P2**  
**状态：NOT_CLOSED**

### 定位

`build_entry()` 约 2293-2320；`main()` 约 2418-2431。

### 证据

`build_entry(trade_date, ...)`：

1. 按传入日期拼路径：
   `daily/YYYY/YYYY-MM-DD.json`
2. JSON 能加载后就直接：
   `evaluate_modules(snapshot, ..., trade_date, ...)`
3. 随后固定：
   `schemaValid: True`

没有检查：

```text
snapshot["tradeDate"] == 文件名 trade_date
```

全文件也没有读取：

```text
web/public/data/latest.json
```

manifest 方面，本文件主要使用：

- `availableDates`
- `latestCapturedDate`（margin PENDING）

没有建立以下身份不变量：

- `manifest.latestDate == manifest.latestCapturedDate`
- `latestFinalDate <= latestCloseCompleteDate <= latestCapturedDate`
- 三个非空 pointer 必须属于 `availableDates`
- `latest.json.tradeDate == manifest.latestCapturedDate`
- `daily/<latestCapturedDate>.json.tradeDate == latestCapturedDate`

### 根因

acceptance 强化了模块内部字段和跨模块 invariant，但没有把“文件路径/根快照/manifest/latest”视作独立的顶层身份事务。

### 影响

可能出现：

- 文件名是 2026-08-20，但内容根 `tradeDate=2026-08-19`；
- manifest 指向 08-20，latest.json 仍指向 08-19；
- 三指针顺序错误；

而验收器仍进入模块验收，甚至 `schemaValid=True`。

这会削弱 R10 以后建立的三指针完整性模型。

---

## [FIX:R13-P3-02]

**路径：** `smi/tools/acceptance/accept.py`

### A. 常量区增加

```python
LATEST_PATH = os.path.join("web", "public", "data", "latest.json")
```

### B. 新增完整身份预检函数

```python
def _validate_manifest_latest_identity(manifest, daily_dir=None):
    """校验 manifest/latest/daily 顶层身份闭合。

    返回 gap 字符串列表；空列表表示通过。
    """
    daily_dir = daily_dir or DAILY_DIR
    gaps = []

    if not isinstance(manifest, dict):
        return ["manifest 不是 object"]

    available = manifest.get("availableDates")
    if not isinstance(available, list) or not all(
        isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v)
        for v in available
    ):
        return ["manifest.availableDates 非严格 YYYY-MM-DD 字符串数组"]

    if len(available) != len(set(available)):
        gaps.append("manifest.availableDates 存在重复日期")

    if available != sorted(available):
        gaps.append("manifest.availableDates 必须按日期升序排列")

    captured = manifest.get("latestCapturedDate")
    close_complete = manifest.get("latestCloseCompleteDate")
    final = manifest.get("latestFinalDate")
    latest_alias = manifest.get("latestDate")

    if available:
        if captured != available[-1]:
            gaps.append(
                "manifest.latestCapturedDate "
                f"{captured!r} != availableDates 最大日期 {available[-1]!r}"
            )
    elif captured is not None:
        gaps.append(
            "availableDates 为空时 latestCapturedDate 必须为 null"
        )

    if latest_alias != captured:
        gaps.append(
            f"manifest.latestDate {latest_alias!r} "
            f"!= latestCapturedDate {captured!r}"
        )

    for name, value in (
        ("latestCapturedDate", captured),
        ("latestCloseCompleteDate", close_complete),
        ("latestFinalDate", final),
    ):
        if value is None:
            continue
        if value not in available:
            gaps.append(
                f"manifest.{name}={value!r} 不在 availableDates 中"
            )

    non_null_chain = [
        value
        for value in (final, close_complete, captured)
        if value is not None
    ]
    if non_null_chain != sorted(non_null_chain):
        gaps.append(
            "manifest 三指针顺序必须满足 "
            "latestFinalDate <= latestCloseCompleteDate <= latestCapturedDate"
        )

    if captured is None:
        if os.path.exists(LATEST_PATH):
            gaps.append(
                "latestCapturedDate=null 但 latest.json 仍存在"
            )
        return gaps

    if not os.path.exists(LATEST_PATH):
        gaps.append(f"latest.json 缺失: {LATEST_PATH}")
        return gaps

    try:
        with open(LATEST_PATH, "r", encoding="utf-8") as fh:
            latest_snapshot = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        gaps.append(f"latest.json 无法读取/解析: {exc}")
        return gaps

    latest_trade_date = (
        latest_snapshot.get("tradeDate")
        if isinstance(latest_snapshot, dict)
        else None
    )
    if latest_trade_date != captured:
        gaps.append(
            f"latest.json.tradeDate={latest_trade_date!r} "
            f"!= manifest.latestCapturedDate={captured!r}"
        )

    daily_path = os.path.join(
        daily_dir,
        captured[:4],
        f"{captured}.json",
    )
    if not os.path.exists(daily_path):
        gaps.append(
            f"latestCapturedDate 对应 daily 文件缺失: {daily_path}"
        )
        return gaps

    try:
        with open(daily_path, "r", encoding="utf-8") as fh:
            daily_snapshot = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        gaps.append(
            f"latestCapturedDate 对应 daily 文件无法读取/解析: {exc}"
        )
        return gaps

    daily_trade_date = (
        daily_snapshot.get("tradeDate")
        if isinstance(daily_snapshot, dict)
        else None
    )
    if daily_trade_date != captured:
        gaps.append(
            f"{daily_path}.tradeDate={daily_trade_date!r} "
            f"!= {captured!r}"
        )

    return gaps
```

### C. 完整替换 `build_entry`

```python
def build_entry(trade_date, manifest, standard, daily_dir=None):
    daily_dir = daily_dir or DAILY_DIR
    yyyy = trade_date[:4]
    path = os.path.join(daily_dir, yyyy, f"{trade_date}.json")
    modules_out = {}

    if not os.path.exists(path):
        for name in MODULE_ORDER:
            modules_out[name] = _result(
                "_",
                False,
                [_detail_gap("FILE_MISSING")],
                "_",
            )
        return {
            "gap": "FILE_MISSING",
            "schemaValid": False,
            "modules": modules_out,
            "overall": "FAIL",
            "pass": False,
        }

    try:
        with open(path, "r", encoding="utf-8") as fh:
            snapshot = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        for name in MODULE_ORDER:
            modules_out[name] = _result(
                "_",
                False,
                [_detail_gap(f"FILE_INVALID: {exc}")],
                "_",
            )
        return {
            "gap": "FILE_INVALID",
            "schemaValid": False,
            "modules": modules_out,
            "overall": "FAIL",
            "pass": False,
        }

    actual_trade_date = (
        snapshot.get("tradeDate")
        if isinstance(snapshot, dict)
        else None
    )
    if actual_trade_date != trade_date:
        msg = (
            "SNAPSHOT_IDENTITY_MISMATCH: "
            f"pathDate={trade_date!r}, "
            f"snapshot.tradeDate={actual_trade_date!r}"
        )
        for name in MODULE_ORDER:
            modules_out[name] = _result(
                "_",
                False,
                [_detail_gap(msg)],
                "_",
            )
        return {
            "gap": "SNAPSHOT_IDENTITY_MISMATCH",
            "schemaValid": False,
            "modules": modules_out,
            "overall": "FAIL",
            "pass": False,
        }

    checks, all_pass, inv_results = evaluate_modules(
        snapshot,
        standard,
        trade_date,
        manifest,
        daily_dir,
    )

    return {
        "gap": None,
        "schemaValid": True,
        "modules": checks,
        "invariants": inv_results,
        "overall": "PASS" if all_pass else "FAIL",
        "pass": all_pass,
    }
```

### D. 完整替换 `main`

```python
def main(argv=None):
    parser = argparse.ArgumentParser(description="SMI 数据侧验收器 v2")
    parser.add_argument("--date", dest="date", help="验收单个日期 YYYY-MM-DD")
    parser.add_argument(
        "--all",
        action="store_true",
        help="验收 manifest 全部 availableDates",
    )
    parser.add_argument(
        "--report",
        default=DEFAULT_REPORT,
        help="报告输出路径",
    )
    args = parser.parse_args(argv)

    try:
        standard = load_standard()
    except FileNotFoundError:
        sys.stderr.write(f"验收标准缺失: {STANDARD_PATH}\n")
        return 2

    self_check_errors = startup_self_check(standard)
    if self_check_errors:
        for error in self_check_errors:
            sys.stderr.write(f"自检失败: {error}\n")
        return 3

    if not os.path.exists(MANIFEST_PATH):
        sys.stderr.write(f"日期清单缺失: {MANIFEST_PATH}\n")
        return 2

    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"manifest 无法读取/解析: {exc}\n")
        return 2

    identity_errors = _validate_manifest_latest_identity(
        manifest,
        DAILY_DIR,
    )
    if identity_errors:
        for error in identity_errors:
            sys.stderr.write(f"身份自检失败: {error}\n")
        return 4

    if args.date:
        dates = [args.date]
    else:
        dates = list(manifest.get("availableDates", []))

    entries = {}
    for trade_date in dates:
        entries[trade_date] = build_entry(
            trade_date,
            manifest,
            standard,
        )
        print(console_line(trade_date, entries[trade_date]))

    pass_dates = [d for d in dates if entries[d]["pass"]]
    fail_dates = [d for d in dates if not entries[d]["pass"]]
    module_fail = {name: [] for name in MODULE_ORDER}

    for date in dates:
        for name in MODULE_ORDER:
            if not entries[date]["modules"].get(name, {}).get("pass"):
                module_fail[name].append(date)

    print()
    print(
        f"汇总：PASS={len(pass_dates)}  "
        f"FAIL={len(fail_dates)}  共 {len(dates)} 个日期"
    )
    print(f"passDates: {pass_dates}")
    print(f"failDates: {fail_dates}")
    print("各模块失败日期数：")

    for name in MODULE_ORDER:
        print(f"  {name:<16} failDates={len(module_fail[name])}")
        if module_fail[name]:
            print(f"    dates: {module_fail[name]}")

    report = build_report(dates, entries, standard, manifest)
    report_dir = os.path.dirname(os.path.abspath(args.report))
    os.makedirs(report_dir, exist_ok=True)

    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print()
    print(f"报告已写入: {args.report}")
    return 0
```

### 应用后必须增加的负向测试

- 文件名 08-20、根 `tradeDate=08-19` → FAIL；
- `latestDate != latestCapturedDate` → 启动失败；
- `latestFinalDate > latestCloseCompleteDate` → 启动失败；
- pointer 不在 `availableDates` → 启动失败；
- `latest.json.tradeDate != latestCapturedDate` → 启动失败；
- latestCaptured 对应 daily 缺失 → 启动失败。

---

# 2.5 `smi/.github/workflows/close-snapshot.yml`

## 已确认 CLOSED

### Node 22

```yaml
uses: actions/setup-node@v4
with:
  node-version: "22"
```

符合 wrangler 4.122.0 的送审修复目标。

### concurrency

```yaml
concurrency:
  group: smi-data-write-${{ github.ref }}
  cancel-in-progress: false
```

与 archive-raw 完全一致。

同一 ref 下：

- 正在写数据的 workflow 不会被新任务取消；
- 新任务排队；
- 避免两个 workflow 同时 commit/push 相同分支数据。

方向正确。

---

## R13-P3-03 — 部署 freshness 自检不能证明“部署的是本次正确快照”

**严重度：P2**  
**状态：NOT_CLOSED**

### 定位

`close-snapshot.yml` 117-155 附近。

### 当前逻辑

线上下载 `latest.json` 后，仅检查：

```text
online.updatedAt >= JOB_START_UTC
```

虽然也解析了 `tradeDate`，但只打印，不参与 verdict。

### 根因

用时间新鲜度代替内容身份。

### 影响

如果某个错误路径生成了：

- updatedAt 是新的；
- 但 tradeDate/revision/内容错误；

自检仍可能得到 `SITE_FRESH`。

这与验收要求中的“最终权威产物身份”并不等价。

### 建议

部署自检直接比较：

```text
web/dist/data/latest.json
VS
线上 /data/latest.json
```

的 SHA-256。

静态文件部署场景下，这是比 `updatedAt` 更强且更简单的证据，同时自动覆盖：

- tradeDate
- revision
- updatedAt
- modules 内容

---

## [FIX:R13-P3-03]

**路径：** `smi/.github/workflows/close-snapshot.yml`  
**完整替换 `Verify deployment freshness` step：**

```yaml
      - name: Verify deployment freshness
        if: steps.commit.outputs.changed == 'true'
        run: |
          set -euo pipefail

          SITE="https://smi-6s2.pages.dev/data/latest.json"
          LOCAL="web/dist/data/latest.json"
          REMOTE="/tmp/smi-site-latest.json"

          if [ ! -s "$LOCAL" ]; then
            echo "LOCAL_LATEST_MISSING_OR_EMPTY: $LOCAL"
            exit 1
          fi

          LOCAL_SHA256="$(sha256sum "$LOCAL" | cut -d' ' -f1)"
          LOCAL_TRADE_DATE="$(
            python3 -c '
          import json, sys
          with open(sys.argv[1], "r", encoding="utf-8") as fh:
              data = json.load(fh)
          print(data.get("tradeDate", ""))
          ' "$LOCAL"
          )"

          if [ -z "$LOCAL_TRADE_DATE" ]; then
            echo "LOCAL_LATEST_TRADE_DATE_MISSING"
            exit 1
          fi

          for attempt in 1 2 3 4 5 6; do
            sleep 30
            rm -f "$REMOTE"

            if ! curl -fsS --max-time 20 \
              -H 'Cache-Control: no-cache' \
              "$SITE" \
              -o "$REMOTE"; then
              echo "attempt=$attempt site unreachable"
              continue
            fi

            SITE_SHA256="$(sha256sum "$REMOTE" | cut -d' ' -f1)"
            SITE_TRADE_DATE="$(
              python3 -c '
          import json, sys
          try:
              with open(sys.argv[1], "r", encoding="utf-8") as fh:
                  data = json.load(fh)
          except Exception:
              print("")
              raise SystemExit(0)
          print(data.get("tradeDate", ""))
          ' "$REMOTE"
            )"

            echo \
              "attempt=$attempt " \
              "localTradeDate=$LOCAL_TRADE_DATE " \
              "siteTradeDate=$SITE_TRADE_DATE " \
              "localSha256=$LOCAL_SHA256 " \
              "siteSha256=$SITE_SHA256"

            if [ "$SITE_TRADE_DATE" = "$LOCAL_TRADE_DATE" ] && \
               [ "$SITE_SHA256" = "$LOCAL_SHA256" ]; then
              echo "SITE_LATEST_EXACT_MATCH"
              exit 0
            fi
          done

          echo "SITE_LATEST_MISMATCH_OR_UNREACHABLE after deploy"
          exit 1
```

---

# 2.6 `smi/.github/workflows/archive-raw.yml`

## 已确认 CLOSED

### Node 22

明确：

```yaml
node-version: "22"
```

### concurrency

与 close-snapshot 相同：

```yaml
group: smi-data-write-${{ github.ref }}
cancel-in-progress: false
```

### archive transaction failure 门禁

本文件先记录 archive 进程真实 rc，只有：

```text
exit_code == 0
```

才允许进入 Git commit 外部副作用。

`rc=1/2` 在 build/deploy 前传播失败。

这一 fail-closed 方向正确。

---

## R13-P3-04 — archive 发布自检允许“部分预期文件缺失仍 PASS”

**严重度：P2**  
**状态：NOT_CLOSED**

### 定位

`archive-raw.yml` 156-189。

### 当前逻辑

固定枚举 5 个 archive 文件：

```text
track-board-close
track-board-flow
limit-up-pool
track-membership-snapshot
industry-universe-snapshot
```

但本地文件缺失/空时：

```bash
echo "... (skipped)"
continue
```

最后只要求：

```bash
if [ "$checked" = "0" ]; then fail
```

因此：

- 5 个预期文件中只有 1 个存在；
- 该 1 个线上 md5 正确；

仍可能最终输出：

```text
SITE_ARCHIVE_FRESH
```

### 根因

“预期集合完整性”和“已存在文件内容一致性”混成一个 `checked>0` 条件。

### 影响

部署验收存在假阳性：构建产物缺失一部分归档底座时仍可能绿灯。

---

## [FIX:R13-P3-04]

**路径：** `smi/.github/workflows/archive-raw.yml`  
**完整替换 `Verify deployment freshness` step：**

```yaml
      - name: Verify deployment freshness
        if: ${{ steps.archive.outputs.exit_code == '0' && (steps.commit.outputs.changed == 'true' || inputs.deploy) }}
        run: |
          set -euo pipefail

          BASE="https://smi-6s2.pages.dev/data/archive"
          REQUIRED_FILES="
          track-board-close
          track-board-flow
          limit-up-pool
          track-membership-snapshot
          industry-universe-snapshot
          "

          ok=1
          required=0
          checked=0

          for f in $REQUIRED_FILES; do
            required=$((required + 1))

            LOCAL="web/dist/data/archive/$f.jsonl"
            if [ ! -s "$LOCAL" ]; then
              echo "REQUIRED_LOCAL_ARCHIVE_MISSING_OR_EMPTY: $LOCAL"
              ok=0
              continue
            fi

            checked=$((checked + 1))
            LOCAL_SHA256="$(sha256sum "$LOCAL" | cut -d' ' -f1)"

            matched=0
            for attempt in 1 2 3 4 5 6; do
              sleep 20

              REMOTE="/tmp/smi-$f.jsonl"
              rm -f "$REMOTE"

              if ! curl -fsS --max-time 20 \
                -H 'Cache-Control: no-cache' \
                "$BASE/$f.jsonl" \
                -o "$REMOTE"; then
                echo "attempt=$attempt $f unreachable"
                continue
              fi

              SITE_SHA256="$(sha256sum "$REMOTE" | cut -d' ' -f1)"

              if [ "$SITE_SHA256" = "$LOCAL_SHA256" ]; then
                echo "MATCH $f.jsonl sha256=$SITE_SHA256"
                matched=1
                break
              fi

              echo \
                "attempt=$attempt $f mismatch " \
                "(local=$LOCAL_SHA256 site=$SITE_SHA256)"
            done

            if [ "$matched" != "1" ]; then
              ok=0
            fi
          done

          if [ "$checked" -ne "$required" ]; then
            echo \
              "LOCAL_ARCHIVE_SET_INCOMPLETE: " \
              "checked=$checked required=$required"
            ok=0
          fi

          if [ "$ok" != "1" ]; then
            echo "SITE_ARCHIVE_INCOMPLETE_OR_MISMATCH"
            exit 1
          fi

          echo "SITE_ARCHIVE_EXACT_MATCH"
```

> 若产品契约事实上允许上述 5 类中某些 archive 永久为可选，则不要静默 `continue`；
> 应把“required/optional 集合”显式写入配置，再分别验收。当前 workflow 自己固定枚举了 5 类，
> 因而本报告按“5 类均为预期发布集合”审查。

---

# 2.7 `smi/web/src/composables/useSnapshots.ts`

## 关于“是否把多态状态压平为获取失败”

该文件只负责：

- 加载 manifest；
- 加载 daily snapshot；
- 捕获网络/解析异常；
- 设置 composable 层的 `error` 字符串。

它**没有读取 `modules[*].status`，也没有任何 `PENDING/PARTIAL/UNAVAILABLE/ERROR → 获取失败` 的映射代码**。

因此：

**在本文件内，没有发现把模块多态状态压平为“获取失败”的证据。**

但真正的卡片/组件展示映射不在本文件内。用户本步限制未允许继续读取其它 Vue 组件，因此：

> **前端模块状态是否在组件层被压平：UNKNOWN。**

不能据此宣称已 CLOSED。

---

## R13-P3-05 — 异步日期切换存在 stale response 覆盖新数据风险

**严重度：P3**  
**状态：NOT_CLOSED**

### 定位

`useDailySnapshot()` 的 `load(date)`。

### 当前逻辑

每次调用独立执行：

```typescript
snapshot.value = await loadDaily(date);
```

没有：

- request id；
- sequence token；
- AbortController；
- “仅最后一次请求可提交状态”的检查。

### 故障序列

1. 用户加载 A 日期，请求 A 较慢；
2. 很快切换 B 日期；
3. B 先返回，页面显示 B；
4. A 后返回；
5. A 再次覆盖 `snapshot.value`。

最终 UI 可能显示与当前选择日期不一致的旧快照。

### 影响

低频但真实的前端一致性问题；在境外托管、大陆网络延迟抖动较大时概率会增加。

---

## [FIX:R13-P3-05]

**路径：** `smi/web/src/composables/useSnapshots.ts`  
**只需完整替换 `useDailySnapshot()`；其它函数不变：**

```typescript
export function useDailySnapshot() {
  const snapshot = ref<DailySnapshot | null>(null);
  const loading = ref(false);
  const error = ref<string>("");

  // 只有最后一次 load() 请求允许提交 snapshot/error/loading。
  let requestSequence = 0;

  async function load(date: string) {
    const requestId = ++requestSequence;

    loading.value = true;
    error.value = "";

    try {
      const nextSnapshot = await loadDaily(date);

      if (requestId !== requestSequence) {
        return;
      }

      snapshot.value = nextSnapshot;
    } catch (e) {
      if (requestId !== requestSequence) {
        return;
      }

      error.value = e instanceof Error ? e.message : String(e);
      snapshot.value = null;
    } finally {
      if (requestId === requestSequence) {
        loading.value = false;
      }
    }
  }

  return { snapshot, loading, error, load };
}
```

---

# 3. R12 三项变更的 Part 2 最终复核

## 3.1 tracks 动态化

**结论：方向正确，但仍 NOT_CLOSED。**

CLOSED：

- 5 日窗口与动态 pool 配置存在；
- 种子轨道存在；
- 元数据和 THS 映射 fail-closed；
- 四维 25/35/25/15 权重准确；
- 总分权重 100。

NOT_CLOSED：

- R13-P2-01：缺预热/迟滞/数据就绪分层；
- R13-P2-02：coverage 没有目标线/硬底线/DEGRADED 分级。

## 3.2 Node 22 部署链路

**本步指定的两个 workflow：CLOSED。**

两者均实际使用 Node 22。

> “全部 workflow 是否均已 Node22”不能由这两个文件推出；本步按用户限定没有读取其它 workflow，因此全仓结论仍是 `UNKNOWN`，不能扩大为全仓 CLOSED。

## 3.3 concurrency

**本步指定的 close/archive：CLOSED。**

两者同组：

```text
smi-data-write-${{ github.ref }}
```

且：

```text
cancel-in-progress=false
```

这一组合不会用后到任务取消当前数据事务。

## 3.4 CI 根因修复（akshare sys.modules 泄漏）

本步指定文件中不包含 CI 测试 fixture/测试源码，因此：

**UNKNOWN / 未在 Part 2 验证。**

不能依据送审声明推定 CLOSED。

---

# 4. 对 Q1 的源码增量回答

在 Part 1 已确认：

- turnover=ERROR
- sentiment=PARTIAL
- fundFlow=UNAVAILABLE
- margin 某日 ERROR
- tracks 连续 UNAVAILABLE

本步源码又增加一个明确的**系统性风险源**：

## netguard 本身可能再次造成 runner 退出卡住

`R13-P3-01` 证明：

- timeout 不是底层任务终止；
- daemon 修补实际失效；
- executor worker 仍可能存活；
- 解释器退出仍存在被未结束工作拖住的风险。

因此 Q1 的答案进一步明确：

> **是，除了 tracks coverage 与 margin T+1，还存在至少一个未被送审说明充分识别的系统性基础设施原因：当前 netguard 的线程式 hard-timeout 并不真正 hard。**

这可以解释“某些上游接口无响应时整个采集链路长时间停住”这一类故障，但：

- 是否已经直接造成 08-18 turnover/fundFlow 的具体异常；
- 各 collector 如何捕获 `GuardTimeoutError` 并映射 ERROR/SKIP；

需要读取调用方 collector 才能做因果归属。本步未读取，不能推测。

---

# 5. 前端“获取失败”问题的限定结论

`useSnapshots.ts` 本身：

- transport/load error 与 snapshot 分开；
- 不解释 module status；
- 不存在 `UNAVAILABLE => 获取失败` 这样的映射。

因此目前只能得出：

```text
useSnapshots.ts：没有状态压平证据
实际卡片组件：UNKNOWN
```

若下一轮需要精准回答“为何部分卡片统一显示获取失败”，应只再定点读取包含文本
`获取失败` 或 `module.status` 映射的 Vue 组件，无需全量展开 web 目录。

---

# 6. 修订优先级

建议按以下顺序处理：

1. **R13-P3-01（P1）**
   - 先修 netguard 为可终止隔离边界；
   - 这是防止整条 close/archive workflow 被黑盒数据源拖死的基础安全件。

2. **R13-P2-01 / R13-P2-02（P2）**
   - tracks 预热/迟滞；
   - coverage 三态/多态分级。

3. **R13-P3-02（P2）**
   - acceptance 增加 daily/latest/manifest 身份闭合。

4. **R13-P3-03 / R13-P3-04（P2）**
   - 发布自检从“时间新鲜/至少一个文件”升级为最终字节/预期集合一致。

5. **R13-P3-05（P3）**
   - 前端请求序列保护。

---

# 7. 收敛判定

本轮 **不能**声明：

> “本轮 0 NOT_CLOSED，ChatGPT 侧已收敛”

当前剩余：

- Part 1：2 项 P2 NOT_CLOSED；
- Part 2 新增：1 项 P1 + 3 项 P2 + 1 项 P3 NOT_CLOSED；
- CI `sys.modules["akshare"]` 修复因本步未读测试/CI 文件，仍为 UNKNOWN；
- 前端卡片层 status → 文案映射因未读组件，仍为 UNKNOWN。

**R13 当前建议：HOLD。**

---

# 8. 本报告边界再次声明

- 只读取用户指定的 7 个文件；
- 没有全量遍历/审核 ZIP 内容；
- 没有读取 `collector/calculators/tracks.py`；
- 没有读取 collector 各模块对 netguard 异常的捕获逻辑；
- 没有读取 `template-standard.json`；
- 没有读取 Vue 卡片组件；
- 没有读取 CI pytest fixture；
- **未修改调用方本地工作区；**
- **未运行调用方项目测试；**
- **未更新 manifest；**
- **未重新打包。**
