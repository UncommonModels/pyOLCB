#!/bin/sh
ip link add dev vcan0 type vcan
ip link set vcan0 mtu 16
ip link set up vcan0
ifconfig vcan0