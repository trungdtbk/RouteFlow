#!/bin/bash
#
# This script should be executed with the python counterpart which performs the tests.
# The script does the following:
#	- Prepare configs for LXC rfvmA, rfvmB, rfvmC and rfvmD (networking)
#	- Create/setup a bridge br0 (management)
#	- Create/setup a bridge dp0 (dataplane)
#	- Start rfserver (without configuration)
#	- Start rfproxy
#	- Start LXC instances
# The python creates a network of two hosts connecting to two switches. Switches are connected
# through two links with bw of 1Mbps and 10Mbps.
# Configurations will be put in by the python script which will be executed at Mininet host
# There are two tests: One for dynamically changing LXC and one for dynamically changing dp
# Before the tests, the python script will push initial configuration to rfserver. Then, in
# the first test, one LXC VM will be replaced by another one, while ping is running.
# The second test, the mapping of inter-link is replaced. 
# Set to 0 to use external switch(es)

MULTITABLEDPS="''"
SATELLITEDPS="''"
LXC_LIST=(rfvmA rfvmB rfvmD)
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
--reset)
    ACTION="RESET"
    ;;
*)
	ACTION="START"   
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

start_rfvms() {
    for VM in ${LXC_LIST[@]}; do
        ROOTFS=$LXCDIR/$VM/rootfs
        # Create the rfclient dir
        RFCLIENTDIR=$ROOTFS/opt/rfclient
    	mkdir -p $RFCLIENTDIR
    	# Copy the rfclient executable
    	cp rfclient/rfclient $RFCLIENTDIR/rfclient
    	#cp -p -P /usr/local/lib/libzmq* $ROOTFS/usr/local/lib
    	chroot $ROOTFS ldconfig
		chmod +x $ROOTFS/root/run_rfclient.sh
		
    	cp /dev/null $ROOTFS/var/log/syslog
        VMLOG=/tmp/$VM.log
    	rm -f $VMLOG
    	lxc-start -n $VM -l DEBUG -o $VMLOG -d
    done
}

stop_rfvms() {
    echo_bold "-> Stopping the virtual machines..."
	for VM in ${LXC_LIST[@]}; do
    	lxc-stop -n $VM &> /dev/null;
    	ROOTFS=$LXCDIR/$VM/rootfs
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
        #echo 0x2a0a0a0a0a0,1,0,0x01,1 >> $RFSERVERCONFIG
        #echo 0x2a0a0a0a0a0,2,0,0x01,2 >> $RFSERVERCONFIG
        #echo 0x2b0b0b0b0b0,1,0,0x02,1 >> $RFSERVERCONFIG
        #echo 0x2b0b0b0b0b0,2,0,0x02,2 >> $RFSERVERCONFIG
        
        cp /dev/null $RFSERVERINTERNAL
        echo "vm_id,ct_id,dp_id,dp_port,eth_addr,rem_ct,rem_id,rem_port,rem_eth_addr" > $RFSERVERINTERNAL
		#echo 0x2a0a0a0a0a0,0,0x01,2,02:a1:a1:a1:a1:a1,0,0x02,2,02:a2:a2:a2:a2:a2 >> $RFSERVERINTERNAL
		#echo 0x2b0b0b0b0b0,0,0x01,3,02:b1:b1:b1:b1:b1,0,0x02,3,02:b2:b2:b2:b2:b2 >> $RFSERVERINTERNAL
    fi

    echo_bold "-> Starting the management network ($RFBR)..."
    add_local_br $RFBR
    ifconfig $RFBR $HOSTVMIP

    echo_bold "-> Starting RFServer..."
	./rfserver/rfserver.py $RFSERVERCONFIG -i $RFSERVERINTERNAL -m $MULTITABLEDPS -s $SATELLITEDPS &
    echo_bold "-> Starting the controller ($ACTION) and RFPRoxy..."
    cd $RYU_HOME
    ryu-manager --use-stderr --ofp-tcp-listen-port=$CONTROLLER_PORT ryu-rfproxy/rfproxy.py &

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
	for vm in ${LXC_LIST[@]}; do
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
