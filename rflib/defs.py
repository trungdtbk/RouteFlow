
IPC_TYPE = 'zeromq'  # options are 'zeromq' or 'mongo'
DB_TYPE = 'memory'   # options are 'memory' or 'mongo'

MONGO_ADDRESS = "127.0.0.1:27017"
MONGO_DB_NAME = "db"

ZEROMQ_ADDRESS =  "tcp://192.168.10.1:25555"

RFCLIENT_RFSERVER_CHANNEL = "rfclient<->rfserver"
RFSERVER_RFPROXY_CHANNEL = "rfserver<->rfproxy"

RFTABLE_NAME = "rftable"
RFCONFIG_NAME = "rfconfig"
RFISL_NAME = "rfisl"
RFISLCONF_NAME = "rfislconf"

RFVMPORTTABLE_NAME = "vmporttable"
RFDPPORTTABLE_NAME = "dpporttable"

RFSERVER_ID = "rfserver"
RFPROXY_ID = "rfproxy"

DEFAULT_RFCLIENT_INTERFACE = "eth0"

RFVS_PREFIX = 0x72667673
is_rfvs = lambda dp_id: not ((dp_id >> 32) ^ RFVS_PREFIX)

RF_ETH_PROTO = 0x0A0A # RF ethernet protocol

VLAN_HEADER_LEN = 4
ETH_HEADER_LEN = 14
ETH_CRC_LEN = 4
ETH_PAYLOAD_MAX = 1500
ETH_TOTAL_MAX = (ETH_HEADER_LEN + ETH_PAYLOAD_MAX + ETH_CRC_LEN)
RF_MAX_PACKET_SIZE = (VLAN_HEADER_LEN + ETH_TOTAL_MAX)

DC_DROP_ALL = 0			# Drop all incoming packets
DC_CLEAR_FLOW_TABLE = 1 # Clear flow table
DC_VM_INFO = 2			# Flow to communicate two linked VMs
DC_RIPV2 = 3			# RIPv2 protocol
DC_OSPF = 4			# OSPF protocol
DC_BGP_PASSIVE = 5		# BGP protocol
DC_BGP_ACTIVE = 6		# BGP protocol
DC_ARP = 7			# ARP protocol
DC_ICMP = 8			# ICMP protocol
DC_LDP_PASSIVE = 9		# LDP protocol
DC_LDP_ACTIVE = 10		# LDP protocol
DC_ICMPV6 = 11			# ICMPv6 protocol
DC_BGP_PASSIVEV6 = 12
DC_BGP_ACTIVEV6 = 13
DC_ALL = 255			# Send all traffic to the controller

RMT_ADD = 0			# Add flow to datapath
RMT_DELETE = 1			# Remove flow from datapath
RMT_CONTROLLER = 2	        # Add flow to datapath, output to datapath's controller
RMT_ADD_GROUP = 3		# Add group to datapath
RMT_DELETE_GROUP = 4		# Delete group from datapath
#RMT_MODIFY = 99                # Modify existing flow (Unimplemented)

# Port Configuration Types
PCT_MAP_REQUEST = 0     # (deprecated) Request for a mapping packet.
PCT_RESET = 1           # Reset the client port to inactive.
PCT_MAP_SUCCESS = 2     # Mapping was successful; port can be brought up.
PCT_ROUTEMOD_ACK = 3

PC_MAP = 0
PC_RESET = 1

# Data plane Port Map Configuration (DCT_)
DCT_UPDATE_DP = 0 # Update Proxy map table by DP info
DCT_UPDATE_VS = 1 # Update Proxy map table by VS info
DCT_DELETE_DP = 2 # Delete Proxy map table by DP info
DCT_DELETE_VS = 3 # Delete Proxy map table by VS info

# Format 12-digit hex ID
format_id = lambda dp_id: hex(dp_id).rstrip("L") if (dp_id is not None) else 'None'

netmask_prefix = lambda a: sum([bin(int(x)).count("1") for x in a.split(".", 4)])
cidr_to_mask = lambda a: ((1 << a) - 1) << (32 - a)

ETHERTYPE_IP = 0x0800
ETHERTYPE_ARP = 0x0806
ETHERTYPE_IPV6 = 0x86DD
IPPROTO_ICMP = 0x01
IPPROTO_TCP = 0x06
IPPROTO_UDP = 0x11
IPPROTO_OSPF = 0x59
IPPROTO_ICMPV6 = 0x3A
IPADDR_RIPv2 = '224.0.0.9'
IPV4_MASK_EXACT = '255.255.255.255'
IPV6_MASK_EXACT = 'FFFF:FFFF:FFFF:FFFF:FFFF:FFFF:FFFF:FFFF'
TPORT_BGP = 0x00B3
TPORT_LDP = 0x286

OFPP_CONTROLLER = 0xFFFFFFFD

PRIORITY_BAND = 0xA
PRIORITY_LOWEST = 0x0000
PRIORITY_LOW = 0x4010
PRIORITY_HIGH = 0x8020
PRIORITY_HIGHEST = 0xC030

CONTROLLER_GROUP = 1
