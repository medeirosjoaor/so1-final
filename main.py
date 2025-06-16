import logging
import multiprocessing as mp
import os
import random
import time
from enum import Enum
from multiprocessing.managers import DictProxy, SyncManager

GRID_SIZE = (40, 20)
CHUNK_SIZE = (5, 5)


class Status(Enum):
    ALIVE = 0
    DEAD = 1


class Viewer(mp.Process):
    def __init__(self, shared_memory: DictProxy) -> None:
        clear_terminal()
        super().__init__()

        self.shared_memory = shared_memory

    def run(self) -> None:
        while True:
            if self.shared_memory["flags"]["init_done"]:
                cols = []

                for row in self.shared_memory["grid"]:
                    rows = []

                    for cell in row:
                        match cell:
                            case "-":
                                rows.append("\033[37m-\033[0m")  # type: ignore
                            case "#":
                                rows.append("\033[90m#\033[0m")  # type: ignore
                            case "*":
                                rows.append("\033[93m*\033[0m")  # type: ignore
                            case _:
                                rows.append(f"\033[31m{cell}\033[0m")  # type: ignore

                    cols.append(" ".join(rows))  # type: ignore

                print("\033[1;1H" + "\n".join(cols))  # type: ignore
            time.sleep(0.5)


class Robot(mp.Process):
    def __init__(
        self, id: str, shared_memory: DictProxy, manager: SyncManager
    ) -> None:
        super().__init__()

        self.id = id
        self.shared_memory = shared_memory
        self.manager = manager

    def run(self) -> None:
        if not self.shared_memory["flags"]["init_done"]:
            self.generate_grid(self.shared_memory, self.manager)  # type: ignore
        logging.info(
            f"Robô {self.id} iniciou com os dados {self.shared_memory['robots'][int(self.id)]} e está rodando!"
        )

        while True:
            if (
                self.shared_memory["robots"][int(self.id)]["status"]
                == Status.DEAD.value
            ):
                return  # Se o robô está morto, ele não faz mais nada

            if (
                self.shared_memory["alive"] == 1
                and self.shared_memory["robots"][int(self.id)]["status"]
                == Status.ALIVE.value
            ):
                self.shared_memory["flags"]["vencedor"] = self.id
                logging.info(f"Robô {self.id} venceu a batalha!")

                return

            self.move_npc()

    def tira_da_grid(self, id):
        robot = self.shared_memory["robots"][int(id)]
        robot["status"] = Status.DEAD.value
        i, j = robot["i"], robot["j"]
        GRID = self.shared_memory["grid"]
        GRID[i][j] = "-"
        self.shared_memory["alive"] -= 1
        logging.info(f"Robô {id} da posição ({i}, {j}) foi removido da grid!")
        return

    def move_npc(self):
        time.sleep(0.2 * self.shared_memory["robots"][int(self.id)]["V"])

        with (
            self.shared_memory["robots_mutex"],
            self.shared_memory["grid_mutex"],
        ):
            logging.info(
                f"Robô {self.id} adquiriu o robots_mutex e o grid_mutex!"
            )
            robot = self.shared_memory["robots"][int(self.id)]

            if robot["E"] <= 0:
                logging.info(
                    f"Robô {robot['id']} não tem energia suficiente para se mover."
                )
                self.tira_da_grid(robot["id"])
                return

            if robot["status"] == Status.DEAD.value:
                logging.info(f"Robô {self.id} está morto e não pode se mover!")
                return

            # Busca o robo mais proximo
            alvo = None
            menor_dist = float("inf")
            for r in self.shared_memory["robots"]:
                if (
                    str(r["id"]) == str(robot["id"])
                    or r["status"] == Status.DEAD.value
                ):
                    continue
                dist = abs(r["i"] - robot["i"]) + abs(r["j"] - robot["j"])
                if dist < menor_dist:
                    menor_dist = dist
                    alvo = {"i": r["i"], "j": r["j"], "id": r["id"]}

            moved = False

            if not alvo:
                logging.info(
                    f"Robô {self.id} não encontrou nenhum alvo ativo."
                )
                return

            # Calcular direção até o alvo
            delta_i = alvo["i"] - robot["i"]
            delta_j = alvo["j"] - robot["j"]

            direcoes = []
            preferenciais = []
            alternativas = []

            # Caso tenha obstaculo na direção do alvo tenta dar a volta
            if delta_i != 0:
                preferenciais.append((1 if delta_i > 0 else -1, 0))
            if delta_j != 0:
                preferenciais.append((0, 1 if delta_j > 0 else -1))
            # Se o robô está na mesma linha ou coluna do alvo, tenta se mover diretamente
            todas_direcoes = [(-1, 0), (1, 0), (0, -1), (0, 1)]
            for d in todas_direcoes:
                if d not in preferenciais:
                    alternativas.append(d)

            # Combina: tenta primeiro as preferenciais, depois alternativas
            direcoes = preferenciais + alternativas

            for di, dj in direcoes:
                new_i = robot["i"] + di
                new_j = robot["j"] + dj
                if robot["ult_pos"] == (new_i, new_j):
                    logging.info(
                        f"Robô {robot['id']} não pode voltar para a posição anterior ({robot['ult_pos']})!"
                    )
                    continue  # não deixa voltar para posição anterior
                if 0 <= new_i < GRID_SIZE[1] and 0 <= new_j < GRID_SIZE[0]:
                    tmp_i, tmp_j = robot["i"], robot["j"]
                    robot["ult_pos"] = (tmp_i, tmp_j)  # Atualiza a ult_pos
                    cell = self.shared_memory["grid"][new_i][new_j]

                    if cell == "#":
                        logging.info(
                            f"Robô {robot['id']} encontrou um obstáculo e não pode se mover nessa direção!"
                        )
                        continue

                    # Simula tempo de movimento
                    time.sleep(0.2 * robot["V"])

                    robot["E"] -= 1  # Consome energia ao mover
                    robot["i"] = new_i
                    robot["j"] = new_j
                    self.shared_memory["grid"][new_i][new_j] = robot["id"]
                    self.shared_memory["grid"][tmp_i][tmp_j] = "-"

                    if cell == "*":
                        logging.info(
                            f"Robô {robot['id']} se moveu para ({robot['i']}, {robot['j']}) e encontrou uma célula de recarga!"
                        )
                        self.pega_energia()
                        logging.info(
                            f"Robô {robot['id']} liberou robots_mutex e o grid_mutex!"
                        )
                        return
                    else:
                        logging.info(
                            f"Robô {robot['id']}  se moveu para ({new_i}, {new_j}) está com {robot['E']} de energia"
                        )
                        self.esta_proximo()
                        logging.info(
                            f"Robo {robot['id']} liberou o robots_mutex e o grid mutex!"
                        )
                    moved = True
                    break

            if not moved:
                logging.info(
                    f"Robô {self.id} não conseguiu se mover em nenhuma direção! e liberou o robots_mutex e o grid_mutex!"
                )

    def esta_proximo(self):
        logging.info(
            f"Robô {self.id} está verificando se está próximo de outro robô."
        )
        robot = self.shared_memory["robots"][int(self.id)]
        i, j = robot["i"], robot["j"]
        # Verifica se o robô atual está em uma zona segura
        cell_atual = self.shared_memory["grid"][i][j]
        if cell_atual == "*":
            # Se o robô está em uma célula de recarga ele está protegido pelo lock
            logging.info(
                f"Robô {self.id} está em uma célula de recarga e não pode atacar."
            )
            return

        linha_de_combate = [
            (i - 1, j),  # Cima W
            (i + 1, j),  # Baixo S
            (i, j - 1),  # Esquerda A
            (i, j + 1),  # Direita D
        ]
        for vi, vj in linha_de_combate:
            if (
                0 <= vi < GRID_SIZE[1] and 0 <= vj < GRID_SIZE[0]
            ):  # Verifica se a linha de combate tá na grid
                cell = self.shared_memory["grid"][vi][vj]
                if isinstance(cell, str) and cell not in ["-", "#", "*"]:
                    robo_adversario = None
                    for r in self.shared_memory["robots"]:  # Busca o robo
                        if r["id"] == cell:
                            robo_adversario = r
                            break
                    if robo_adversario:
                        cell_ad = self.shared_memory["grid"][
                            robo_adversario["i"]
                        ][robo_adversario["j"]]
                        if cell_ad == "*":
                            logging.info(
                                f"Robô {cell_ad} está recarregando e não pode ser atacado."
                            )
                            continue
                        else:
                            # Se o robô adversário não está em uma célula de recarga ele pode ser atacado
                            logging.info(
                                f"Robô {self.id} encontrou o robô {cell_ad} próximo e irá ataca-lo!"
                            )
                            self.briga(int(self.id), int(cell_ad))
                            return

        logging.info(
            f"Robô {self.id} não encontrou nenhum robô próximo para atacar."
        )
        return  # Se não encontrou nenhum robô próximo, continua a busca

    def briga(self, id1: int, id2: int):
        robots = self.shared_memory["robots"]
        logging.info(f"Robô {self.id} está brigando com o robô {id2}!")
        Poder1 = (robots[id1]["F"] * 2) + robots[id1]["E"]
        Poder2 = (robots[id2]["F"] * 2) + robots[id2]["E"]

        if Poder1 > Poder2:
            logging.info(f"Robô {self.id} venceu o Robô {id2}!")
            self.tira_da_grid(id2)
            return
        elif Poder1 < Poder2:
            logging.info(f"Robô {self.id} foi derrotado pelo Robô {id2}!")
            self.tira_da_grid(id1)
            return
        else:
            logging.info(
                f"Robô {self.id} e Robô {id2} empataram e ambos foram mortos"
            )
            self.tira_da_grid(id1)
            self.tira_da_grid(id2)
            return

    def pega_energia(self) -> None:
        robot = self.shared_memory["robots"][int(self.id)]
        if robot["E"] == 100:
            logging.info(f"Robô {self.id} já está com energia máxima!")
            return
        robot["E"] = min(robot["E"] + 20, 100)
        logging.info(
            f"Robô {self.id} recarregou energia! Energia atual: {robot['E']}"
        )

    def generate_grid(
        self, shared_memory: DictProxy, manager: SyncManager
    ) -> None:
        with shared_memory["grid_mutex"]:
            if not shared_memory["flags"]["init_done"]:
                logging.info(f"Robô {self.id} adquiriu o grid_mutex!")

                logging.info(f"Robô {self.id} está gerando o grid!")

                shared_memory["grid"] = manager.list(
                    [
                        manager.list(["-" for _ in range(GRID_SIZE[0])])
                        for _ in range(GRID_SIZE[1])
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

                    for _ in range(int(random.uniform(-0.25, 0.75) + 1)):
                        i, j = quadrant.pop()
                        shared_memory["grid"][i][j] = "*"

                    for _ in range(int(random.uniform(2.5, 7.5))):
                        i, j = quadrant.pop()
                        shared_memory["grid"][i][j] = "#"

                for robot in shared_memory["robots"]:
                    Q = [i for i in range(len(shared_memory["quadrants"]))]

                    random.shuffle(Q)
                    q = Q.pop()

                    i, j = random.choice(shared_memory["quadrants"][q])
                    robot["i"] = i
                    robot["j"] = j
                    shared_memory["grid"][i][j] = robot["id"]  # //////

                shared_memory["flags"]["init_done"] = True

            logging.info(f"Robô {self.id} liberou o grid_mutex!")


def clear_terminal():
    """Limpa o terminal."""

    os.system("cls" if os.name == "nt" else "clear")


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
            robots=None,  # será preenchido depois
            grid_mutex=manager.Lock(),
            robots_mutex=manager.Lock(),
            flags=manager.dict({"init_done": False, "vencedor": None}),
            alive=4,
        )

        # Cria a lista de dicionários de robo
        robot_dicts = [
            manager.dict(
                {
                    "id": str(id),
                    "F": random.randint(1, 10),
                    "E": random.randint(10, 100),
                    "V": random.randint(1, 5),
                    "i": 0,
                    "j": 0,
                    "status": Status.ALIVE.value,
                    "ult_pos": None,
                }
            )
            for id in range(4)
        ]
        shared_memory["robots"] = manager.list(robot_dicts)

        # Recebe o shared_memory e cria cada robo com ele pronto
        robots = [Robot(str(id), shared_memory, manager) for id in range(4)]

        viewer = Viewer(shared_memory)
        for robot in robots:
            robot.start()
        viewer.start()

        for robot in robots:
            robot.join()
        viewer.join()


if __name__ == "__main__":
    main()
