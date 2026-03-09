from enum import Enum
from entities.material import MaterialState

class Direction(Enum):
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

class TransportComponent:
    """所有运输组件的基类"""
    def __init__(self, component_id: int, state: MaterialState):
        self.component_id = component_id
        self.state = state  # 固体或液体
        self.size = (1, 1)  # 默认占地 1x1

class Belt(TransportComponent):
    """传送带/管道 (编号: 101)"""
    def __init__(self, state: MaterialState, speed: float, direction: Direction):
        super().__init__(component_id=101, state=state)
        self.speed = speed
        self.direction = direction
        self.accepts_side_input = True   # 是否接受侧面输入
        self.allows_side_output = False  # 是否侧面输出

class TransportBridge(TransportComponent):
    """运输桥/管道桥 (编号: 104)"""
    def __init__(self, state: MaterialState, length: int, input_face: Direction, output_face: Direction):
        super().__init__(component_id=104, state=state)
        self.length = length
        self.input_face = input_face
        self.output_face = output_face
        # 起点和终点占地由外部网格逻辑处理，均为 1x1

class LogicRouter(TransportComponent):
    """分配器、准入口、溢流门等通用逻辑组件"""
    def __init__(self, component_id: int, state: MaterialState):
        super().__init__(component_id=component_id, state=state)
        # 具体的输入输出优先级逻辑可以在此扩展