"""FastAPI Web Application for Tiny-Agent"""

import re
import json
import asyncio
from datetime import datetime
from typing import Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.loop import AgentLoop
from agent.types import ToolUseBlock
from config import Config
from safety.manager import SafetyMode


# Global state
agent: Optional[AgentLoop] = None
config: Optional[Config] = None
active_connections: list[WebSocket] = []
# Confirmation id -> Future[bool]. Access is guarded by _confirm_lock because
# multiple WS connections may resolve / inspect the map concurrently.
pending_confirmations: dict[str, "asyncio.Future[bool]"] = {}
_confirm_lock = asyncio.Lock()


# Whitelisted runtime-mutable config fields (dotted path -> type).
_PATCHABLE_FIELDS: dict[str, type] = {
    "llm.temperature": float,
    "llm.max_tokens": int,
    "agent.max_loops": int,
    "agent.verbose": bool,
    "safety.mode": str,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan"""
    print("Starting Tiny-Agent Web UI...")

    if agent and agent.safety:
        agent.safety.set_confirmation_callback(handle_confirmation)

    yield

    print("Shutting down...")


def create_app(agent_instance: AgentLoop, config_instance: Config) -> FastAPI:
    """Create the FastAPI application"""
    global agent, config
    agent = agent_instance
    config = config_instance

    app = FastAPI(
        title="Tiny-Agent",
        description="A lightweight AI agent framework",
        version="0.2.0",
        lifespan=lifespan,
    )

    # CORS — default to localhost only.
    cors_origins = getattr(config_instance.webui, "cors_origins", None) or [
        f"http://{config_instance.webui.host}:{config_instance.webui.port}",
        f"http://127.0.0.1:{config_instance.webui.port}",
        f"http://localhost:{config_instance.webui.port}",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static files
    static_path = Path(__file__).parent / "static"
    static_path.mkdir(parents=True, exist_ok=True)

    if (static_path / "css").exists():
        app.mount("/static/css", StaticFiles(directory=str(static_path / "css")), name="css")
    if (static_path / "js").exists():
        app.mount("/static/js", StaticFiles(directory=str(static_path / "js")), name="js")

    # Routes
    @app.get("/")
    async def index():
        """Serve the main page"""
        index_path = static_path / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return HTMLResponse(
            content="<h1>Tiny-Agent</h1><p>static/index.html is missing.</p>",
            status_code=500,
        )

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for real-time communication"""
        await websocket.accept()
        active_connections.append(websocket)

        chat_task: Optional[asyncio.Task] = None

        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)

                if message["type"] == "chat":
                    if chat_task and not chat_task.done():
                        chat_task.cancel()
                    chat_task = asyncio.create_task(
                        handle_chat(websocket, message["content"])
                    )

                elif message["type"] == "confirm":
                    await handle_confirm_response(message)

                elif message["type"] == "clear":
                    # Auto-archive before clearing, if enabled.
                    try:
                        if (
                            config
                            and config.memory.archive.enabled
                            and config.memory.archive.auto_archive_on_clear
                            and agent.memory.archive is not None
                        ):
                            await agent.memory.archive_current_session(
                                clear_after=True,
                            )
                        else:
                            agent.memory.clear_short_term()
                    except Exception as e:
                        agent.memory.clear_short_term()
                        await websocket.send_json(
                            {"type": "error", "message": f"archive failed: {e}"}
                        )
                    await websocket.send_json({"type": "cleared"})

        except WebSocketDisconnect:
            if chat_task and not chat_task.done():
                chat_task.cancel()
            if websocket in active_connections:
                active_connections.remove(websocket)

    # -------------------- REST: tools / config --------------------
    @app.get("/api/tools")
    async def list_tools():
        """List available tools"""
        return {"tools": agent.tools.list_tools_info() if agent else []}

    @app.get("/api/config")
    async def get_config():
        """Return config with sensitive fields masked."""
        if not config:
            return {}
        data = config.to_dict()
        # Mask secrets
        llm = data.get("llm", {})
        key = llm.get("api_key") or ""
        if key:
            llm["api_key"] = (
                f"{key[:4]}…{key[-4:]}" if len(key) > 10 else "***"
            )
        data["llm"] = llm
        data["_patchable_fields"] = sorted(_PATCHABLE_FIELDS.keys())
        return data

    @app.patch("/api/config")
    async def patch_config(body: dict):
        """Hot-update a whitelist of runtime config fields.

        Only mutates the in-memory ``Config`` + live agent — does not write
        back to config.yaml.
        """
        if not agent or not config:
            raise HTTPException(500, "agent not initialized")

        applied: dict[str, Any] = {}
        for key, value in body.items():
            if key not in _PATCHABLE_FIELDS:
                raise HTTPException(400, f"field not patchable: {key}")
            expected_type = _PATCHABLE_FIELDS[key]
            try:
                if expected_type is bool:
                    coerced = bool(value)
                else:
                    coerced = expected_type(value)
            except (TypeError, ValueError):
                raise HTTPException(400, f"bad value for {key}")

            section, field = key.split(".", 1)
            target = getattr(config, section)
            setattr(target, field, coerced)
            applied[key] = coerced

            # Propagate to live agent instances.
            if key == "llm.temperature":
                agent.llm.temperature = coerced
            elif key == "llm.max_tokens":
                agent.llm.max_tokens = coerced
            elif key == "agent.max_loops":
                agent.config.max_loops = coerced
            elif key == "agent.verbose":
                agent.config.verbose = coerced
            elif key == "safety.mode" and agent.safety is not None:
                mode_enum = {
                    "sandbox": SafetyMode.SANDBOX,
                    "confirm": SafetyMode.CONFIRM,
                    "trust": SafetyMode.TRUST,
                }.get(coerced)
                if mode_enum is None:
                    raise HTTPException(400, f"unknown safety mode: {coerced}")
                agent.safety.config.mode = mode_enum

        return {"applied": applied}

    # -------------------- REST: memory --------------------
    @app.get("/api/memory/short-term")
    async def get_short_term():
        msgs = agent.memory.short_term.get_messages()
        max_msgs = agent.memory.short_term.max_messages
        trigger = (
            config.memory.compression.trigger_threshold
            if config and config.memory.compression.enabled
            else None
        )
        return {
            "messages": msgs,
            "count": len(msgs),
            "max": max_msgs,
            "trigger_threshold": trigger,
        }

    @app.get("/api/memory/chat-history")
    async def get_chat_history():
        """Return short-term messages in UI-friendly format, preserving thinking blocks."""
        msgs = agent.memory.short_term.get_messages()
        result = []
        for m in msgs:
            role = m.get("role", "")
            content = m.get("content", "")
            if role not in ("user", "assistant"):
                continue
            if isinstance(content, list):
                text = ""
                thinking = ""
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text":
                        text += b.get("text", "")
                    elif b.get("type") == "thinking":
                        thinking += b.get("thinking", "")
            elif isinstance(content, str):
                text = content
                thinking = ""
            else:
                continue
            text = text.strip()
            thinking = thinking.strip()
            if text or thinking:
                entry = {"role": role, "text": text}
                if thinking:
                    entry["thinking"] = thinking
                result.append(entry)
        return {"messages": result}

    @app.get("/api/memory/search")
    async def search_memory(q: str, limit: int = 10):
        if not agent.memory.archive:
            return {"results": []}
        return {"results": await agent.memory.archive.search(q, limit)}

    @app.get("/api/memory/archives")
    async def list_archives(limit: int = 50, offset: int = 0):
        sessions = await agent.memory.list_archived_sessions(limit, offset)
        return {"sessions": sessions}

    @app.get("/api/memory/archives/{session_id}")
    async def get_archive(session_id: str):
        data = await agent.memory.load_archived_session(session_id)
        if data is None:
            raise HTTPException(404, "session not found")
        return data

    @app.post("/api/memory/compress")
    async def trigger_compress():
        n = await agent.memory.force_compress()
        return {"compressed_count": n}

    @app.post("/api/memory/archive")
    async def trigger_archive():
        sid = await agent.memory.archive_current_session()
        if sid is None:
            raise HTTPException(400, "archive not enabled or memory empty")
        return {"archived_session_id": sid}

    @app.get("/api/memory/important")
    async def get_important_memory():
        """Return the contents of memory.md (important persistent memories)."""
        storage = getattr(agent.memory, "_storage_path", None) or "./data/memory"
        path = Path(storage) / "memory.md"
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        return {"content": content}

    @app.delete("/api/memory/important")
    async def clear_important_memory():
        """Clear memory.md (reset important memories)."""
        storage = getattr(agent.memory, "_storage_path", None) or "./data/memory"
        path = Path(storage) / "memory.md"
        if path.exists():
            path.write_text("# 重要记忆\n", encoding="utf-8")
        return {"ok": True}

    # -------------------- REST: config / prompt --------------------
    @app.get("/api/config/prompt")
    async def get_prompt():
        """Return the current system prompt file content."""
        path = Path("prompts/tiny.md")
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        return {"content": content}

    @app.patch("/api/config/prompt")
    async def patch_prompt(body: dict):
        """Overwrite prompts/tiny.md and hot-reload the agent's system prompt."""
        new_content = body.get("content", "")
        if not new_content.strip():
            raise HTTPException(400, "content cannot be empty")
        Path("prompts/tiny.md").write_text(new_content, encoding="utf-8")
        if agent:
            agent.config.system_prompt = new_content
        return {"ok": True}

    # -------------------- REST: MCP servers --------------------
    @app.get("/api/mcp/servers")
    async def get_mcp_servers():
        """List MCP servers with connection status."""
        connector = getattr(agent, 'mcp', None)
        servers = []
        if connector and connector._configs:
            tool_names = agent.tools.list_tools() if agent else []
            for name, cfg in connector._configs.items():
                tool_count = sum(1 for t in tool_names if t.startswith(f"mcp_{name}_"))
                servers.append({
                    "name": name,
                    "command": cfg.command,
                    "args": cfg.args or [],
                    "env": cfg.env or {},
                    "enabled": True,
                    "connected": tool_count > 0,
                    "tool_count": tool_count,
                })
        elif config and config.mcp.servers:
            for name, cfg in config.mcp.servers.items():
                servers.append({
                    "name": name,
                    "command": cfg.command,
                    "args": cfg.args or [],
                    "env": cfg.env or {},
                    "enabled": cfg.enabled,
                    "connected": False,
                    "tool_count": 0,
                })
        return {"servers": servers}

    @app.post("/api/mcp/servers")
    async def add_mcp_server(body: dict):
        """Add a new MCP server (live + persisted to config.yaml)."""
        name = body.get("name", "").strip()
        command = body.get("command", "").strip()
        if not name or not command:
            raise HTTPException(400, "name and command are required")
        args = body.get("args") or []
        env = body.get("env") or {}
        connected = False
        connector = getattr(agent, 'mcp', None)
        if connector:
            try:
                ok = await connector.add_server(name=name, command=command, args=args, env=env)
                connected = ok
            except Exception as e:
                pass  # Live connection failed — still persist to yaml
        _patch_mcp_yaml(name, {"command": command, "args": args, "env": env})
        return {"ok": True, "connected": connected}

    @app.delete("/api/mcp/servers/{name}")
    async def remove_mcp_server(name: str):
        """Remove an MCP server (disconnect + remove from config.yaml)."""
        connector = getattr(agent, 'mcp', None)
        if connector:
            try:
                await connector.remove_server(name)
            except Exception:
                pass
        _patch_mcp_yaml(name, None)
        return {"ok": True}

    @app.post("/api/mcp/servers/{name}/reload")
    async def reload_mcp_server(name: str):
        """Reconnect to an MCP server."""
        connector = getattr(agent, 'mcp', None)
        if not connector:
            raise HTTPException(400, "MCP connector not initialized")
        ok = await connector.reload_server(name)
        return {"ok": ok}

    # -------------------- REST: skills --------------------
    @app.get("/api/skills")
    async def list_skills():
        """List loaded skills with metadata."""
        skills = getattr(agent, '_loaded_skills', [])
        dirs = config.skills.directories if config else []
        auto = config.skills.auto_discover if config else True
        return {"skills": list(skills), "directories": dirs, "auto_discover": auto}

    @app.post("/api/skills")
    async def create_skill(body: dict):
        """Create a new skill file, write it to the skills/custom directory, and hot-load it.

        Supports two skill types:
        - type="python" (default): writes skill.py, hot-loads tools via SkillLoader
        - type="knowledge": writes SKILL.md, hot-reloads KnowledgeSkillRegistry
        """
        import re as _re
        name = body.get("name", "").strip()
        skill_type = body.get("type", "python")  # "python" or "knowledge"

        if not name:
            raise HTTPException(400, "name is required")
        if not _re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', name):
            raise HTTPException(400, "name must start with a letter and contain only letters, digits, underscores")

        dirs = config.skills.directories if config else []
        if not dirs:
            raise HTTPException(400, "no skills.directories configured")

        # Prefer a directory named "custom" for user-created skills; fall back to last dir
        target_dir = next(
            (d for d in dirs if Path(d).name == "custom"),
            dirs[-1],
        )
        skill_dir = Path(target_dir) / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        # ── Knowledge skill (SKILL.md) ──
        if skill_type == "knowledge":
            content = body.get("content", "").strip()
            description = body.get("description", "").strip() or "(no description)"
            if not content:
                raise HTTPException(400, "content is required for knowledge skills")

            skill_file = skill_dir / "SKILL.md"
            full_md = f"---\nname: {name}\ndescription: {description}\n---\n\n{content}"
            skill_file.write_text(full_md, encoding="utf-8")

            # Hot-reload knowledge registry
            try:
                registry = getattr(agent, '_knowledge_registry', None)
                if registry is not None:
                    registry.reload(dirs)
            except Exception:
                pass

            return {"ok": True, "loaded": True, "path": str(skill_file), "type": "knowledge",
                    "skill": {"name": name, "description": description}}

        # ── Python tool skill (skill.py) ──
        code = body.get("code", "").strip()
        if not code:
            raise HTTPException(400, "code is required for python skills")

        skill_file = skill_dir / "skill.py"
        skill_file.write_text(code, encoding="utf-8")

        # Hot-load the skill
        loaded_info = None
        try:
            from skills.loader import SkillLoader
            loader = SkillLoader(str(target_dir))
            skill = loader.load(str(skill_file))
            if skill:
                for tool in loader.get_all_tools():
                    try:
                        agent.tools.register(tool)
                    except Exception:
                        pass
                if not hasattr(agent, '_loaded_skills'):
                    agent._loaded_skills = []  # type: ignore[attr-defined]
                # Remove old entry if reloading
                agent._loaded_skills = [  # type: ignore[attr-defined]
                    s for s in agent._loaded_skills if s.get("name") != skill.info.name
                ]
                loaded_info = {
                    "name": skill.info.name,
                    "description": skill.info.description,
                    "version": skill.info.version,
                    "author": skill.info.author,
                    "tags": skill.info.tags,
                    "tools": [t.name for t in skill.get_tools()],
                }
                agent._loaded_skills.append(loaded_info)  # type: ignore[attr-defined]
        except Exception as e:
            # File saved but hot-load failed — will work on restart
            return {"ok": True, "loaded": False, "path": str(skill_file), "error": str(e)}

        return {"ok": True, "loaded": loaded_info is not None, "path": str(skill_file), "skill": loaded_info}

    # -------------------- REST: metrics --------------------
    @app.get("/api/metrics/usage")
    async def get_usage(days: int = 14):
        """Return aggregated token usage statistics."""
        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).parent.parent / "data" / "metrics"))
            from stats import load_usage, aggregate
            records = load_usage(limit=2000)
            pricing_override = getattr(config, "_pricing", None)
            return aggregate(records, days=days, pricing_override=pricing_override)
        except Exception as e:
            return {"summary": {}, "by_model": [], "by_day": [], "top_tools": [], "error": str(e)}

    return app


def _patch_mcp_yaml(name: str, data) -> None:
    """Add/update or remove a named MCP server entry in config.yaml (best-effort)."""
    try:
        import yaml as _yaml
        path = Path("config.yaml")
        raw = _yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        raw.setdefault("mcp", {}).setdefault("servers", {})
        if data is None:
            raw["mcp"]["servers"].pop(name, None)
        else:
            raw["mcp"]["servers"][name] = data
        path.write_text(_yaml.dump(raw, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to patch config.yaml MCP entry '{name}': {e}")


# Patterns that indicate the user wants something saved to persistent memory.
_MEMORY_SAVE_RE = re.compile(
    r'(?:帮我|请|麻烦)?(?:记住|记下|保存|别忘了|牢记|存一下|记一下)',
    re.IGNORECASE,
)


def _extract_memory_content(user_input: str) -> str:
    """Strip the 'save this' verb phrase and return the core content."""
    cleaned = _MEMORY_SAVE_RE.sub('', user_input).strip()
    cleaned = cleaned.lstrip('，,、：: ')
    return cleaned or user_input


async def handle_chat(websocket: WebSocket, user_input: str):
    """Handle a chat message"""
    _tool_names_used: list[str] = []
    try:
        await websocket.send_json({"type": "typing"})

        async for event_type, data in agent.run_stream(user_input):
            if event_type == "thinking":
                await websocket.send_json({"type": "thinking", "content": data})

            elif event_type == "text":
                await websocket.send_json({"type": "text", "content": data})

            elif event_type == "step_start":
                await websocket.send_json({"type": "step_start", "n": data["step"]})

            elif event_type == "tool_call":
                _tool_names_used.append(data.get("name", ""))
                await websocket.send_json({
                    "type": "tool_call",
                    "id": data["id"],
                    "tool": data["name"],
                    "input": data["input"],
                })

            elif event_type == "tool_result":
                await websocket.send_json({
                    "type": "tool_result",
                    "tool_use_id": data["tool_use_id"],
                    "content": data["content"],
                    "is_error": data["is_error"],
                })

            elif event_type == "done":
                await websocket.send_json({
                    "type": "done",
                    "message": data.text if hasattr(data, "text") else str(data.content),
                })
                # Auto-save memory if user explicitly asked but LLM skipped the tool call
                if (
                    _MEMORY_SAVE_RE.search(user_input)
                    and "save_important_memory" not in _tool_names_used
                    and agent.tools.has("save_important_memory")
                ):
                    content = _extract_memory_content(user_input)
                    try:
                        result = await agent.tools.execute(
                            "save_important_memory", {"content": content}
                        )
                        synthetic_id = f"auto_{id(user_input)}"
                        await websocket.send_json({
                            "type": "tool_call",
                            "id": synthetic_id,
                            "tool": "save_important_memory",
                            "input": {"content": content},
                        })
                        await websocket.send_json({
                            "type": "tool_result",
                            "tool_use_id": synthetic_id,
                            "content": str(result),
                            "is_error": False,
                        })
                    except Exception:
                        pass
                # Persist usage record
                _append_usage_record(_tool_names_used)

    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})


def _append_usage_record(tool_names: list[str]) -> None:
    """Write one usage record to data/metrics/usage.jsonl (best-effort)."""
    try:
        import sys as _sys
        metrics_dir = Path(__file__).parent.parent / "data" / "metrics"
        _sys.path.insert(0, str(metrics_dir))
        from stats import append_usage
        m = agent._metrics if agent else None
        append_usage({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "session_id": getattr(agent, "_session_id", ""),
            "model": config.llm.model if config else "unknown",
            "input_tokens": getattr(m, "input_tokens", 0) if m else 0,
            "output_tokens": getattr(m, "output_tokens", 0) if m else 0,
            "tool_calls": getattr(m, "tool_calls", 0) if m else 0,
            "loops": getattr(m, "total_loops", 0) if m else 0,
            "duration_s": round(
                ((m.end_time or 0) - (m.start_time or 0)) if m else 0, 2
            ),
            "tool_names": list(set(tool_names)),
        })
    except Exception:
        pass  # Metrics are best-effort


async def handle_confirmation(tool_use: ToolUseBlock) -> bool:
    """Handle tool confirmation request."""
    confirmation_id = tool_use.id
    loop = asyncio.get_running_loop()
    future: asyncio.Future[bool] = loop.create_future()

    async with _confirm_lock:
        if not active_connections:
            return False
        pending_confirmations[confirmation_id] = future

    try:
        for connection in list(active_connections):
            try:
                await connection.send_json({
                    "type": "confirmation_required",
                    "id": confirmation_id,
                    "tool": tool_use.name,
                    "input": tool_use.input,
                })
            except Exception:
                continue

        try:
            return await future
        except asyncio.CancelledError:
            return False
    finally:
        async with _confirm_lock:
            pending_confirmations.pop(confirmation_id, None)


async def handle_confirm_response(message: dict):
    """Handle confirmation response from client"""
    confirmation_id = message.get("id")
    allowed = bool(message.get("allowed", False))

    async with _confirm_lock:
        future = pending_confirmations.get(confirmation_id)
        if future is not None and not future.done():
            future.set_result(allowed)
