import heapq


# --- 1. 环境定义 ---
class GridEnvironment:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        # 0: 空地, 1: 建筑, 2: 传送带
        self.grid = [[0 for _ in range(width)] for _ in range(height)]

    def place_building(self, x, y):
        """放置建筑（障碍物）"""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y][x] = 1

    def place_belt(self, path):
        """根据路径铺设传送带，避开起点和终点的建筑本身"""
        for x, y in path:
            if self.grid[y][x] == 0:  # 只有空地才能铺传送带
                self.grid[y][x] = 2

    def display(self):
        """在控制台可视化网格"""
        symbols = {0: ' . ', 1: '[B]', 2: ' * '}
        print("-" * (self.width * 3))
        for row in self.grid:
            print("".join(symbols[cell] for cell in row))
        print("-" * (self.width * 3))


# --- 2. 寻路算法 (A* Search) ---
def heuristic(a, b):
    """曼哈顿距离启发函数"""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def a_star_search(env, start, goal):
    """A* 寻路，避开建筑 (值为 1 的网格)"""
    frontier = []
    heapq.heappush(frontier, (0, start))
    came_from = {start: None}
    g_score = {start: 0}

    while frontier:
        current = heapq.heappop(frontier)[1]

        if current == goal:
            break

        # 检查上下左右四个邻居
        x, y = current
        neighbors = [(x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y)]

        for nx, ny in neighbors:
            # 边界检查
            if 0 <= nx < env.width and 0 <= ny < env.height:
                # 碰撞检测：不能是建筑（除非是目标点本身，因为我们要连过去）
                if env.grid[ny][nx] == 1 and (nx, ny) != goal:
                    continue

                new_cost = g_score[current] + 1
                if (nx, ny) not in g_score or new_cost < g_score[(nx, ny)]:
                    g_score[(nx, ny)] = new_cost
                    priority = new_cost + heuristic((nx, ny), goal)
                    heapq.heappush(frontier, (priority, (nx, ny)))
                    came_from[(nx, ny)] = current

    # 回溯路径
    path = []
    if goal in came_from:
        curr = goal
        while curr != start:
            path.append(curr)
            curr = came_from[curr]
        path.append(start)
        path.reverse()
        return path
    return None  # 找不到路径


# --- 3. 可行性测试 ---
if __name__ == "__main__":
    # 初始化一个 10x10 的网格环境
    env = GridEnvironment(10, 10)

    # 定义两个建筑的位置
    building_A_out = (2, 2)  # 产出点
    building_B_in = (8, 7)  # 输入点

    # 放置建筑
    env.place_building(*building_A_out)
    env.place_building(*building_B_in)

    # 增加一些额外的障碍物（模拟复杂的工厂环境）
    env.place_building(2, 3)
    env.place_building(5, 2)
    env.place_building(5, 4)
    env.place_building(5, 5)
    env.place_building(5, 6)
    env.place_building(6, 6)
    env.place_building(5, 7)

    print("【初始环境】 (B代表建筑，.代表空地):")
    env.display()

    # 让 Agent 进行路径规划
    print("\nAgent 正在寻找路径...")
    path = a_star_search(env, building_A_out, building_B_in)

    if path:
        print(f"找到路径！总长度: {len(path)} 步")
        env.place_belt(path)
        print("\n【铺设传送带后】 (*代表传送带):")
        env.display()
    else:
        print("寻路失败：通道被堵死。")