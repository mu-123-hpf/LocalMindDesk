# -*- coding: utf-8 -*-
"""LocalMindDesk — 项目总结 PDF 生成器"""
import os
from fpdf import FPDF

class ProjectPDF(FPDF):
    FONT_PATH = os.path.join(os.path.dirname(__file__), "frontend")
    
    def __init__(self):
        super().__init__()
        # 使用系统中文字体
        font_candidates = [
            r"C:\Windows\Fonts\msyh.ttc",    # 微软雅黑
            r"C:\Windows\Fonts\simhei.ttf",   # 黑体
            r"C:\Windows\Fonts\simsun.ttc",   # 宋体
        ]
        self.cn_font = "helvetica"
        for fp in font_candidates:
            if os.path.exists(fp):
                self.add_font("cn", "", fp)
                self.add_font("cn", "B", fp)
                self.cn_font = "cn"
                break
    
    def header(self):
        self.set_font(self.cn_font, "B", 10)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, "LocalMindDesk — 项目技术文档", align="C", new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font(self.cn_font, "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"第 {self.page_no()} 页", align="C")

    def title_page(self):
        self.add_page()
        self.ln(50)
        self.set_font(self.cn_font, "B", 28)
        self.set_text_color(33, 37, 41)
        self.cell(0, 15, "LocalMindDesk", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(5)
        self.set_font(self.cn_font, "", 16)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, "本地 AI 助手 — 项目技术总结文档", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(10)
        self.set_font(self.cn_font, "", 12)
        self.cell(0, 8, "Your mind, locally amplified.", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(30)
        self.set_font(self.cn_font, "", 11)
        self.set_text_color(80, 80, 80)
        lines = [
            "技术栈: Python (FastAPI) + JavaScript + HTML/CSS",
            "AI 引擎: LM Studio (本地大模型推理)",
            "记忆系统: 三层架构 (L1热窗口 + L2长期 + L3向量)",
            "测试: 23 个自动化测试全通过",
            f"生成日期: 2026-05-12",
        ]
        for line in lines:
            self.cell(0, 8, line, align="C", new_x="LMARGIN", new_y="NEXT")

    def h1(self, text):
        self.ln(6)
        self.set_font(self.cn_font, "B", 18)
        self.set_text_color(30, 100, 200)
        self.cell(0, 12, text, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(30, 100, 200)
        self.line(10, self.get_y(), 80, self.get_y())
        self.ln(4)

    def h2(self, text):
        self.ln(4)
        self.set_font(self.cn_font, "B", 14)
        self.set_text_color(50, 50, 50)
        self.cell(0, 10, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def body(self, text):
        self.set_font(self.cn_font, "", 11)
        self.set_text_color(60, 60, 60)
        self.multi_cell(0, 7, text)
        self.ln(2)

    def bullet(self, text):
        self.set_font(self.cn_font, "", 11)
        self.set_text_color(60, 60, 60)
        x = self.get_x()
        self.cell(6, 7, "  *")
        self.multi_cell(self.w - self.r_margin - self.get_x(), 7, " " + text)
        self.set_x(x)

    def code_block(self, text):
        self.set_font(self.cn_font, "", 9)
        self.set_fill_color(245, 245, 245)
        self.set_text_color(40, 40, 40)
        w = self.w - 20
        self.set_x(12)
        for line in text.split("\n"):
            self.cell(w, 6, "  " + line, fill=True, new_x="LMARGIN", new_y="NEXT")
            self.set_x(12)
        self.ln(3)

    def table(self, headers, rows):
        self.set_font(self.cn_font, "B", 10)
        self.set_fill_color(30, 100, 200)
        self.set_text_color(255, 255, 255)
        col_w = (self.w - 20) / len(headers)
        for h in headers:
            self.cell(col_w, 8, h, border=1, fill=True, align="C")
        self.ln()
        self.set_font(self.cn_font, "", 10)
        self.set_text_color(50, 50, 50)
        fill = False
        for row in rows:
            if fill:
                self.set_fill_color(240, 245, 250)
            else:
                self.set_fill_color(255, 255, 255)
            for val in row:
                self.cell(col_w, 7, str(val), border=1, fill=True, align="C")
            self.ln()
            fill = not fill
        self.ln(3)


def generate():
    pdf = ProjectPDF()
    pdf.set_auto_page_break(auto=True, margin=20)

    # === 封面 ===
    pdf.title_page()

    # === 目录 ===
    pdf.add_page()
    pdf.h1("目 录")
    toc = [
        "一、项目概述 — 这是什么？能做什么？",
        "二、技术架构 — 系统如何构成",
        "三、项目目录结构 — 文件怎么组织的",
        "四、核心模块详解 — 关键代码说明",
        "五、14 项架构提升 — 我们做了哪些改进",
        "六、如何运行 — 从零开始启动项目",
        "七、API 接口列表 — 系统提供的所有接口",
        "八、测试报告 — 自动化测试结果",
    ]
    for i, item in enumerate(toc):
        pdf.bullet(item)

    # === 一、项目概述 ===
    pdf.add_page()
    pdf.h1("一、项目概述")
    pdf.body('LocalMindDesk 是一个完全运行在本地的 AI 助手系统。它的核心理念是 "Your mind, locally amplified" ——所有数据都存储在你的电脑上，不上传到云端，保护隐私的同时提供强大的 AI 能力。')
    pdf.h2("核心能力")
    abilities = [
        "智能对话: 支持流式输出(SSE)，实时逐字显示回复",
        "多模型路由: 自动根据问题复杂度选择合适的AI模型",
        "三层记忆: L1热窗口 + L2长期记忆 + L3向量语义记忆",
        "文件操作: 可以读写文件、执行命令、管理项目",
        "工具集成: 联网搜索、PPT生成、Word文档、代码助手",
        "桌宠系统: 可爱的桌面宠物，有情绪和动画",
        "微信集成: 可接入微信消息自动回复",
        "多角色人格: 支持创建和切换不同的AI人格",
        "定时任务: 支持定时提醒和周期性任务",
        "WebSocket: 实时推送消息，替代传统轮询",
    ]
    for a in abilities:
        pdf.bullet(a)

    # === 二、技术架构 ===
    pdf.add_page()
    pdf.h1("二、技术架构")
    pdf.body("系统采用前后端分离架构，后端使用 Python FastAPI 框架，前端使用原生 HTML/CSS/JavaScript。AI 推理通过 LM Studio 在本地运行大语言模型。")
    pdf.h2("技术栈")
    pdf.table(["层级", "技术", "说明"], [
        ["后端框架", "FastAPI + Uvicorn", "高性能异步 Web 框架"],
        ["AI 引擎", "LM Studio + OpenAI SDK", "本地大模型推理"],
        ["前端", "HTML + CSS + JavaScript", "模块化原生前端"],
        ["数据库", "SQLite + JSON", "轻量本地存储"],
        ["向量引擎", "Embedding + TF-IDF", "混合语义搜索"],
        ["通信", "REST + SSE + WebSocket", "多协议支持"],
        ["测试", "pytest + httpx", "23个自动化测试"],
    ])
    pdf.h2("架构图 (文字版)")
    pdf.code_block(
        "浏览器 (前端 15 个 JS 模块)\n"
        "   |  REST API / SSE / WebSocket\n"
        "   v\n"
        "FastAPI 后端 (main.py + routes/)\n"
        "   |-- agent_router (意图分析 -> 路由)\n"
        "   |-- llm_provider (LLM 调用 + 流式)\n"
        "   |-- model_router (智能模型选择)\n"
        "   |-- memory (三层记忆系统)\n"
        "   |-- vector_memory (混合向量引擎)\n"
        "   |-- metrics (可观测性指标)\n"
        "   v\n"
        "LM Studio (本地运行 Gemma/DeepSeek 等模型)"
    )

    # === 三、项目目录结构 ===
    pdf.add_page()
    pdf.h1("三、项目目录结构")
    pdf.body("以下是项目的核心文件组织方式，帮助你快速定位代码：")
    pdf.code_block(
        "localminddesk/\n"
        "|\n"
        "|-- app/                    # 后端 Python 代码\n"
        "|   |-- main.py            # FastAPI 入口 (所有 API 路由)\n"
        "|   |-- llm_provider.py    # LLM 调用封装\n"
        "|   |-- config.py          # 配置管理\n"
        "|   |-- memory.py          # 记忆系统 (L1+L2)\n"
        "|   |-- vector_memory.py   # 向量记忆 (L3)\n"
        "|   |-- model_router.py    # 智能模型路由\n"
        "|   |-- ws_manager.py      # WebSocket 管理\n"
        "|   |-- logger.py          # 统一日志\n"
        "|   |-- metrics.py         # 可观测性指标\n"
        "|   |-- router/            # 路由拆分模块\n"
        "|   |   |-- intent.py      #   意图分析\n"
        "|   |   |-- chat_handler.py#   聊天处理\n"
        "|   |   |-- action_handler.py# 操作执行\n"
        "|   |-- routes/            # APIRouter 模块\n"
        "|       |-- metrics.py     #   指标路由\n"
        "|       |-- vector.py      #   向量路由\n"
        "|\n"
        "|-- frontend/              # 前端代码\n"
        "|   |-- index.html         # 主页面\n"
        "|   |-- style.css          # 样式表\n"
        "|   |-- app.js             # 入口编排\n"
        "|   |-- js/                # 模块化 JS\n"
        "|       |-- chat.js        #   聊天模块\n"
        "|       |-- sessions.js    #   会话管理\n"
        "|       |-- websocket.js   #   WebSocket\n"
        "|       |-- i18n.js        #   国际化\n"
        "|       |-- perf.js        #   性能优化\n"
        "|\n"
        "|-- tests/                 # 自动化测试\n"
        "|   |-- test_api.py        # API 冒烟测试\n"
        "|   |-- test_intent.py     # 意图分析测试\n"
        "|   |-- test_vector_memory.py # 向量引擎测试\n"
        "|\n"
        "|-- data/                  # 运行时数据\n"
        "|-- doc/                   # 开发文档 (22篇)\n"
        "|-- config.json            # 运行配置"
    )

    # === 四、核心模块详解 ===
    pdf.add_page()
    pdf.h1("四、核心模块详解")

    pdf.h2("4.1 LLM 调用 (llm_provider.py)")
    pdf.body("这是与 AI 模型通信的核心模块。支持同步和流式两种调用方式，自动过滤 DeepSeek 的 <think> 标签，并集成了 metrics 计量。")
    pdf.code_block(
        "# 同步调用\n"
        "reply = llm_provider.chat(\n"
        "    messages=[{'role':'user','content':'你好'}],\n"
        "    system_prompt='你是AI助手',\n"
        "    temperature=0.7,\n"
        ")\n"
        "\n"
        "# 流式调用 (逐字输出)\n"
        "for chunk in llm_provider.chat_stream(...):\n"
        "    print(chunk, end='', flush=True)"
    )

    pdf.h2("4.2 智能模型路由 (model_router.py)")
    pdf.body("根据问题复杂度自动选择模型。简单问题(打招呼、翻译)走本地小模型，复杂问题(编程、分析)走大模型。只有一个模型时自动跳过路由。")
    pdf.code_block(
        "# 复杂度评估\n"
        "'你好'        -> simple  -> 本地快速模型\n"
        "'写排序算法'   -> complex -> 远程强模型\n"
        "'翻译hello'   -> simple  -> 本地快速模型"
    )

    pdf.h2("4.3 三层记忆系统")
    pdf.body("受  启发的三层记忆架构：")
    pdf.bullet("L1 热窗口: 当前对话的最近 20 条消息，直接作为上下文发送给模型")
    pdf.bullet("L2 长期记忆: 跨会话持久化的关键信息，自动压缩和归档")
    pdf.bullet("L3 向量记忆: 使用 Embedding 或 TF-IDF 的语义搜索，召回相关历史")

    pdf.h2("4.4 混合向量引擎 (vector_memory.py)")
    pdf.body("向量记忆引擎支持两种模式：当 LM Studio 有 embedding 模型时使用语义嵌入(精度高)；没有时自动降级为 TF-IDF(零依赖)。嵌入向量缓存为 .npy 文件。")

    pdf.h2("4.5 意图分析 (router/intent.py)")
    pdf.body("快速关键词匹配识别用户意图，支持 5 种类型：")
    pdf.table(["意图", "触发示例", "处理方式"], [
        ["chat", "你好 / 聊天", "直接调用 LLM"],
        ["action", "创建文件 / 执行命令", "Action Agent"],
        ["config", "你是猫娘 / 改名字", "Meta Agent"],
        ["schedule", "每天8点提醒 / 定时", "Scheduler"],
        ["tool", "搜索 / 做PPT", "Tool Agent"],
    ])

    # === 五、14项架构提升 ===
    pdf.add_page()
    pdf.h1("五、14 项架构提升")
    pdf.body("以下是本次优化中完成的所有改进：")
    pdf.table(["编号", "提升项", "状态"], [
        ["1", "前端模块化 (4234行拆12模块)", "已完成"],
        ["2", "后端路由拆分 (9个模块)", "已完成"],
        ["3", "SSE 流式响应", "已完成"],
        ["4", "向量记忆升级 (Embedding+TF-IDF)", "已完成"],
        ["5", "统一日志系统 (logger.py)", "已完成"],
        ["6", "测试覆盖 (23个测试)", "已完成"],
        ["7", "WebSocket 实时通信", "已完成"],
        ["8", "多模型智能路由", "已完成"],
        ["9", "前端性能优化 (懒加载)", "已完成"],
        ["10", "国际化 i18n (中/英)", "已完成"],
        ["11", "main.py APIRouter拆分", "已完成"],
        ["12", "配置热重载", "已完成"],
        ["13", "可观测性 Metrics", "已完成"],
        ["14", "文档索引 (22篇)", "已完成"],
    ])

    # === 六、如何运行 ===
    pdf.add_page()
    pdf.h1("六、如何运行")
    pdf.h2("前置条件")
    pdf.bullet("Python 3.10+ (推荐 3.12)")
    pdf.bullet("LM Studio (下载地址: lmstudio.ai)")
    pdf.bullet("一个 AI 模型 (推荐 Gemma 4 或 DeepSeek)")

    pdf.h2("第一步: 安装依赖")
    pdf.code_block(
        "# 进入项目目录\n"
        "cd localminddesk\n"
        "\n"
        "# 安装 Python 依赖\n"
        "pip install fastapi uvicorn openai pydantic numpy fpdf2"
    )

    pdf.h2("第二步: 启动 LM Studio")
    pdf.bullet("打开 LM Studio，下载一个模型 (如 gemma-4-e4b-it)")
    pdf.bullet("点击左侧 'Server' 标签")
    pdf.bullet("点击 'Start Server' 按钮")
    pdf.bullet("确认服务运行在 http://127.0.0.1:1234")

    pdf.h2("第三步: 启动后端")
    pdf.code_block("python -m app.main")
    pdf.body("看到以下输出说明启动成功：")
    pdf.code_block(
        "==================================================\n"
        "  LocalMindDesk v2 启动完成\n"
        "  地址: http://localhost:8000\n"
        "=================================================="
    )

    pdf.h2("第四步: 打开浏览器")
    pdf.body("在浏览器中访问 http://localhost:8000，即可看到 LocalMindDesk 界面。在底部输入框输入消息，按 Enter 发送。")

    pdf.h2("运行测试")
    pdf.code_block("python -m pytest tests/ -v")
    pdf.body("预期结果: 23 passed")

    # === 七、API 接口 ===
    pdf.add_page()
    pdf.h1("七、API 接口列表")
    pdf.table(["端点", "方法", "说明"], [
        ["/api/chat", "POST", "发送聊天消息"],
        ["/api/chat/stream", "POST", "流式聊天(SSE)"],
        ["/api/health", "GET", "健康检查"],
        ["/api/sessions", "GET", "获取会话列表"],
        ["/api/sessions", "POST", "创建新会话"],
        ["/api/sessions/{id}", "DELETE", "删除会话"],
        ["/api/models", "GET", "获取模型列表"],
        ["/api/models/route", "POST", "测试智能路由"],
        ["/api/metrics", "GET", "系统指标"],
        ["/api/vector/status", "GET", "向量引擎状态"],
        ["/api/vector/rebuild", "POST", "重建嵌入向量"],
        ["/api/config/reload", "POST", "热重载配置"],
        ["/ws", "WebSocket", "实时推送通道"],
    ])

    # === 八、测试报告 ===
    pdf.add_page()
    pdf.h1("八、测试报告")
    pdf.body("自动化测试使用 pytest 框架，覆盖 API 端点、意图分析和向量引擎三个核心模块。")
    pdf.table(["测试文件", "测试数", "覆盖范围"], [
        ["test_api.py", "7", "API 端点冒烟测试"],
        ["test_intent.py", "6", "意图分析关键词覆盖"],
        ["test_vector_memory.py", "10", "TF-IDF + 向量搜索"],
    ])
    pdf.body("最新测试结果: 23 passed in 4.07s")
    pdf.ln(10)
    pdf.set_font(pdf.cn_font, "B", 14)
    pdf.set_text_color(30, 150, 30)
    pdf.cell(0, 10, "全部 23 个测试通过 !", align="C")

    # === 保存 ===
    out = os.path.join(os.path.dirname(__file__), "doc", "LocalMindDesk_项目技术文档.pdf")
    pdf.output(out)
    print(f"PDF 已生成: {out}")
    return out

if __name__ == "__main__":
    generate()
