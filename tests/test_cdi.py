import pytest

from pyolcb import cdi

HOST_NODE_CDI = (
    "<?xml version='1.0'?><cdi>"
    "<identification><manufacturer>AOLCB</manufacturer><model>Host test node</model>"
    "<hardwareVersion>PC</hardwareVersion><softwareVersion>0.2.0</softwareVersion></identification>"
    "<acdi/>"
    "<segment space='251' origin='1'><name>Node</name>"
    "<string size='63'><name>Name</name></string>"
    "<string size='64'><name>Description</name></string>"
    "</segment>"
    "<segment space='253' origin='128'><name>Settings</name>"
    "<int size='1'><name>Mode</name><map>"
    "<relation><property>0</property><value>Off</value></relation>"
    "<relation><property>1</property><value>On</value></relation>"
    "</map></int>"
    "<eventid><name>Trigger</name></eventid>"
    "</segment></cdi>\x00garbage")


def test_host_node_layout():
    layout = cdi.parse(HOST_NODE_CDI)
    assert layout.identification["model"] == "Host test node"
    assert layout.acdi
    fields = layout.fields()
    assert [(f.space, f.address, f.size, f.kind) for f in fields] == [
        (251, 1, 63, "string"), (251, 64, 64, "string"), (253, 128, 1, "int"), (253, 129, 8, "eventid")]
    mode = fields[2]
    assert mode.map == [("0", "Off"), ("1", "On")]
    assert mode.path == ["Settings", "Mode"]
    assert layout.ranges() == [(251, 1, 127), (253, 128, 9)]


REPLICATED = """<?xml version="1.0"?>
<cdi xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
 <segment space="253" origin="10">
  <int size="2" offset="2"><name>Speed</name><min>1</min><max>500</max><default>100</default></int>
  <group replication="3" offset="4">
   <name>Channels</name><repname>Channel</repname>
   <int size="1"><name>Mode</name></int>
   <group><name>Events</name>
     <eventid><name>On</name></eventid>
     <eventid offset="-8"><name>Alias of On</name></eventid>
     <eventid><name>Off</name></eventid>
   </group>
   <string size="4"><name>Label</name></string>
  </group>
  <float><name>Gain</name></float>
  <float size="2"><name>Half</name></float>
  <action size="1"><name>Reboot</name><buttonText>Go</buttonText><value>5</value></action>
 </segment>
</cdi>"""


def test_offsets_and_replication():
    layout = cdi.parse(REPLICATED)
    fields = {"/".join(f.path): f for f in layout.fields()}
    assert fields["Speed"].address == 12
    assert fields["Speed"].minimum == 1 and fields["Speed"].maximum == 500
    # Group starts after Speed (14) plus offset 4. Each replica is
    # Mode(1) + On(8) + Alias(-8+8) + Off(8) + Label(4) = 21 bytes.
    assert fields["Channels/Channel 1/Mode"].address == 18
    assert fields["Channels/Channel 1/Events/On"].address == 19
    assert fields["Channels/Channel 1/Events/Alias of On"].address == 19
    assert fields["Channels/Channel 1/Events/Off"].address == 27
    assert fields["Channels/Channel 1/Label"].address == 35
    assert fields["Channels/Channel 2/Mode"].address == 39
    assert fields["Channels/Channel 3/Label"].address == 35 + 42
    assert fields["Gain"].address == 18 + 63 and fields["Gain"].size == 4
    assert fields["Half"].size == 2
    assert fields["Reboot"].kind == "action" and fields["Reboot"].value == 5
    tree = layout.to_dict()
    replicated = tree["segments"][0]["children"][1]
    assert replicated["type"] == "replicated"
    assert [r["label"] for r in replicated["replicas"]] == ["Channel 1", "Channel 2", "Channel 3"]


def test_multiple_repnames():
    xml = ("<cdi><segment space='253'><group replication='3'><repname>Left</repname>"
           "<repname>Right</repname><repname>Spare</repname><int><name>v</name></int></group>"
           "</segment></cdi>")
    labels = [f.path[0] for f in cdi.parse(xml).fields()]
    assert labels == ["Left", "Right", "Spare"]


def test_value_codec():
    layout = cdi.parse(REPLICATED)
    fields = {"/".join(f.path): f for f in layout.fields()}
    speed = fields["Speed"]
    assert speed.encode(300) == b"\x01\x2c"
    assert speed.decode(b"\x01\x2c") == 300
    with pytest.raises(ValueError):
        speed.encode(501)
    label = fields["Channels/Channel 1/Label"]
    assert label.encode("abcdef") == b"abc\x00"
    assert label.decode(b"ab\x00z") == "ab"
    on = fields["Channels/Channel 1/Events/On"]
    assert on.encode("02.01.57.00.00.99.00.01") == bytes.fromhex("0201570000990001")
    assert on.decode(bytes.fromhex("0201570000990001")) == "02.01.57.00.00.99.00.01"
    gain = fields["Gain"]
    assert gain.decode(gain.encode(1.5)) == 1.5
    assert fields["Half"].decode(fields["Half"].encode(0.25)) == 0.25


def test_malformed():
    with pytest.raises(ValueError):
        cdi.parse("<cdi><segment space='253'>")
    with pytest.raises(ValueError):
        cdi.parse("<notcdi/>")
    with pytest.raises(ValueError):
        cdi.parse("<cdi><segment space='253'><int size='3'/></segment></cdi>")
    with pytest.raises(ValueError):
        cdi.parse("<cdi><segment space='253'><string/></segment></cdi>")
