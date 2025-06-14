import logging
import multiprocessing as mp
import random
import threading as th
from enum import Enum
from multiprocessing.managers import DictProxy, SyncManager
from threading import Lock
from typing import Optional
import os
GRID_SIZE = (40, 20)
CHUNK_SIZE = (5, 5)


class Status(Enum):
    ALIVE = 0
    DEAD = 1


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
            self.generate_grid(self.shared_memory, self.manager)
        if int(self.id) == 0:
            while True:
                comando = self.shared_memory["fila_comandos"].get()
                if comando == 'quit':
                    break
                di, dj = comando 
                self.move_player(di, dj)
        else:
            while True:
                self.move_npc()
        
        self.snapshot_grid()
        
    
    def snapshot_grid(self) -> None:
            with self.shared_memory["grid_mutex"]:
                logging.info(f"Robô {self.id} adquiriu o grid_mutex!")
                if self.shared_memory["flags"]["init_done"]:
                        robot = self.shared_memory["robots"][int(self.id)]
                        logging.info(
                            f"Robô {self.id} está fazendo uma snapshot do grid e está na posição ({robot['i']},{robot['j']}) !"
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
    
    def move_player(self, di, dj):
            with self.shared_memory["robots_mutex"]:
                robot = self.shared_memory["robots"][0]
                new_i = robot['i'] + di
                new_j = robot['j'] + dj
                if 1 <= new_i < GRID_SIZE[0] - 1 and 1 <= new_j < GRID_SIZE[1] - 1:
                    with self.shared_memory["grid_mutex"]: #Seguro a grid apenas um modifica
                        cell =  self.shared_memory['grid'][new_i][new_j]  # type: ignore
                        if isinstance(cell, Cell) and cell.type == CellType.OBSTACLE:
                            print(f"Movimento inválido! O robô {robot['id']} encontrou um obstáculo.")
                            return
                        robot['E'] -= 1  # Consome energia ao mover
                        if robot['E'] <= 0:
                            print(f"Energia esgotada! O robô {robot['id']} não pode se mover.")
                            return 
                        robot['i'] = new_i
                        robot['j'] = new_j
                        self.shared_memory["grid"][new_i][new_j] = robot['id']
                        if cell.type == CellType.RECHARGE:
                            self.pega_energia()
                        else:
                            self.esta_proximo()
                            self.snapshot_grid()
                        logging.info(f"Robô {robot['id']} se moveu para ({new_i}, {new_j})!")
            self.snapshot_grid()
    def move_npc(self):
        import random
        # Só executa para NPCs (id diferente de 0)
        if int(self.id) == 0:
            return
    
        direcoes = [(-1, 0), (1, 0), (0, -1), (0, 1)]  # cima, baixo, esquerda, direita
        random.shuffle(direcoes)  # embaralha para escolher aleatoriamente
    
        for di, dj in direcoes:
            with self.shared_memory["robots_mutex"]:
                robot = self.shared_memory["robots"][int(self.id)]
                new_i = robot['i'] + di
                new_j = robot['j'] + dj
                if 1 <= new_i < GRID_SIZE[0] - 1 and 1 <= new_j < GRID_SIZE[1] - 1:
                    with self.shared_memory["grid_mutex"]:
                        cell = self.shared_memory['grid'][new_i][new_j]
                        if isinstance(cell, Cell) and cell.type != CellType.OBSTACLE:
                            robot['i'] = new_i
                            robot['j'] = new_j
                            self.shared_memory["grid"][new_i][new_j] = robot['id']
                            if cell.type == CellType.RECHARGE:
                                self.pega_energia()
                            else:
                                self.esta_proximo()
            self.snapshot_grid()
            logging.info(f"NPC {robot['id']} se moveu para ({new_i}, {new_j})!")
            return


    def esta_proximo(self):
        robot = self.shared_memory['robots'][int(self.id)]
        i, j = robot['i'], robot['j']
        # Verifica se o robô atual está em uma zona segura 
        cell_atual = self.shared_memory['grid'][i][j]
        if isinstance(cell_atual, Cell) and cell_atual.type == CellType.RECHARGE:
            # Se o robô está em uma célula de recarga ele está protegido pelo lock
            logging.info(f"Robô {self.id} está em uma célula de recarga e não pode atacar.")
            return False

        linha_de_combate = [
            (i - 1, j),  # Cima W
            (i + 1, j),  # Baixo S
            (i, j - 1),  # Esquerda A
            (i, j + 1)   # Direita D
        ]
        for vi, vj in linha_de_combate:
            if 0 <= vi < GRID_SIZE[0] and 0 <= vj < GRID_SIZE[1]: #Verifica se a linha de combate tá na grid
                cell = self.shared_memory['grid'][vi][vj] 
                if isinstance(cell, str): # Vê se a celula contém um robo
                    robo_adversario = None
                    for r in self.shared_memory['robots']: #Busca o robo 
                        if r['id'] == cell:  #Acha o robo que irá enfrentar
                            robo_adversario = r
                            break
                    if robo_adversario:
                        cell_ad = self.shared_memory['grid'][robo_adversario['i']][robo_adversario['j']]
                        if isinstance(cell_ad, Cell) and cell_ad.type == CellType.RECHARGE:
                                logging.info(f"Robô {cell_ad} está recarregando e não pode ser atacado.")
                                continue
                        else:
                        # Se o robô adversário não está em uma célula de recarga, ele pode ser atacado 
                            logging.info(f"Robô {self.id} encontrou o robô {cell_ad} próximo e irá ataca-lo!")
                            resultado_briga = self.briga(int(self.id), int(cell_ad))
                            if resultado_briga == "empate" or  "morreu":
                                    #Criar situação matando robos
                                    return True
                    else:
                        logging.info(f"Robô {self.id} não encontrou nenhum robô próximo para atacar.")
                        return False
            return False
        
    def briga(self, id1: int, id2: int) -> str:
        with self.shared_memory["robots_mutex"]:
            robots = self.shared_memory["robots"]
            logging.info(f"Robô {self.id} está brigando com o robô {id2}!")
            Poder1 = (
                (robots[id1]["F"] * 2)+ robots[id1]["E"]
            )
            Poder2 = (
                (robots[id2]["F"] * 2)+ robots[id2]["E"]
            )

            if Poder1 > Poder2:
                logging.info(f"Robô {self.id} venceu o Robô {id2}!")
                robots[id2]["status"] = Status.DEAD
                return "matou"
            elif Poder1 < Poder2:
                logging.info(f"Robô {self.id} foi derrotado pelo Robô {id2}!")
                robots[id1]["status"] = Status.DEAD
                return "morreu"
            else:
                logging.info(
                    f"Robô {self.id} e Robô {id2} empataram e ambos foram mortos"
                )
                robots[id1]["status"] = Status.DEAD
                robots[id2]["status"] = Status.DEAD
                return "empate"         
               
    def pega_energia(self) -> None:
                self.shared_memory["robots"][int(self.id)]["E"] += 20
                logging.info(
                f"Robô {self.id} recarregou energia! Energia atual: {self.shared_memory['robots'][int(self.id)]['E']}"
                    )
                #Criar o lock para a célula de recarga

    def generate_grid(
        self, shared_memory: DictProxy, manager: SyncManager
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
                    shared_memory["grid"][i][j] = robot["id"] #//////

                shared_memory["flags"]["init_done"] = True

            logging.info(f"Robô {self.id} liberou o grid_mutex!")
    # def sense_act(self):
    #     if int(self.id) == 0:
    #         self.move_player(0, 0)  # O jogador controla o robô 0
    #     else:
    #         self.move_npc()



class CellType(Enum):
    STANDARD = 0
    OBSTACLE = 1
    RECHARGE = 2

def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')


class Cell:
    def __init__(
        self,
        i: int,
        j: int,
        type: CellType,
        value: str | None = None,
        lock: Optional[Lock] | None = None,
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
        fila_comandos = manager.Queue()
        shared_memory = manager.dict(
            grid=manager.list(),
            robots=manager.list(),
            grid_mutex=manager.Lock(),
            robots_mutex=manager.Lock(),
            flags=manager.dict({"init_done": False, "vencedor": None}),
            fila_comandos=fila_comandos,
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
        
        while True:
            # clear_terminal()  # Limpa o terminal antes de desenhar a grade
            move = input("Mover (w/a/s/d, q para sair): ").strip().lower()
            if move == 'w':
                shared_memory["fila_comandos"].put((0, -1))
            elif move == 's':
                shared_memory["fila_comados"].put((0, 1))
            elif move == 'a':
                shared_memory["fila_comados"].put((-1, 0))
            elif move == 'd':
                shared_memory["fila_comados"].put((1, 0))
            elif move == 'q':
                shared_memory["fila_comados"].put("quit")
                break


if __name__ == "__main__":
    main()
   