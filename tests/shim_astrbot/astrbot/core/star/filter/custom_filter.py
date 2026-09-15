# 自定义过滤器基类（语义照抄真实现：__init__(raise_error=True) + filter(event, cfg)）
from . import HandlerFilter


class CustomFilter(HandlerFilter):
    def __init__(self, raise_error: bool = True, **kwargs) -> None:
        self.raise_error = raise_error

    def filter(self, event, cfg) -> bool:
        raise NotImplementedError


class CustomFilterOr(CustomFilter):
    def __init__(self, filter1, filter2) -> None:
        super().__init__()
        self.filter1 = filter1
        self.filter2 = filter2

    def filter(self, event, cfg) -> bool:
        return self.filter1.filter(event, cfg) or self.filter2.filter(event, cfg)


class CustomFilterAnd(CustomFilter):
    def __init__(self, filter1, filter2) -> None:
        super().__init__()
        self.filter1 = filter1
        self.filter2 = filter2

    def filter(self, event, cfg) -> bool:
        return self.filter1.filter(event, cfg) and self.filter2.filter(event, cfg)
