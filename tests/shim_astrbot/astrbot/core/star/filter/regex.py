# 正则过滤器（语义照抄真实现）
import re

from . import HandlerFilter


class RegexFilter(HandlerFilter):
    def __init__(self, regex):
        self.regex = re.compile(regex)
        self.regex_str = self.regex.pattern

    def filter(self, event, cfg) -> bool:
        return bool(self.regex.search(event.get_message_str().strip()))
