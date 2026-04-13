"""MCP (Model Context Protocol) integration for Tiny-Agent"""

from .client import MCPClient, MCPServerConfig
from .connector import MCPConnector

__all__ = ["MCPClient", "MCPServerConfig", "MCPConnector"]