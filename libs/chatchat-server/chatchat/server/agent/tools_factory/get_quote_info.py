"""
Query quote / tooling price by quote number via external API.
"""
import requests

from chatchat.server.pydantic_v1 import Field
from chatchat.server.utils import get_tool_config

from .tools_registry import regist_tool

from langchain_chatchat.agent_toolkits.all_tools.tool import (
    BaseToolOutput,
)


@regist_tool(title="Quote info query")
def get_quote_info(
    quotenum: str = Field(
        description="Quote number provided by the user. Supports multiple formats (e.g. U-250310-001, C-140829063653). Pass the value as-is; do not refuse to call based on format; let the API return the result or error."
    ),
):
    """Call this tool when the user asks for quote info, price, cost, lead time, etc. for a quote. Quote numbers may be in various formats (U-*, C-*, etc.); pass the user's value as-is and do not refuse based on format; whether it is queryable is determined by the API response."""

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
