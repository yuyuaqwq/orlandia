# Handler 过滤器基类
class HandlerFilter:
    def filter(self, event, cfg) -> bool:
        raise NotImplementedError
