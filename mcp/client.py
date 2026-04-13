"""MCP Client - JSON-RPC client for MCP servers"""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server"""
    name: str
    command: str
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None


class MCPClient:
    """
    MCP Client

    Connects to MCP servers via stdio and manages tool discovery/execution.
    """

    def __init__(self):
        self._processes: Dict[str, asyncio.subprocess.Process] = {}
        self._tools: Dict[str, Dict] = {}  # full_name -> {server, tool}
        self._request_id = 0

    async def connect(self, config: MCPServerConfig) -> bool:
        """
        Connect to an MCP server

        Args:
            config: Server configuration

        Returns:
            True if connected successfully
        """
        try:
            # Build environment
            env = dict(os.environ)
            if config.env:
                env.update(config.env)

            # Start subprocess
            process = await asyncio.create_subprocess_exec(
                config.command,
                *(config.args or []),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            self._processes[config.name] = process

            # Initialize handshake
            init_response = await self._send_request(config.name, {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "tiny-agent",
                        "version": "1.0.0"
                    }
                }
            })

            if "error" in init_response:
                logger.error(f"Failed to initialize {config.name}: {init_response['error']}")
                return False

            # Get tools list
            tools_response = await self._send_request(config.name, {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/list"
            })

            tools = tools_response.get("result", {}).get("tools", [])

            # Register tools
            for tool in tools:
                full_name = f"mcp_{config.name}_{tool['name']}"
                self._tools[full_name] = {
                    "server": config.name,
                    "tool": tool
                }

            logger.info(f"Connected to MCP server '{config.name}' with {len(tools)} tools")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to {config.name}: {e}")
            return False

    async def disconnect(self, server_name: str) -> bool:
        """Disconnect from a server"""
        if server_name in self._processes:
            process = self._processes.pop(server_name)
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()

            # Remove tools
            to_remove = [name for name in self._tools if self._tools[name]["server"] == server_name]
            for name in to_remove:
                del self._tools[name]

            logger.info(f"Disconnected from MCP server: {server_name}")
            return True
        return False

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """
        Call an MCP tool

        Args:
            tool_name: Full tool name (mcp_servername_toolname)
            arguments: Tool arguments

        Returns:
            Tool result
        """
        if tool_name not in self._tools:
            raise ValueError(f"Tool not found: {tool_name}")

        tool_info = self._tools[tool_name]
        server_name = tool_info["server"]
        actual_name = tool_info["tool"]["name"]

        response = await self._send_request(server_name, {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": actual_name,
                "arguments": arguments
            }
        })

        if "error" in response:
            raise RuntimeError(response["error"].get("message", "Tool call failed"))

        return response.get("result", {}).get("content", [])

    def get_tools(self) -> List[dict]:
        """Get all MCP tools in LLM schema format"""
        schemas = []
        for full_name, info in self._tools.items():
            tool = info["tool"]
            schemas.append({
                "name": full_name,
                "description": tool.get("description", ""),
                "input_schema": tool.get("inputSchema", {"type": "object", "properties": {}})
            })
        return schemas

    def list_tools(self) -> List[str]:
        """List all available tool names"""
        return list(self._tools.keys())

    def is_mcp_tool(self, tool_name: str) -> bool:
        """Check if a tool is an MCP tool"""
        return tool_name.startswith("mcp_") and tool_name in self._tools

    async def _send_request(self, server_name: str, request: dict) -> dict:
        """Send a JSON-RPC request to a server"""
        if server_name not in self._processes:
            raise ValueError(f"Not connected to server: {server_name}")

        process = self._processes[server_name]

        # Send request
        request_str = json.dumps(request) + "\n"
        process.stdin.write(request_str.encode())
        await process.stdin.drain()

        # Read response
        response_line = await process.stdout.readline()
        if not response_line:
            raise RuntimeError(f"No response from server: {server_name}")

        return json.loads(response_line)

    def _next_id(self) -> int:
        """Get next request ID"""
        self._request_id += 1
        return self._request_id