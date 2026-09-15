# 消息组件（字段类，仅构造/持有数据）
class BaseMessageComponent:
    type = "component"

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class Plain(BaseMessageComponent):
    type = "Plain"

    def __init__(self, text: str, convert: bool = True, **_):
        self.text = text


class Node(BaseMessageComponent):
    """转发消息节点：uin/name 为 QQ 昵称与 QQ 号，content 为组件列表。"""

    type = "Node"

    def __init__(self, content: list, **kwargs):
        self.content = content
        self.id = kwargs.pop("id", 0)
        self.name = kwargs.pop("name", "")
        self.uin = kwargs.pop("uin", "0")
        self.seq = kwargs.pop("seq", "")
        self.time = kwargs.pop("time", 0)


class Nodes(BaseMessageComponent):
    type = "Nodes"

    def __init__(self, nodes: list, **kwargs):
        self.nodes = nodes
