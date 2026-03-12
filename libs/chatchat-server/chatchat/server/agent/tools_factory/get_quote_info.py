"""
通过外部 API 根据报价单号查询报价/工装价格信息。
"""
import requests

from chatchat.server.pydantic_v1 import Field
from chatchat.server.utils import get_tool_config

from .tools_registry import regist_tool

from langchain_chatchat.agent_toolkits.all_tools.tool import (
    BaseToolOutput,
)


@regist_tool(title="报价信息查询")
def get_quote_info(
    quotenum: str = Field(
        description="Quote number, e.g. U-250310-001. 报价单号。"
    ),
):
    """Use this tool when the user asks for quote info, tooling price, or data by quote number (报价单号). Fetches from the getToolingPriceByQuotenum API."""

    config = get_tool_config("get_quote_info")
    base_url = (config.get("base_url") or "http://127.0.0.1:8000").rstrip("/")
    url = f"{base_url}/api/customer/getToolingPriceByQuotenum"
    params = {"quotenum": quotenum}

    try:
        resp = requests.get(url, params=params, timeout=config.get("timeout", 30))
        resp.raise_for_status()
        data = resp.json()
        return BaseToolOutput(data)
    except requests.exceptions.RequestException as e:
        return BaseToolOutput({"error": str(e), "quotenum": quotenum})
    except ValueError as e:
        return BaseToolOutput({"error": f"Invalid response: {e}", "quotenum": quotenum})
