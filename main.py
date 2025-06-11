import logging
import multiprocessing as mp
import random
import threading as th
from enum import Enum
from multiprocessing.managers import DictProxy, SyncManager
from typing import Any

GRID_SIZE = (40, 20)
CHUNK_SIZE = (5, 5)


class Status(Enum):
    ALIVE = 0
    DEAD = 1


class Robot(mp.Process):
    def __init__(
        self, id: str, shared_memory: DictProxy[str, Any], manager: SyncManager
    ) -> None:
        super().__init__()

        self.id = id
        self.shared_memory = shared_memory
        self.manager = manager

    def run(self) -> None:
        self.generate_grid(self.shared_memory, self.manager)
        self.snapshot_grid()

    def move(self) -> None:
        pass

    def generate_grid(
        self, shared_memory: DictProxy[str, Any], manager: SyncManager
    ) -> None:
        with shared_memory["grid_mutex"]:
            logging.info(f"Robô {self.id} adquiriu o grid_mutex!")

            if not shared_memory["flags"]["init_done"]:
                logging.info(f"Robô {self.id} está gerando o grid!")

                shared_memory["grid"] = manager.list(
                    [
                        manager.list(
                            [
                                Cell(i, j, CellType.STANDARD)
                                for i in range(GRID_SIZE[0])
                            ]
                        )
                        for j in range(GRID_SIZE[1])
                    ]
                )

                shared_memory["quadrants"] = manager.list(
                    [
                        [
                            (i, j)
                            for i in range(m, m + CHUNK_SIZE[0])
                            for j in range(n, n + CHUNK_SIZE[1])
                        ]
                        for m in range(0, GRID_SIZE[1], CHUNK_SIZE[0])
                        for n in range(0, GRID_SIZE[0], CHUNK_SIZE[1])
                    ]
                )

                for quadrant in shared_memory["quadrants"]:
                    random.shuffle(quadrant)

                    for _ in range(int(random.uniform(-0.7, 0.3) + 1)):
                        i, j = quadrant.pop()
                        shared_memory["grid"][i][j] = Cell(
                            i, j, CellType.RECHARGE, lock=manager.Lock()
                        )

                    for _ in range(int(random.uniform(2.5, 7.5))):
                        i, j = quadrant.pop()
                        shared_memory["grid"][i][j] = Cell(
                            i, j, CellType.OBSTACLE
                        )

                for robot in shared_memory["robots"]:
                    Q = [i for i in range(len(shared_memory["quadrants"]))]

                    random.shuffle(Q)
                    q = Q.pop()

                    i, j = random.choice(shared_memory["quadrants"][q])
                    robot["i"] = i
                    robot["j"] = j
                    shared_memory["grid"][i][j] = robot["id"]

                shared_memory["flags"]["init_done"] = True

            logging.info(f"Robô {self.id} liberou o grid_mutex!")

    def snapshot_grid(self) -> None:
        with self.shared_memory["grid_mutex"]:
            if self.shared_memory["flags"]["init_done"] and self.id == "3":
                logging.info(
                    f"Robô {self.id} está fazendo uma snapshot do grid!"
                )

                for row in self.shared_memory["grid"]:
                    for cell in row:
                        if isinstance(cell, Cell):
                            match cell.type:
                                case CellType.STANDARD:
                                    print(
                                        "\033[37m" + "-" + "\033[0m", end=" "
                                    )
                                case CellType.OBSTACLE:
                                    print(
                                        "\033[90m" + "#" + "\033[0m", end=" "
                                    )
                                case CellType.RECHARGE:
                                    print(
                                        "\033[93m" + "*" + "\033[0m", end=" "
                                    )

                        elif isinstance(cell, str):
                            print("\033[31m" + cell + "\033[0m", end=" ")

                    print()


class CellType(Enum):
    STANDARD = 0
    OBSTACLE = 1
    RECHARGE = 2


class Cell:
    def __init__(
        self,
        i: int,
        j: int,
        type: CellType,
        value: str | None = None,
        lock: th.Lock | None = None,
    ) -> None:
        self.i = i
        self.j = j
        self.type = type
        self.value = value
        self.lock = lock


def main() -> None:
    logging.basicConfig(
        datefmt="%H:%M:%S",
        format="[%(asctime)s] %(message)s",
        handlers=[
            logging.FileHandler(filename="log.txt", mode="w"),
        ],
        level=logging.INFO,
    )

    with SyncManager() as manager:
        shared_memory = manager.dict(
            grid=manager.list(),
            robots=manager.list(),
            grid_mutex=manager.Lock(),
            flags=manager.dict({"init_done": False, "vencedor": None}),
        )

        robots = [Robot(str(id), shared_memory, manager) for id in range(4)]

        shared_memory["robots"] = manager.list(
            [
                manager.dict(
                    {
                        "id": robot.id,
                        "F": random.randint(1, 10),
                        "E": random.randint(10, 100),
                        "V": random.randint(1, 5),
                        "i": 0,
                        "j": 0,
                        "status": Status.ALIVE,
                    }
                )
                for robot in robots
            ]
        )

        for robot in robots:
            robot.start()

        for robot in robots:
            robot.join()

        for robot in shared_memory["robots"]:  # type: ignore
            logging.info(robot)  # type: ignore


if __name__ == "__main__":
    main()
