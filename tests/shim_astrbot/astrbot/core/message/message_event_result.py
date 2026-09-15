# 消息链（语义照抄真实现：chain 列表 + message() 返回 self）
from .components import Plain


class MessageChain:
    def __init__(self, chain=None):
        self.chain = list(chain) if chain else []
        self.use_t2i_ = None
        self.use_markdown_ = None
        self.type = None

    def message(self, text: str):
        self.chain.append(Plain(text))
        return self

    def get_plain_text(self) -> str:
        return " ".join(c.text for c in self.chain if isinstance(c, Plain))

    def __str__(self):
        return self.get_plain_text()
