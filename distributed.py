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
# Classe Node: representa cada nó do sistema
# -----------------------------------------------------------
class Node:
    def __init__(self, node_id, port, peers, monitor_url):
        """
        Inicializa o node com:
          - node_id: ID único.
          - port: porta de atendimento.
          - peers: dicionário dos outros nós {node_id: (host, port)}.
          - monitor_url: URL do monitor para enviar heartbeat.
        """
        self.node_id = node_id
        self.port = port
        self.peers = peers
        self.monitor_url = monitor_url

        # Lamport Clock
        self.lamport_clock = 0

        # Estado de aplicação (ex.: contador)
        self.value = 0

        # Snapshot (Chandy-Lamport)
        self.snapshot_initiated = False
        self.snapshot_state = None
        self.channel_state = {peer: [] for peer in self.peers}
        self.markers_received = {peer: False for peer in self.peers}

        # Bully (Eleição)
        self.coordinator = None
        self.in_election = False

        # Heartbeat: thread que envia heartbeat pro monitor
        threading.Thread(target=self.heartbeat_loop, daemon=True).start()

    def heartbeat_loop(self):
        while True:
            self.send_heartbeat()
            time.sleep(2)

    def send_heartbeat(self):
        try:
            monitor = xmlrpc.client.ServerProxy(self.monitor_url)
            monitor.receive_heartbeat(self.node_id)
        except Exception as e:
            print(f"HB: node {self.node_id} falhou no heartbeat: {e}")

    # ----------------------------
    # Lamport Clock e Eventos
    # ----------------------------
    def local_event(self, description):
        self.lamport_clock += 1
        print(f"Lamport: node {self.node_id} (Clk {self.lamport_clock}): {description}")
        return self.lamport_clock

    def send_message(self, target_node_id, message):
        self.lamport_clock += 1
        timestamp = self.lamport_clock
        print(f"Lamport: Nód {self.node_id} envinando p/ Nód {target_node_id} (Clk {timestamp}): {message}")
        target_info = self.peers.get(target_node_id)
        if not target_info:
            print(f"Lamport: Nód {self.node_id}: Nód {target_node_id} não achado!")
            return
        url = f"http://{target_info[0]}:{target_info[1]}"
        try:
            proxy = xmlrpc.client.ServerProxy(url)
            new_clock = proxy.receive_message(timestamp, message, self.node_id)
            # Atualiza o clock do nó remetente como max(clock atual, novo clock) + 1
            self.lamport_clock = max(self.lamport_clock, new_clock) + 1
        except Exception as e:
            print(f"Lamport: Nód {self.node_id}: Erro ao enviar p/ Nód {target_node_id}: {e}")

    def receive_message(self, timestamp, message, sender_node_id):
        self.lamport_clock = max(self.lamport_clock, timestamp) + 1
        print(f"Lamport: node {self.node_id} (Clk {self.lamport_clock}) recebeu do node {sender_node_id}: {message}")
        return self.lamport_clock

    # ----------------------------
    # Snapshot (Chandy-Lamport)
    # ----------------------------
    def initiate_snapshot(self):
        if not self.snapshot_initiated:
            self.snapshot_initiated = True
            self.snapshot_state = self.value
            print(f"Snapshhot: node {self.node_id} inicia snap. Estado: {self.snapshot_state}")
            for peer_id, info in self.peers.items():
                url = f"http://{info[0]}:{info[1]}"
                try:
                    proxy = xmlrpc.client.ServerProxy(url)
                    proxy.receive_marker(self.node_id)
                except Exception as e:
                    print(f"Snapshhot: node {self.node_id}: Erro ao enviar marcador p/ node {peer_id}: {e}")
            return "Snap iniciado"
        else:
            return "Snap já iniciado"

    def receive_marker(self, sender_node_id):
        if not self.snapshot_initiated:
            self.snapshot_initiated = True
            self.snapshot_state = self.value
            print(f"Snapshhot: node {self.node_id} recebeu 1º marcador do node {sender_node_id}. Estado: {self.snapshot_state}")
            for peer_id, info in self.peers.items():
                if peer_id == sender_node_id:
                    continue
                url = f"http://{info[0]}:{info[1]}"
                try:
                    proxy = xmlrpc.client.ServerProxy(url)
                    proxy.receive_marker(self.node_id)
                except Exception as e:
                    print(f"Snapshhot: node {self.node_id}: Erro ao enviar marcador p/ node {peer_id}: {e}")
        self.markers_received[sender_node_id] = True
        print(f"Snapshhot: node {self.node_id} marca canal do node {sender_node_id} com marcador.")
        if all(self.markers_received.values()):
            print(f"Snapshhot: node {self.node_id} snap completo. Estado: {self.snapshot_state}, Canais: {self.channel_state}")
        return self.snapshot_state

    def get_snapshot(self):
        channel_state_str = {str(peer): msgs for peer, msgs in self.channel_state.items()}
        return {"local_state": self.snapshot_state, "channel_state": channel_state_str}

    def send_app_message(self, target_node_id, delta):
        self.value += delta
        print(f"App: node {self.node_id} atualiza +{delta}. Novo valor: {self.value}")
        target_info = self.peers.get(target_node_id)
        if not target_info:
            print(f"App: node {self.node_id}: node {target_node_id} não achado!")
            return
        url = f"http://{target_info[0]}:{target_info[1]}"
        try:
            proxy = xmlrpc.client.ServerProxy(url)
            proxy.receive_app_message(delta, self.node_id)
        except Exception as e:
            print(f"App: node {self.node_id}: Erro ao enviar app msg p/ node {target_node_id}: {e}")

    def receive_app_message(self, delta, sender_node_id):
        if self.snapshot_initiated and not self.markers_received.get(sender_node_id, True):
            self.channel_state[sender_node_id].append(delta)
        self.value += delta
        print(f"App: node {self.node_id} recebeu app msg de node {sender_node_id} (+{delta}). Novo valor: {self.value}")
        return self.value

    # ----------------------------
    # Bully (Eleição)
    # ----------------------------
    def start_election(self):
        if self.in_election:
            return "Eleiçã já em prog."
        self.in_election = True
        print(f"Bully: node {self.node_id} inicia eleiçã.")
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
                print(f"Bully: node {self.node_id}: Sem resposta do node {nid} na eleiçã: {e}")
        if not recebeu_ok:
            self.coordinator = self.node_id
            print(f"Bully: node {self.node_id} se torna o coord.")
            for nid, info in self.peers.items():
                url = f"http://{info[0]}:{info[1]}"
                try:
                    proxy = xmlrpc.client.ServerProxy(url)
                    proxy.announce_coordinator(self.node_id)
                except Exception as e:
                    print(f"Bully: node {self.node_id}: Erro ao anunciar coord p/ node {nid}: {e}")
            self.in_election = False
            return f"Coord é node {self.node_id}"
        else:
            print(f"Bully: node {self.node_id} aguardando anúncio do coord.")
            time.sleep(3)
            self.in_election = False
            return f"Coord é node {self.coordinator}"

    def receive_election(self, sender_node_id):
        print(f"Bully: node {self.node_id} recebeu eleiçã do node {sender_node_id}. Responde OK.")
        if not self.in_election:
            threading.Thread(target=self.start_election, daemon=True).start()
        return "OK"

    def announce_coordinator(self, coordinator_id):
        self.coordinator = coordinator_id
        print(f"Bully: node {self.node_id} reconhece coord: node {coordinator_id}")
        return "Coord reconhecido"

# -----------------------------------------------------------
# Classe Monitor: detecta falhas via heartbeat
# -----------------------------------------------------------
class Monitor:
    def __init__(self):
        self.heartbeats = {}
        self.timeout = 5

    def receive_heartbeat(self, node_id):
        self.heartbeats[node_id] = time.time()
        print(f"Monit: Recebeu HB do node {node_id}")
        return True

    def check_failures(self):
        current_time = time.time()
        failed = []
        for node_id, last in self.heartbeats.items():
            if current_time - last > self.timeout:
                failed.append(node_id)
        return failed

    def get_status(self):
        return self.heartbeats

# -----------------------------------------------------------
# Funções para iniciar os servidores (multithreaded)
# -----------------------------------------------------------
def run_monitor(port):
    monitor = Monitor()
    server = ThreadedXMLRPCServer(("localhost", port), allow_none=True, logRequests=False)
    server.register_instance(monitor)
    print(f"Monit: Rodando na porta {port}...")
    server.serve_forever()

def run_node(node_id, port, peers, monitor_url):
    node = Node(node_id, port, peers, monitor_url)
    server = ThreadedXMLRPCServer(("localhost", port), allow_none=True, logRequests=False)
    server.register_instance(node)
    print(f"node {node_id} rodando na porta {port}...")
    server.serve_forever()

# -----------------------------------------------------------
# Cliente (Simulação) - testes com erros forçados
# -----------------------------------------------------------
def client_simulation(nodes_info, monitor_port):
    # Cria proxies normais
    proxies = {node_id: xmlrpc.client.ServerProxy(f"http://{info[0]}:{info[1]}") 
               for node_id, info in nodes_info.items()}
    monitor = xmlrpc.client.ServerProxy(f"http://localhost:{monitor_port}")

    time.sleep(3)

    # --- Parte 1: Lamport ---
    print("\n== Lamport: Eventos ==")
    try:
        proxies[1].local_event("Evento nulo no node 1")
        time.sleep(1)
        # Força erro: envia menssagem para node inexistente (ID 4)
        proxies[1].send_message(4, "Msg errada")
    except Exception as e:
        print("Erro Lamport:", e)
    time.sleep(1)
    try:
        proxies[2].local_event("Evento normal no node 2")
        time.sleep(1)
        proxies[2].send_message(3, "Msg normal do node 2")
    except Exception as e:
        print("Erro Lamport:", e)
    time.sleep(1)

    # --- Parte 2: Snapshot ---
    print("\n== Snapshot: Inicia ==")
    try:
        proxies[1].initiate_snapshot()
        time.sleep(3)
        # Força erro: envia app msg para node inexistente (ID 0)
        proxies[2].send_app_message(0, 10)
    except Exception as e:
        print("Erro Snapshot:", e)
    time.sleep(1)
    try:
        proxies[3].send_app_message(2, -5)
    except Exception as e:
        print("Erro Snapshot:", e)
    time.sleep(1)
    
    # --- Parte 3: Bully ---
    print("\n== Bully: Eleiçã ==")
    try:
        # Para eleição natural, simulamos que o node 3 falha naturalmente
        print("Simulando falha natural: node 3 cai...")
        # Alteramos o proxy do node 3 para um endereço inválido (simula queda)
        proxies[3] = xmlrpc.client.ServerProxy("http://localhost:9999")
        result = proxies[1].start_election()
        print("Resultado eleição:", result)
    except Exception as e:
        print("Erro Bully:", e)
    time.sleep(1)

    # --- Parte 4: Heartbeat ---
    print("\n== Monit: HB ==")
    try:
        time.sleep(6)
        failed = monitor.check_failures()
        if failed:
            print("Monit: Falha detectada nos nodes:", failed)
        else:
            print("Monit: Todos os nodes ativos.")
    except Exception as e:
        print("Erro Monit HB:", e)
    time.sleep(1)

    # Coleta dos snapshots
    print("\n== Snapshot: Coleta ==")
    for node_id, proxy in proxies.items():
        try:
            snap = proxy.get_snapshot()
            print(f"node {node_id} snap:", snap)
        except Exception as e:
            print(f"Erro na coleta snap - node {node_id}:", e)

# -----------------------------------------------------------
# Bloco Principal
# -----------------------------------------------------------
if __name__ == '__main__':
    nodes_info = {
        1: ("localhost", 8001),
        2: ("localhost", 8002),
        3: ("localhost", 8003)
    }
    monitor_port = 8004

    peers_for_node = {node_id: {nid: info for nid, info in nodes_info.items() if nid != node_id}
                      for node_id in nodes_info}

    monitor_process = multiprocessing.Process(target=run_monitor, args=(monitor_port,))
    monitor_process.start()

    processes = []
    for node_id, (host, port) in nodes_info.items():
        p = multiprocessing.Process(target=run_node, args=(node_id, port, peers_for_node[node_id], f"http://localhost:{monitor_port}"))
        p.start()
        processes.append(p)

    client_simulation(nodes_info, monitor_port)

    time.sleep(5)
    for p in processes:
        p.terminate()
    monitor_process.terminate()
    for p in processes:
        p.join()
    monitor_process.join()
