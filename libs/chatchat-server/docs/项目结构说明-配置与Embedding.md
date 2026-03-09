# 项目结构说明：配置与 Embedding 模型

本文档说明如何在不改源码的前提下，通过配置和操作切换 Embedding 模型（例如从 Ollama 改为 DeepSeek API）。

---

## 一、配置从哪里读（数据目录）

- 环境变量 **`CHATCHAT_ROOT`** 决定「数据目录」。
- 未设置时，默认是**当前工作目录下的 `chatchat_data`**（若你曾改过 `settings.py` 的默认值，则以当前代码为准）。
- 所有运行时用到的配置 YAML 都在该目录下：
  - `model_settings.yaml` — 模型与平台（LLM、Embedding、MODEL_PLATFORMS）
  - `basic_settings.yaml` — 基础、知识库路径等
  - `prompt_settings.yaml` — 提示词模板
  - 其他 `*_settings.yaml` / `*.json`

**你需要改的，是「实际生效」的那份配置**：  
即 **`<CHATCHAT_ROOT>/model_settings.yaml`**（例如 `C:\projects\Langchain-Chatchat\chatchat_data\model_settings.yaml`，或你在启动前设置的目录）。

---

## 二、Embedding 相关配置（改用其他模型）

### 1. 默认 Embedding 模型

- 在 **`<CHATCHAT_ROOT>/model_settings.yaml`** 中：
  - **`DEFAULT_EMBEDDING_MODEL`**：全局默认使用的 Embedding 模型名。
- 新建知识库、临时向量库、以及未显式指定模型的地方，都会用这个默认值。

### 2. 模型平台（MODEL_PLATFORMS）

- 同一文件中的 **`MODEL_PLATFORMS`** 是一个列表，每一项是一个「平台」：
  - `platform_name`：平台名称（仅标识用）
  - `platform_type`：类型，如 `openai`、`ollama`、`xinference`、`oneapi` 等
  - `api_base_url`：该平台的 API 地址（如 Ollama 为 `http://127.0.0.1:11434/v1`，DeepSeek 为 `https://api.deepseek.com/v1`）
  - `api_key`：若需要则填写（DeepSeek/OpenAI 等必填）
  - `embed_models`：该平台提供的 Embedding 模型名列表

- 代码会根据 **模型名** 找到其所属平台，再用该平台的 `api_base_url` + `api_key` 调用。
- 因此：要改用 DeepSeek Embedding，需要：
  1. 在 `MODEL_PLATFORMS` 里有一个 `platform_type: openai`、`api_base_url: https://api.deepseek.com/v1`、`api_key` 填好的平台，且 `embed_models` 中包含 `deepseek-embedding`（或你实际使用的模型名）。
  2. 把 **`DEFAULT_EMBEDDING_MODEL`** 设为该模型名（如 `deepseek-embedding`）。

---

## 三、为什么会出现「连 11434 / Ollama」的报错

- 报错里的 **127.0.0.1:11434** 是 **Ollama** 的默认端口。
- 可能两种情况：
  1. **当前默认仍是 Ollama 的模型**  
     `<CHATCHAT_ROOT>/model_settings.yaml` 里 `DEFAULT_EMBEDDING_MODEL` 指向了 Ollama 平台下的某个模型（如 `quentinz/bge-large-zh-v1.5`），且该平台 `api_base_url` 为 `http://127.0.0.1:11434/v1`。
  2. **知识库创建时用的是 Ollama 模型**  
     每个知识库在**创建时**会把当时使用的 Embedding 模型名写入数据库。之后**加载该知识库**时，会用**库里记录的模型**，而不是当前的 `DEFAULT_EMBEDDING_MODEL`。  
     所以：只要某个知识库当初是用 Ollama 模型建的，之后每次加载这个知识库都会去连 11434。

**你只需通过配置和操作解决，无需改代码：**

- 对**新知识库**：保证上面第二节中 `DEFAULT_EMBEDDING_MODEL` 和 `MODEL_PLATFORMS` 已改为 DeepSeek（或你想要的模型），新建的知识库就会用新模型。
- 对**已经用 Ollama 建好的知识库**：  
  向量索引是按「当时用的 Embedding 模型」建的，不能直接换成另一个模型名继续用（维度可能不同）。  
  做法只能是：**删除该知识库后，用当前默认的 Embedding 模型重新建一个知识库，再重新上传文档**；或在支持「按知识库选择 Embedding 模型」的界面里，新建时选择 DeepSeek 等新模型。

---

## 四、关键文件与路径速查（仅作理解用，不必改代码）

| 作用 | 位置 |
|------|------|
| 配置根目录（数据目录） | 环境变量 `CHATCHAT_ROOT`，或 `chatchat/settings.py` 中的默认值 |
| 默认 Embedding 与模型平台 | `<CHATCHAT_ROOT>/model_settings.yaml` 的 `DEFAULT_EMBEDDING_MODEL`、`MODEL_PLATFORMS` |
| 配置如何被读取 | `chatchat/settings.py` 中 `ApiModelSettings` 等通过 `CHATCHAT_ROOT` 读上述 yaml |
| 获取默认 Embedding 模型名 | `chatchat/server/utils.py` 的 `get_default_embedding()` |
| 根据模型名创建 Embeddings 实例 | `chatchat/server/utils.py` 的 `get_Embeddings(embed_model=...)`，内部根据 `get_model_info(model_name)` 取对应平台的 `api_base_url`、`api_key` |
| 知识库使用的 embed_model 来源 | 创建时传入并写入 DB；加载时从 `chatchat/server/knowledge_base/kb_service/base.py` 的 `load_kb_from_db` → `get_service_by_name` 取出的 `embed_model` 用于 `faiss_cache.load_vector_store(..., embed_model=...)` |
| 向量库加载（报错发生处） | `chatchat/server/knowledge_base/kb_cache/faiss_cache.py` 的 `KBFaissPool.load_vector_store`、`MemoFaissPool.load_vector_store`，内部调用 `get_Embeddings(embed_model=...)` |

---

## 五、你自己需要做的修改步骤（不改源码）

1. **确认实际使用的数据目录**  
   启动服务时是否设置了 `CHATCHAT_ROOT`？若未设置，数据目录是当前工作目录下的 `chatchat_data`（或你在 `settings.py` 里设的默认值）。  
   然后打开 **该目录下的 `model_settings.yaml`**。

2. **在 `model_settings.yaml` 中**  
   - 在 `MODEL_PLATFORMS` 中确保有一个 DeepSeek（或你想要的）平台：`platform_type: openai`，`api_base_url: https://api.deepseek.com/v1`，`api_key` 填好，`embed_models` 里包含 `deepseek-embedding`。  
   - 把 **`DEFAULT_EMBEDDING_MODEL`** 改为 `deepseek-embedding`（或该平台下的其他 Embedding 模型名）。

3. **对已存在的、曾用 Ollama 建的知识库**  
   - 在 Web 或 API 中**删除**该知识库（若需要可先备份文档）。  
   - **新建**一个知识库（此时会使用当前的 `DEFAULT_EMBEDDING_MODEL`，即 DeepSeek）。  
   - 重新上传文档，让新知识库用新 Embedding 模型建索引。

按以上步骤操作即可在不改源码的前提下，把 Embedding 从 Ollama 换成 DeepSeek（或其它已配置的模型）。
