#!/usr/bin/python
import sys
from mininet.net import Mininet
from mininet.node import Controller, RemoteController
from mininet.node import CPULimitedHost, Host, Node
from mininet.node import OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink
from mininet.util import run

import time
import xmlrpclib
import json

#
# This will create two switches with one inter-link
# It takes input argument as the number of host ports for each sw
# the topology will look like
#
#           ____                           ____
#          |    |(2)-----1Mb,10ms------(2)|    |
# h1----(1)| s1 |(3)----10Mb,10ms------(3)| s2 |(1)-----h2
#          |____|(4)----20Mb,10ms------(4)|____|
#            (5)                            (5)
#             |             ____             |
#             |            |    |            |
#              \--------(1)| s3 |(2)--------/
#                          |____|
#                 
def myNetwork():
    
    rfserver_ip = '192.168.56.101'
    # Initialize RPC connection to RFServer.
    #
    info("Connect to RFServer...\n")
    rfserver = xmlrpclib.ServerProxy('http://' + '192.168.56.101' +':8008', 
                                     allow_none=True)
    
    info("Prepare network configuration for the tests...\n")
    net = Mininet(topo=None, build=False, link=TCLink, switch=OVSSwitch)
    info('---------- Add controller ----------\n')
    c0 = net.addController(name='c0', controller=RemoteController, 
                           ip=rfserver_ip, port=6633)
    
    info('---------- Add switches\n ----------')
    s1 = net.addSwitch(name='s1', protocols='OpenFlow13')
    s2 = net.addSwitch(name='s2', protocols='OpenFlow13')
    s3 = net.addSwitch(name='s3', protocols='OpenFlow13')
    
    info('*** Add hosts\n')
    h1 = net.addHost(name="h1", cls=Host, ip='172.16.1.2/24', defaultRoute='via 172.16.1.1')
    h2 = net.addHost(name="h2", cls=Host, ip='172.16.2.2/24', defaultRoute='via 172.16.2.1')
    
    info("---------- Add links ----------\n")
    net.addLink(h1, s1)
    net.addLink(h2, s2)
    
    net.addLink(s1, s2, bw=1, delay='10ms')
    net.addLink(s1, s2, bw=10, delay='10ms')
    net.addLink(s1, s2, bw=20, delay='10ms')
    net.addLink(s1, s3)
    net.addLink(s2, s3)
    
    info('---------- Start network ----------\n')
    net.build()    
    net.start()
    run("ovs-vsctl set bridge s1 protocols=OpenFlow13")
    run("ovs-vsctl set bridge s2 protocols=OpenFlow13")
    run("ovs-vsctl set bridge s3 protocols=OpenFlow13")
    
    info('\n\n')
    info('Start the first test: Two ISL linked witches are mapped to rfvmA\n')
    first_test(rfserver, net)
    info('\n\n')
    info('Start the first test: Two ISL linked witches are mapped to rfvmB\n')
    second_test(rfserver, net)
    info('\n\n')
    info('Start the first test: Two ISL linked witches are mapped to rfvmC\n')
    third_test(rfserver, net)
    try:
        while True:
            pass
    except KeyboardInterrupt:
        pass
    #CLI(net)
    net.stop()

def first_test(rfserver, net):
    info('Test in progress....\n')
    info('Two switches with an ISL link are mapped to rfvmA\n')
    config = [{'vm_id': '2a0a0a0a0a0', 'vm_port': 1, 'dp_id': '1', 'dp_port': 1},
              {'vm_id': '2a0a0a0a0a0', 'vm_port': 2, 'dp_id': '2', 'dp_port': 1}]
    
    for entry in config:
        rfserver.add_map_config(entry['vm_id'], entry['vm_port'], 
                                0, entry['dp_id'], entry['dp_port'])
    
    net.get('h1').cmd('ping -c 1 172.16.1.1')
    net.get('h2').cmd('ping -c 1 172.16.2.1')
    info('Wait for flow entries installation completed...\n')
    time.sleep(10)
    info(net.iperf())
    info('\n')
    rfserver.delete_map_configs(config[0]['vm_id'])
    info('Test completed')
            
def second_test(rfserver, net):
    info('Test in progress....\n')
    config = [{'vm_id': '2b0b0b0b0b0', 'vm_port': 1, 'dp_id': '1', 'dp_port': 1},
              {'vm_id': '2b0b0b0b0b0', 'vm_port': 2, 'dp_id': '2', 'dp_port': 1}]
    
    for entry in config:
        rfserver.add_map_config(entry['vm_id'], entry['vm_port'], 
                                0, entry['dp_id'], entry['dp_port'])
    
    net.get('h1').cmd('ping -c 1 172.16.1.1')
    net.get('h2').cmd('ping -c 1 172.16.2.1')
    info('Wait for flow entries installation completed...\n')
    time.sleep(10)
    info(net.iperf())
    info('\n')
    rfserver.delete_map_configs(config[0]['vm_id'])
    info('Test completed\n')
        
def third_test(rfserver, net):
    info('Test in progress....\n')
    info('Two switches with an ISL link are mapped to rfvmC\n')
    config = [{'vm_id': '2c0c0c0c0c0', 'vm_port': 1, 'dp_id': '1', 'dp_port': 1},
              {'vm_id': '2c0c0c0c0c0', 'vm_port': 2, 'dp_id': '2', 'dp_port': 1}]
    
    for entry in config:
        rfserver.add_map_config(entry['vm_id'], entry['vm_port'], 
                                0, entry['dp_id'], entry['dp_port'])
    
    net.get('h1').cmd('ping -c 1 172.16.1.1')
    net.get('h2').cmd('ping -c 1 172.16.2.1')
    info('Wait for flow entries installation completed...\n')
    time.sleep(10)
    info(net.iperf())
    info('\n')
    rfserver.delete_map_configs(config[0]['vm_id'])
    info('Test completed\n')
    
if __name__ == '__main__':
    setLogLevel('info')
    myNetwork()