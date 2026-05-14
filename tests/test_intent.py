"""意图分析模块单元测试"""
from app.router.intent import analyze_intents


class TestAnalyzeIntents:
    """测试 analyze_intents 函数"""

    def test_default_is_chat(self):
        """无特殊关键词时应返回 chat"""
        assert analyze_intents("你好") == ["chat"]
        assert analyze_intents("今天天气怎么样") == ["chat"]

    def test_tool_intents(self):
        """工具关键词应触发 tool 意图"""
        intents = analyze_intents("帮我搜索 Python 教程")
        assert "tool" in intents

    def test_action_intents(self):
        """操作关键词应触发 action 意图"""
        intents = analyze_intents("创建一个文件叫 test.py")
        assert "action" in intents

    def test_schedule_intents(self):
        """定时关键词应触发 schedule 意图"""
        intents = analyze_intents("每天早上8点提醒我喝水")
        assert "schedule" in intents

    def test_config_intents(self):
        """配置关键词应触发 config 意图（需命中 2+ 关键词）"""
        intents = analyze_intents("你是猫娘，从现在起你是一个活泼的助手")
        assert "config" in intents

    def test_always_list(self):
        """返回值应始终是 list"""
        result = analyze_intents("hello")
        assert isinstance(result, list)
        assert len(result) >= 1
