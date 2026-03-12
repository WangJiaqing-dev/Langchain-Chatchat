# 自定义 Function Tool 指南

在 Chatchat 中，Agent 使用的「Function Tool」都通过 `@regist_tool` 注册，并可在对话页被勾选调用。按下面步骤即可新增或自定义自己的工具。

---

## 一、步骤概览

1. 在 `chatchat/server/agent/tools_factory/` 下新增或修改一个 Python 文件，用 `@regist_tool` 定义工具函数。
2. 在 `tools_factory/__init__.py` 中 import 该工具，使其被加载进全局注册表。
3. 若工具需要配置（API Key、开关等），在 `tool_settings.yaml` 中增加对应配置项。
4. 重启服务后，新工具会出现在「对话」页的工具列表中，可被勾选使用。

---

## 二、最小示例：无配置工具

函数名即工具名（如 `my_echo`），会作为调用时的 `name`。参数用 `Field` 描述，便于模型生成正确入参。

```python
# chatchat/server/agent/tools_factory/my_echo.py
from chatchat.server.pydantic_v1 import Field
from .tools_registry import regist_tool
from langchain_chatchat.agent_toolkits.all_tools.tool import BaseToolOutput


@regist_tool(title="回显工具")
def my_echo(
    message: str = Field(description="User message to echo back"),
) -> str:
    """Echo the user message. Use when the user asks to repeat or echo something."""
    return BaseToolOutput(message)
```

- **title**：在对话页工具列表中显示的名称。
- **函数 docstring**：会作为工具的 `description` 传给模型，用于决定何时调用该工具，建议写清适用场景。
- **返回值**：统一用 `BaseToolOutput(...)` 包装，支持纯文本或结构化数据（如 dict），Agent 会将其转为模型可读的字符串。

在 `__init__.py` 中增加一行：

```python
from .my_echo import my_echo
```

保存后重启服务，在「对话」里勾选「回显工具」即可在 Agent 对话中调用。

---

## 三、带配置的工具（如 API Key）

若工具需要从配置读取参数（如 API Key、开关、URL），在函数内用 `get_tool_config(工具名)` 读取，并在 `tool_settings.yaml` 中增加同名配置块。

**1. 工具实现示例**

```python
# chatchat/server/agent/tools_factory/my_weather.py
from chatchat.server.pydantic_v1 import Field
from chatchat.server.utils import get_tool_config
from .tools_registry import regist_tool
from langchain_chatchat.agent_toolkits.all_tools.tool import BaseToolOutput


@regist_tool(title="我的天气")
def my_weather(
    city: str = Field(description="City name, e.g. Beijing"),
) -> str:
    """Query weather for a city. Use when user asks about weather."""
    config = get_tool_config("my_weather")
    api_key = config.get("api_key", "")
    if not api_key:
        return BaseToolOutput({"error": "my_weather.api_key not configured"})
    # 调用你的 API，示例省略
    result = f"Weather in {city}: ..."
    return BaseToolOutput(result)
```

**2. 在 `tool_settings.yaml` 中增加配置**

```yaml
# tool_settings.yaml 末尾或合适位置增加：
my_weather:
  use: true
  api_key: "your-api-key"
```

- 配置项完全自定义，`get_tool_config("my_weather")` 会返回该 dict。
- `use` 为项目内常见约定，是否在 UI 中过滤由前端/业务决定；工具逻辑里可按需读取。

**3. 在 `__init__.py` 中注册**

```python
from .my_weather import my_weather
```

---

## 四、`@regist_tool` 常用参数

| 参数 | 说明 |
|------|------|
| **title** | 展示名称，如「数学计算器」「本地知识库」。 |
| **description** | 覆盖函数 docstring，给模型看的工具说明。不传则用 docstring。 |
| **return_direct** | 为 True 时，工具返回后不再交给模型总结，直接作为最终回复（按需使用）。 |
| **args_schema** | 自定义 Pydantic 模型作为入参 schema；不传则从函数参数自动推断。 |
| **infer_schema** | 是否从函数签名推断 schema，默认 True。 |

函数参数建议都用 `Field(description="...")`，便于模型生成正确的 `tool_calls` 参数。

---

## 五、多参数与复杂入参

多参数时保持顺序或命名与 schema 一致即可，Agent 会按 name 传参：

```python
@regist_tool(title="两数运算")
def my_calc(
    a: float = Field(description="First number"),
    b: float = Field(description="Second number"),
    op: str = Field(description="One of: add, sub, mul, div"),
) -> str:
    """Simple calculator. Use for math between two numbers."""
    config = get_tool_config("my_calc")  # 若需要配置
    if op == "add":
        return BaseToolOutput(str(a + b))
    # ...
    return BaseToolOutput("unknown op")
```

---

## 六、强制使用你的工具（tool_choice）

当用户在对话页**只勾选你这一个工具**时，请求会带 `tool_choice`，后端会**直接调用该工具**而不再经过 Agent 推理（参见 `chat_routes.py` / `chat.py` 中 `tool_choice` 逻辑）。  
因此只要你的工具在列表里且被单独选中，就会按用户输入直接执行，无需模型“选择”。

---

## 七、调试与单独调用

- **列出所有工具**：`GET /tools`，返回所有已注册工具的 name、title、description、args、config。
- **直接调用工具**：`POST /tools/call`，body 示例：`{"name": "my_echo", "tool_input": {"message": "hello"}}`，用于不经过对话的联调。

---

## 八、文件与配置小结

| 操作 | 位置 |
|------|------|
| 定义工具 | `chatchat/server/agent/tools_factory/你的工具.py` |
| 注册到列表 | `chatchat/server/agent/tools_factory/__init__.py` 中 import |
| 工具配置 | `tool_settings.yaml` 中增加与工具名同名的配置块（可选） |
| 工具列表/直接调用 API | `GET /tools`、`POST /tools/call` |

按上述方式即可自定义自己的 Function Tool，并在 Agent 对话或 `tool_choice` 场景下使用。
