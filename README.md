# so1-final
Trabalho final de SO1

Demonstração de deadlock
A função cria_deadlock cria a seguinte sequência: 
Robô 1: Adquire o battery_mutex (sucesso), dorme por 2 segundos (mantendo o lock) e tenta adquirir o grid_mutex (mas está bloqueado pelo Robô 2).
Robô 2 (Processo 2): Adquire o grid_mutex (sucesso), dorme por 2 segundos (mantendo o lock), e tenta adquirir o battery_mutex (mas está bloqueado pelo Robô 1)
Nesse caso o robô 1 espera por um recurso que o robô 2 detêm(grid_mutex), e o robô 2 espera por um recurso que o robô 1 detêm(battery_mutex). Quando isso acontece os processos ficam parados indefinidamente e as mensagem de log depois da segunda aquisição de lock nunca serão executadas. 
A função cenário_deadlock implementa uma prevenção de deadlock, implementando um timeout de 2 segundos em que, se nesse tempo o processo não adquirir o lock, ele gera uma mensagem de erro e o processo é abortado. 
