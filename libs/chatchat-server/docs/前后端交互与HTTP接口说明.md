# 前后端交互与 HTTP 接口说明

本文档说明当前应用中**后端 API 的 HTTP 接口**以及**前端（Streamlit Web UI）如何调用**，便于排查请求、对接第三方客户端或查看接口列表。

---

## 一、如何看到 HTTP 接口

1. **Swagger 文档（推荐）**  
   后端启动后访问：  
   **`http://<API地址>/docs`**  
   例如本地默认：`http://127.0.0.1:7861/docs`  
   可查看所有已注册路由、请求体格式，并在线调试。

2. **浏览器开发者工具**  
   打开 Streamlit 页面后按 F12 → **Network**，在页面进行对话或切换知识库，即可看到实际发出的请求 URL、Method、Request/Response。

3. **API 地址来源**  
   前端使用的 base_url 来自配置：`basic_settings.API_SERVER`（`host` / `port`，公网则 `public_host` / `public_port`）。默认 `http://127.0.0.1:7861`。

---

## 二、后端路由总览

后端由 **FastAPI** 提供，无全局前缀，各模块前缀如下：

| 前缀 | 说明 | 定义文件 |
|------|------|----------|
| `/chat` | 对话相关 | `chat_routes.py` |
| `/knowledge_base` | 知识库管理与知识库对话 | `kb_routes.py` |
| `/v1` | OpenAI 兼容接口（模型、补全、Embedding 等） | `openai_routes.py` |
| `/tools` | 工具列表与调用 | `tool_routes.py` |
| `/server` | 服务端状态、Prompt 模板等 | `server_routes.py` |
| `/api/v1/mcp_connections` | MCP 连接管理 | `mcp_routes.py` |

---

## 三、与「对话」相关的主要 HTTP 接口

### 1. 多功能对话（Agent / 工具）

- **用途**：带 Agent、本地知识库等工具的对话。
- **前端调用**：`dialogue.py` 使用  
  `openai.Client(base_url=f"{api_address()}/chat", ...)`  
  实际请求为 **POST** `base_url + "/chat/completions"`。
- **HTTP 接口**：  
  **`POST /chat/chat/completions`**  
  - 请求体：OpenAI 风格 `messages`、`model`、`stream` 等；`extra_body` 中可传 `conversation_id`、`tools`、`metadata`、`use_mcp` 等。
  - 响应：流式或非流式，与 OpenAI Chat Completions 兼容。

### 2. RAG 知识库对话（当前 RAG 页使用的接口）

- **用途**：按选中的知识库/临时库/搜索引擎进行检索并生成回复。
- **前端调用**：`kb_chat.py` 根据模式构造 base_url，再用 **OpenAI SDK** 调用 `client.chat.completions.create(...)`，等价于对下述 URL 发 **POST**：
  - 本地知识库：  
    **`POST /knowledge_base/local_kb/{知识库名}/chat/completions`**
  - 临时知识库（文件对话）：  
    **`POST /knowledge_base/temp_kb/{knowledge_id}/chat/completions`**
  - 搜索引擎：  
    **`POST /knowledge_base/search_engine/{搜索引擎名}/chat/completions`**
- **请求体**：同上，OpenAI 风格；`extra_body` 可带 `top_k`、`score_threshold`、`prompt_name`、`return_direct` 等（与 `/chat/kb_chat` 参数一致）。

### 3. 纯 LLM 对话（无 Agent）

- **用途**：仅调用大模型，不走 Agent/工具。
- **接口**：  
  **`POST /v1/chat/completions`**  
- **前端**：若使用 `base_url=f"{api_address()}/v1"` 的 OpenAI Client，即调用此接口。

### 4. 传统表单式接口（仍存在，供兼容）

- 知识库对话（表单式）：**`POST /chat/kb_chat`**  
  请求体为 JSON，包含 `query`、`knowledge_id`、`history`、`stream` 等。
- 文件对话：**`POST /chat/file_chat`**
- 反馈：**`POST /chat/feedback`**

---

## 四、前端如何与后端交互（简要）

1. **API 地址**  
   通过 `chatchat.server.utils.api_address()` 获取，来源于 `basic_settings.API_SERVER`（默认 `http://127.0.0.1:7861`）。

2. **RAG 对话（知识库问答）**  
   - Streamlit 页：`kb_chat.py`  
   - 使用 `openai.Client(base_url=api_url + "/knowledge_base/local_kb/" + selected_kb)`（或 `temp_kb` / `search_engine`），调用 `client.chat.completions.create(messages=..., stream=True, ...)`。  
   - 等价于对 **`POST /knowledge_base/{mode}/{param}/chat/completions`** 发 HTTP 请求。

3. **多功能对话（Agent）**  
   - Streamlit 页：`dialogue.py`  
   - 使用 `openai.Client(base_url=f"{api_address()}/chat", ...)`，调用 `client.chat.completions.create(...)`。  
   - 等价于对 **`POST /chat/chat/completions`** 发 HTTP 请求。

4. **其他**  
   - 知识库列表、上传、搜索等：通过 `ApiRequest`（`webui_pages.utils`）发 HTTP 请求到 `/knowledge_base/*` 等路径。  
   - 上传图片等：`POST /v1/files`、`GET /v1/files/{id}/content`。

---

## 五、常用接口速查

| 功能 | 方法 | URL |
|------|------|-----|
| 多功能/Agent 对话 | POST | `/chat/chat/completions` |
| 知识库对话（OpenAI 兼容） | POST | `/knowledge_base/local_kb/{kb_name}/chat/completions` |
| 临时知识库对话 | POST | `/knowledge_base/temp_kb/{knowledge_id}/chat/completions` |
| 搜索引擎对话 | POST | `/knowledge_base/search_engine/{engine}/chat/completions` |
| 纯 LLM 对话 | POST | `/v1/chat/completions` |
| 模型列表 | GET | `/v1/models` |
| 知识库列表 | GET | `/knowledge_base/list_knowledge_bases` |
| 知识库内搜索 | POST | `/knowledge_base/search_docs` |
| Prompt 模板 | POST | `/server/get_prompt_template` |
| 工具列表 | GET | `/tools` |

更多路由请直接查看 **`http://<API地址>/docs`** 的 Swagger 文档。

---

## 六、RAG 配置通过接口如何传参（对话模式 + 知识库）

页面上「请选择对话模式」和「请选择知识库」对应接口的 **URL 路径** 和 **请求体**，无需单独“配置接口”，在一次对话请求里即可完成。

### 1. 调用哪个接口

**统一入口**：**`POST /knowledge_base/{mode}/{param}/chat/completions`**

- **对话模式** → 用 **`mode`** 表示：
  - 知识库问答 → **`local_kb`**
  - 文件对话（临时知识库）→ **`temp_kb`**
  - 搜索引擎 → **`search_engine`**
- **知识库/来源** → 用 **`param`** 表示：
  - `mode=local_kb` 时：**知识库名称**（如 `Netpropto`）
  - `mode=temp_kb` 时：**临时知识库 ID**（上传文件后返回的 id）
  - `mode=search_engine` 时：**搜索引擎名称**（配置中的引擎名）

因此：
- 选「知识库问答」+「Netpropto」→ 调用  
  **`POST /knowledge_base/local_kb/Netpropto/chat/completions`**
- 选「文件对话」且临时库 id 为 `abc123` →  
  **`POST /knowledge_base/temp_kb/abc123/chat/completions`**
- 选「搜索引擎」且引擎名为 `bing` →  
  **`POST /knowledge_base/search_engine/bing/chat/completions`**

### 2. 如何传参（请求体）

请求体为 **OpenAI Chat Completions** 风格，并可在同一 JSON 中带 RAG 相关参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `messages` | array | 是 | 对话消息，最后一条为本次用户问题 |
| `model` | string | 否 | LLM 模型名，默认取配置中的默认模型 |
| `stream` | bool | 否 | 是否流式返回，默认 true |
| `temperature` | float | 否 | 采样温度 |
| `max_tokens` | int | 否 | 最大生成 token 数 |
| `top_k` | int | 否 | 知识库检索条数，默认见 kb_settings |
| `score_threshold` | float | 否 | 检索相关度阈值（0–2） |
| `prompt_name` | string | 否 | RAG 使用的 prompt 模板名，默认 `"default"` |
| `return_direct` | bool | 否 | 是否只返回检索结果不调用 LLM，默认 false |
| `return_docs` | bool | 否 | 响应中是否包含检索文档内容，设为 `false` 可减少响应体积与 token 占用，默认 true |
| `docs_snippet_len` | int | 否 | 响应中每条 doc 最大字符数，0 表示不截断，>0 时仅截断响应中的 docs、不影响送入 LLM 的上下文，默认 0 |

`top_k`、`score_threshold`、`prompt_name`、`return_direct`、`return_docs`、`docs_snippet_len` 与请求体其他字段同级传入即可（后端从 `body.model_extra` 读取）。

### 3. 示例（知识库问答 + Netpropto）

```http
POST http://127.0.0.1:7861/knowledge_base/local_kb/Netpropto/chat/completions
Content-Type: application/json

{
  "messages": [
    { "role": "user", "content": "Are there any DFM issues with my uploaded model?" }
  ],
  "model": "deepseek-chat",
  "stream": true,
  "top_k": 3,
  "score_threshold": 0.5,
  "prompt_name": "default"
}
```

获取可用的知识库列表（用于填充「请选择知识库」）：**`GET /knowledge_base/list_knowledge_bases`**，返回数据里包含各知识库名称，可作为上面 URL 中的 `param`（如 `Netpropto`）。
