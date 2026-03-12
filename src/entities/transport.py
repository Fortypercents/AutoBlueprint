from enum import Enum
from entities.material import MaterialState, MaterialType

class Direction(Enum):
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

class TransportComponent:
    """所有运输元件的基类"""
    def __init__(self, component_id: int, name: str, allowed_state: MaterialState):
        self.component_id = component_id
        self.name = name
        self.allowed_state = allowed_state  # 决定是运物品(SOLID)还是液体(LIQUID)
        self.size = (1, 1)
        self.direction = Direction.RIGHT    # 默认方向，放置时修改

class Belt(TransportComponent):
    """传送带 / 管道"""
    def __init__(self, component_id: int, name: str, allowed_state: MaterialState,
                 speed: float, max_capacity: int, accepts_side_input: bool, allows_side_output: bool):
        super().__init__(component_id, name, allowed_state)
        self.speed = speed
        self.max_capacity = max_capacity
        self.accepts_side_input = accepts_side_input
        self.allows_side_output = allows_side_output

class Bridge(TransportComponent):
    """传输桥 / 管道桥"""
    def __init__(self, component_id: int, name: str, allowed_state: MaterialState,
                 min_len: int, max_len: int):
        super().__init__(component_id, name, allowed_state)
        self.min_length = min_len
        self.max_length = max_len
        # 桥的 I/O 面规则：
        # 起点：除了前方（桥梁延伸方向），另外三面仅作为输入。
        # 终点：除了后方（接收桥梁方向），另外三面仅作为输出。
        # （具体连接逻辑由 GridMap 在摆放时校验）

class LogicRouter(TransportComponent):
    """逻辑分配元件的基类 (分配器, 分类器, 溢流门等)"""
    def __init__(self, component_id: int, name: str):
        # 逻辑元件通常只处理固体物品
        super().__init__(component_id, name, MaterialState.SOLID)
        self.omni_io = True  # 四面均可作为输入或输出

class Sorter(LogicRouter):
    """分类器 / 反向分类器"""
    def __init__(self, component_id: int, name: str, inverted: bool = False):
        super().__init__(component_id, name)
        self.inverted = inverted
        self.filter_item: MaterialType = None  # 在放置或配置时指定过滤的物品

class OverflowGate(LogicRouter):
    """溢流门 / 反向溢流门 (欠流门)"""
    def __init__(self, component_id: int, name: str, inverted: bool = False):
        super().__init__(component_id, name)
        self.inverted = inverted