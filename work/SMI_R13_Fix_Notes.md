# SMI R13 修订记录（2026-08-20）

## 已应用

### R13-P3-01（P1）netguard 硬超时失效 —— 已修

- **问题**：R12 线程方案 `future.result(timeout)` 只停止等待、不终止底层调用；
  `_orphanify_executor()` 依赖的私有 API 按 CPython 语义不生效（运行中线程禁止改
  daemon；`_threads_queues` 的键是 worker Thread 而非 executor），08-18 式挂死风险仍在。
- **修订**（基于 ChatGPT [FIX:R13-P3-01]，加 Windows spawn 兜底，经用户确认）：
  - `collector/netguard.py` 整体重写：被装饰采集函数在独立子进程执行，超时
    `terminate()→kill()` 确定性终止；结果经 pickle 文件原子回传；异常优先原样
    传递，不可序列化时退化 `GuardedCallError`；
  - POSIX（GitHub ubuntu 生产）用 fork；Windows 用 spawn 子进程（被装饰函数须为
    模块级可 pickle 函数——本项目全部采集入口满足；不可 pickle 时 fail-closed，
    绝不退化为不可终止线程）；
  - `process.close()` 释放句柄（Windows 句柄不释放会让 pid 探测失真）。
- **测试**（`collector/tests/test_tracks_dynamic.py`）：worker 全部改模块级函数
  （spawn 可 pickle）；新增 worker 终止验证（pid 探测）、retries=0 不产生第二子进程、
  DataFrame 可序列化、不可 pickle 异常 fail-closed；保留负向变异说明。
- **测试直通**：进程隔离使依赖进程内 monkeypatch 的单测失效，新增
  `collector/tests/conftest.py` 设 `SMI_NETGUARD_MODE=inline`（仅测试会话）；
  netguard 专项测试经 `_real_netguard` fixture 删该变量走真实子进程。
  **生产 workflow 严禁设置该变量。**
- **验证**：全量 pytest 209 passed / 1 skipped / 10.35s（Windows spawn 路径实测）。

## 暂缓（已在 R13 报告登记，待用户拍板）

| 编号 | 严重度 | 摘要 |
|---|---|---|
| R13-P2-01 | P2 | tracks 动态选池缺预热池/迟滞/历史就绪门禁（设计变更） |
| R13-P2-02 | P2 | coverage=80 单硬门槛过激 → 目标线+hard floor+PARTIAL 三态（设计变更） |
| R13-P3-02 | P2 | acceptance 缺 daily↔tradeDate、latest↔manifest 身份闭合校验 |
| R13-P3-03 | P2 | close-snapshot 自检只验 updatedAt，不验内容身份 |
| R13-P3-04 | P2 | archive-raw 自检允许部分预期文件缺失仍 PASS |
| R13-P3-05 | P3 | 前端 useDailySnapshot 无请求序列保护（快速切日期旧响应可覆盖新数据） |

## 复核报告存档

- `work/SMI_R13_Review_Request.md`（送审说明）
- `work/SMI_R13_Review_Report_Part1.md`（方案层：含 Q1/Q2 完整答案与托管方案对比）
- `work/SMI_R13_Review_Report_Part2.md`（源码层：7 文件定点复核）
