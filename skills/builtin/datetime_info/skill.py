"""
Datetime Info Skill — provides current date/time and timezone tools.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from skills.base import Skill, SkillInfo
from tools.base import tool


class DatetimeInfoSkill(Skill):
    @property
    def info(self) -> SkillInfo:
        return SkillInfo(
            name="datetime_info",
            description="提供当前日期、时间和时区转换工具",
            version="1.0.0",
            author="builtin",
            tags=["builtin", "datetime", "time"],
        )

    async def execute(self, context):
        pass

    def get_tools(self):
        return [get_current_datetime, convert_timezone]


@tool
async def get_current_datetime(timezone_name: str = "Asia/Shanghai") -> str:
    """Get the current date and time in a specified timezone.
    Args:
        timezone_name: IANA timezone name, e.g. 'Asia/Shanghai', 'UTC', 'America/New_York'
    """
    try:
        tz = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, KeyError):
        tz = ZoneInfo("UTC")
        timezone_name = "UTC (fallback)"
    now = datetime.now(tz)
    return (
        f"当前时间（{timezone_name}）：{now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        f"星期：{['一','二','三','四','五','六','日'][now.weekday()]}\n"
        f"Unix 时间戳：{int(now.timestamp())}"
    )


@tool
async def convert_timezone(time_str: str, from_tz: str, to_tz: str) -> str:
    """Convert a time string from one timezone to another.
    Args:
        time_str: Time in format 'YYYY-MM-DD HH:MM:SS'
        from_tz: Source IANA timezone, e.g. 'UTC'
        to_tz: Target IANA timezone, e.g. 'Asia/Shanghai'
    """
    try:
        src = ZoneInfo(from_tz)
        dst = ZoneInfo(to_tz)
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=src)
        converted = dt.astimezone(dst)
        return f"{time_str} ({from_tz}) → {converted.strftime('%Y-%m-%d %H:%M:%S')} ({to_tz})"
    except Exception as e:
        return f"转换失败: {e}"
