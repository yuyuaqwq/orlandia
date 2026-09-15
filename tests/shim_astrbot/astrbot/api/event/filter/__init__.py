# 命令装饰器（语义照抄 astrbot.core.star.register：注册副作用，返回原函数）
from astrbot.core.star.register import (
    register_command as command,
    register_command_group as command_group,
    register_custom_filter as custom_filter,
    register_regex as regex,
)
from astrbot.core.star.filter.custom_filter import CustomFilter

__all__ = ["command", "command_group", "custom_filter", "regex", "CustomFilter"]
