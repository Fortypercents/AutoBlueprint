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
        self.supported_state = None  # None means no material-state restriction.


class SystemATransport(TransportComponent):
    def __init__(self, component_id: int, name: str):
        super().__init__(component_id, name)
        self.system_type = "SYSTEM_A"


class SystemABelt(SystemATransport):
    def __init__(self, component_id: int, name: str = "System A Belt"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID


class SystemALogicRouter(SystemATransport):
    def __init__(self, component_id: int, name: str = "System A Router"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID


class SystemAOverflowGate(SystemATransport):
    def __init__(self, component_id: int, name: str = "System A Overflow Gate"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID


class SystemABridge(SystemATransport):
    def __init__(self, component_id: int, name: str = "System A Bridge", min_length: int = 1, max_length: int = 3):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID
        self.min_length = min_length
        self.max_length = max_length
        self.end_pos = (0, 0)


class SystemAPipe(SystemATransport):
    def __init__(self, component_id: int, name: str = "System A Pipe"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID


class SystemAPipeRouter(SystemATransport):
    def __init__(self, component_id: int, name: str = "System A Pipe Router"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID


class SystemAPipeOverflowGate(SystemATransport):
    def __init__(self, component_id: int, name: str = "System A Pipe Overflow Gate"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID


class SystemAPipeBridge(SystemATransport):
    def __init__(self, component_id: int, name: str = "System A Pipe Bridge", min_length: int = 1, max_length: int = 3):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID
        self.min_length = min_length
        self.max_length = max_length
        self.end_pos = (0, 0)


class SystemACrosser(SystemATransport):
    def __init__(self, component_id: int, name: str = "System A Crosser"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID


class SystemAPipeCrosser(SystemATransport):
    def __init__(self, component_id: int, name: str = "System A Pipe Crosser"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID


class SystemBTransport(TransportComponent):
    def __init__(self, component_id: int, name: str):
        super().__init__(component_id, name)
        self.system_type = "SYSTEM_B"


class SystemBBelt(SystemBTransport):
    def __init__(self, component_id: int, name: str = "System B Belt"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID


class SystemBPipe(SystemBTransport):
    def __init__(self, component_id: int, name: str = "System B Pipe"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID


class SystemBSplitter(SystemBTransport):
    def __init__(self, component_id: int, name: str = "System B Splitter"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID


class SystemBPipeSplitter(SystemBTransport):
    def __init__(self, component_id: int, name: str = "System B Pipe Splitter"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID


class SystemBMerger(SystemBTransport):
    def __init__(self, component_id: int, name: str = "System B Merger"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID


class SystemBPipeMerger(SystemBTransport):
    def __init__(self, component_id: int, name: str = "System B Pipe Merger"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID


class SystemBBeltAccess(SystemBTransport):
    def __init__(self, component_id: int, name: str = "System B Belt Access"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID


class SystemBPipeAccess(SystemBTransport):
    def __init__(self, component_id: int, name: str = "System B Pipe Access"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID


class SystemBCrosser(SystemBTransport):
    def __init__(self, component_id: int, name: str = "System B Crosser"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.SOLID


class SystemBPipeCrosser(SystemBTransport):
    def __init__(self, component_id: int, name: str = "System B Pipe Crosser"):
        super().__init__(component_id, name)
        self.supported_state = MaterialState.LIQUID
