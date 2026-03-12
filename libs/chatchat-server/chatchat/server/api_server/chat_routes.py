from __future__ import annotations

import json
from typing import Any, Dict, List

from fastapi import APIRouter, Request
from langchain.prompts.prompt import PromptTemplate
from sse_starlette import EventSourceResponse

from chatchat.server.api_server.api_schemas import OpenAIChatInput
from chatchat.server.chat.chat import chat
from chatchat.server.chat.kb_chat import kb_chat
from chatchat.server.chat.feedback import chat_feedback
from chatchat.server.chat.file_chat import file_chat
from chatchat.server.db.repository import add_message_to_db
from langchain_core.utils.function_calling import convert_to_openai_tool

from chatchat.server.utils import (
    get_OpenAIClient,
    get_prompt_template,
    get_tool,
    get_tool_config,
)
from chatchat.settings import Settings
from chatchat.utils import build_logger
from .openai_routes import openai_request, OpenAIChatOutput


logger = build_logger()


def _message_to_dict(msg: Any) -> Dict:
    """将 API 返回的 message 对象转为请求体所需的 dict（含 tool_calls）。"""
    d = msg.model_dump() if hasattr(msg, "model_dump") else dict(msg)
    if not d.get("tool_calls"):
        return d
    out_tc = []
    for t in d["tool_calls"]:
        if isinstance(t, dict):
            fn = t.get("function") or {}
            out_tc.append({
                "id": t.get("id", ""),
                "type": t.get("type", "function"),
                "function": {"name": fn.get("name", ""), "arguments": fn.get("arguments", "{}")},
            })
        else:
            fn = getattr(t, "function", None)
            out_tc.append({
                "id": getattr(t, "id", "") or "",
                "type": getattr(t, "type", None) or "function",
                "function": {
                    "name": getattr(fn, "name", "") or (fn.get("name") if isinstance(fn, dict) else ""),
                    "arguments": getattr(fn, "arguments", "{}") or (fn.get("arguments") if isinstance(fn, dict) else "{}"),
                },
            })
    d["tool_calls"] = out_tc
    return d


async def _run_tool_and_to_content(name: str, args: Dict) -> str:
    """执行工具并将返回值转为给模型看的字符串。"""
    tool = get_tool(name)
    if not tool:
        return json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)
    try:
        result = await tool.ainvoke(args)
    except Exception as e:
        logger.exception(e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    if hasattr(result, "data"):
        data = result.data
    else:
        data = result
    if isinstance(data, (dict, list)):
        return json.dumps(data, ensure_ascii=False)
    return str(data)


chat_router = APIRouter(prefix="/chat", tags=["ChatChat 对话"])

# chat_router.post(
#     "/chat",
#     summary="与llm模型对话(通过LLMChain)",
# )(chat)

chat_router.post(
    "/feedback",
    summary="返回llm模型对话评分",
)(chat_feedback)


chat_router.post("/kb_chat", summary="知识库对话")(kb_chat)
chat_router.post("/file_chat", summary="文件对话")(file_chat)


@chat_router.post("/chat/completions", summary="兼容 openai 的统一 chat 接口")
async def chat_completions(
    request: Request,
    body: OpenAIChatInput,
) -> Dict:
    """
    请求参数与 openai.chat.completions.create 一致，可以通过 extra_body 传入额外参数
    tools 和 tool_choice 可以直接传工具名称，会根据项目里包含的 tools 进行转换
    通过不同的参数组合调用不同的 chat 功能：
    - tool_choice 指定时：直接调用该工具（入参为 extra_body.tool_input，缺省则为 {"query": 用户最后一条消息}），不经过 Agent
    - 仅 tools、无 tool_choice：agent 对话
    - 其它：LLM 对话
    以后还要考虑其它的组合（如文件对话）
    返回与 openai 兼容的 Dict
    """
    # 打印接口实际收到的 POST 参数，便于调试
    try:
        payload = body.model_dump() if hasattr(body, "model_dump") else body.dict()
        logger.info(f"[POST /chat/chat/completions] request params: {payload}")
    except Exception as e:
        logger.warning(f"log POST params failed: {e}")

    # 当调用本接口且 body 中没有传入 "max_tokens" 参数时, 默认使用配置中定义的值
    if body.max_tokens in [None, 0]:
        body.max_tokens = Settings.model_settings.MAX_TOKENS

    client = get_OpenAIClient(model_name=body.model, is_async=True)
    extra = {**body.model_extra} or {}
    for key in list(extra):
        delattr(body, key)

    # check tools & tool_choice in request body
    if isinstance(body.tool_choice, str):
        if t := get_tool(body.tool_choice):
            body.tool_choice = {"function": {"name": t.name}, "type": "function"}
    forced_tool_name = None
    if body.tool_choice:
        if isinstance(body.tool_choice, dict):
            forced_tool_name = (body.tool_choice.get("function") or {}).get("name")
        elif isinstance(body.tool_choice, str):
            forced_tool_name = body.tool_choice
    tool_input_extra = extra.get("tool_input")
    if isinstance(body.tools, list):
        for i in range(len(body.tools)):
            if isinstance(body.tools[i], str):
                if t := get_tool(body.tools[i]):
                    body.tools[i] = {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.args,
                        },
                    }

    conversation_id = extra.get("conversation_id")
  
    try:
        message_id = (
            add_message_to_db(
                chat_type="agent_chat",
                query=body.messages[-1]["content"],
                conversation_id=conversation_id,
            )
            if conversation_id
            else None
        )
    except Exception as e:
        logger.warning(f"failed to add message to db: {e}")
        message_id = None

    chat_model_config = {}  # TODO: 前端支持配置模型
    tool_config = {}
    if body.tools:
        tool_names = [x["function"]["name"] for x in body.tools]
        tool_config = {name: get_tool_config(name) for name in tool_names}

    return await _do_chat_completions(
        body, extra, forced_tool_name, tool_input_extra, tool_config, chat_model_config, message_id,
        extra_system_prompt="",
    )


@chat_router.post("/chat/openai/completions", summary="直接转发 OpenAI 格式 chat completions")
async def chat_openai_completions(
    request: Request,
    body: OpenAIChatInput,
) -> Dict:
    """
    请求体与 OpenAI Chat Completions API 一致，直接转发到配置的模型平台，不做 Agent/工具封装。
    支持 stream 与 非 stream，tools / tool_choice 由上游模型原生处理。
    """
    try:
        payload = body.model_dump() if hasattr(body, "model_dump") else body.dict()
        logger.info(f"[POST /chat/chat/openai/completions] request params: {payload}")
    except Exception as e:
        logger.warning(f"log POST params failed: {e}")

    params = body.model_dump(exclude_unset=True)
    if params.get("max_tokens") in [None, 0]:
        params["max_tokens"] = Settings.model_settings.MAX_TOKENS

    # 将 tools 中的工具名（字符串）转为上游 API 要求的 ChatCompletionTool 结构（含完整 JSON Schema）
    if isinstance(params.get("tools"), list):
        for i in range(len(params["tools"])):
            if isinstance(params["tools"][i], str):
                if t := get_tool(params["tools"][i]):
                    params["tools"][i] = convert_to_openai_tool(t)
    # tool_choice 若为字符串（工具名），转为完整 function 结构（name + description + parameters）
    if isinstance(params.get("tool_choice"), str) and params["tool_choice"] not in ("auto", "none"):
        if t := get_tool(params["tool_choice"]):
            full_tool = convert_to_openai_tool(t)
            params["tool_choice"] = {"type": "function", "function": full_tool["function"]}

    client = get_OpenAIClient(model_name=body.model, is_async=True)

    if body.stream:
        logger.info("提交给大模型的参数: %s", json.dumps(params, ensure_ascii=False, default=str))
        async def gen():
            try:
                stream = await client.chat.completions.create(**params)
                async for chunk in stream:
                    yield f"data: {chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.exception(e)
                yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"

        return EventSourceResponse(gen(), media_type="text/event-stream")
    else:
        # 非流式：若模型返回 tool_calls 则在服务端执行工具并继续请求，直到得到最终回复；最终统一返回 {data: content}
        max_tool_rounds = 10
        result = None
        for round_no in range(max_tool_rounds):
            logger.info("提交给大模型的参数(第%d轮): %s", round_no + 1, json.dumps(params, ensure_ascii=False, default=str))
            result = await client.chat.completions.create(**params)
            try:
                result_dump = result.model_dump() if hasattr(result, "model_dump") else str(result)
                logger.info("大模型返回(第%d轮): %s", round_no + 1, json.dumps(result_dump, ensure_ascii=False, default=str))
            except Exception as e:
                logger.warning("大模型返回序列化失败: %s", e)
            choice = result.choices[0] if result.choices else None
            if not choice:
                return {"data": ""}
            msg = choice.message
            tool_calls = getattr(msg, "tool_calls", None) or []
            # 无需调用工具（直接文本回复）或已结束：提取 content 返回 {data: content}
            if choice.finish_reason == "stop" or not tool_calls:
                content = getattr(msg, "content", None) or ""
                return {"data": content if isinstance(content, str) else str(content)}
            # 需要调用工具：执行后继续请求
            messages = list(params.get("messages", []))
            messages.append(_message_to_dict(msg))
            for tc in tool_calls:
                tc_id = getattr(tc, "id", None) or ""
                fn = getattr(tc, "function", tc) if hasattr(tc, "function") else tc
                name = getattr(fn, "name", None) or (fn.get("name") if isinstance(fn, dict) else None)
                args_raw = getattr(fn, "arguments", None) or (fn.get("arguments") if isinstance(fn, dict) else "") or "{}"
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
                except json.JSONDecodeError:
                    args = {}
                content = await _run_tool_and_to_content(name, args)
                messages.append({"role": "tool", "tool_call_id": tc_id, "content": content})
            params["messages"] = messages
        # 达到最大轮次仍未 stop：按最后一条消息的 content 返回
        if result and result.choices:
            msg = result.choices[0].message
            content = getattr(msg, "content", None) or ""
            return {"data": content if isinstance(content, str) else str(content)}
        return {"data": ""}


async def _do_chat_completions(
    body: OpenAIChatInput,
    extra: dict,
    forced_tool_name,
    tool_input_extra,
    tool_config: dict,
    chat_model_config: dict,
    message_id,
    extra_system_prompt: str = "",
):
    """chat/completions 与 chat/openai/completions 共用逻辑。"""
    return await chat(
        query=body.messages[-1]["content"],
        metadata=extra.get("metadata", {}),
        conversation_id=extra.get("conversation_id", ""),
        message_id=message_id,
        history_len=-1,
        stream=body.stream,
        chat_model_config=extra.get("chat_model_config", chat_model_config),
        tool_config=tool_config,
        use_mcp=extra.get("use_mcp", False),
        max_tokens=body.max_tokens,
        tool_choice=forced_tool_name,
        tool_input=tool_input_extra,
        extra_system_prompt=extra_system_prompt or "",
    )
