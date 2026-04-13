"""Skill Loader - Dynamic loading of skills"""

import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

from .base import Skill

logger = logging.getLogger(__name__)


class SkillLoader:
    """
    Dynamic skill loader

    Loads skills from Python files and manages their lifecycle.
    """

    def __init__(self, skills_dir: Optional[str] = None):
        """
        Initialize skill loader

        Args:
            skills_dir: Directory to search for skills
        """
        self.skills_dir = Path(skills_dir) if skills_dir else None
        self._loaded: Dict[str, Skill] = {}

    def load(self, skill_path: str) -> Optional[Skill]:
        """
        Load a skill from a file path

        Args:
            skill_path: Path to the skill Python file

        Returns:
            Loaded Skill instance or None if failed
        """
        path = Path(skill_path)

        if not path.exists():
            logger.error(f"Skill file not found: {skill_path}")
            return None

        try:
            # Dynamic import
            spec = importlib.util.spec_from_file_location("skill_module", path)
            if not spec or not spec.loader:
                logger.error(f"Could not load spec from: {skill_path}")
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find Skill subclass
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Skill)
                    and attr is not Skill
                ):
                    skill = attr()
                    skill.on_load()
                    self._loaded[skill.info.name] = skill
                    logger.info(f"Loaded skill: {skill.info.name}")
                    return skill

            logger.error(f"No Skill class found in: {skill_path}")
            return None

        except Exception as e:
            logger.error(f"Error loading skill from {skill_path}: {e}")
            return None

    def load_from_module(self, module_name: str) -> Optional[Skill]:
        """
        Load a skill from an installed module

        Args:
            module_name: Name of the module containing the skill
        """
        try:
            module = importlib.import_module(module_name)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Skill)
                    and attr is not Skill
                ):
                    skill = attr()
                    skill.on_load()
                    self._loaded[skill.info.name] = skill
                    return skill

            return None

        except Exception as e:
            logger.error(f"Error loading skill from module {module_name}: {e}")
            return None

    def unload(self, name: str) -> bool:
        """
        Unload a skill by name

        Args:
            name: Name of the skill to unload

        Returns:
            True if successfully unloaded
        """
        if name in self._loaded:
            skill = self._loaded.pop(name)
            skill.on_unload()
            logger.info(f"Unloaded skill: {name}")
            return True
        return False

    def get(self, name: str) -> Optional[Skill]:
        """Get a loaded skill by name"""
        return self._loaded.get(name)

    def list_loaded(self) -> List[str]:
        """List names of loaded skills"""
        return list(self._loaded.keys())

    def get_all_tools(self) -> List[Any]:
        """Get all tools from loaded skills"""
        tools = []
        for skill in self._loaded.values():
            tools.extend(skill.get_tools())
        return tools

    def auto_discover(self) -> List[str]:
        """
        Auto-discover and load skills from skills_dir

        Returns:
            List of loaded skill names
        """
        if not self.skills_dir or not self.skills_dir.exists():
            return []

        loaded = []
        for skill_file in self.skills_dir.glob("**/skill.py"):
            skill = self.load(str(skill_file))
            if skill:
                loaded.append(skill.info.name)

        return loaded

    def clear(self) -> None:
        """Unload all skills"""
        for name in list(self._loaded.keys()):
            self.unload(name)