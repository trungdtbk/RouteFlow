#!/bin/bash

# Set to 0 to use external switch(es)
STARTBVMS=0

MULTITABLEDPS="''"
SATELLITEDPS="''"

HOME=/home/ubuntu
RF_HOME=$HOME/RouteFlow
RYU_HOME=$HOME/ryu-rfproxy
RFSERVERCONFIG=/tmp/rfserverconfig.csv
RFSERVERINTERNAL=/tmp/rfserverinternal.csv
HOME_RFSERVERCONFIG="$HOME/"`basename $RFSERVERCONFIG`
HOME_RFSERVERINTERNAL="$HOME/"`basename $RFSERVERINTERNAL`
CONTROLLER_PORT=6633
LXCDIR=/var/lib/lxc
RFBR=br0
RFDP=dp0
RFDPID=7266767372667673
OFP=OpenFlow13
HOSTVMIP=192.168.10.1
VSCTL="ovs-vsctl"
OFCTL="ovs-ofctl -O$OFP"
export PATH=$PATH:/usr/local/bin:/usr/local/sbin
export PYTHONPATH=$PYTHONPATH:$RF_HOME

#modprobe 8021q
ulimit -c 1000000000

if [ "$EUID" != "0" ]; then
  echo "You must be root to run this script."
  exit 1
fi

ACTION=""
case "$1" in
--ryu)
    ACTION="RYU"
    ;;
--reset)
    ACTION="RESET"
    ;;
*)
    echo "Invalid argument: $1"
    echo "Options: "
    echo "    --ryu: run using RYU"
    echo "    --reset: stop running and clear data from previous executions"
    exit
    ;;
esac

cd $RF_HOME

wait_port_listen() {
    port=$1
    while ! `nc -z localhost $port` ; do
        echo -n .
        sleep 1
    done
}

echo_bold() {
    echo -e "\033[1m${1}\033[0m"
}

kill_process_tree() {
    top=$1
    pid=$2

    children=`ps -o pid --no-headers --ppid ${pid}`

    for child in $children
    do
        kill_process_tree 0 $child
    done

    if [ $top -eq 0 ]; then
        kill -9 $pid &> /dev/null
    fi
}

add_local_br() {
    br=$1
    dpid=$2
    $VSCTL add-br $br
    $VSCTL set bridge $br protocols=$OFP
    if [ "$dpid" != "" ] ; then 
      $VSCTL set bridge $br other-config:datapath-id=$dpid
    fi
    ifconfig $br up
    check_local_br_up $br
}

check_local_br_up() {
    br=$1
    echo waiting for OVS sw/controller $br to come up
    while ! $OFCTL ping $br 64|grep -q "64 bytes from" ; do
      echo -n "."
      sleep 1
    done 
}

start_ovs() {
	if [ ! -f /usr/local/etc/openvswitch/conf.db ] ; then
		ovsdb-tool create /usr/local/etc/openvswitch/conf.db /usr/local/share/openvswitch/vswitch.ovsschema
	fi
        ovsdb-server --pidfile --detach --remote=punix:$OVSSOCK
        ovs-vswitchd --pidfile --detach unix:$OVSSOCK
}

start_rfvms() {
	i=1
	j=2
	for vm in rfvmA rfvmB; do
		ROOTFS=$LXCDIR/$vm/rootfs

		# Quagga ospf configuration
		cat > $ROOTFS/etc/quagga/ospfd.conf <<EOF
password 123
enable password 123
!
router ospf
	network 172.16.0.0/12 area 0
	network 10.0.0.0/8 area 0
	passive-interface eth1

log file /var/log/quagga/ospfd.log
!
interface eth1
	ip ospf hello-interval 1
	ip ospf dead-interval 4

interface eth2
	ip ospf hello-interval 1
	ip ospf dead-interval 4
!
EOF
		cat > $ROOTFS/etc/quagga/zebra.conf <<EOF
password 123
enable password 123
!
log file /var/log/quagga/zebra.log
!
interface eth1
	ip address 172.16.$i.1/24
!
interface eth2
	ip address 10.0.0.$i/24

ip route 172.16.$j.0 255.255.255.0 10.0.0.$j
EOF
		# Prepare configs for LXCs
		cat > $ROOTFS/etc/network/interfaces <<EOF
auto lo
iface lo inet loopback
auto eth0
iface eth0 inet static
address 192.168.10.10$i
netmask 255.255.255.0
EOF
		i=$(($i+1))
		j=$(($j-1))
		cat > $ROOTFS/etc/rc.local <<EOF
/root/run_rfclient.sh &
exit 0
EOF
		cat > $ROOTFS/root/run_rfclient.sh <<EOF
#!/bin/sh
/opt/rfclient/rfclient > /var/log/rfclient.log 2> /var/log/rfclient.log.err
EOF
		# Create the rfclient dir
    	RFCLIENTDIR=$ROOTFS/opt/rfclient
    	mkdir -p $RFCLIENTDIR
    	# Copy the rfclient executable
    	cp rfclient/rfclient $RFCLIENTDIR/rfclient
    	#cp -p -P /usr/local/lib/libzmq* $ROOTFS/usr/local/lib
    	chroot $ROOTFS ldconfig
		chmod +x $ROOTFS/root/run_rfclient.sh
		
    	cp /dev/null $ROOTFS/var/log/syslog
		VMLOG=/tmp/$vm.log
    	rm -f $VMLOG
    	lxc-start -n $vm -l DEBUG -o $VMLOG -d
    done
}

stop_rfvms() {
	cd $RF_HOME
    echo_bold "-> Stopping the virtual machines..."
	for vm in rfvmA rfvmB; do
    	lxc-stop -n $vm &> /dev/null;
    	ROOTFS=$LXCDIR/$vm/rootfs
    	rm -rf $ROOTFS/var/run/network/ifstate;
    done
}

reset() {
    echo_bold "-> Stopping and resetting LXC VMs...";
    stop_rfvms

    init=$1;
    if [ $init -eq 1 ]; then
        echo_bold "-> Starting OVS daemons...";
		#start_ovs
    else
        echo_bold "-> Stopping child processes...";
        kill_process_tree 1 $$
    fi

    sudo $VSCTL del-br $RFBR &> /dev/null;
    sudo $VSCTL del-br $RFDP &> /dev/null;
    sudo $VSCTL emer-reset &> /dev/null;
}
reset 1
trap "reset 0; exit 0" INT

if [ "$ACTION" != "RESET" ]; then
    if [ -f "$HOME_RFSERVERCONFIG" ] && [ -f "$HOME_RFSERVERINTERNAL" ] ; then
        echo_bold "-> Using existing external config..."
        cp $HOME_RFSERVERCONFIG $RFSERVERCONFIG
        cp $HOME_RFSERVERINTERNAL $RFSERVERINTERNAL
    else
        echo_bold "-> Run with default config..."
        cp /dev/null $RFSERVERCONFIG
        echo "vm_id,vm_port,ct_id,dp_id,dp_port" > $RFSERVERCONFIG
        
        # Initially, rfvmA is mapped the port1 to dp1, port1
		# & port2 to dp2, port1
        #echo 0x2a0a0a0a0a0,1,0,0x01,1 >> $RFSERVERCONFIG
        #echo 0x2a0a0a0a0a0,2,0,0x02,1 >> $RFSERVERCONFIG
        
        cp /dev/null $RFSERVERINTERNAL
        echo "vm_id,ct_id,dp_id,dp_port,eth_addr,rem_ct,rem_id,rem_port,rem_eth_addr" > $RFSERVERINTERNAL
		#echo 0x2a0a0a0a0a0,0,0x01,2,02:a1:a1:a1:a1:a1,0,0x02,2,02:a2:a2:a2:a2:a2 >> $RFSERVERINTERNAL	
		#echo 0x2b0b0b0b0b0,0,0x01,3,02:b1:b1:b1:b1:b1,0,0x02,3,02:b2:b2:b2:b2:b2 >> $RFSERVERINTERNAL
		#echo 0x2c0c0c0c0c0,0,0x01,4,02:c1:c1:c1:c1:c1,0,0x02,4,02:c2:c2:c2:c2:c2 >> $RFSERVERINTERNAL
		#echo 0x2d0d0d0d0d0,0,0x01,5,02:d1:d1:d1:d1:d1,0,0x03,1,02:d2:d2:d2:d2:d2 >> $RFSERVERINTERNAL
		#echo 0x2d0d0d0d0d0,0,0x03,2,02:d1:d1:d1:d1:d1,0,0x02,5,02:d2:d2:d2:d2:d2 >> $RFSERVERINTERNAL
    fi

    echo_bold "-> Starting the management network ($RFBR)..."
    add_local_br $RFBR
    ifconfig $RFBR $HOSTVMIP

    echo_bold "-> Starting RFServer..."
    #winpdb ./rfserver/rfserver.py $RFSERVERCONFIG -i $RFSERVERINTERNAL -m $MULTITABLEDPS -s $SATELLITEDPS &
	./rfserver/rfserver.py $RFSERVERCONFIG -i $RFSERVERINTERNAL -m $MULTITABLEDPS -s $SATELLITEDPS &

    echo_bold "-> Starting the controller ($ACTION) and RFPRoxy..."
    case "$ACTION" in
    RYU)
        cd $RYU_HOME
        ryu-manager --use-stderr --ofp-tcp-listen-port=$CONTROLLER_PORT ryu-rfproxy/rfproxy.py &
        ;;
    esac
    cd - &> /dev/null
    wait_port_listen $CONTROLLER_PORT
    check_local_br_up tcp:127.0.0.1:$CONTROLLER_PORT

    echo_bold "-> Starting the control plane network ($RFDP VS)..."
    $VSCTL add-br $RFDP
    $VSCTL set bridge $RFDP other-config:datapath-id=$RFDPID
    $VSCTL set bridge $RFDP protocols=$OFP
    $VSCTL set-controller $RFDP tcp:127.0.0.1:$CONTROLLER_PORT
    $OFCTL add-flow $RFDP actions=CONTROLLER:65509
    ifconfig $RFDP up
    check_local_br_up $RFDP

    echo_bold "-> Waiting for $RFDP to connect to controller..."
    while ! $VSCTL find Controller target=\"tcp:127.0.0.1:$CONTROLLER_PORT\" is_connected=true | grep -q connected ; do
      echo -n .
      sleep 1
    done

    echo_bold "-> Starting virtual machines..."
    start_rfvms
    while ! ifconfig -s rfvmA.0 ; do
      echo -n .
      sleep 1
    done
    
    # Add VM eth0 port to management bridge
	for vm in rfvmA rfvmB; do
		$VSCTL add-port $RFBR $vm.0
	done
    
    # Add VM interfaces to dataplane bridge
    for i in `netstat -i|grep rfvm|cut -f 1 -d " "` ; do
    if [ "$i" != "`echo $i | grep .0`" ] ; then
        $VSCTL add-port $RFDP $i
      fi
    done

    echo_bold "-> Waiting for VMs to come up..."
    while ! ping -W 1 -c 1 192.168.10.101 ; do
      echo -n .
      sleep 1
    done

    echo_bold "You can stop this test by pressing Ctrl+C."
    wait
fi
exit 0
