import socket
import threading
import time
import pyolcb

TEST_ADDRESS = '05.01.01.01.8C.00'
TEST_OTHER_ADDRESS = '05.01.01.01.8C.01'
TEST_PORT = 12021


def test_gridconnect_encoding():
    """
    Test GridConnect format encoding.
    """
    # Test encoding a message to GridConnect format
    arbitration_id = 0x195B4123
    data = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])
    
    result = pyolcb.utilities.to_gridconnect(arbitration_id, data, is_extended=True)
    expected = ':X195B4123N0102030405060708;'
    assert result == expected, f"Expected {expected}, got {result}"


def test_gridconnect_decoding():
    """
    Test GridConnect format decoding.
    """
    frame = ':X195B4123N0102030405060708;'
    result = pyolcb.utilities.from_gridconnect(frame)
    
    assert result is not None, "Failed to parse GridConnect frame"
    arbitration_id, data, is_extended = result
    
    assert arbitration_id == 0x195B4123, f"Expected ID 0x195B4123, got {hex(arbitration_id)}"
    assert data == bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])
    assert is_extended == True


def test_gridconnect_empty_data():
    """
    Test GridConnect format with empty data.
    """
    arbitration_id = 0x19100123
    data = bytes()
    
    result = pyolcb.utilities.to_gridconnect(arbitration_id, data, is_extended=True)
    expected = ':X19100123N;'
    assert result == expected


def test_gridconnect_roundtrip():
    """
    Test encoding and decoding roundtrip.
    """
    # Test multiple frames
    test_cases = [
        (0x19100123, bytes([0x05, 0x01, 0x01, 0x01, 0x8C, 0x00])),
        (0x195B4123, bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])),
        (0x19490123, bytes()),
    ]
    
    for arb_id, data in test_cases:
        encoded = pyolcb.utilities.to_gridconnect(arb_id, data, is_extended=True)
        decoded = pyolcb.utilities.from_gridconnect(encoded)
        
        assert decoded is not None, f"Failed to decode {encoded}"
        dec_id, dec_data, dec_ext = decoded
        
        assert dec_id == arb_id, f"ID mismatch: {hex(arb_id)} != {hex(dec_id)}"
        assert dec_data == data, f"Data mismatch: {data.hex()} != {dec_data.hex()}"
        assert dec_ext == True


def test_message_to_gridconnect():
    """
    Test Message to GridConnect conversion.
    """
    address = pyolcb.Address(TEST_ADDRESS)
    address.set_alias(0x123)  # Set an alias
    message = pyolcb.Message(
        pyolcb.message_types.Initialization_Complete,
        pyolcb.utilities.process_bytes(6, TEST_ADDRESS),
        address
    )
    
    gridconnect = message.to_gridconnect()
    
    # Should start with : and end with ;
    assert gridconnect.startswith(':')
    assert gridconnect.endswith(';')
    assert 'X' in gridconnect  # Extended frame
    assert 'N' in gridconnect  # Data separator


def test_message_from_gridconnect():
    """
    Test creating Message from GridConnect string.
    """
    # Initialization Complete message
    frame = ':X19100123N050101018C00;'
    message = pyolcb.Message.from_gridconnect(frame)
    
    assert message is not None, "Failed to create message from GridConnect"
    assert message.message_type == pyolcb.message_types.Initialization_Complete
    assert message.source is not None
    assert message.source.get_alias() == 0x123


def test_tcp_interface_creation():
    """
    Test creating a TCP Interface.
    """
    # Create a socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # Create interface
    interface = pyolcb.Interface(sock)
    
    assert interface.phy == pyolcb.interface.InterfaceType.TCP
    assert interface.connection == sock
    
    sock.close()


def test_tcp_send_receive():
    """
    Test sending and receiving messages over TCP.
    """
    received_messages = []
    
    def message_handler(message):
        received_messages.append(message)
    
    # Create server socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('127.0.0.1', TEST_PORT))
    server_socket.listen(1)
    
    # Server thread to accept connection
    client_sock = None
    def server_thread():
        nonlocal client_sock
        client_sock, _ = server_socket.accept()
    
    server_t = threading.Thread(target=server_thread)
    server_t.start()
    
    # Create client socket and connect
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(('127.0.0.1', TEST_PORT))
    
    # Wait for server to accept
    server_t.join(timeout=2)
    
    # Create interfaces
    client_interface = pyolcb.Interface(client_socket)
    server_interface = pyolcb.Interface(client_sock)
    
    # Register listener on server side
    server_interface.register_listener(message_handler)
    
    # Create and send a message from client
    address = pyolcb.Address(TEST_ADDRESS)
    address.set_alias(0x123)  # Set an alias
    message = pyolcb.Message(
        pyolcb.message_types.Initialization_Complete,
        pyolcb.utilities.process_bytes(6, TEST_ADDRESS),
        address
    )
    
    client_interface.send(message)
    
    # Wait for message to be received
    time.sleep(0.5)
    
    # Verify message was received
    assert len(received_messages) > 0, "No messages received"
    received = received_messages[0]
    assert received.message_type == pyolcb.message_types.Initialization_Complete
    
    # Clean up
    server_interface.stop_listener()
    client_socket.close()
    client_sock.close()
    server_socket.close()


def test_tcp_node_initialization():
    """
    Test Node initialization with TCP interface.
    """
    received_messages = []
    
    def message_handler(message):
        received_messages.append(message)
    
    # Create server socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('127.0.0.1', TEST_PORT + 1))
    server_socket.listen(1)
    
    # Server thread
    client_sock = None
    def server_thread():
        nonlocal client_sock
        client_sock, _ = server_socket.accept()
    
    server_t = threading.Thread(target=server_thread)
    server_t.start()
    
    # Create client socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(('127.0.0.1', TEST_PORT + 1))
    
    server_t.join(timeout=2)
    
    # Create server interface with listener
    server_interface = pyolcb.Interface(client_sock)
    server_interface.register_listener(message_handler)
    
    # Create node with TCP interface
    client_interface = pyolcb.Interface(client_socket)
    address = pyolcb.Address(TEST_ADDRESS)
    node = pyolcb.Node(address, client_interface)
    
    # Wait for initialization message
    time.sleep(0.5)
    
    # Verify initialization message was sent
    assert len(received_messages) > 0, "No initialization message received"
    init_msg = received_messages[0]
    assert init_msg.message_type == pyolcb.message_types.Initialization_Complete
    
    # Clean up
    server_interface.stop_listener()
    client_socket.close()
    client_sock.close()
    server_socket.close()


if __name__ == '__main__':
    # Run tests
    test_gridconnect_encoding()
    test_gridconnect_decoding()
    test_gridconnect_empty_data()
    test_gridconnect_roundtrip()
    test_message_to_gridconnect()
    test_message_from_gridconnect()
    test_tcp_interface_creation()
    test_tcp_send_receive()
    test_tcp_node_initialization()
    print("All TCP tests passed!")
