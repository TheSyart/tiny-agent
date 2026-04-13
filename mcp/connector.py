"""MCP Connector - High-level MCP management"""

from typing import Dict, List, Optional, Any
from pathlib import Path
import logging

from .client import MCPClient, MCPServerConfig

logger = logging.getLogger(__name__)


class MCPConnector:
    """
    High-level MCP management

    Provides a unified interface for managing MCP servers and tools.
    """

    def __init__(self):
        self.client = MCPClient()
        self._configs: Dict[str, MCPServerConfig] = {}

    async def add_server(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Add and connect to an MCP server

        Args:
            name: Server name
            command: Command to run
            args: Command arguments
            env: Environment variables

        Returns:
            True if connected successfully
        """
        config = MCPServerConfig(
            name=name,
            command=command,
            args=args,
            env=env
        )

        self._configs[name] = config
        return await self.client.connect(config)

    async def remove_server(self, name: str) -> bool:
        """Remove and disconnect from a server"""
        if name in self._configs:
            del self._configs[name]
        return await self.client.disconnect(name)

    async def reload_server(self, name: str) -> bool:
        """Reconnect to a server"""
        if name not in self._configs:
            logger.warning(f"Server not found: {name}")
            return False

        await self.client.disconnect(name)
        return await self.client.connect(self._configs[name])

    def get_tools(self) -> List[dict]:
        """Get all MCP tool schemas"""
        return self.client.get_tools()

    def list_tools(self) -> List[str]:
        """List all MCP tool names"""
        return self.client.list_tools()

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Call an MCP tool"""
        return await self.client.call_tool(tool_name, arguments)

    def is_mcp_tool(self, tool_name: str) -> bool:
        """Check if a tool is an MCP tool"""
        return self.client.is_mcp_tool(tool_name)

    async def load_from_config(self, config: dict) -> List[str]:
        """
        Load MCP servers from configuration

        Args:
            config: Config dict with 'servers' key

        Returns:
            List of successfully connected server names
        """
        connected = []
        servers = config.get("servers", {})

        for name, server_config in servers.items():
            success = await self.add_server(
                name=name,
                command=server_config.get("command", ""),
                args=server_config.get("args"),
                env=server_config.get("env")
            )
            if success:
                connected.append(name)

        return connected

    async def close(self) -> None:
        """Disconnect from all servers"""
        for name in list(self._configs.keys()):
            await self.client.disconnect(name)