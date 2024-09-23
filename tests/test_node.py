import can
import pyolcb

TEST_ADDRESS = '05.01.01.01.8C.00'
TEST_OTHER_ADDRESS = '05.01.01.01.8C.01'
GLOBAL_ADDRESS = '00.00.00.00.00.00'
BUS = can.Bus(interface='socketcan', channel='vcan0', bitrate=125000, receive_own_messages=True)
NODE = pyolcb.Node(pyolcb.Address(TEST_ADDRESS), pyolcb.Interface(BUS))

def test_initialize_node():
    msg = BUS.recv()
    assert msg.data == bytearray(
        pyolcb.utilities.process_bytes(6, TEST_ADDRESS))
    print(hex(msg.arbitration_id))
    assert msg.arbitration_id == pyolcb.message_types.Initialization_Complete.get_can_header(NODE.address)

def test_produce_event():
    NODE.produce(1)
    msg = BUS.recv()
    assert msg.data == bytearray(
        pyolcb.utilities.process_bytes(8, TEST_ADDRESS+'.00.01'))
    assert msg.arbitration_id == pyolcb.message_types.Producer_Consumer_Event_Report.get_can_header(NODE.address)

def test_verify_node_id_global():
    NODE.verify_node_id()
    msg = BUS.recv()
    assert msg.data == bytearray(
        pyolcb.utilities.process_bytes(6, NODE.address.full))
    assert msg.arbitration_id == pyolcb.message_types.Verify_Node_ID_Number_Global.get_can_header(NODE.address)

def test_verify_node_id_addressed():
    test_addr = pyolcb.Address(TEST_OTHER_ADDRESS)
    test_addr.set_alias(TEST_OTHER_ADDRESS[-4:])
    NODE.verify_node_id(test_addr)
    msg = BUS.recv()
    assert msg.data == bytearray(
        pyolcb.utilities.process_bytes(2, TEST_OTHER_ADDRESS[-4:]))
    assert msg.arbitration_id == pyolcb.message_types.Verify_Node_ID_Number_Addressed.get_can_header(NODE.address)


        
