import random
from enum import Enum, auto

# 检测最基础的框架能否正常运转，在测试中添加了输入口，一级工厂以及一个二级工厂，
# 测试文件验证在最简单的情况之下能否正常构建蓝图以及能否发现将两个工厂直接相连能节省传送带以及占地面积

# --- 1. 沿用之前的类定义 ---
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


# --- 2. 环境与智能体评估逻辑 ---
class BlueprintAgent:
    def __init__(self, grid_width=10, grid_height=8):
        self.width = grid_width
        self.height = grid_height
        self.furnace = Building("熔炉", (3, 3))
        self.press = Building("压制机", (3, 3))
        # 固定的初始输入带，位于 (0, 1)，向右传输
        self.input_belt_pos = (0, 1)

    def is_overlapping(self, fx, fy, px, py):
        """检查两个 3x3 的建筑是否重叠"""
        return not (fx + 3 <= px or px + 3 <= fx or fy + 3 <= py or py + 3 <= fy)

    def evaluate_layout(self, fx, fy, px, py):
        """
        评估当前布局的占地面积 (Fitness Function)
        返回: (是否合法, 总占地面积, 需要的传送带数量)
        """
        # 1. 碰撞检测
        if self.is_overlapping(fx, fy, px, py):
            return False, 999, 0

        # 2. 检查与输入带的连接 (为了简化，假设熔炉必须贴着左边界且覆盖 y=1)
        if fx != 1 or not (fy <= self.input_belt_pos[1] < fy + 3):
            return False, 999, 0  # 熔炉没接上源头

        # 3. 计算熔炉到压制机的连线距离
        # 熔炉的右边缘是 fx + 3。压制机的左边缘是 px。
        # 如果 px >= fx + 3 且它们的 y 轴有交集，则可以直接连线或直连
        y_overlap = max(0, min(fy + 3, py + 3) - max(fy, py))

        if px >= fx + 3 and y_overlap > 0:
            # 距离 = x轴的空隙
            belt_needed = px - (fx + 3)
            # 总面积 = 建筑本身面积 + 传送带面积 (每格 1x1)
            total_area = self.furnace.area + self.press.area + belt_needed
            return True, total_area, belt_needed
        else:
            return False, 999, 0  # 错位严重，此基础算法暂不处理复杂绕线

    def optimize_layout(self, iterations=500):
        """智能体核心算法：随机搜索以寻找最小占地面积"""
        best_score = float('inf')
        best_layout = None
        best_belts = 0

        print(f"Agent 开始在 {self.width}x{self.height} 网格中尝试 {iterations} 次布局组合...")

        for _ in range(iterations):
            # 随机生成坐标
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
        """可视化蓝图"""
        if not layout:
            print("未找到合法的蓝图！")
            return

        fx, fy, px, py = layout
        grid = [[' . ' for _ in range(self.width)] for _ in range(self.height)]

        # 画源头传送带
        grid[self.input_belt_pos[1]][self.input_belt_pos[0]] = ' > '

        # 画熔炉 [F]
        for y in range(fy, fy + 3):
            for x in range(fx, fx + 3):
                grid[y][x] = '[F]'

        # 画新增的传送带 *
        if belts_needed > 0:
            belt_y = max(fy, py)  # 取交集的 y 坐标打一条直线
            for x in range(fx + 3, px):
                grid[belt_y][x] = ' * '

        # 画压制机 [P]
        for y in range(py, py + 3):
            for x in range(px, px + 3):
                grid[y][x] = '[P]'

        # 打印网格
        print("\n=== Agent 规划出的最优蓝图 ===")
        for row in grid:
            print("".join(row))
        print("==============================")


# --- 3. 运行测试 ---
if __name__ == "__main__":
    agent = BlueprintAgent()
    best_layout, min_area, belts = agent.optimize_layout(iterations=1000)

    print("\n【智能体报告】")
    if best_layout:
        print(f" -> 发现最优解！")
        print(f" -> 熔炉坐标: ({best_layout[0]}, {best_layout[1]})")
        print(f" -> 压机坐标: ({best_layout[2]}, {best_layout[3]})")
        print(f" -> 新增传送带数量: {belts} 条")
        print(f" -> 蓝图总占地面积: {min_area} 格")
        if belts == 0:
            print(" -> 💡 Agent 发现了【建筑直连 (Direct Insertion)】技巧，极限压缩了占地！")

    agent.render_blueprint(best_layout, belts)