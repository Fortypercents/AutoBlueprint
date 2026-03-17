from enum import Enum
from entities.material import MaterialState

class Direction(Enum):
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)


class TransportComponent:
    def __init__(self, component_id: int, name: str = "Unknown"):
        self.component_id = component_id
        self.name = name
        self.pos = (0, 0)
        self.direction = Direction.RIGHT
        self.current_item = None
        self.next_tick_item = None
        self.max_capacity = 12.0

        self.system_type = "UNKNOWN"
        self.supported_state = None  # None 表示不限制物质形态 (固体液体都能运)


# ==========================================
# 体系 A: 经典异星工厂体系 (全向接口，但区分固液)
# ==========================================
class SystemATransport(TransportComponent):
    def __init__(self, component_id: int, name: str):
        super().__init__(component_id, name)
        self.system_type = "SYSTEM_A"

# --- 1. System A 固体运输元件 ---
class SystemABelt(SystemATransport):
    def __init__(self, component_id: int, name: str = "SystemA传送带"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID

class SystemALogicRouter(SystemATransport):
    def __init__(self, component_id: int, name: str = "SystemA分配器"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID

class SystemAOverflowGate(SystemATransport):
    def __init__(self, component_id: int, name: str = "SystemA溢流门"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID

class SystemABridge(SystemATransport):
    def __init__(self, component_id: int, name: str = "SystemA传送桥", min_length: int = 1, max_length: int = 3):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID
        self.min_length = min_length
        self.max_length = max_length
        self.end_pos = (0, 0)


# --- 2. System A 液体运输元件 ---
class SystemAPipe(SystemATransport):
    def __init__(self, component_id: int, name: str = "SystemA管道"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID

class SystemAPipeRouter(SystemATransport):
    def __init__(self, component_id: int, name: str = "SystemA管道分配器"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID

class SystemAPipeOverflowGate(SystemATransport):
    def __init__(self, component_id: int, name: str = "SystemA管道溢流门"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID

class SystemAPipeBridge(SystemATransport):
    def __init__(self, component_id: int, name: str = "SystemA管道桥", min_length: int = 1, max_length: int = 3):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID
        self.min_length = min_length
        self.max_length = max_length
        self.end_pos = (0, 0)


# ==========================================
# 体系 B: 严格定向、区分固液的现代物流体系
# ==========================================
class SystemBTransport(TransportComponent):
    def __init__(self, component_id: int, name: str):
        super().__init__(component_id, name)
        self.system_type = "SYSTEM_B"

# --- 1. 基础传输 (Belts & Pipes) ---
class SystemBBelt(SystemBTransport):
    def __init__(self, component_id: int, name: str = "SystemB传送带"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID

class SystemBPipe(SystemBTransport):
    def __init__(self, component_id: int, name: str = "SystemB管道"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID

# --- 2. 分流器 (Splitters: 只能 1 进多出) ---
class SystemBSplitter(SystemBTransport):
    def __init__(self, component_id: int, name: str = "SystemB传送分流器"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID

class SystemBPipeSplitter(SystemBTransport):
    def __init__(self, component_id: int, name: str = "SystemB管道分流器"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID

# --- 3. 汇流器 (Mergers: 只能多进 1 出) ---
class SystemBMerger(SystemBTransport):
    def __init__(self, component_id: int, name: str = "SystemB传送汇流器"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID

class SystemBPipeMerger(SystemBTransport):
    def __init__(self, component_id: int, name: str = "SystemB管道汇流器"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID

# --- 4. 准入器 (Access: 机器端口的安全阀) ---
class SystemBBeltAccess(SystemBTransport):
    def __init__(self, component_id: int, name: str = "SystemB传送准入器"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID

class SystemBPipeAccess(SystemBTransport):
    def __init__(self, component_id: int, name: str = "SystemB管道准入器"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID