## Projeto Sistemas Distribuídos

### Introdução

Para a implementação desse projeto, foi solicitado a simulação dos conceitos de algorítmos dados em sala.
Foi implementado uma simulação de algoritmos distribuídos utilizando Python e Pytest para testes automatizados. O projeto aborda quatro principais conceitos:  
1. Sincronização de tempo com relógios lógicos (Lamport).  
2. Captura de estado global (Snapshot com o algoritmo de Chandy-Lamport).  
3. Algoritmo de eleição (Bully).  
4. Detecção de falhas por meio de heartbeat.

Durante o desenvolvimento, foi enfrentado vários desafios ao trabalhar com Python e Pytest, num processo de adaptação a uma linguagem e a uma abordagem de testes que são bastante diferentes do que estava acostumado em outros contextos. A seguir, é relatado os principais pontos e soluções encontradas.

---

### Desafios e Soluções Encontradas

#### Adaptação à Sintaxe e Dinâmica de Python

Ao iniciar o projeto, tive dificuldades com a sintaxe e a forma de gerenciamento de objetos e threads em Python. Por exemplo, o gerenciamento de threads e processos com o módulo `multiprocessing` e o uso de classes herdadas (como a criação do servidor XMLRPC multithreaded utilizando `ThreadingMixIn`) foi demorado para garantir que as requisições fossem processadas de forma concorrente.

#### Integração com XMLRPC

A comunicação entre nós foi feita via XMLRPC, e um dos desafios foi garantir que os objetos retornados fossem compatíveis com o protocolo XMLRPC. Por exemplo, precisei converter as chaves de dicionários para strings no método `get_snapshot` para evitar erros de serialização.

#### Implementação do Algoritmo de Eleição (Bully)

Pra implementar o algoritmo de eleição foi precisei garantir que as chamadas remotas fossem processadas mesmo quando outros métodos estavam em execução. Para resolver isso, optei por utilizar um servidor XMLRPC multithreaded, que permite o processamento simultâneo de requisições. Além disso, enfrentei problemas relacionados à sincronização dos métodos de eleição e à definição de quais nós deveriam responder. Ajustei a lógica para que, em caso de ausência de resposta dos nós de maior ID, o nó que iniciou a eleição se declare coordenador.

#### Testes com Pytest e Mocks

A transição para Pytest foi outro desafio. Tive que aprender a utilizar o framework pra escrever os testes unitários e de integração.  
Alguns dos erros que ocorreram foram:
- A necessidade de ajustar os métodos fake para receberem o parâmetro `self` quando são usados em métodos de instância (por exemplo, no teste do heartbeat).
- Problemas com a ordem de aplicação do monkeypatch, que precisou que o patch fosse aplicado antes de criar instâncias das classes.

Com o auxílio do `unittest.mock` e de testes iterativos, tentei isolar cada funcionalidade (Lamport, Snapshot, Bully e Heartbeat) e garantir que os métodos respondessem como esperado, inclusive simulando falhas (como tentar enviar mensagens para nós inexistentes).

---

### Instruções de Execução e Dependências

#### Dependências

Para executar o projeto e os testes, é necessário ter instalado:
- **Python 3.7+** (a versão 3.11 foi testada, mas versões recentes são recomendadas);
- **Pytest** para os testes automatizados;
- **Unittest.mock** (já incluso no Python);
- **XMLRPC** (já incluso no Python).

Instalação via pip:

```bash
pip install pytest
```

#### Estrutura de Arquivos

O projeto está organizado em dois arquivos principais:
- `distributed.py`: Contém a implementação das classes (Node, Monitor, etc.) e as funções para iniciar os servidores e a simulação do cliente.
- `test_node.py`: Contém os testes automatizados usando pytest e mocks para validar os comportamentos das funcionalidades.

#### Execução do Projeto

1. **Para Executar a Simulação Completa:**

   Execute o arquivo `distributed.py`:
   ```bash
   python distributed.py
   ```
   Isso vai iniciar os servidores, o monitor e o cliente que simula os algoritmos distribuídos. Vai ter os logs de execução no terminal.

2. **Para Executar os Testes com Pytest:**

   No terminal, estando no diretório dos arquivos, execute:
   ```bash
   python -m pytest test_node.py
   ```
   ou, se o comando `pytest` estiver disponível:
   ```bash
   pytest test_node.py
   ```

   Os testes vão validar cada parte do sistema (Lamport, Snapshot, Bully e Heartbeat) e exibir o resultado dos casos de sucesso e dos testes forçados a erro.

#### Exemplos Práticos

No arquivo de teste `test_node.py`, criei cenários como:
- Envio de mensagem para um nó inexistente, que deve retornar erro e incrementar o relógio conforme esperado.
- Inicialização de snapshot e simulação de erro ao enviar uma mensagem de aplicação para um nó inválido.
- Execução do algoritmo Bully, simulando situações em que nós de maior ID não respondem, de modo que o nó iniciador se declara coordenador.
- Teste do heartbeat, onde uso monkeypatch para substituir o método `send_heartbeat` e garantir que ele seja chamado periodicamente.

Cada teste foi elaborado para cobrir tanto os casos de sucesso quanto as falhas, permitindo validar a robustez do sistema distribuído.

---

### Conceitos Teóricos

#### Relógio de Lamport

O algoritmo de Lamport permite a ordenação de eventos em sistemas distribuídos através de um contador lógico. Cada vez que ocorre um evento local, o contador é incrementado; ao enviar uma mensagem, o contador é enviado junto, e no recebimento o nó atualiza seu contador com o valor máximo entre seu próprio contador e o recebido, somando 1.

#### Snapshot Global (Chandy-Lamport)

O algoritmo de Chandy-Lamport permite capturar o estado global de um sistema distribuído de forma consistente. Quando um nó inicia o snapshot, ele registra seu estado local e envia marcadores para todos os outros nós. Cada nó, ao receber o primeiro marcador, registra seu estado e passa o marcador adiante. As mensagens que chegam após o início do snapshot e antes da recepção do marcador em cada canal são registradas como parte do estado dos canais.

#### Algoritmo de Eleição (Bully)

O algoritmo de Bully é utilizado para eleger um coordenador em um sistema distribuído quando o coordenador atual falha. Cada nó tem um identificador único. Quando um nó detecta a falha do coordenador, ele inicia a eleição enviando mensagens para os nós com identificador maior. Se nenhum desses nós responder, ele se declara o coordenador; caso contrário, ele aguarda o anúncio do novo coordenador.

#### Detecção de Falhas (Heartbeat)

Para monitorar a saúde dos nós, cada nó envia periodicamente uma mensagem de heartbeat para um monitor central. Se o monitor não receber um heartbeat dentro de um intervalo de tempo definido, ele considera que o nó falhou e pode disparar ações corretivas, como iniciar uma nova eleição.
