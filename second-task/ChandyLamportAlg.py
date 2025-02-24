import xmlrpc.server
import xmlrpc.client
import multiprocessing
import time

class Node:
    def __init__(self, node_id, port, peers):
        """
        Inicializa o nó com seu identificador, porta e peers.
        Também define o estado local (value) e as variáveis necessárias para o snapshot.
        """
        self.node_id = node_id          # Identificador do nó
        self.port = port                # Porta de atendimento via XMLRPC
        self.peers = peers              # Dicionário com peers: {node_id: (host, porta)}

        # Estado local do nó (exemplo: um contador ou valor)
        self.value = 0

        # Variáveis para o snapshot (captura de estado global)
        self.snapshot_iniciado = False      # Indica se o snapshot já foi iniciado
        self.snapshot_registrado = False      # Indica se o estado local já foi registrado
        self.snapshot_state = None            # Armazena o estado local no momento do snapshot

        # Para cada canal (de cada peer), armazenamos as mensagens que chegam após o snapshot iniciar
        self.channel_state = {peer_id: [] for peer_id in peers}
        # Registra se já recebeu o marcador de cada canal (peer)
        self.markers_recebidos = {peer_id: False for peer_id in peers}

    def local_event(self, description):
        """
        Simula um evento local que altera o estado do nó.
        """
        self.value += 1
        print(f"Node {self.node_id}: Evento local '{description}'. Novo valor: {self.value}")
        return self.value

    def send_app_message(self, target_node_id, amount):
        """
        Envia uma mensagem de aplicação para outro nó.
        A mensagem altera o estado local e é transmitida ao nó de destino.
        """
        self.value += amount
        print(f"Node {self.node_id}: Enviando mensagem de aplicação com valor {amount} para Node {target_node_id}. Novo valor: {self.value}")
        target_info = self.peers.get(target_node_id)
        if target_info is None:
            print(f"Node {self.node_id}: Peer {target_node_id} não encontrado.")
            return -1

        url = f"http://{target_info[0]}:{target_info[1]}"
        try:
            proxy = xmlrpc.client.ServerProxy(url)
            proxy.receive_app_message(amount, self.node_id)
        except Exception as e:
            print(f"Node {self.node_id}: Erro ao enviar mensagem de aplicação para Node {target_node_id}: {e}")
        return self.value

    def receive_app_message(self, amount, sender_node_id):
        """
        Processa a mensagem de aplicação recebida.
        Se um snapshot estiver em andamento e o marcador ainda não tiver sido recebido no canal,
        registra a mensagem no estado daquele canal.
        """
        # Se o snapshot foi iniciado e ainda não recebeu o marcador do canal do remetente,
        # a mensagem faz parte do estado do canal.
        if self.snapshot_iniciado and not self.markers_recebidos.get(sender_node_id, True):
            self.channel_state[sender_node_id].append(amount)

        self.value += amount
        print(f"Node {self.node_id}: Recebeu mensagem de aplicação com valor {amount} de Node {sender_node_id}. Novo valor: {self.value}")
        return self.value

    def initiate_snapshot(self):
        """
        Inicia o snapshot global:
          - Registra o estado local.
          - Envia um marcador para todos os peers.
        """
        if not self.snapshot_iniciado:
            self.snapshot_iniciado = True
            self.snapshot_registrado = True
            self.snapshot_state = self.value
            print(f"Node {self.node_id}: Iniciando snapshot. Estado local registrado: {self.snapshot_state}")
            # Envia marcador para todos os peers
            for peer_id, info in self.peers.items():
                url = f"http://{info[0]}:{info[1]}"
                try:
                    proxy = xmlrpc.client.ServerProxy(url)
                    proxy.receive_marker(self.node_id)
                except Exception as e:
                    print(f"Node {self.node_id}: Erro ao enviar marcador para Node {peer_id}: {e}")
            return "Snapshot iniciado"
        else:
            return "Snapshot já foi iniciado"

    def receive_marker(self, sender_node_id):
        """
        Processa a recepção de um marcador:
          - Se for a primeira vez que o nó recebe um marcador, registra o estado local e envia marcadores para os peers.
          - Em qualquer caso, marca o canal do remetente como concluído (marcador recebido).
        """
        if not self.snapshot_iniciado:
            # Primeiro marcador recebido: registra o estado local e envia marcadores para os demais
            self.snapshot_iniciado = True
            self.snapshot_registrado = True
            self.snapshot_state = self.value
            print(f"Node {self.node_id}: Recebeu primeiro marcador de Node {sender_node_id}. Estado local registrado: {self.snapshot_state}")
            for peer_id, info in self.peers.items():
                url = f"http://{info[0]}:{info[1]}"
                try:
                    proxy = xmlrpc.client.ServerProxy(url)
                    proxy.receive_marker(self.node_id)
                except Exception as e:
                    print(f"Node {self.node_id}: Erro ao enviar marcador para Node {peer_id}: {e}")

        # Marca o canal (do peer remetente) como tendo recebido o marcador
        self.markers_recebidos[sender_node_id] = True
        print(f"Node {self.node_id}: Marcador recebido de Node {sender_node_id}.")

        # Se o nó recebeu marcadores de todos os seus canais, o snapshot deste nó está completo
        if all(self.markers_recebidos.values()):
            print(f"Node {self.node_id}: Snapshot completo!")
            print(f"   Estado local: {self.snapshot_state}")
            print(f"   Estados dos canais: {self.channel_state}")
        return self.snapshot_state

    def get_snapshot(self):
        """
        Retorna os dados do snapshot, contendo o estado local e o estado registrado dos canais.
        """
        return {"local_state": self.snapshot_state, "channel_state": self.channel_state}


def run_node(node_id, port, peers):
    """
    Inicializa o nó e registra seus métodos para serem acessados remotamente via XMLRPC.
    """
    node = Node(node_id, port, peers)
    server = xmlrpc.server.SimpleXMLRPCServer(("localhost", port), allow_none=True, logRequests=False)
    server.register_instance(node)
    print(f"Node {node_id} rodando na porta {port}...")
    server.serve_forever()


def client_simulation(nodes_info):
    """
    Simula a comunicação entre os nós e a captura do estado global.
    Executa as seguintes etapas:
      1. Envia mensagens de aplicação entre os nós.
      2. Inicia o snapshot a partir de um nó (Node 1).
      3. Envia mais mensagens após o início do snapshot.
      4. Coleta e imprime os estados capturados (snapshot) de cada nó.
    """
    time.sleep(2)  # Aguarda os nós iniciarem

    # Cria proxies para cada nó
    proxies = {node_id: xmlrpc.client.ServerProxy(f"http://{info[0]}:{info[1]}") 
               for node_id, info in nodes_info.items()}

    # Etapa 1: Envia mensagens de aplicação entre os nós
    proxies[1].send_app_message(2, 5)
    time.sleep(1)
    proxies[2].send_app_message(3, 10)
    time.sleep(1)
    proxies[3].send_app_message(1, -3)
    time.sleep(1)

    # Etapa 2: Inicia o snapshot a partir do Node 1
    print("\n=== Iniciando snapshot global a partir do Node 1 ===\n")
    proxies[1].initiate_snapshot()
    time.sleep(1)

    # Etapa 3: Envia mensagens de aplicação após o início do snapshot
    proxies[2].send_app_message(1, 7)
    time.sleep(1)
    proxies[3].send_app_message(2, -2)
    time.sleep(1)

    # Aguarda para que todos os nós completem o snapshot
    time.sleep(3)
    
    # Etapa 4: Coleta e imprime os snapshots de cada nó
    print("\n=== Estados capturados (Snapshot) ===\n")
    for node_id, proxy in proxies.items():
        snapshot = proxy.get_snapshot()
        print(f"Node {node_id}: {snapshot}")


if __name__ == '__main__':
    # Configuração dos nós: node_id -> (host, porta)
    nodes_info = {
        1: ("localhost", 9001),
        2: ("localhost", 9002),
        3: ("localhost", 9003)
    }

    # Para cada nó, define seus peers (todos os outros nós)
    peers_for_node = {node_id: {other_id: info 
                                for other_id, info in nodes_info.items() 
                                if other_id != node_id}
                      for node_id in nodes_info}

    # Cria um processo para cada nó
    processes = []
    for node_id, (host, port) in nodes_info.items():
        p = multiprocessing.Process(target=run_node, args=(node_id, port, peers_for_node[node_id]))
        p.start()
        processes.append(p)

    # Executa a simulação do cliente
    client_simulation(nodes_info)

    # Aguarda um tempo para visualização e encerra os processos
    time.sleep(2)
    for p in processes:
        p.terminate()
    for p in processes:
        p.join()
