"""Base classes for Skills"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class SkillInfo:
    """Information about a Skill"""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    tags: List[str] = field(default_factory=list)


class Skill(ABC):
    """
    Base class for Skills

    A Skill is a plugin that can add new capabilities to the agent,
    including tools and specialized behaviors.
    """

    @property
    @abstractmethod
    def info(self) -> SkillInfo:
        """Return information about this skill"""
        pass

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Any:
        """
        Execute the skill

        Args:
            context: Execution context with agent state

        Returns:
            Skill execution result
        """
        pass

    def get_tools(self) -> List[Any]:
        """
        Return tools provided by this skill

        Override this to add tools to the agent.
        """
        return []

    def on_load(self) -> None:
        """Called when the skill is loaded"""
        pass

    def on_unload(self) -> None:
        """Called when the skill is unloaded"""
        pass

    def __repr__(self) -> str:
        return f"<Skill {self.info.name} v{self.info.version}>"