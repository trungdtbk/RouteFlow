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
# h[1-N] ----(2-N)sw1(1)--------(1)sw2(2-N)------- h[N-(2*N-1)]
#

def myNetwork(num_hosts):
    net = Mininet(topo=None, build=False, ipBase='172.16.0.0/16')
    info('*** Add controller\n')
    c0 = net.addController(name='c0', controller=RemoteController, ip='192.168.56.101', port=6633)
    
    info('*** Add switches\n')
    s1 = net.addSwitch(name='s1', cls=OVSKernelSwitch)
    s2 = net.addSwitch(name='s2', cls=OVSKernelSwitch)
    net.addLink(s1, s2)
    
    info('*** Add hosts\n')
    hosts = []
    for i in range(1, 2*num_hosts + 1):
        hostname = 'h%d' % i
        addr = '172.16.%d.1/24' % (i%254)
        gw = "via 172.16.%d.254" % (i%254)
        host = net.addHost(name=hostname, cls=Host, ip=addr, defaultRoute=gw)
        hosts.append(host)
        if (i <= num_hosts):
            net.addLink(hosts[i-1], s1)
        else:
            net.addLink(hosts[i-1], s2)
    
    info('Start network\n')
    net.build()
    for controller in net.controllers:
        controller.start()
        
    info('Start switches\n')
    net.get('s1').start([c0])
    net.get('s2').start([c0])
    
    s1.cmd('ovs-vsctl set bridge s1 protocols=OpenFlow13')
    s2.cmd('ovs-vsctl set bridge s2 protocols=OpenFlow13')
    
    info('Configure switches\n')
    CLI(net)
    net.stop()
    
if __name__ == '__main__':
    setLogLevel('info')
    if len(sys.argv) == 0:
        num_hosts = 1 # Number of host per switch
    else:
        try:
            num_hosts = int(sys.argv[1])
        except:
            num_hosts = 1
            
    myNetwork(num_hosts)
