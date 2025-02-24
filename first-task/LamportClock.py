class Node:
    def __init__(self, node_id):
        self.node_id = node_id
        self.clock = 0

    def local_event(self, description):
        """Simula um evento local no nó, incrementando o clock."""
        self.clock += 1
        print(f"Node {self.node_id} - Evento local: {description} | Clock: {self.clock}")

    def send_message(self, target, message):
        """Envia uma mensagem para outro nó. Incrementa o clock e inclui o timestamp."""
        self.clock += 1
        timestamp = self.clock
        print(f"Node {self.node_id} - Enviando mensagem para Node {target.node_id}: '{message}' | Timestamp: {timestamp}")
        target.receive_message(self, message, timestamp)

    def receive_message(self, sender, message, sender_timestamp):
        """
        Ao receber uma mensagem, atualiza o clock:
        clock = max(clock atual, timestamp recebido) + 1
        """
        self.clock = max(self.clock, sender_timestamp) + 1
        print(f"Node {self.node_id} - Recebeu mensagem de Node {sender.node_id}: '{message}' | Timestamp do remetente: {sender_timestamp} | Clock atualizado: {self.clock}")


def main():
    # Cria três nós
    node1 = Node(1)
    node2 = Node(2)
    node3 = Node(3)

    # Simulação de eventos:
    # Nó 1 realiza um evento local e envia uma mensagem para Nó 2
    node1.local_event("Início do processo")
    node1.send_message(node2, "Olá do Node 1")
    
    # Nó 2 realiza um evento local e, depois, envia uma mensagem para Nó 3
    node2.local_event("Processando dados")
    node2.send_message(node3, "Dados processados")
    
    # Nó 3 realiza um evento local e envia uma mensagem para Nó 1
    node3.local_event("Finalizando")
    node3.send_message(node1, "Confirmação do Node 3")


if __name__ == "__main__":
    main()
