#!/usr/bin/env python3
"""
Example: OpenLCB Node over TCP/IP using GridConnect format

This example demonstrates how to create an OpenLCB node that communicates
over TCP/IP using the GridConnect ASCII protocol. This is useful for
connecting to OpenLCB hubs, simulators, or other TCP-based tools.

To run this example, you'll need:
1. An OpenLCB hub or simulator listening on TCP port 12021
2. Or you can test with two instances of this script (one as server, one as client)
"""

import socket
import pyolcb
import time
import threading


def simple_tcp_client_example():
    """
    Simple example of connecting to an OpenLCB hub over TCP/IP
    """
    print("=== Simple TCP Client Example ===")

    # Connect to an OpenLCB hub
    # Replace 'localhost' and 12021 with your hub's address and port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(('localhost', 12021))
        print("Connected to OpenLCB hub at localhost:12021")
    except ConnectionRefusedError:
        print("Could not connect to hub at localhost:12021")
        print("Make sure an OpenLCB hub is running on that port")
        sock.close()
        return

    # Create an interface
    interface = pyolcb.Interface(sock)

    # Create a node with a unique address
    address = pyolcb.Address('05.01.01.01.8C.00')
    node = pyolcb.Node(address, interface)

    print(f"Created node with address: {address}")

    # Produce an event
    print("Producing event 125...")
    node.produce(pyolcb.Event(125, address))

    # Give some time for the message to be sent
    time.sleep(0.5)

    # Clean up
    sock.close()
    print("Disconnected from hub")


def tcp_listener_example():
    """
    Example of setting up a listener for incoming messages
    """
    print("\n=== TCP Listener Example ===")

    def message_handler(message):
        """Called when a message is received"""
        print(f"Received message: MTI={hex(message.message_type.value)}, "
              f"Source={message.source.get_alias() if message.source else 'unknown'}")
        if message.data:
            print(f"  Data: {message.data.hex()}")

    # Connect to hub
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(('localhost', 12021))
        print("Connected to OpenLCB hub at localhost:12021")
    except ConnectionRefusedError:
        print("Could not connect to hub at localhost:12021")
        sock.close()
        return

    # Create interface
    interface = pyolcb.Interface(sock)

    # Register the listener
    interface.register_listener(message_handler)

    # Create a node
    address = pyolcb.Address('05.01.01.01.8C.01')
    node = pyolcb.Node(address, interface)

    print(f"Created node with address: {address}")
    print("Listening for messages for 5 seconds...")

    # Listen for a while
    time.sleep(5)

    # Clean up
    interface.stop_listener()
    sock.close()
    print("Stopped listening and disconnected")


def peer_to_peer_example():
    """
    Example of two nodes communicating directly over TCP
    """
    print("\n=== Peer-to-Peer Example ===")

    received_events = []
    event_received = threading.Event()

    def event_consumer(message):
        """Called when an event is received"""
        print(f"Node 2 received event!")
        received_events.append(message)
        event_received.set()

    # Create a simple server socket
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(('127.0.0.1', 12022))
    server_sock.listen(1)

    print("Server listening on 127.0.0.1:12022")

    # Accept connection in a thread
    client_sock = None

    def accept_connection():
        nonlocal client_sock
        client_sock, addr = server_sock.accept()
        print(f"Accepted connection from {addr}")

    accept_thread = threading.Thread(target=accept_connection)
    accept_thread.start()

    # Connect from client
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(('127.0.0.1', 12022))
    print("Client connected to server")

    # Wait for accept to complete
    accept_thread.join(timeout=2)

    # Create interfaces
    client_interface = pyolcb.Interface(client_socket)
    server_interface = pyolcb.Interface(client_sock)

    # Create nodes
    node1_address = pyolcb.Address('05.01.01.01.8C.10')
    node1 = pyolcb.Node(node1_address, client_interface)
    print(f"Node 1 created with address: {node1_address}")

    node2_address = pyolcb.Address('05.01.01.01.8C.20')
    node2 = pyolcb.Node(node2_address, server_interface)
    print(f"Node 2 created with address: {node2_address}")

    # Register event consumer on node 2
    event = pyolcb.Event(100, node1_address)
    node2.add_consumer(event, event_consumer)
    print(f"Node 2 registered consumer for event {event.id.hex()}")

    # Produce event from node 1
    print("Node 1 producing event 100...")
    node1.produce(100)

    # Wait for event to be received
    if event_received.wait(timeout=2.0):
        print("Event successfully received by Node 2!")
    else:
        print("Event not received within timeout")

    # Clean up
    server_interface.stop_listener()
    client_interface.stop_listener()
    client_socket.close()
    client_sock.close()
    server_sock.close()
    print("Peer-to-peer communication complete")


def gridconnect_format_example():
    """
    Example showing the GridConnect ASCII format
    """
    print("\n=== GridConnect Format Example ===")

    # Create a message
    address = pyolcb.Address('05.01.01.01.8C.00')
    address.set_alias(0x123)

    message = pyolcb.Message(
        pyolcb.message_types.Initialization_Complete,
        pyolcb.utilities.process_bytes(6, '05.01.01.01.8C.00'),
        address
    )

    # Convert to GridConnect format
    gridconnect = message.to_gridconnect()
    print(f"Message in GridConnect format: {gridconnect}")

    # Parse it back
    parsed = pyolcb.Message.from_gridconnect(gridconnect)
    print(f"Parsed message type: {hex(parsed.message_type.value)}")
    print(f"Parsed source alias: {hex(parsed.source.get_alias())}")
    print(f"Parsed data: {parsed.data.hex()}")

    # Show the format breakdown
    print("\nGridConnect format breakdown:")
    print("  : - Start delimiter")
    print("  X - Extended frame")
    print("  19100123 - CAN arbitration ID (hex)")
    print("  N - Data separator")
    print("  050101018C00 - Message data (hex)")
    print("  ; - End delimiter")


if __name__ == '__main__':
    print("OpenLCB over TCP/IP Examples\n")

    # Show GridConnect format
    gridconnect_format_example()

    # Try peer-to-peer (always works)
    peer_to_peer_example()

    # These require an external hub
    print("\n" + "="*60)
    print("The following examples require an OpenLCB hub at localhost:12021")
    print("You can skip them if you don't have a hub running")
    print("="*60)

    response = input("\nRun hub-dependent examples? (y/n): ")
    if response.lower() == 'y':
        simple_tcp_client_example()
        tcp_listener_example()
    else:
        print("Skipping hub-dependent examples")

    print("\nExamples complete!")
