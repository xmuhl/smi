"""R14-P1-01：真实 @net_guard 装饰器语法 + 强制 spawn 回归。

旧实现把原始函数对象直接 pickle 传给 spawn 子进程；生产装饰器语法下
模块同名符号已被 wrapper 覆盖，pickle 回查命中 wrapper → PicklingError
→ GuardedCallError，Windows 采集路径全灭。registry 化后必须保证：
真实 @net_guard 模块级装饰函数在强制 spawn 下可成功/传异常/可超时终止。
"""

import importlib
import sys
import textwrap

import pytest

from collector.netguard import (
    GuardedCallError,
    GuardTimeoutError,
    net_guard,
)

FIXTURE_MODULE = "ng_spawn_fixture_mod"
FIXTURE_SRC = textwrap.dedent(
    """
    import time

    from collector.netguard import net_guard


    @net_guard(timeout=30.0, retries=0)
    def ng_quick():
        return 42


    @net_guard(timeout=30.0, retries=0)
    def ng_boom():
        raise ValueError("fixture boom")


    @net_guard(timeout=1.0, retries=0)
    def ng_slow():
        time.sleep(60)
        return "unreachable"
    """
)


@pytest.fixture
def spawn_fixture_module(tmp_path, monkeypatch):
    """生成真实装饰器语法的临时模块，并强制 spawn + 真实子进程。"""
    monkeypatch.delenv("SMI_NETGUARD_MODE", raising=False)
    monkeypatch.setenv("SMI_NETGUARD_FORCE_SPAWN", "1")
    (tmp_path / f"{FIXTURE_MODULE}.py").write_text(FIXTURE_SRC, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop(FIXTURE_MODULE, None)
    module = importlib.import_module(FIXTURE_MODULE)
    yield module
    sys.modules.pop(FIXTURE_MODULE, None)


def test_spawn_real_decorator_success(spawn_fixture_module):
    """真实 @net_guard 装饰函数在强制 spawn 下正常返回（R14-P1-01 核心回归）。"""
    assert spawn_fixture_module.ng_quick() == 42


def test_spawn_real_decorator_exception(spawn_fixture_module):
    """子进程异常按原类型传回父进程。"""
    with pytest.raises(ValueError, match="fixture boom"):
        spawn_fixture_module.ng_boom()


def test_spawn_real_decorator_timeout_terminates(spawn_fixture_module):
    """超时后子进程被确定性终止并抛 GuardTimeoutError。"""
    import time

    started = time.monotonic()
    with pytest.raises(GuardTimeoutError):
        spawn_fixture_module.ng_slow()
    assert time.monotonic() - started < 30


def test_spawn_non_module_level_fails_closed():
    """闭包/局部函数在装饰时即 fail-closed（不等到采集运行时才暴露）。"""

    def local_fn():
        return 1

    with pytest.raises(GuardedCallError):
        net_guard(timeout=1.0, retries=0)(local_fn)
