# handler 注册表（语义照抄真实现：_handlers 列表 + full_name 去重）
import enum
from dataclasses import dataclass, field
from typing import Any, Callable


class EventType(enum.Enum):
    AdapterMessageEvent = enum.auto()
    OnAstrBotLoadedEvent = enum.auto()
    OnPlatformLoadedEvent = enum.auto()


@dataclass
class StarHandlerMetadata:
    event_type: EventType
    handler_full_name: str
    handler_name: str
    handler_module_path: str
    handler: Callable[..., Any]
    event_filters: list
    desc: str = ""
    extras_configs: dict = field(default_factory=dict)
    enabled: bool = True


class StarHandlerRegistry:
    def __init__(self):
        self._handlers: list[StarHandlerMetadata] = []

    def append(self, md: StarHandlerMetadata) -> None:
        self._handlers.append(md)

    def get_handler_by_full_name(self, full_name: str):
        for md in self._handlers:
            if md.handler_full_name == full_name:
                return md
        return None

    def get_handlers_by_event_type(self, event_type: EventType):
        return [h for h in self._handlers if h.event_type == event_type]


star_handlers_registry = StarHandlerRegistry()
