import xmlrpc.server
import xmlrpc.client
import multiprocessing
import time

# Classe do nó
class Node:
    # Inicialização das variáveis
    def __init__(self, node_id, port, peers):
        self.node_id = node_id      
        self.port = port            
        self.peers = peers          
        self.lamport_clock = 0


    def local_event(self, description):
        self.lamport_clock += 1
        log_msg = f"Node id:{self.node_id} \n Descrição: '{description}' - Clock: {self.lamport_clock} \n"
        print(log_msg)
        return self.lamport_clock

    def send_message(self, target_node_id, message):
        self.lamport_clock += 1
        timestamp = self.lamport_clock
        log_msg = f"Node remetente: {self.node_id} \n Node de destino: {target_node_id} \n (timestamp {timestamp}) - Mensagem: {message}\n"
        print(log_msg)
        
        target_info = self.peers.get(target_node_id)
        if target_info is None:
            print(f"Node {self.node_id}: Peer {target_node_id} não existe.")
            return -1
        
        url = f"http://{target_info[0]}:{target_info[1]}"
        try:
            # Proxy serve para chamar métodos remotos
            proxy = xmlrpc.client.ServerProxy(url)
            
            # Usa o método remoto para enviar a mensagem
            new_clock = proxy.receive_message(timestamp, message, self.node_id)
            
            self.lamport_clock = max(self.lamport_clock, new_clock)
            return new_clock
        except Exception as e:
            print(f"Node {self.node_id}: Erro ao enviar mensagem para Node {target_node_id}: {e}")
            return self.lamport_clock

    def receive_message(self, incoming_timestamp, message, sender_node_id):
        self.lamport_clock = max(self.lamport_clock, incoming_timestamp) + 1
        log_msg = (f"Node {self.node_id} recebeu a mensagem do Node {sender_node_id}\n"
                   f"(timestamp recebido: {incoming_timestamp}).\n"
                   f"Clock atualizado para {self.lamport_clock}. Mensagem: {message} \n")
        print(log_msg)
        return self.lamport_clock

def run_node(node_id, port, peers):
    
    node = Node(node_id, port, peers)

    # Cria um servidor XML-RPC para o nó e registra a instância do nó nele 
    # logRequests=False pra não poluir o terminal
    server = xmlrpc.server.SimpleXMLRPCServer(("localhost", port), allow_none=True, logRequests=False)
    
    # Registra a instância do nó no servidor XML-RPC para que possa ser chamada remotamente 
    server.register_instance(node)
    print(f"rodando o node {node_id} na porta {port}")
    
    # Inicia o servidor em loop
    server.serve_forever()

def client_simulation(peers):
    
    time.sleep(2) # Espera um pouco pra garantir que os nós estão funcionando

    # Cria proxies pra cada nó
    proxies = {}
    for node_id, info in peers.items():
        # Desempacota o host e a porta
        host, port = info
        # Cria a URL pro servidor 
        url = f"http://localhost:{port}"
        # Roda um servidor proxy pra cada nó
        proxies[node_id] = xmlrpc.client.ServerProxy(url)


    proxies[1].local_event("teste")
    time.sleep(1)

   
    proxies[1].send_message(2, "node 1 para node 2")
    time.sleep(1)

    
    proxies[2].local_event("evento local do node 2")
    time.sleep(1)

    
    proxies[2].send_message(3, "node 2 pro node 3")
    time.sleep(1)

    
    proxies[3].send_message(1, "node 3 para node 1")
    time.sleep(1)

    
    proxies[1].local_event("parando o node 1")
    proxies[2].local_event("parando o node 2")
    proxies[3].local_event("parando o node 3")
    time.sleep(1)

if __name__ == '__main__':
    
    nodes_info = {
        1: ("localhost", 8001),
        2: ("localhost", 8002),
        3: ("localhost", 8003)
    }
    
    def obter_peers(nodes_info, node_id):
        # Retorna um dicionário com os peers de um nó específico (node_id) 
        return {outro_id: info for outro_id, info in nodes_info.items() if outro_id != node_id}

    # Para cada nó, define os peers usando a função auxiliar
    peers_for_node = {node_id: obter_peers(nodes_info, node_id) for node_id in nodes_info}


    # Cria um processo para cada nó
    processes = []
    for node_id, (host, port) in nodes_info.items():
        p = multiprocessing.Process(target=run_node, args=(node_id, port, peers_for_node[node_id]))
        p.start()
        processes.append(p)

    # Inicia uma simulação de cliente
    client_simulation(nodes_info)

    # Aguarda um tempo para visualização e encerra os processos
    time.sleep(2)
    for p in processes:
        p.terminate()
    for p in processes:
        p.join()
