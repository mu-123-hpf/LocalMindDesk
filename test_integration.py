"""
LocalMindDesk — Phase 1/2/3 集成测试
"""
import sys
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

print("=" * 50)
print("  LocalMindDesk - Integration Test")
print("=" * 50)

passed = 0
failed = 0

def test(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        print(f"  [PASS] {name}")
    except Exception as e:
        failed += 1
        print(f"  [FAIL] {name}: {e}")

# Test 1
def t1():
    from app.tools.registry import get_registry
    r = get_registry()
    assert len(r.get_tool_names()) == 7
test("Tool Registry (5 tools)", t1)

# Test 2
def t2():
    from app.tools.registry import get_registry
    r = get_registry()
    shell = r.get("shell_exec")
    assert shell.name == "shell_exec"
    assert shell.danger_level == "critical"
test("BaseTool interface", t2)

# Test 3
def t3():
    from app.action_engine import SafetyGate, add_sandbox_root
    add_sandbox_root(os.path.dirname(os.path.abspath(__file__)))
    result = SafetyGate.assess("file_op", {"action": "read", "source": os.path.abspath("requirements.txt")})
    assert result["level"] in ("safe", "low"), f"unexpected level: {result}"
test("SafetyGate backward compat", t3)

# Test 4
def t4():
    from app.action_engine import execute_action
    result = execute_action("file_op", {"action": "list", "source": "app/tools"})
    assert result["success"]
    assert result["count"] >= 5
test("execute_action backward compat", t4)

# Test 5
def t5():
    from app.tools.registry import get_registry
    r = get_registry()
    result = r.execute("code_search", {"action": "grep", "pattern": "BaseTool", "path": "app/tools"})
    assert result["success"]
    assert result["count"] > 0
test("SearchTool grep", t5)

# Test 6
def t6():
    from app.tools.registry import get_registry
    r = get_registry()
    result = r.execute("code_search", {"action": "find", "pattern": "*.py", "path": "app"})
    assert result["success"]
    assert result["count"] > 10
test("SearchTool find", t6)

# Test 7
def t7():
    from app.tools.registry import get_registry
    r = get_registry()
    result = r.execute("file_op", {"action": "read", "source": "app/tools/base.py", "start_line": 1, "end_line": 3})
    assert result["success"]
    assert "total_lines" in result
test("FileTool line range read", t7)

# Test 8
def t8():
    from app.context import create_context
    ctx = create_context("test", [{"role": "user", "content": "hi"}], "sys")
    assert ctx.user_message == "test"
    assert ctx.estimate_context_tokens() > 0
test("SessionContext", t8)

# Test 9
def t9():
    from app.compact import get_compactor
    c = get_compactor()
    short = [{"role": "user", "content": "hi"}]
    long_msgs = [{"role": "user", "content": "x" * 600}] * 30
    assert not c.should_compact(short)
    assert c.should_compact(long_msgs)
test("Compact auto-detect", t9)

# Test 10
def t10():
    from app.memory_extractor import get_extractor
    e = get_extractor()
    assert e.get_stats()["extract_count"] == 0
test("MemoryExtractor init", t10)

# Test 11
def t11():
    from app.router.intent import analyze_intents
    intents = analyze_intents("grep BaseTool")
    assert "action" in intents
test("agent_router import + intents", t11)

# Test 12
def t12():
    from app.action_planner import _quick_plan
    plan = _quick_plan("grep BaseTool", "app")
    assert plan is not None
    assert plan[0]["tool"] == "code_search"
test("action_planner grep quick-match", t12)

# Test 13
def t13():
    from app.action_planner import _quick_plan
    plan = _quick_plan("find *.py", "app")
    assert plan is not None
    assert plan[0]["tool"] == "code_search"
    assert plan[0]["params"]["action"] == "find"
test("action_planner find quick-match", t13)

# Test 14
def t14():
    from app.context import create_context
    ctx = create_context("test", [], "sys", os.path.dirname(os.path.abspath(__file__)))
    info = ctx.get_workspace_info()
    assert info["exists"]
    assert info["file_count"] > 0
test("Workspace info scan", t14)

print()
print("=" * 50)
print(f"  Results: {passed} PASSED, {failed} FAILED / {passed + failed} total")
print("=" * 50)

if failed > 0:
    sys.exit(1)
