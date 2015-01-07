#!/usr/bin/python
import sys
from mininet.net import Mininet
from mininet.node import Controller, RemoteController, OVSController
from mininet.node import CPULimitedHost, Host, Node
from mininet.node import OVSKernelSwitch, UserSwitch
from mininet.node import IVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink, Intf

#
# This will create two switches with one inter-link
# It takes input argument as the number of host ports for each sw
# the topology will look like
# h1 ----(1)sw1(2)--------(2)sw2(1)------- h2
#            (3)              (3)
#              \              /
#               \            /
#                \          /
#                 \        /
#                  \      /
#                  (1)  (2)
#                     s3

def myNetwork():
    net = Mininet(topo=None, build=False, ipBase='172.16.0.0/16')
    info('*** Add controller\n')
    c0 = net.addController(name='c0', controller=RemoteController, ip='192.168.56.101', port=6633)
    
    info('*** Add switches\n')
    s1 = net.addSwitch(name='s1', cls=OVSKernelSwitch)
    s2 = net.addSwitch(name='s2', cls=OVSKernelSwitch)
    s3 = net.addSwitch(name='s3', cls=OVSKernelSwitch)
    
    info('*** Add hosts\n')
    h1 = net.addHost(name="h1", cls=Host, ip='172.16.1.1/24', defaultRoute='via 172.16.1.254')
    h2 = net.addHost(name="h2", cls=Host, ip='172.16.2.1/24', defaultRoute='via 172.16.2.254')
    
    net.addLink(h1, s1)
    net.addLink(h2, s2)
    
    net.addLink(s1, s2)
    net.addLink(s1, s3)
    net.addLink(s2, s3)
    
    info('Start network\n')
    net.build()
    for controller in net.controllers:
        controller.start()
    
    info('Start switches\n')
    net.get('s1').start([c0])
    net.get('s2').start([c0])
    net.get('s3').start([c0])
    
    info('Configure switches\n')
    s1.cmd('ovs-vsctl set bridge s1 protocols=OpenFlow13')
    s2.cmd('ovs-vsctl set bridge s2 protocols=OpenFlow13')
    s3.cmd('ovs-vsctl set bridge s3 protocols=OpenFlow13')
    
    CLI(net)
    net.stop()
    
if __name__ == '__main__':
    setLogLevel('info')        
    myNetwork()