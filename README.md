# AI 投研辅助工作流（演示项目）

输入股票代码 → 抓取实时行情 → 组装结构化 Prompt → 大模型流式生成盘面解读 → 前端打字机输出。

一个可完整运行的 AI 应用闭环，用于演示「把大模型能力接入真实业务场景」的工程实现。

---

## 一、它做了什么

```
用户输入 600519
      │
      ▼
① 行情抓取      新浪财经公开接口（无需 API Key）
      │         解析 GBK 编码的文本行情，提取价格/涨跌/振幅/成交额等
      ▼
② 数据加工      计算涨跌幅、振幅，格式化为结构化上下文
      │
      ▼
③ Prompt 组装   把行情数据填进模板，并约束「只依据给定数据、不编造」
      │
      ▼
④ 大模型调用    OpenAI 兼容协议，stream=True 流式返回
      │
      ▼
⑤ SSE 推送      服务端逐块推送到浏览器（text/event-stream）
      │
      ▼
⑥ 前端呈现     EventSource 接收，打字机效果逐字渲染
```

---

## 二、快速启动

**无需任何配置，直接运行即可看到完整效果（演示模式）：**

```bat
双击 run.bat
```

或者命令行：

```bat
cd ai-invest-demo
python app.py
```

然后用浏览器打开 **http://127.0.0.1:8000**

> 未配置 API Key 时会进入**演示模式**，用一段模拟文本走完整条流式链路。
> 这样可以先验证「行情 → Prompt → SSE → 打字机」这条管道是通的，再接入真实模型。

**依赖**：只用到 `requests` 和 `openai`（若已安装则无需额外操作）

```bat
pip install -r requirements.txt
```

---

## 三、接入真实大模型

只需要三个环境变量。以下三种任选其一：

### 方案 A：智谱 GLM（推荐，`glm-4-flash` 免费）

1. 打开 https://open.bigmodel.cn/ 注册
2. 控制台 → API Keys → 新建，复制 Key
3. 设置环境变量后启动：

```bat
set LLM_API_KEY=你的key
python app.py
```

默认已指向智谱：
```
LLM_BASE_URL = https://open.bigmodel.cn/api/paas/v4
LLM_MODEL    = glm-4-flash
```

### 方案 B：DeepSeek

```bat
set LLM_BASE_URL=https://api.deepseek.com
set LLM_MODEL=deepseek-chat
set LLM_API_KEY=你的key
python app.py
```

### 方案 C：硅基流动 SiliconFlow

```bat
set LLM_BASE_URL=https://api.siliconflow.cn/v1
set LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
set LLM_API_KEY=你的key
python app.py
```

> 三家都是 OpenAI 兼容协议，所以代码不用改，只换 base_url / model 即可。

---

## 四、接口说明

| 接口 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 前端页面 |
| `/api/config` | GET | 返回是否已配置 LLM |
| `/api/quote?code=600519` | GET | 返回行情 JSON |
| `/api/analyze?code=600519` | GET | **SSE 流式**返回 AI 解读 |

SSE 事件格式：

```
data: {"type":"meta","mode":"llm","model":"glm-4-flash"}
data: {"type":"delta","text":"走势概况："}
data: {"type":"delta","text":"该股当前价"}
...
data: {"type":"done"}
```

---

## 五、项目结构

```
ai-invest-demo/
├── app.py              # 主服务：行情抓取 + Prompt 组装 + LLM 流式 + 输出校验 + HTTP/SSE
├── static/index.html   # 前端：行情卡片 + 打字机效果 + 校验提示
├── selftest.py         # 端到端自测（接口连通性）
├── test_llm.py         # 真实模型链路测试（含首字延迟、分片数统计）
├── test_guard.py       # 输出校验层单元测试 + 真实链路校验验证
├── run.bat             # 一键启动
├── requirements.txt
├── .env                # 本地密钥（已加入 .gitignore，不会提交）
└── README.md
```

---

## 六、工程上做了哪些处理（面试可讲）

1. **流式输出而非一次性返回**——大模型生成需要数秒，流式能让用户第一秒就看到内容。实现上用 `text/event-stream` + 逐块 flush，前端用 `EventSource` 接收。
2. **两层防编造机制（本项目最有价值的工程点）**

   - **第一层 · Prompt 约束**：system prompt 明确「只依据给定数据分析」，并在输出格式里逐条列出禁止项（历史对比、量能趋势、财务数据、消息面），强制结尾加风险提示。
   - **第二层 · 输出校验**：**实测发现仅靠 Prompt 不可靠**——模型仍会输出「今日成交量…较昨日有所增加」这类无数据支撑的对比。因此在流式结束后追加规则校验：按句子切分，命中以下模式即过滤，并把过滤原因显式告知用户。
     - 成交量的历史对比（未提供历史数据）
     - 同比 / 环比（未提供历史数据）
     - 放量 / 缩量（未提供历史量能基准）
     - 资金流入 / 流出（未提供资金数据）
     - 均线 / MACD / RSI 等技术指标（未提供指标数据）
   - **关键设计：只拦截无依据的表述，不一刀切。**
     「较昨日收盘价上涨 16.51 元」是有依据的（Prompt 提供了昨收价）→ **放行**；
     「成交量较昨日增加」无依据 → **拦截**。
     这条边界如果划错，就会把正确内容也过滤掉，属于典型的过度防御。

3. **演示模式兜底**——没有 API Key 时自动降级为 mock 流，保证链路可验证、可演示，不会因为缺 Key 就跑不起来。
4. **客户端断连处理**——用户刷新页面时 SSE 连接会中断，服务端捕获 `ConnectionAbortedError` 后静默终止，不打印堆栈。
5. **数据源解耦**——行情抓取封装在 `fetch_quote()`，换数据源不影响上层逻辑。
6. **代码归一化**——用户输入 `600519` / `sh600519` / `SH600519` 都能正确识别沪市或深市。

---

## 七、可继续扩展的方向

- **历史行情 + 技术指标**：接入日线数据，计算 MA / MACD / RSI 后再交给模型解读
- **RAG 增强**：把研报或公告向量化存进向量库，检索相关片段作为补充上下文，避免模型靠记忆瞎猜
- **多标的对比**：一次输入多只股票，让模型做横向对比
- **工作流编排**：用 Dify / Coze 把这套流程视觉化，便于业务方自己调整 Prompt

---

## 免责声明

本项目仅用于技术演示，行情数据来源于新浪财经公开接口，AI 生成内容**不构成任何投资建议**。
