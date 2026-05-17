import random
from enum import Enum, auto

# Input/output port handling.
# Test and validation logic.

# Implementation note.
class MaterialType(Enum):
    IRON_ORE = auto()
    IRON_INGOT = auto()
    IRON_PLATE = auto()


class Direction(Enum):
    RIGHT = (1, 0)


class Building:
    def __init__(self, name: str, size: tuple):
        self.name = name
        self.size = size
        self.area = size[0] * size[1]


# Implementation note.
class BlueprintAgent:
    def __init__(self, grid_width=10, grid_height=8):
        self.width = grid_width
        self.height = grid_height
        self.furnace = Building('AutoBlueprint status message.', (3, 3))
        self.press = Building('AutoBlueprint status message.', (3, 3))
        # Input/output port handling.
        self.input_belt_pos = (0, 1)

    def is_overlapping(self, fx, fy, px, py):
        'Layout status message.'
        return not (fx + 3 <= px or px + 3 <= fx or fy + 3 <= py or py + 3 <= fy)

    def evaluate_layout(self, fx, fy, px, py):
        'Layout status message.'
        # Implementation note.
        if self.is_overlapping(fx, fy, px, py):
            return False, 999, 0

        # Input/output port handling.
        if fx != 1 or not (fy <= self.input_belt_pos[1] < fy + 3):
            return False, 999, 0  # Implementation note.

        # Implementation note.
        # Implementation note.
        # Implementation note.
        y_overlap = max(0, min(fy + 3, py + 3) - max(fy, py))

        if px >= fx + 3 and y_overlap > 0:
            # Implementation note.
            belt_needed = px - (fx + 3)
            # Building placement logic.
            total_area = self.furnace.area + self.press.area + belt_needed
            return True, total_area, belt_needed
        else:
            return False, 999, 0  # Implementation note.

    def optimize_layout(self, iterations=500):
        'AutoBlueprint status message.'
        best_score = float('inf')
        best_layout = None
        best_belts = 0

        print(f"Agent is testing {iterations} layout combinations on a {self.width}x{self.height} grid.")

        for _ in range(iterations):
            # Implementation note.
            fx = random.randint(1, self.width - 3)
            fy = random.randint(0, self.height - 3)
            px = random.randint(1, self.width - 3)
            py = random.randint(0, self.height - 3)

            is_valid, score, belts = self.evaluate_layout(fx, fy, px, py)

            if is_valid and score < best_score:
                best_score = score
                best_layout = (fx, fy, px, py)
                best_belts = belts

        return best_layout, best_score, best_belts

    def render_blueprint(self, layout, belts_needed):
        'AutoBlueprint status message.'
        if not layout:
            print('AutoBlueprint status message.')
            return

        fx, fy, px, py = layout
        grid = [[' . ' for _ in range(self.width)] for _ in range(self.height)]

        # Implementation note.
        grid[self.input_belt_pos[1]][self.input_belt_pos[0]] = ' > '

        # Implementation note.
        for y in range(fy, fy + 3):
            for x in range(fx, fx + 3):
                grid[y][x] = '[F]'

        # Implementation note.
        if belts_needed > 0:
            belt_y = max(fy, py)  # Implementation note.
            for x in range(fx + 3, px):
                grid[belt_y][x] = ' * '

        # Implementation note.
        for y in range(py, py + 3):
            for x in range(px, px + 3):
                grid[y][x] = '[P]'

        # Implementation note.
        print('Agent status message.')
        for row in grid:
            print("".join(row))
        print("==============================")


# Test and validation logic.
if __name__ == "__main__":
    agent = BlueprintAgent()
    best_layout, min_area, belts = agent.optimize_layout(iterations=1000)

    print('AutoBlueprint status message.')
    if best_layout:
        print("AutoBlueprint status message.")
        print("Best layout metric updated.")
        print("Best layout metric updated.")
        print("Best layout metric updated.")
        print("Best layout metric updated.")
        if belts == 0:
            print('Layout status message.')

    agent.render_blueprint(best_layout, belts)