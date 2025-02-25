import xmlrpc.server
import xmlrpc.client
import multiprocessing
import threading
import time
from socketserver import ThreadingMixIn

# -----------------------------------------------------------
# Servidor XMLRPC multithreaded
# -----------------------------------------------------------
class ThreadedXMLRPCServer(ThreadingMixIn, xmlrpc.server.SimpleXMLRPCServer):
    pass

# -----------------------------------------------------------
# Classe Node: representa cada nó do sistema distribuído
# -----------------------------------------------------------
class Node:
    def __init__(self, node_id, port, peers, monitor_url):
        """
        Inicializa o nó com:
          - node_id: identificador único.
          - port: porta onde o nó atende via XMLRPC.
          - peers: dicionário dos outros nós {node_id: (host, port)}.
          - monitor_url: URL do monitor para enviar heartbeat.
        """
        self.node_id = node_id
        self.port = port
        self.peers = peers
        self.monitor_url = monitor_url

        # ----- Função 1: Lamport Clock -----
        self.lamport_clock = 0

        # Estado de aplicação (exemplo: um contador)
        self.value = 0

        # ----- Função 2: Snapshot (Chandy-Lamport) -----
        self.snapshot_initiated = False     # Indica se o snapshot foi iniciado
        self.snapshot_state = None          # Estado local registrado no snapshot
        # Para cada canal (de cada peer), guarda as mensagens que chegam após iniciar o snapshot
        self.channel_state = {peer: [] for peer in self.peers}
        # Indica se já foi recebido o marcador naquele canal
        self.markers_received = {peer: False for peer in self.peers}

        # ----- Função 3: Eleição (Bully) -----
        self.coordinator = None             # ID do coordenador atual
        self.in_election = False            # Indica se o nó está em eleição

        # ----- Função 4: Heartbeat -----
        # Inicia uma thread que envia periodicamente heartbeat para o monitor
        heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
        heartbeat_thread.start()

    # Método que envia heartbeat periodicamente para o monitor
    def heartbeat_loop(self):
        while True:
            self.send_heartbeat()
            time.sleep(2)  # Envia heartbeat a cada 2 segundos

    def send_heartbeat(self):
        try:
            monitor = xmlrpc.client.ServerProxy(self.monitor_url)
            monitor.receive_heartbeat(self.node_id)
        except Exception as e:
            print(f"Node {self.node_id}: Erro ao enviar heartbeat: {e}")

    # -----------------------------------------------------
    # Métodos para Clocks e Sincronização (Lamport Clock)
    # -----------------------------------------------------
    def local_event(self, description):
        self.lamport_clock += 1
        print(f"[Lamport] Node {self.node_id} (Clock {self.lamport_clock}): {description}")
        return self.lamport_clock

    def send_message(self, target_node_id, message):
        self.lamport_clock += 1
        timestamp = self.lamport_clock
        print(f"[Lamport] Node {self.node_id} enviando para Node {target_node_id} (Clock {timestamp}): {message}")
        target_info = self.peers.get(target_node_id)
        if not target_info:
            print(f"Node {self.node_id}: Node {target_node_id} não encontrado!")
            return
        url = f"http://{target_info[0]}:{target_info[1]}"
        try:
            proxy = xmlrpc.client.ServerProxy(url)
            proxy.receive_message(timestamp, message, self.node_id)
        except Exception as e:
            print(f"Node {self.node_id}: Erro ao enviar para Node {target_node_id}: {e}")

    def receive_message(self, timestamp, message, sender_node_id):
        self.lamport_clock = max(self.lamport_clock, timestamp) + 1
        print(f"[Lamport] Node {self.node_id} (Clock {self.lamport_clock}) recebeu de Node {sender_node_id}: {message}")
        return self.lamport_clock

    # -----------------------------------------------------
    # Métodos para Captura de Estado (Snapshot – Chandy-Lamport)
    # -----------------------------------------------------
    def initiate_snapshot(self):
        if not self.snapshot_initiated:
            self.snapshot_initiated = True
            self.snapshot_state = self.value
            print(f"[Snapshot] Node {self.node_id} inicia snapshot. Estado local: {self.snapshot_state}")
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
            return "Snapshot já iniciado"

    def receive_marker(self, sender_node_id):
        if not self.snapshot_initiated:
            self.snapshot_initiated = True
            self.snapshot_state = self.value
            print(f"[Snapshot] Node {self.node_id} recebeu primeiro marcador de Node {sender_node_id}. Estado local: {self.snapshot_state}")
            # Envia marcador para todos os peers apenas uma vez.
            for peer_id, info in self.peers.items():
                if peer_id == sender_node_id:
                    continue
                url = f"http://{info[0]}:{info[1]}"
                try:
                    proxy = xmlrpc.client.ServerProxy(url)
                    proxy.receive_marker(self.node_id)
                except Exception as e:
                    print(f"Node {self.node_id}: Erro ao enviar marcador para Node {peer_id}: {e}")
        # Marca o canal do sender como tendo recebido o marcador
        self.markers_received[sender_node_id] = True
        print(f"[Snapshot] Node {self.node_id} marca canal de Node {sender_node_id} com marcador.")
        
        # Verifica se recebeu marcadores de todos os canais
        if all(self.markers_received.values()):
            print(f"[Snapshot] Node {self.node_id} snapshot completo. Estado local: {self.snapshot_state}, Canais: {self.channel_state}")
        return self.snapshot_state

    def get_snapshot(self):
        # Converte as chaves de channel_state para strings para que sejam válidas para o XMLRPC
        channel_state_str = {str(peer): messages for peer, messages in self.channel_state.items()}
        return {"local_state": self.snapshot_state, "channel_state": channel_state_str}


    # Método para simular uma mensagem de aplicação que altera o estado (usado no snapshot)
    def send_app_message(self, target_node_id, delta):
        self.value += delta
        print(f"[App] Node {self.node_id} atualiza valor em {delta}. Novo valor: {self.value}")
        target_info = self.peers.get(target_node_id)
        if not target_info:
            print(f"Node {self.node_id}: Node {target_node_id} não encontrado!")
            return
        url = f"http://{target_info[0]}:{target_info[1]}"
        try:
            proxy = xmlrpc.client.ServerProxy(url)
            proxy.receive_app_message(delta, self.node_id)
        except Exception as e:
            print(f"Node {self.node_id}: Erro ao enviar app message para Node {target_node_id}: {e}")

    def receive_app_message(self, delta, sender_node_id):
        # Se o snapshot estiver em andamento e o marcador ainda não foi recebido neste canal,
        # a mensagem faz parte do estado do canal.
        if self.snapshot_initiated and not self.markers_received.get(sender_node_id, True):
            self.channel_state[sender_node_id].append(delta)
        self.value += delta
        print(f"[App] Node {self.node_id} recebeu app message de Node {sender_node_id} (delta {delta}). Novo valor: {self.value}")
        return self.value

    # -----------------------------------------------------
    # Métodos para Eleição (Bully)
    # -----------------------------------------------------
    def start_election(self):
        if self.in_election:
            return "Eleição já em progresso"
        self.in_election = True
        print(f"[Bully] Node {self.node_id} inicia eleição.")
        # Envia mensagem de eleição para nós com ID maior
        higher_nodes = {nid: info for nid, info in self.peers.items() if nid > self.node_id}
        recebeu_ok = False
        for nid, info in higher_nodes.items():
            url = f"http://{info[0]}:{info[1]}"
            try:
                proxy = xmlrpc.client.ServerProxy(url)
                resposta = proxy.receive_election(self.node_id)
                if resposta == "OK":
                    recebeu_ok = True
            except Exception as e:
                print(f"[Bully] Node {self.node_id}: Sem resposta do Node {nid} na eleição: {e}")
        if not recebeu_ok:
            # Não houve resposta, declara-se coordenador
            self.coordinator = self.node_id
            print(f"[Bully] Node {self.node_id} se torna o coordenador.")
            # Notifica todos os nós
            for nid, info in self.peers.items():
                url = f"http://{info[0]}:{info[1]}"
                try:
                    proxy = xmlrpc.client.ServerProxy(url)
                    proxy.announce_coordinator(self.node_id)
                except Exception as e:
                    print(f"[Bully] Node {self.node_id}: Erro ao anunciar coordenador para Node {nid}: {e}")
            self.in_election = False
            return f"Coordenador é o Node {self.node_id}"
        else:
            print(f"[Bully] Node {self.node_id} aguardando anúncio do coordenador.")
            time.sleep(3)
            self.in_election = False
            return f"Coordenador é o Node {self.coordinator}"

    def receive_election(self, sender_node_id):
        print(f"[Bully] Node {self.node_id} recebeu mensagem de eleição do Node {sender_node_id}. Respondendo OK.")
        # Responde OK e, se não estiver em eleição, inicia sua própria eleição
        if not self.in_election:
            threading.Thread(target=self.start_election, daemon=True).start()
        return "OK"

    def announce_coordinator(self, coordinator_id):
        self.coordinator = coordinator_id
        print(f"[Bully] Node {self.node_id} reconhece o novo coordenador: Node {coordinator_id}")
        return "Coordenador reconhecido"

# -----------------------------------------------------------
# Classe Monitor: responsável por detectar falhas via heartbeat
# -----------------------------------------------------------
class Monitor:
    def __init__(self):
        self.heartbeats = {}  # Armazena último timestamp de heartbeat de cada nó
        self.timeout = 5      # Timeout em segundos

    def receive_heartbeat(self, node_id):
        self.heartbeats[node_id] = time.time()
        print(f"[Monitor] Recebeu heartbeat de Node {node_id}")
        return True

    def check_failures(self):
        current_time = time.time()
        failed_nodes = []
        for node_id, last_time in self.heartbeats.items():
            if current_time - last_time > self.timeout:
                failed_nodes.append(node_id)
        return failed_nodes

    def get_status(self):
        return self.heartbeats

# -----------------------------------------------------------
# Funções para iniciar os servidores com multithreading
# -----------------------------------------------------------
def run_monitor(port):
    monitor = Monitor()
    server = ThreadedXMLRPCServer(("localhost", port), allow_none=True, logRequests=False)
    server.register_instance(monitor)
    print(f"[Monitor] Rodando na porta {port}...")
    server.serve_forever()

def run_node(node_id, port, peers, monitor_url):
    node = Node(node_id, port, peers, monitor_url)
    server = ThreadedXMLRPCServer(("localhost", port), allow_none=True, logRequests=False)
    server.register_instance(node)
    print(f"Node {node_id} rodando na porta {port}...")
    server.serve_forever()

# -----------------------------------------------------------
# Cliente que interage com os nós e o monitor (Simulação)
# -----------------------------------------------------------
def client_simulation(nodes_info, monitor_port):
    # Cria proxies para cada nó normalmente
    proxies = {node_id: xmlrpc.client.ServerProxy(f"http://{info[0]}:{info[1]}")
               for node_id, info in nodes_info.items()}
    monitor = xmlrpc.client.ServerProxy(f"http://localhost:{monitor_port}")

    time.sleep(3)  # Aguarda o início dos nós e heartbeats

    # --- Parte 1: Lamport Clock ---
    print("\n=== [Lamport] Eventos ===")
  
    proxies[1].local_event("Evento local no Node 1")
    time.sleep(1)
    proxies[1].send_message(2, "Olá do Node 1 para Node 2")
    time.sleep(1)
    proxies[2].local_event("Evento local no Node 2")
    time.sleep(1)
    proxies[2].send_message(3, "Olá do Node 2 para Node 3")
    time.sleep(1)
    proxies[3].send_message(1, "Olá do Node 3 para Node 1")
    time.sleep(1)

    # --- Parte 2: Snapshot (Chandy-Lamport) ---
    print("\n=== [Snapshot] Iniciando snapshot ===")
   
    proxies[1].initiate_snapshot()
    time.sleep(3)
    proxies[2].send_app_message(1, 10)
    time.sleep(3)
    proxies[3].send_app_message(2, -5)
    time.sleep(3)
    proxies[1].send_app_message(3, 20)
    time.sleep(3)
    proxies[3].send_app_message(1, 15)
    time.sleep(3)
    proxies[2].send_app_message(3, -10)
    time.sleep(3)

    # --- Parte 3: Eleição (Bully) ---
    print("\n=== [Bully] Iniciando eleição ===")
    # Simulando falha do coordenador 
    result = proxies[1].start_election()
    print("Resultado da eleição:", result)
    
        
    

    # --- Parte 4: Detecção de Falhas (Heartbeat) ---
    print("\n=== [Heartbeat] Monitoramento ===")

    time.sleep(6)  # Aguarda para que o monitor identifique nós inativos (se houver)
    failed = monitor.check_failures()
    if failed:
        print("[Monitor] Falha detectada nos nós:", failed)
    else:
        print("[Monitor] Todos os nós estão ativos.")
   
    time.sleep(1)

    # Coleta dos snapshots de cada nó
    print("\n=== [Snapshot] Estados coletados ===")
    for node_id, proxy in proxies.items():
        try:
            snapshot = proxy.get_snapshot()
            print(f"Node {node_id} snapshot:", snapshot)
        except Exception as e:
            print(f"Erro ao coletar snapshot do Node {node_id}:", e)



# -----------------------------------------------------------
# Bloco principal
# -----------------------------------------------------------
if __name__ == '__main__':
    # Definição dos nós: node_id -> (host, porta)
    nodes_info = {
        1: ("localhost", 8001),
        2: ("localhost", 8002),
        3: ("localhost", 8003)
    }
    monitor_port = 8004  # Porta do monitor

    # Para cada nó, define seus peers (todos os outros nós)
    peers_for_node = {
        node_id: {nid: info for nid, info in nodes_info.items() if nid != node_id}
        for node_id in nodes_info
    }

    # Inicia o processo do monitor
    monitor_process = multiprocessing.Process(target=run_monitor, args=(monitor_port,))
    monitor_process.start()

    # Inicia um processo para cada nó
    processes = []
    for node_id, (host, port) in nodes_info.items():
        p = multiprocessing.Process(target=run_node, args=(node_id, port, peers_for_node[node_id], f"http://localhost:{monitor_port}"))
        p.start()
        processes.append(p)

    # Executa a simulação do cliente
    client_simulation(nodes_info, monitor_port)

    # Aguarda um pouco para visualização e encerra os processos
    time.sleep(5)
    for p in processes:
        p.terminate()
    monitor_process.terminate()
    for p in processes:
        p.join()
    monitor_process.join()