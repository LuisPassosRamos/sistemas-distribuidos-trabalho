import time
import xmlrpc.client
import pytest
from unittest.mock import MagicMock, patch

# Supondo que o código principal esteja no arquivo "distributed.py"
# Ajuste o nome do módulo conforme necessário.
from distributed import Node

# --------------------------
# Testes para Lamport Clock
# --------------------------
def test_local_event():
    peers = {2: ("localhost", 8002)}
    node = Node(1, 8001, peers, "http://dummy:8004")
    initial_clock = node.lamport_clock
    returned = node.local_event("Evento teste")
    assert returned == initial_clock + 1
    assert node.lamport_clock == initial_clock + 1

@patch("xmlrpc.client.ServerProxy")
def test_send_message_success(mock_server_proxy):
    dummy_proxy = MagicMock()
    dummy_proxy.receive_message.return_value = 5  # Simula resposta com clock 5
    mock_server_proxy.return_value = dummy_proxy

    peers = {2: ("localhost", 8002)}
    node = Node(1, 8001, peers, "http://dummy:8004")
    node.lamport_clock = 3
    node.send_message(2, "Olá")
    # Envio incrementa para 4 e, após o retorno, o clock fica max(4, 5)+1 = 6
    assert node.lamport_clock == 6
    dummy_proxy.receive_message.assert_called_once_with(4, "Olá", 1)

@patch("xmlrpc.client.ServerProxy")
def test_send_message_failure(mock_server_proxy):
    dummy_proxy = MagicMock()
    dummy_proxy.receive_message.side_effect = Exception("Erro de conexão")
    mock_server_proxy.return_value = dummy_proxy

    peers = {2: ("localhost", 8002)}
    node = Node(1, 8001, peers, "http://dummy:8004")
    node.lamport_clock = 2
    node.send_message(2, "Teste")
    # Mesmo que a chamada falhe, o clock já foi incrementado para 3.
    assert node.lamport_clock == 3
    dummy_proxy.receive_message.assert_called_once()

# --------------------------
# Testes para Snapshot
# --------------------------
def test_initiate_snapshot(monkeypatch):
    dummy_proxy = MagicMock()
    dummy_proxy.receive_marker.return_value = None
    def fake_server_proxy(url):
        return dummy_proxy
    monkeypatch.setattr(xmlrpc.client, "ServerProxy", fake_server_proxy)

    peers = {2: ("localhost", 8002), 3: ("localhost", 8003)}
    node = Node(1, 8001, peers, "http://dummy:8004")
    result = node.initiate_snapshot()
    assert result == "Snap iniciado"
    assert node.snapshot_initiated is True
    # Verifica se receive_marker foi chamado para cada peer
    assert dummy_proxy.receive_marker.call_count == len(peers)

# --------------------------
# Testes para Bully (Eleição)
# --------------------------
@patch("xmlrpc.client.ServerProxy")
def test_start_election_no_response(mock_server_proxy):
    dummy_proxy = MagicMock()
    dummy_proxy.receive_election.side_effect = Exception("No resp")
    mock_server_proxy.return_value = dummy_proxy

    peers = {2: ("localhost", 8002), 3: ("localhost", 8003)}
    node = Node(1, 8001, peers, "http://dummy:8004")
    result = node.start_election()
    # Sem resposta, Node 1 se torna coordenador.
    assert "Coord é node 1" in result
    assert node.coordinator == 1

@patch("xmlrpc.client.ServerProxy")
def test_start_election_with_response(mock_server_proxy):
    dummy_proxy = MagicMock()
    dummy_proxy.receive_election.return_value = "OK"
    mock_server_proxy.return_value = dummy_proxy

    peers = {2: ("localhost", 8002), 3: ("localhost", 8003)}
    node = Node(1, 8001, peers, "http://dummy:8004")
    result = node.start_election()
    # Se algum nó maior responde, a string deve conter "Coord é node"
    assert "Coord é node" in result

def test_receive_election_calls_start_election(monkeypatch):
    peers = {2: ("localhost", 8002)}
    node = Node(1, 8001, peers, "http://dummy:8004")
    started = False
    def fake_start_election():
        nonlocal started
        started = True
        return "Fake election"
    monkeypatch.setattr(node, "start_election", fake_start_election)
    response = node.receive_election(2)
    time.sleep(0.1)  # Dá tempo para a thread disparada iniciar
    assert started is True
    assert response == "OK"

# --------------------------
# Testes para Heartbeat
# --------------------------
def test_heartbeat_loop(monkeypatch):
    called = 0
    def fake_send_heartbeat():
        nonlocal called
        called += 1
    # Aplica o fake no método send_heartbeat da classe Node antes de criar uma instância
    monkeypatch.setattr(Node, "send_heartbeat", fake_send_heartbeat)
    peers = {}
    node = Node(1, 8001, peers, "http://dummy:8004")
    # Aguarda 5 segundos para que a thread (iniciada no __init__) execute o fake_send_heartbeat
    time.sleep(5)
    assert called >= 2
