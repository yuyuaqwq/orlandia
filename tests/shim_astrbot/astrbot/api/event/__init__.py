# 游戏代码仅把 AstrMessageEvent 当类型标注（运行时事件是测试的 FakeEvent，duck-typed）
class AstrMessageEvent:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def get_message_str(self):
        return getattr(self, "message_str", "")

    def get_group_id(self):
        return getattr(self, "_g", "")

    def get_sender_id(self):
        return getattr(self, "_q", "")

    async def send(self, message):
        return message
