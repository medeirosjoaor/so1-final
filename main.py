from __future__ import annotations

import random
from enum import Enum
from multiprocessing.managers import SyncManager, DictProxy
import multiprocessing as mp
import threading as th


class Status(Enum):
    ALIVE = 0
    DEAD = 1


class Robot(mp.Process):

    def __init__(self, id: str, shared_memory: DictProxy,
                 manager: SyncManager) -> None:
        super().__init__()

        self.id = id
        self.i = 0
        self.j = 0
        self.F = random.randint(1, 10)
        self.E = random.randint(10, 100)
        self.V = random.randint(1, 5)
        self.status = Status.ALIVE
        self.shared_memory = shared_memory
        self.manager = manager

    def __repr__(self) -> str:
        return f"Robot({self.id}, {self.status}, {self.F}, {self.E}, {self.V})"

    def run(self) -> None:
        self.generate_grid(self.shared_memory, self.manager)

    def move(self) -> None:
        pass

    def generate_grid(self, shared_memory: DictProxy,
                      manager: SyncManager) -> None:

        with shared_memory["grid_mutex"]:
            if not shared_memory["flags"]["init_done"]:
                shared_memory["grid"] = manager.list([
                    manager.list(
                        [Cell(i, j, CellType.STANDARD) for i in range(40)])
                    for j in range(20)
                ])

                shared_memory["quadrants"] = manager.list([[
                    (i, j) for i in range(m, m + 5) for j in range(n, n + 10)
                ] for m in range(0, 20, 5) for n in range(0, 40, 10)])

                for quadrant in shared_memory["quadrants"]:
                    random.shuffle(quadrant)

                    for _ in range(int(random.uniform(0.5, 1.5))):
                        i, j = quadrant.pop()
                        shared_memory["grid"][i][j] = Cell(
                            i, j, CellType.RECHARGE, manager.Lock())

                    for _ in range(int(random.uniform(2, 16))):
                        i, j = quadrant.pop()
                        shared_memory["grid"][i][j] = Cell(
                            i, j, CellType.OBSTACLE)

                for robot in shared_memory["robots"]:
                    Q = [i for i in range(len(shared_memory["quadrants"]))]

                    random.shuffle(Q)

                    q = Q.pop()

                    i, j = random.choice(shared_memory["quadrants"][q])
                    robot["i"] = i
                    robot["j"] = j

                    shared_memory["grid"][i][j] = robot["id"]

                shared_memory["flags"]["init_done"] = True


class CellType(Enum):
    STANDARD = 0
    OBSTACLE = 1
    RECHARGE = 2


class Cell:

    def __init__(self,
                 i: int,
                 j: int,
                 type: CellType,
                 lock: th.Lock | None = None) -> None:
        self.i = i
        self.j = j
        self.type = type
        self.value: str | None = None
        self.lock = lock

    def __repr__(self) -> str:
        match self.type:
            case CellType.STANDARD:
                match type(self.value):
                    case str():
                        return str(self.value)
                    case _:
                        return "-"
            case CellType.OBSTACLE:
                return "#"
            case CellType.RECHARGE:
                return "+"

    def move(self) -> None:
        pass


def main() -> None:
    with SyncManager() as manager:
        shared_memory = manager.dict(grid=manager.list(),
                                     robots=manager.list(),
                                     grid_mutex=manager.Lock(),
                                     flags=manager.dict({
                                         "init_done": False,
                                         "vencedor": None
                                     }))

        robots = [Robot(str(i), shared_memory, manager) for i in range(4)]

        shared_memory["robots"] = manager.list([
            manager.dict({
                "id": robot.id,
                "F": robot.F,
                "E": robot.E,
                "V": robot.V,
                "i": robot.i,
                "j": robot.j,
                "status": robot.status
            }) for robot in robots
        ])

        for robot in robots:
            robot.start()
            robot.join()

        for robot in shared_memory["robots"]:  # type: ignore
            print(robot)

        print()

        for row in shared_memory["grid"]:  # type: ignore
            for cell in row:
                print(cell, end=" ")

            print()


if __name__ == "__main__":
    main()
