# 命令注册装饰器（语义照抄 astrbot.core.star.register 的游戏用子集：
# 注册副作用 + 返回原函数，直接调用 handler 不经 filter 检查）
from ..filter.custom_filter import CustomFilterAnd, CustomFilterOr
from ..filter.regex import RegexFilter
from ..star_handler import EventType, StarHandlerMetadata, star_handlers_registry


def get_handler_full_name(awaitable) -> str:
    return f"{awaitable.__module__}_{awaitable.__name__}"


def get_handler_or_create(handler, event_type, dont_add=False, **kwargs):
    handler_full_name = get_handler_full_name(handler)
    md = star_handlers_registry.get_handler_by_full_name(handler_full_name)
    if md:
        return md
    md = StarHandlerMetadata(
        event_type=event_type,
        handler_full_name=handler_full_name,
        handler_name=handler.__name__,
        handler_module_path=handler.__module__,
        handler=handler,
        event_filters=[],
    )
    if handler.__doc__:
        md.desc = handler.__doc__.strip()
    if "desc" in kwargs:
        md.desc = kwargs["desc"]
        del kwargs["desc"]
    md.extras_configs = kwargs
    if not dont_add:
        star_handlers_registry.append(md)
    return md


def register_regex(regex, **kwargs):
    def decorator(awaitable):
        md = get_handler_or_create(awaitable, EventType.AdapterMessageEvent, **kwargs)
        md.event_filters.append(RegexFilter(regex))
        return awaitable

    return decorator


def register_custom_filter(custom_type_filter, *args, **kwargs):
    custom_filter = custom_type_filter
    raise_error = args[0] if args else True
    if not isinstance(custom_filter, (CustomFilterAnd, CustomFilterOr)):
        custom_filter = custom_filter(raise_error)

    def decorator(awaitable):
        md = get_handler_or_create(awaitable, EventType.AdapterMessageEvent, **kwargs)
        md.event_filters.append(custom_filter)
        return awaitable

    return decorator


def register_command(command_name=None, sub_command=None, alias=None, **kwargs):
    def decorator(awaitable):
        md = get_handler_or_create(awaitable, EventType.AdapterMessageEvent, **kwargs)
        return awaitable

    return decorator


def register_command_group(command_group_name=None, sub_command=None, alias=None, **kwargs):
    def decorator(obj):
        return obj

    return decorator
