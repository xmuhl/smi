"""测试会话级配置。

SMI_NETGUARD_MODE=inline：单测默认让 net_guard 直通调用（不建子进程）。
原因：多数单测靠进程内 monkeypatch / sys.modules 替换注入假数据源，
进程隔离会让 mock 失效并触发真实联网。netguard 进程隔离行为本身由
test_tracks_dynamic.py 中的 netguard 专项测试覆盖（这些测试显式
删除该环境变量，走真实 fork/spawn 子进程）。

生产与采集 workflow 绝不设置此变量。
"""

from __future__ import annotations

import os

os.environ.setdefault("SMI_NETGUARD_MODE", "inline")
