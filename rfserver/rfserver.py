#!/usr/bin/env python
#-*- coding:utf-8 -*-

import os
import sys
import logging
import binascii
import argparse
import time
import copy
import Queue
import threading

from bson.binary import Binary

import rflib.ipc.IPC as IPC
import rflib.ipc.IPCService as IPCService
from rflib.ipc.RFProtocol import *
from rflib.ipc.RFProtocolFactory import RFProtocolFactory
from rflib.defs import *
from rflib.types.Match import *
from rflib.types.Action import *
from rflib.types.Option import *

from rftable import *

from rfserverrpc import RFServerRPC

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)-15s %(levelname)-8s %(message)s',
    datefmt='%b %d %H:%M:%S'
    )

# Register actions
REGISTER_IDLE = 0
REGISTER_ASSOCIATED = 1
REGISTER_ISL = 2


class RouteModTranslator(object):

    DROP_PRIORITY = Option.PRIORITY(PRIORITY_LOWEST + PRIORITY_BAND)
    CONTROLLER_PRIORITY = Option.PRIORITY(PRIORITY_HIGH)
    DEFAULT_PRIORITY = Option.PRIORITY(PRIORITY_LOWEST + PRIORITY_BAND + 1000)

    def __init__(self, dp_id, ct_id, rftable, isltable, log):
        self.dp_id = dp_id
        self.ct_id = ct_id
        self.rftable = rftable
        self.isltable = isltable
        self.log = log

    def configure_datapath(self):
        raise Exception

    def handle_controller_route_mod(self, entry, rm):
        raise Exception

    def handle_route_mod(self, entry, rm):
        raise Exception

    def handle_isl_route_mod(self, entry, rm):
        raise Exception


class DefaultRouteModTranslator(RouteModTranslator):

    def _send_rm_with_matches(self, rm, out_port, entries):
        rms = []
        for entry in entries:
            if out_port != entry.dp_port:
                if (entry.get_status() == RFENTRY_ACTIVE or
                    entry.get_status() == RFISL_ACTIVE):
                    local_rm = copy.deepcopy(rm)
                    local_rm.add_match(Match.ETHERNET(entry.eth_addr))
                    local_rm.add_match(Match.IN_PORT(entry.dp_port))
                    rms.append(local_rm)
        return rms

    def configure_datapath(self):
        rms = []

        # delete all groups
        rm = RouteMod(RMT_DELETE_GROUP, self.dp_id)
        rms.append(rm)
        
        # delete all flows
        rm = RouteMod(RMT_DELETE, self.dp_id)
        rms.append(rm)

        # default drop
        rm = RouteMod(RMT_ADD, self.dp_id)
        #rm.add_match(Match.ETHERTYPE(ETHERTYPE_IP))
        rm.add_option(self.DROP_PRIORITY)
        rms.append(rm)

        # ARP
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_ARP))
        rm.add_action(Action.CONTROLLER())
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)

        return rms

    def handle_controller_route_mod(self, entry, rm):
        rm.add_action(Action.CONTROLLER())
        return [rm]

    def handle_route_mod(self, entry, rm):
        rms = []
        # Add vm_id in the query to limit the flow entry installation to only ports
        # that are mapped to the VM
        entries = self.rftable.get_entries(vm_id=entry.vm_id,
                                           dp_id=entry.dp_id,
                                           ct_id=entry.ct_id)
        entries.extend(self.isltable.get_entries(vm_id=entry.vm_id,
                                                 dp_id=entry.dp_id,
                                                 ct_id=entry.ct_id))

        # Replace the VM port with the datapath port
        rm.add_action(Action.OUTPUT(entry.dp_port))

        rms.extend(self._send_rm_with_matches(rm, entry.dp_port, entries))
        return rms

    def handle_isl_route_mod(self, r, rm):
        rms = []
        rm.set_id(self.dp_id)
        rm.set_table(0)
        rm.set_actions(None)
        rm.add_action(Action.SET_ETH_SRC(r.eth_addr))
        rm.add_action(Action.SET_ETH_DST(r.rem_eth_addr))
        rm.add_action(Action.OUTPUT(r.dp_port))
        entries = self.rftable.get_entries(vm_id=r.vm_id,
                                           dp_id=r.dp_id, 
                                           ct_id=r.ct_id)
        rms.extend(self._send_rm_with_matches(rm, r.dp_port, entries))
        return rms
    
    # Delete flow entries from switch's flow table
    def dp_delete_flows(self, entry):
        rms = []
        
        rm = RouteMod(RMT_DELETE, self.dp_id)
        rm.add_match(Match.IN_PORT(entry.dp_port))
        rm.add_option(self.DEFAULT_PRIORITY)
        rms.append(rm)
        
        rm = RouteMod(RMT_DELETE, self.dp_id)
        rm.add_match(Match.ETHERNET(entry.eth_addr))
        rm.add_option(self.DEFAULT_PRIORITY)
        rms.append(rm)
        
        return rms

class SatelliteRouteModTranslator(DefaultRouteModTranslator):

    def __init__(self, dp_id, ct_id, rftable, isltable, log):
        super(SatelliteRouteModTranslator, self).__init__(
            dp_id, ct_id, rftable, isltable, log)
        self.sent_isl_dl = set()

    def handle_isl_route_mod(self, r, rm):
        rms = []
        for ethertype in (ETHERTYPE_IP, ETHERTYPE_IPV6):
            rm.set_matches(None)
            rm.add_match(Match.ETHERTYPE(ethertype))
            rm.set_options(None)
            rm.add_option(self.DEFAULT_PRIORITY)
            if r.rem_eth_addr not in self.sent_isl_dl:
                self.sent_isl_dl.add(r.rem_eth_addr)
                rm.set_id(self.dp_id)
                rm.set_table(0)
                rm.set_actions(None)
                rm.add_action(Action.SET_ETH_SRC(r.eth_addr))
                rm.add_action(Action.SET_ETH_DST(r.rem_eth_addr))
                rm.add_action(Action.OUTPUT(r.dp_port))
                entries = self.rftable.get_entries(dp_id=r.dp_id, ct_id=r.ct_id)
                rms.extend(self._send_rm_with_matches(rm, r.dp_port, entries))
        return rms


class NoviFlowMultitableRouteModTranslator(RouteModTranslator):

    FIB_TABLE = 2
    ETHER_TABLE = 1

    def __init__(self, dp_id, ct_id, rftable, isltable, log):
        super(NoviFlowMultitableRouteModTranslator, self).__init__(
            dp_id, ct_id, rftable, isltable, log)

    def _send_rm_with_matches(self, rm, out_port, entries):
        rms = []
        for entry in entries:
            if out_port != entry.dp_port:
                if (entry.get_status() == RFENTRY_ACTIVE or
                    entry.get_status() == RFISL_ACTIVE):
                    rms.append(rm)
                    break
        return rms

    def configure_datapath(self):
        rms = []

        # delete all groups
        rm = RouteMod(RMT_DELETE_GROUP, self.dp_id)
        rms.append(rm)
        # default group - send to controller
        rm = RouteMod(RMT_ADD_GROUP, self.dp_id)
        rm.set_group(CONTROLLER_GROUP);
        rm.add_action(Action.CONTROLLER())
        rms.append(rm)

        # delete all flows
        rm = RouteMod(RMT_DELETE, self.dp_id)
        rms.append(rm)

        # default drop
        for table_id in (0, self.ETHER_TABLE, self.FIB_TABLE):
            rm = RouteMod(RMT_ADD, self.dp_id)
            rm.set_table(table_id)
            rm.add_option(self.DROP_PRIORITY)
            rms.append(rm)
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.add_match(Match.ETHERNET("ff:ff:ff:ff:ff:ff"))
        rm.add_action(Action.GOTO(self.ETHER_TABLE))
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)
        # ARP
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.ETHER_TABLE)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_ARP))
        rm.add_action(Action.GROUP(CONTROLLER_GROUP))
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)
        # IPv4
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.ETHER_TABLE)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_IP))
        rm.add_option(self.DEFAULT_PRIORITY)
        rm.add_action(Action.GOTO(self.FIB_TABLE))
        rms.append(rm)
        return rms

    def handle_controller_route_mod(self, entry, rm):
        rms = []
        rm.add_action(Action.GROUP(CONTROLLER_GROUP))
        # should be FIB_TABLE, but see NoviFlow note.
        rm.set_table(self.ETHER_TABLE)
        dl_dst = None
        orig_matches = rm.get_matches()
        rm.set_matches(None)
        for match_dict in orig_matches:
            match = Match.from_dict(match_dict)
            match_type = match.type_to_str(match._type)
            if match_type == "RFMT_ETHERNET":
                dl_dst = match
            else:
                rm.add_match(match)
        rms.append(rm)

        if dl_dst is not None:
            hw_rm = RouteMod(RMT_CONTROLLER, entry.dp_id)
            hw_rm.set_id(rm.get_id())
            hw_rm.set_vm_port(rm.get_vm_port())
            hw_rm.add_match(dl_dst)
            hw_rm.add_action(Action.GOTO(self.ETHER_TABLE))
            hw_rm.add_option(self.DEFAULT_PRIORITY)
            rms.append(hw_rm)

        return rms

    def handle_route_mod(self, entry, rm):
        rms = []
        entries = self.rftable.get_entries(dp_id=entry.dp_id,
                                           ct_id=entry.ct_id)
        entries.extend(self.isltable.get_entries(dp_id=entry.dp_id,
                                                 ct_id=entry.ct_id))

        # Replace the VM port with the datapath port
        rm.add_action(Action.OUTPUT(entry.dp_port))

        rm.set_table(self.FIB_TABLE)

        rm.set_options(None)
        rm.add_option(self.CONTROLLER_PRIORITY)

        rms.extend(self._send_rm_with_matches(rm, entry.dp_port, entries))
        return rms

    def handle_isl_route_mod(self, r, rm):
        rms = []
        rm.set_id(self.dp_id)
        rm.set_table(self.FIB_TABLE)
        rm.set_options(None)
        rm.add_option(self.CONTROLLER_PRIORITY)
        rm.set_actions(None)
        rm.add_action(Action.SET_ETH_SRC(r.eth_addr))
        rm.add_action(Action.SET_ETH_DST(r.rem_eth_addr))
        rm.add_action(Action.OUTPUT(r.dp_port))
        entries = self.rftable.get_entries(dp_id=r.dp_id, ct_id=r.ct_id)
        rms.extend(self._send_rm_with_matches(rm, r.dp_port, entries))
        return rms

class CorsaMultitableRouteModTranslator(RouteModTranslator):

    DROP_PRIORITY = Option.PRIORITY(0)
    CONTROLLER_PRIORITY = Option.PRIORITY(255)
    DEFAULT_PRIORITY = Option.PRIORITY(PRIORITY_LOWEST + PRIORITY_BAND + 1)

    VLAN_MPLS_TABLE = 1
    VLAN_TABLE = 2
    MPLS_TABLE = 3 # not currently implemented
    ETHER_TABLE = 4
    COS_MAP_TABLE = 5
    FIB_TABLE = 6
    LOCAL_TABLE = 9

    def __init__(self, dp_id, ct_id, rftable, isltable, log):
        super(CorsaMultitableRouteModTranslator, self).__init__(
            dp_id, ct_id, rftable, isltable, log)
        self.last_groupid = CONTROLLER_GROUP
        self.actions_to_groupid = {}

    def configure_datapath(self):
        rms = []

        # delete all groups
        rm = RouteMod(RMT_DELETE_GROUP, self.dp_id)
        rms.append(rm)

        # delete all flows
        rm = RouteMod(RMT_DELETE, self.dp_id)
        rms.append(rm)

        # default drop
        for table_id in (0, self.VLAN_MPLS_TABLE, self.VLAN_TABLE,
                         self.ETHER_TABLE, self.FIB_TABLE):
            rm = RouteMod(RMT_ADD, self.dp_id)
            rm.set_table(table_id)
            rm.add_option(self.DROP_PRIORITY)
            rms.append(rm)

        ## Table 0
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.add_match(Match.ETHERNET("ff:ff:ff:ff:ff:ff"))
        rm.add_action(Action.GOTO(self.VLAN_MPLS_TABLE))
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)

        ## VLAN/MPLS table 1
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.VLAN_MPLS_TABLE)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_IP))
        rm.add_action(Action.GOTO(self.VLAN_TABLE))
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.VLAN_MPLS_TABLE)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_ARP))
        rm.add_action(Action.GOTO(self.VLAN_TABLE))
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.VLAN_MPLS_TABLE)
        rm.add_match(Match.ETHERTYPE(0x8100))
        rm.add_action(Action.GOTO(self.VLAN_TABLE))
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)

        ## VLAN table 2
        # no default flows other than drop.

        ## Ether type table 3
        # ARP
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.ETHER_TABLE)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_ARP))
        rm.add_action(Action.CONTROLLER())
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)
        # IPv4
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.ETHER_TABLE)
        rm.add_match(Match.ETHERTYPE(ETHERTYPE_IP))
        rm.add_option(self.CONTROLLER_PRIORITY)
        rm.add_action(Action.GOTO(self.COS_MAP_TABLE))
        rms.append(rm)

        # COS table 5 (just map to FIB table)
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.COS_MAP_TABLE)
        rm.add_action(Action.GOTO(self.FIB_TABLE))
        rm.add_option(self.DROP_PRIORITY)
        rms.append(rm)

        ## Local table temporary catch-all entry (table 9)
        rm = RouteMod(RMT_ADD, self.dp_id)
        rm.set_table(self.LOCAL_TABLE)
        rm.add_action(Action.CONTROLLER())
        rm.add_option(self.CONTROLLER_PRIORITY)
        rms.append(rm)

        return rms

    def _send_rm_with_matches(self, rm, out_port, entries):
        rms = []
        for entry in entries:
            if out_port != entry.dp_port:
                if (entry.get_status() == RFENTRY_ACTIVE or
                    entry.get_status() == RFISL_ACTIVE):
                    dst_eth = None
                    actions = rm.actions
                    rm.set_actions(None)
                    for action_dict in actions:
                        action = Action.from_dict(action_dict)
                        action_type = action.type_to_str(action._type)
                        if action_type == 'RFAT_SET_ETH_DST':
                            dst_eth = action.get_value()
                        elif action_type == 'RFAT_SWAP_VLAN_ID':
                            vlan_id = action.get_value()
                            action = Action.SET_VLAN_ID(vlan_id)
                        rm.add_action(action)
                    if dst_eth not in self.actions_to_groupid:
                        self.last_groupid += 1
                        new_groupid = self.last_groupid
                        self.actions_to_groupid[dst_eth] = new_groupid
                        group_rm = RouteMod(RMT_ADD_GROUP, self.dp_id)
                        group_rm.set_group(new_groupid)
                        group_rm.set_actions(rm.actions)
                        rms.append(group_rm)
                        self.log.info("adding new group %u for Ethernet destination %s" % (
                            new_groupid, dst_eth))
                    rm.set_actions(None)
                    rm.add_action(Action.GROUP(self.actions_to_groupid[dst_eth]))
                    rms.append(rm)
                    break
        return rms

    def handle_controller_route_mod(self, entry, rm):
        rms = []
        rm.add_action(Action.GOTO(self.LOCAL_TABLE))
        rm.set_table(self.FIB_TABLE)
        dl_dst = None
        dst_vlan = None
        orig_matches = rm.get_matches()
        rm.set_matches(None)
        for match_dict in orig_matches:
            match = Match.from_dict(match_dict)
            match_type = match.type_to_str(match._type)
            if match_type == "RFMT_ETHERNET":
                dl_dst = match
            # TODO: support more than IP address matches
            # TODO: support more than IPv4
            elif match_type == "RFMT_IPV4":
                rm.add_match(Match.ETHERTYPE(ETHERTYPE_IP))
                rm.add_match(match)
            elif match_type == "RFMT_VLAN_ID":
                dst_vlan = match.get_value()

        if rm.matches:
            rms.append(rm)

        if dst_vlan is not None:
            vlan_rm = RouteMod(RMT_ADD, self.dp_id)
            vlan_rm.set_table(self.VLAN_TABLE)
            vlan_rm.add_match(Match.IN_PORT(entry.dp_port))
            vlan_rm.add_match(Match.VLAN_ID(dst_vlan))
            vlan_rm.add_action(Action.STRIP_VLAN_DEFERRED())
            vlan_rm.add_action(Action.GOTO(self.ETHER_TABLE))
            vlan_rm.add_option(self.CONTROLLER_PRIORITY)
            self.log.info("adding new VLAN strip rule for VLAN %s" % (dst_vlan))
            rms.append(vlan_rm)

        if dl_dst is not None:
            hw_rm = RouteMod(RMT_CONTROLLER, entry.dp_id)
            hw_rm.set_id(rm.get_id())
            hw_rm.set_vm_port(rm.get_vm_port())
            hw_rm.add_match(dl_dst)
            hw_rm.add_action(Action.GOTO(self.VLAN_MPLS_TABLE))
            hw_rm.add_option(self.DEFAULT_PRIORITY)
            rms.append(hw_rm)

        return rms

    def handle_route_mod(self, entry, rm):
        rms = []
        entries = self.rftable.get_entries(dp_id=entry.dp_id,
                                           ct_id=entry.ct_id)
        entries.extend(self.isltable.get_entries(dp_id=entry.dp_id,
                                                 ct_id=entry.ct_id))

        # Replace the VM port with the datapath port
        rm.add_action(Action.OUTPUT(entry.dp_port))

        rm.set_table(self.FIB_TABLE)

        rms.extend(self._send_rm_with_matches(rm, entry.dp_port, entries))
        return rms

class RFServer(RFProtocolFactory, IPC.IPCMessageProcessor):

    def __init__(self, configfile, islconffile, multitabledps, satellitedps):
        self.config = RFConfig(configfile)
        self.islconf = RFISLConf(islconffile)
        try:
            self.multitabledps = set([int(x, 16) for x in multitabledps.split(",")])
        except ValueError:
            self.multitabledps = set()
        try:
            self.satellitedps = set([int(x, 16) for x in satellitedps.split(",")])
        except ValueError:
            self.satellitedps = set()

        # Initialise state tables
        self.rftable = RFTable()
        self.isltable = RFISLTable()
        
        # Keep info about LXCs' ports and switches' ports in the tables & use it
        # to create the new associations as the user requests 
        self.vmporttable = RFVMPortTable()
        self.dpporttable = RFDPPortTable()
        
        self.route_mod_translator = {}

        # Logging
        self.log = logging.getLogger("rfserver")

        if self.satellitedps:
            self.log.info("Datapaths that are ISL satellites: %s",
                          list(self.satellitedps))
        if self.multitabledps:
            self.log.info("Datapaths that support multiple tables: %s",
                          list(self.multitabledps))

        # Queue for flow entries going to be deleted
        self.del_rm_q = [] 
        self.ack_q = Queue.Queue()
        self.dp_q = Queue.Queue()
        self.ipc_lock = threading.Lock()
        self.routemod_outstanding = threading.Event()
        self.ipc = IPCService.for_server(RFSERVER_ID)

        self.worker = threading.Thread(target=self.dp_worker)
        self.worker.daemon = True
        self.worker.start()

        # Delete RMs worker
        self.del_rm_worker = threading.Thread(target=self.del_rm_worker)
        self.del_rm_worker.daemon = True
        self.del_rm_worker.start()

        self.ipc.listen(RFCLIENT_RFSERVER_CHANNEL, self, self, False)
        self.ipc.listen(RFSERVER_RFPROXY_CHANNEL, self, self, False)

    def ipc_send(self, channel, channel_id, msg):
        self.ipc_lock.acquire()
        self.ipc.send(channel, channel_id, msg)
        self.ipc_lock.release()
    
    # Delete old flow entries from switch flow table
    def del_rm_worker(self):
        while True:
            if self.del_rm_q:
                (secs, ct_id, rm) = self.del_rm_q[0]
                elapse = time.time() - secs
                if elapse > DEL_RM_DELAY: 
                    self.send_route_mod(ct_id, rm)
                    self.del_rm_q.pop(0)
            else:
                time.sleep(0.5)

    def dp_worker(self):
        while True:
            (ct_id, rm) = self.dp_q.get(block=True)
            self.ipc_send(RFSERVER_RFPROXY_CHANNEL, ct_id, rm)
            self.dp_q.task_done()

    def send_routemod_acks(self):
        while not self.ack_q.empty():
            (vm_id, ack) = self.ack_q.get()
            self.ipc_send(RFCLIENT_RFSERVER_CHANNEL, vm_id, ack)
            self.ack_q.task_done()

    def process(self, from_, to, channel, msg):
        type_ = msg.get_type()
        if channel == RFCLIENT_RFSERVER_CHANNEL:
            if type_ == ROUTE_MOD:
                self.register_route_mod(msg)
            elif type_ == PORT_REGISTER:
                self.register_vm_port(msg.get_vm_id(), msg.get_vm_port(),
                                      msg.get_hwaddress())
        elif channel == RFSERVER_RFPROXY_CHANNEL:
            if type_ == DATAPATH_PORT_REGISTER:
                self.register_dp_port(msg.get_ct_id(),
                                      msg.get_dp_id(),
                                      msg.get_dp_port(),
                                      msg.get_port_state())
            elif type_ == DATAPATH_DOWN:
                self.set_dp_down(msg.get_ct_id(), msg.get_dp_id())
            elif type_ == VIRTUAL_PLANE_MAP:
                self.map_port(msg.get_vm_id(), msg.get_vm_port(),
                              msg.get_vs_id(), msg.get_vs_port())
            elif type_ == ROUTE_MOD:
                self.send_routemod_acks()
            elif type_ == DATAPATH_PORT_STATUS:
                dpport = self.dpporttable.get_dp_port_info(msg.get_ct_id(),
                                                           msg.get_dp_id(),
                                                           msg.get_dp_port())
                if dpport is not None:
                    dpport.state = msg.get_port_state()
                    self.dpporttable.set_entry(dpport)
                    self.log.info('Update port state of port %i to state %i' % (dpport.dp_port, dpport.state))

                entry = self.rftable.get_entry_by_dp_port(msg.get_ct_id(), msg.get_dp_id(), msg.get_dp_port())
                if entry is not None and entry.get_status() == RFENTRY_ACTIVE:
                    operation_id = None
                    if msg.get_port_state() == DP_PORT_UP:
                        operation_id = PCT_PORT_UP
                    elif msg.get_port_state() == DP_PORT_DOWN:
                        operation_id = PCT_PORT_DOWN
                    msg = PortConfig(vm_id=entry.vm_id, vm_port=entry.vm_port,
                                 operation_id=operation_id)
                    self.ipc_send(RFCLIENT_RFSERVER_CHANNEL, str(entry.vm_id), msg)
            elif type_ == DATAPATH_PORT_REMOVE:
                self.delete_dp_port(msg.get_ct_id(),
                                    msg.get_dp_id(),
                                    msg.get_dp_port())

    # Port register methods
    def register_vm_port(self, vm_id, vm_port, eth_addr):
        entry = self.vmporttable.get_vm_port_info(vm_id=vm_id, vm_port=vm_port)
        if entry is not None:
            entry.update_eth_addr(eth_addr = eth_addr)
            entry.update_vs(vs_id=None, vs_port=None)
        else:
            entry = RFVMPortEntry(vm_id=vm_id, vm_port=vm_port, eth_addr=eth_addr)
        
        self.vmporttable.set_entry(entry)
        self.log.info("Updating vm port table (vm_id=%s, vm, vm_port=%i, eth_addr=%s)"
                      % (format(vm_id), vm_port, eth_addr))
        entry = None
        action = None
        config_entry = self.config.get_config_for_vm_port(vm_id, vm_port)
        if config_entry is None:
            # Register idle VM awaiting for configuration
            action = REGISTER_IDLE
            self.log.warning('No config entry for client port (vm_id=%s, vm_port=%i)'
                % (format_id(vm_id), vm_port))
			# Trung: Should return here. No need to add an entry to rftable if the port
			# hasn't been configured
            return
        else:
            entry = self.rftable.get_entry_by_dp_port(config_entry.ct_id,
                                                      config_entry.dp_id,
                                                      config_entry.dp_port)
            # If there's no entry, we have no DP, register VM as idle
            if entry is None:
                action = REGISTER_IDLE
            # If there's an idle DP entry matching configuration, associate
            elif entry.get_status() == RFENTRY_IDLE_DP_PORT:
                action = REGISTER_ASSOCIATED

        # Apply action
        if action == REGISTER_IDLE:
            self.rftable.set_entry(RFEntry(vm_id=vm_id, vm_port=vm_port,
                                           eth_addr=eth_addr))
            self.log.info("Registering client port as idle (vm_id=%s, "
                          "vm_port=%i, eth_addr=%s)" % (format_id(vm_id),
                                                        vm_port, eth_addr))
        elif action == REGISTER_ASSOCIATED:
            entry.associate(vm_id, vm_port, eth_addr=eth_addr)
            self.rftable.set_entry(entry)
            self.log.info("Registering client port and associating to "
                          "datapath port (vm_id=%s, vm_port=%i, "
                          "eth_addr = %s, dp_id=%s, dp_port=%s)"
                          % (format_id(vm_id), vm_port, eth_addr,
                             format_id(entry.dp_id), entry.dp_port))

    def queue_routemod_ack(self, ct_id, vm_id, vm_port):
        self.ack_q.put((str(vm_id), 
                        PortConfig(vm_id=vm_id, vm_port=vm_port, operation_id=PCT_ROUTEMOD_ACK)))

    def send_route_mod(self, ct_id, rm):
        rm.add_option(Option.CT_ID(ct_id))
        self.dp_q.put((str(ct_id), rm))

    # Handle RouteMod messages (type ROUTE_MOD)
    #
    # Takes a RouteMod, replaces its VM id,port with the associated DP id,port
    # and sends to the corresponding controller
    def register_route_mod(self, rm):
        vm_id = rm.get_id()
        vm_port = rm.get_vm_port()

        # Find the (vmid, vm_port), (dpid, dpport) pair
        entry = self.rftable.get_entry_by_vm_port(vm_id, vm_port)
        translator = self.route_mod_translator[entry.dp_id]

        # If we can't find an associated datapath for this RouteMod,
        # drop it.
        if entry is None or entry.get_status() == RFENTRY_IDLE_VM_PORT:
            self.log.info("Received RouteMod destined for unknown "
                          "datapath - Dropping (vm_id=%s, vm_port=%d)" %
                          (format_id(vm_id), vm_port))
            return

        # Replace the VM id,port with the Datapath id.port
        rm.set_id(int(entry.dp_id))

        rms = []
        
        if rm.get_mod() is RMT_CONTROLLER:
            rms.extend(translator.handle_controller_route_mod(entry, rm))

        elif rm.get_mod() in (RMT_ADD, RMT_DELETE):
            rms.extend(translator.handle_route_mod(entry, rm))

            # Add vm_id to avoid installing flow entries to ports that are mapped to
            # different switches
            remote_dps = self.isltable.get_entries(vm_id=entry.vm_id,
                                                   rem_ct=entry.ct_id,
                                                   rem_id=entry.dp_id)

            for r in remote_dps:
                if r.get_status() == RFISL_ACTIVE:
                    local_rm = copy.deepcopy(rm)
                    remote_translator = self.route_mod_translator[int(r.dp_id)]
                    rms.extend(remote_translator.handle_isl_route_mod(r, local_rm))
        else:
            self.log.info("Received RouteMod with unknown type: %s " % rm)

        for rm in rms:
            self.send_route_mod(entry.ct_id, rm)

        if rms:
            self.queue_routemod_ack(entry.ct_id, vm_id, vm_port)
        else:
            # Trung: Send back an ACK immediately if no RM to be sent to PROXY. This is to fix the 
            # issue that RFClient stuck waiting for ACK.
            ack = PortConfig(vm_id=vm_id, vm_port=vm_port, operation_id=PCT_ROUTEMOD_ACK)
            self.ipc_send(RFCLIENT_RFSERVER_CHANNEL, str(vm_id), ack)

    # DatapathPortRegister methods
    def register_dp_port(self, ct_id, dp_id, dp_port, port_state):
        stop = self.config_dp(ct_id, dp_id)
        if stop:
            return

        entry = self.dpporttable.get_dp_port_info(ct_id=ct_id, 
                                                  dp_id=dp_id, 
                                                  dp_port=dp_port)
        if entry is None:
            entry = RFDPPortEntry(ct_id = ct_id, dp_id = dp_id, dp_port = dp_port, state=port_state)
            self.dpporttable.set_entry(entry)
            self.log.debug("Update DPPortTable with ct_id=%s, dp_id=%s, dp_port=%d" 
                          % (format_id(ct_id), format_id(dp_id), dp_port))
            entry = None
        else:
            entry.state = port_state
            
        # The logic down here is pretty much the same as register_vm_port
        action = None
        config_entry = self.config.get_config_for_dp_port(ct_id, dp_id,
                                                          dp_port)
        if config_entry is None:
            islconfs = self.islconf.get_entries_by_port(ct_id, dp_id, dp_port)
            if islconfs:
                action = REGISTER_ISL
            else:
                # Register idle DP awaiting for configuration
                action = REGISTER_IDLE
				# Should not create an entry on rftable at this state
                return
        else:
            entry = self.rftable.get_entry_by_vm_port(config_entry.vm_id,
                                                      config_entry.vm_port)
            # If there's no entry, we have no VM, register DP as idle
            if entry is None:
                action = REGISTER_IDLE
            # If there's an idle VM entry matching configuration, associate
            elif entry.get_status() == RFENTRY_IDLE_VM_PORT:
                action = REGISTER_ASSOCIATED

        # Apply action
        if action == REGISTER_IDLE:
            self.rftable.set_entry(RFEntry(ct_id=ct_id, dp_id=dp_id,
                                           dp_port=dp_port))
            self.log.info("Registering datapath port as idle (dp_id=%s, "
                          "dp_port=%i)" % (format_id(dp_id), dp_port))
        elif action == REGISTER_ASSOCIATED:
            entry.associate(dp_id, dp_port, ct_id)
            self.rftable.set_entry(entry)
            self.log.info("Registering datapath port and associating to "
                          "client port (dp_id=%s, dp_port=%i, vm_id=%s, "
                          "vm_port=%s)" % (format_id(dp_id), dp_port,
                                           format_id(entry.vm_id),
                                           entry.vm_port))
        elif action == REGISTER_ISL:
            self._register_islconf(islconfs, ct_id, dp_id, dp_port)

    def _register_islconf(self, c_entries, ct_id, dp_id, dp_port):
        for conf in c_entries:
            entry = None
            eth_addr = None
            if conf.rem_id != dp_id or conf.rem_ct != ct_id:
                entry = self.isltable.get_entry_by_addr(conf.rem_ct,
                                                        conf.rem_id,
                                                        conf.rem_port,
                                                        conf.rem_eth_addr)
                eth_addr = conf.eth_addr
            else:
                entry = self.isltable.get_entry_by_addr(conf.ct_id,
                                                        conf.dp_id,
                                                        conf.dp_port,
                                                        conf.eth_addr)
                eth_addr = conf.rem_eth_addr

            if entry is None:
                n_entry = RFISLEntry(vm_id=conf.vm_id, ct_id=ct_id,
                                     dp_id=dp_id, dp_port=dp_port,
                                     eth_addr=eth_addr)
                self.isltable.set_entry(n_entry)
                self.log.info("Registering ISL port as idle "
                              "(dp_id=%s, dp_port=%i, eth_addr=%s)" %
                              (format_id(dp_id), dp_port, eth_addr))
            elif entry.get_status() == RFISL_IDLE_DP_PORT:
                entry.associate(ct_id, dp_id, dp_port, eth_addr)
                self.isltable.set_entry(entry)
                n_entry = self.isltable.get_entry_by_remote(entry.ct_id,
                                                            entry.dp_id,
                                                            entry.dp_port,
                                                            entry.eth_addr)
                if n_entry is None:
                    n_entry = RFISLEntry(vm_id=entry.vm_id, ct_id=ct_id,
                                         dp_id=dp_id, dp_port=dp_port,
                                         eth_addr=entry.rem_eth_addr,
                                         rem_ct=entry.ct_id,
                                         rem_id=entry.dp_id,
                                         rem_port=entry.dp_port,
                                         rem_eth_addr=entry.eth_addr)
                    self.isltable.set_entry(n_entry)
                else:
                    n_entry.associate(ct_id, dp_id, dp_port, eth_addr)
                    self.isltable.set_entry(n_entry)
                self.log.info("Registering ISL port and associating to "
                              "remote ISL port (ct_id=%s, dp_id=%s, "
                              "dp_port=%s, rem_ct=%s, rem_id=%s, "
                              "rem_port=%s)" % (ct_id, format_id(dp_id),
                                                dp_port, entry.ct_id,
                                                format_id(entry.dp_id),
                                                entry.dp_port))
    # Handle the event when a port is removed from a datapath 
    def delete_dp_port(self, ct_id, dp_id, dp_port):
        entry = self.dpporttable.get_dp_port_info(ct_id=ct_id, 
                                                  dp_id=dp_id, 
                                                  dp_port=dp_port)
        if entry is not None:
            self.dpporttable.remove_entry(entry)
            
        action = None
        config_entry = self.config.get_config_for_dp_port(ct_id, dp_id,
                                                          dp_port)
        if config_entry is None:
            islconf_entries = self.islconf.get_entries_by_port(ct_id, dp_id, dp_port)
            entries = self.isltable.get_entries(ct_id=ct_id,
                                          dp_id=dp_id,
                                          dp_port=dp_port)
            for entry in entries:
                entry.make_idle(RFISL_IDLE_REMOTE)
                self.isltable.set_entry(entry)
            
            entries = self.isltable.get_entries(rem_ct=ct_id,
                                          rem_dp=dp_id,
                                          rem_port=dp_port)
            for entry in entries:
                entry.make_idle(RFISL_IDLE_DP_PORT)
                self.isltable.set_entry(entry)

        else:
            entry = self.rftable.get_entry_by_vm_port(config_entry.vm_id,
                                                      config_entry.vm_port)
            if entry is None:
                self.rftable.remove_entry(entry)
                if entry.get_status() == RFENTRY_ACTIVE:
                    self.reset_vm_port(entry.vm_id, entry.vm_port)
                    
                    translator = self.route_mod_translator[entry.dp_id]
                    rms = translator.dp_delete_flows(entry)
                    for rm in rms:
                        self.del_rm_q.append((time.time(), entry.ct_id, rm))

        # Apply action
        if action == REGISTER_IDLE:
            self.rftable.set_entry(RFEntry(ct_id=ct_id, dp_id=dp_id,
                                           dp_port=dp_port))
            self.log.info("Registering datapath port as idle (dp_id=%s, "
                          "dp_port=%i)" % (format_id(dp_id), dp_port))
        elif action == REGISTER_ASSOCIATED:
            entry.associate(dp_id, dp_port, ct_id)
            self.rftable.set_entry(entry)
            self.log.info("Registering datapath port and associating to "
                          "client port (dp_id=%s, dp_port=%i, vm_id=%s, "
                          "vm_port=%s)" % (format_id(dp_id), dp_port,
                                           format_id(entry.vm_id),
                                           entry.vm_port))
        elif action == REGISTER_ISL:
            self._register_islconf(islconfs, ct_id, dp_id, dp_port)

    def _register_islconf(self, c_entries, ct_id, dp_id, dp_port):
        for conf in c_entries:
            entry = None
            eth_addr = None
            if conf.rem_id != dp_id or conf.rem_ct != ct_id:
                entry = self.isltable.get_entry_by_addr(conf.rem_ct,
                                                        conf.rem_id,
                                                        conf.rem_port,
                                                        conf.rem_eth_addr)
                eth_addr = conf.eth_addr
            else:
                entry = self.isltable.get_entry_by_addr(conf.ct_id,
                                                        conf.dp_id,
                                                        conf.dp_port,
                                                        conf.eth_addr)
                eth_addr = conf.rem_eth_addr

            if entry is None:
                n_entry = RFISLEntry(vm_id=conf.vm_id, ct_id=ct_id,
                                     dp_id=dp_id, dp_port=dp_port,
                                     eth_addr=eth_addr)
                self.isltable.set_entry(n_entry)
                self.log.info("Registering ISL port as idle "
                              "(dp_id=%s, dp_port=%i, eth_addr=%s)" %
                              (format_id(dp_id), dp_port, eth_addr))
            elif entry.get_status() == RFISL_IDLE_DP_PORT:
                entry.associate(ct_id, dp_id, dp_port, eth_addr)
                self.isltable.set_entry(entry)
                n_entry = self.isltable.get_entry_by_remote(entry.ct_id,
                                                            entry.dp_id,
                                                            entry.dp_port,
                                                            entry.eth_addr)
                if n_entry is None:
                    n_entry = RFISLEntry(vm_id=entry.vm_id, ct_id=ct_id,
                                         dp_id=dp_id, dp_port=dp_port,
                                         eth_addr=entry.rem_eth_addr,
                                         rem_ct=entry.ct_id,
                                         rem_id=entry.dp_id,
                                         rem_port=entry.dp_port,
                                         rem_eth_addr=entry.eth_addr)
                    self.isltable.set_entry(n_entry)
                else:
                    n_entry.associate(ct_id, dp_id, dp_port, eth_addr)
                    self.isltable.set_entry(n_entry)
                self.log.info("Registering ISL port and associating to "
                              "remote ISL port (ct_id=%s, dp_id=%s, "
                              "dp_port=%s, rem_ct=%s, rem_id=%s, "
                              "rem_port=%s)" % (ct_id, format_id(dp_id),
                                                dp_port, entry.ct_id,
                                                format_id(entry.dp_id),
                                                entry.dp_port))

    def send_datapath_config_messages(self, ct_id, dp_id):
        rms = self.route_mod_translator[dp_id].configure_datapath()
        for rm in rms:
            self.send_route_mod(ct_id, rm) 

    def config_dp(self, ct_id, dp_id):
        if is_rfvs(dp_id):
            return True
        else:
            if (self.rftable.is_dp_registered(ct_id, dp_id) or
                self.isltable.is_dp_registered(ct_id, dp_id) or True):
                if dp_id not in self.route_mod_translator:
                    self.log.info("Configuring datapath (dp_id=%s)" % format_id(dp_id))
                    if dp_id in self.multitabledps:
                        self.route_mod_translator[dp_id] = NoviFlowMultitableRouteModTranslator(
                            dp_id, ct_id, self.rftable, self.isltable, self.log)
                    elif dp_id in self.satellitedps:
                        self.route_mod_translator[dp_id] = SatelliteRouteModTranslator(
                            dp_id, ct_id, self.rftable, self.isltable, self.log)
                    else:
                        self.route_mod_translator[dp_id] = DefaultRouteModTranslator(
                            dp_id, ct_id, self.rftable, self.isltable, self.log)
                    self.send_datapath_config_messages(ct_id, dp_id) 
            return False
    # DatapathDown methods
    def set_dp_down(self, ct_id, dp_id):
        # Trung: Remove RouteMod Translator, otherwise, when the sw restarts, it won't get configured
        try:
            del self.route_mod_translator[dp_id]
        except:
            pass

        for entry in self.dpporttable.get_entries(dp_id=dp_id):
            self.dpporttable.remove_entry(entry)
        for entry in self.rftable.get_dp_entries(ct_id, dp_id):
            # For every port registered in that datapath, put it down
            self.set_dp_port_down(entry.ct_id, entry.dp_id, entry.dp_port)
        for entry in self.isltable.get_dp_entries(ct_id, dp_id):
            entry.make_idle(RFISL_IDLE_REMOTE)
            self.isltable.set_entry(entry)
        for entry in self.isltable.get_entries(rem_ct=ct_id, rem_id=dp_id):
            entry.make_idle(RFISL_IDLE_DP_PORT)
            self.isltable.set_entry(entry)
        self.log.info("Datapath down (dp_id=%s)" % format_id(dp_id))

    def set_dp_port_down(self, ct_id, dp_id, dp_port):
        entry = self.rftable.get_entry_by_dp_port(ct_id, dp_id, dp_port)
        if entry is not None:
            # If the DP port is registered, delete it and leave only the
            # associated VM port. Reset this VM port so it can be reused.
            vm_id, vm_port = entry.vm_id, entry.vm_port
            entry.make_idle(RFENTRY_IDLE_VM_PORT)
            self.rftable.set_entry(entry)
            if vm_id is not None:
                self.reset_vm_port(vm_id, vm_port)
            self.log.debug("Datapath port down (dp_id=%s, dp_port=%i)" %
                           (format_id(dp_id), dp_port))

    def reset_vm_port(self, vm_id, vm_port):
        if vm_id is None:
            return
        self.ipc_send(RFCLIENT_RFSERVER_CHANNEL, str(vm_id),
                      PortConfig(vm_id=vm_id, vm_port=vm_port,
                                 operation_id=PCT_RESET))
        self.log.info("Resetting client port (vm_id=%s, vm_port=%i)" %
                      (format_id(vm_id), vm_port))

    # PortMap methods
    def map_port(self, vm_id, vm_port, vs_id, vs_port):
        entry = self.vmporttable.get_vm_port_info(vm_id, vm_port)
        if entry is not None:
            entry.update_vs(vs_id=vs_id, vs_port=vs_port)
            self.vmporttable.set_entry(entry)
        entry = None    
        entry = self.rftable.get_entry_by_vm_port(vm_id, vm_port)
        if entry is not None and entry.get_status() == RFENTRY_ASSOCIATED:
            # If the association is valid, activate it
            entry.activate(vs_id, vs_port)
            self.rftable.set_entry(entry)
            msg = DataPlaneMap(ct_id=entry.ct_id,
                               dp_id=entry.dp_id, dp_port=entry.dp_port,
                               vs_id=vs_id, vs_port=vs_port)
            self.ipc_send(RFSERVER_RFPROXY_CHANNEL, str(entry.ct_id), msg)

            dpport = self.dpporttable.get_dp_port_info(entry.ct_id,
                                                       entry.dp_id,
                                                       entry.dp_port)
            oper_id = PCT_MAP_SUCCESS
            if dpport.state ==  DP_PORT_UP:
                oper_id |= PCT_PORT_UP
            elif dpport.state == DP_PORT_DOWN:
                oper_id |= PCT_PORT_DOWN

            msg = PortConfig(vm_id=vm_id, vm_port=vm_port,
                             operation_id=oper_id)
            self.ipc_send(RFCLIENT_RFSERVER_CHANNEL, str(entry.vm_id), msg)
            self.log.info("Mapping client-datapath association "
                          "(vm_id=%s, vm_port=%i, dp_id=%s, "
                          "dp_port=%i, vs_id=%s, vs_port=%i)" %
                          (format_id(entry.vm_id), entry.vm_port,
                           format_id(entry.dp_id), entry.dp_port,
                           format_id(entry.vs_id), entry.vs_port))
    
    # Delete mapping configs from CONFIG table & also RFTable if the associations
    # exist.
    def delete_map_configs(self, **kwargs):
        count = 0
        cf_entries = self.config.get_entries(**kwargs)
        for cf_entry in cf_entries:
            self.config.remove_entry(cf_entry)
            rf_entry = self.rftable.get_entry_by_vm_port(cf_entry.vm_id, 
                                                         cf_entry.vm_port)
            if rf_entry is None:
                rf_entry = self.rftable.get_entry_by_dp_port(cf_entry.ct_id,
                                                             cf_entry.dp_id,
                                                             cf_entry.dp_port)
            if rf_entry is not None:
                self.rftable.remove_entry(rf_entry)
                if rf_entry.get_status() == RFENTRY_ACTIVE:
                    msg = DataPlaneMap(ct_id=rf_entry.ct_id,
                                       dp_id=rf_entry.dp_id, 
                                       dp_port=rf_entry.dp_port,
                                       vs_id=rf_entry.vs_id, 
                                       vs_port=rf_entry.vs_port, 
                                       operation_id=DCT_MAP_DELETE)
                    self.ipc.send(RFSERVER_RFPROXY_CHANNEL, 
                                  str(rf_entry.ct_id), msg)
                    self.log.info("Resetting RFProxy map table \
                    (dp_id=%s, dp_port=%i) - (vs_id=%s, vs_port=%i)" %
                                  (format_id(rf_entry.dp_id), 
                                   rf_entry.dp_port, format_id(rf_entry.vs_id), 
                                   rf_entry.vs_port))
                    
                    self.ipc.send(RFCLIENT_RFSERVER_CHANNEL, str(rf_entry.vm_id), 
                                  PortConfig(vm_id=rf_entry.vm_id, 
                                             vm_port=rf_entry.vm_port, 
                                             operation_id=PCT_RESET))
                    self.log.info("Resetting client port (vm_id=%s, vm_port=%i)" % 
                                  (format_id(rf_entry.vm_id), rf_entry.vm_port))
                    
                    # Put the RMs for deleting flow entries into queue
                    # which a thread will read and send to proxy for actual deletion 
                    translator = self.route_mod_translator[rf_entry.dp_id]
                    rms = translator.dp_delete_flows(rf_entry)
                    for rm in rms:
                        self.del_rm_q.append((time.time(), rf_entry.ct_id, rm))

            count += 1
            self.log.info("Successfully deleted a mapping (vm_id=%s, \
            vm_port=%i) - (dp_id=%s, dp_port=%i)" % (format_id(cf_entry.vm_id), 
                                                    cf_entry.vm_port, 
                                                    format_id(cf_entry.dp_id), 
                                                    cf_entry.dp_port))            
        return count
    
    # Add a mapping between a VM port & DP port
    def add_map_config(self, vm_id, vm_port, ct_id, dp_id, dp_port):
        if (vm_id is None or vm_port is None or
            ct_id is None or
            dp_id is None or dp_port is None):
            return False
        
        vm_port_conf = self.config.get_config_for_vm_port(vm_id=vm_id, 
                                                          vm_port=vm_port)
        dp_port_conf = self.config.get_config_for_dp_port(ct_id=ct_id, 
                                                          dp_id=dp_id, 
                                                          dp_port=dp_port)
        if vm_port_conf is not None or dp_port_conf is not None:
            return False # Can't map in-use ones
        
        cf_entry = RFConfigEntry(vm_id=vm_id, vm_port=vm_port,
                                 ct_id=ct_id, dp_id=dp_id, dp_port=dp_port)
        self.config.set_entry(cf_entry)
    
        vm_port_info = self.vmporttable.get_vm_port_info(vm_id=vm_id, 
                                                         vm_port=vm_port)
        dp_port_info = self.dpporttable.get_dp_port_info(ct_id=ct_id, 
                                                         dp_id=dp_id, 
                                                         dp_port=dp_port)
        if vm_port_info is None and dp_port_info is None:
            return True
        
        rf_entry = RFEntry()
        if vm_port_info is not None:
            rf_entry.update_vm_port(vm_id=vm_id, vm_port=vm_port,
                                    vs_id=None, 
                                    vs_port=None,
                                    eth_addr=vm_port_info.eth_addr)
            
        if dp_port_info is not None:
            rf_entry.update_dp_port(dp_id=dp_id, dp_port=dp_port, ct_id=ct_id)
        
        self.rftable.set_entry(rf_entry)
        
        if rf_entry.get_status() == RFENTRY_ACTIVE:
            msg = DataPlaneMap(ct_id=rf_entry.ct_id, 
                                          dp_id=rf_entry.dp_id,
                                          dp_port=rf_entry.dp_port, 
                                          vs_id=rf_entry.vs_id,
                                          vs_port=rf_entry.vs_port, 
                                          operation_id=DCT_MAP_ADD)
            self.ipc.send(RFSERVER_RFPROXY_CHANNEL, str(rf_entry.ct_id), msg)
            
            msg = PortConfig(vm_id=rf_entry.vm_id, vm_port=rf_entry.vm_port,
                             operation_id=PCT_MAP_SUCCESS)
            self.ipc.send(RFCLIENT_RFSERVER_CHANNEL, str(rf_entry.vm_id), msg)
            
            self.log.info("Successfully map between (vm_id=%s, vm_port=%i)"
                          "(dp_id=%s, dp_port=%i)" % 
                          (format_id(rf_entry.vm_id),
                           rf_entry.vm_port,
                           format_id(rf_entry.dp_id),
                           rf_entry.dp_port))
        return True
           
    # Update an existing mapping:
    # change the mapping of a vm_port to another dp_port
    # or change the mapping of dp_port to another vm_port
    def update_map_config(self, vm_id, vm_port, ct_id, dp_id, dp_port):       
        if vm_id is None or vm_port is None \
        or dp_id is None or dp_port is None or ct_id is None:
            return False
        
        vm_port_conf = self.config.get_config_for_vm_port(vm_id=vm_id, 
                                                          vm_port=vm_port)       
        dp_port_conf = self.config.get_config_for_dp_port(ct_id=ct_id, 
                                                          dp_id=dp_id, 
                                                          dp_port=dp_port)
        if vm_port_conf is not None and dp_port_conf is not None:
            return False # Both are in used, can't update
             
        if vm_port_conf is not None: # Map the vm_port to a new dp_port
            # Delete the existing mapping first
            if self.delete_map_configs(vm_id=vm_port_conf.vm_id, 
                                    vm_port=vm_port_conf.vm_port,
                                    ct_id=vm_port_conf.ct_id,
                                    dp_id=vm_port_conf.dp_id,
                                    dp_port=vm_port_conf.dp_port):
                pass
            else:
                return False
        
        if dp_port_conf is not None: # Map the dp_port to a new vm_port
            # Delete the existing mapping first
            if self.delete_map_configs(vm_id=dp_port_conf.vm_id, 
                                    vm_port=dp_port_conf.vm_port,
                                    ct_id=dp_port_conf.ct_id,
                                    dp_id=dp_port_conf.dp_id,
                                    dp_port=dp_port_conf.dp_port):             
                pass
            else:
                return False
        self.add_map_config(vm_id, vm_port, ct_id, dp_id, dp_port)
        return True

    def add_isl_config(self, vm_id, 
                       ct_id, dp_id, dp_port, eth_addr,
                       rem_ct, rem_id, rem_port, rem_eth_addr):
        entry = RFISLConfEntry(vm_id=vm_id,
                               ct_id=ct_id, dp_id=dp_id, dp_port=dp_port, eth_addr=eth_addr,
                               rem_ct=rem_ct, rem_dp=rem_dp, rem_port=rem_port, rem_eth_addr=rem_addr_eth)
        self.islconf.set_entry(entry)

        dpport = self.dpporttable.get_dp_port_info(ct_id=ct_id, dp_id=dp_id, dp_port=dp_port)
        r_dpport = self.dpporttable.get_dp_port_info(ct_id=rem_ct, dp_id=rem_id, dp_port=rem_port)
        entry = None
        r_entry = None
        if dpport is not None:
            entry = RFISLEntry(vm_id=vm_id, 
                               ct_id=ct_id, 
                               dp_id=dp_id, 
                               dp_port=dp_port,
                               eth_addr=eth_addr)
        if r_dpport is not None:
            r_entry = RFISLEntry(vm_id=vm_id, 
                               ct_id=rem_ct, 
                               dp_id=rem_dp, 
                               dp_port=rem_port,
                               eth_addr=rem_eth_addr)

        if entry is not None:
            if r_entry is not None:
                entry.associate(r_entry.ct_id, r_entry.dp_id, r_entry.dp_port, r_entry.eth_addr)
                r_entry.associate(entry.ct_id, entry.dp_id, entry.dp_port, entry.eth_addr) 
                self.islconf.set_entry(r_entry)
            self.islconf.set_entry(entry)
        elif r_entry is not None:
            self.islconf.set_entry(r_entry)

    def delete_isl_configs(self, **kwargs):
        cf_entries = self.islconf.get_entries(**kwargs)
        for cf_entry in cf_entries:
            self.islconf.remove_entry(cf_entry)
            entries = self.isltable.get_entries(ct_id=cf_entry.ct_id,
                                                dp_id=cf_entry.dp_id,
                                                dp_port=cf_entry.dp_port,
                                                eth_addr=cf_entry.eth_addr)
            
            entries.extend(self.isltable.get_entries(ct_id=cf_entry.rem_ct,
                                                dp_id=cf_entry.rem_id,
                                                dp_port=cf_entry.rem__port,
                                                eth_addr=cf_entry.rem_eth_addr))
            for entry in entries:
                self.isltable.remove_entry(entry)
        
        #TODO: Update flow table


if __name__ == "__main__":
    description = 'RFServer co-ordinates RFClient and RFProxy instances, ' \
                  'listens for route updates, and configures flow tables'
    epilog = 'Report bugs to: https://github.com/routeflow/RouteFlow/issues'

    config = os.path.dirname(os.path.realpath(__file__)) + "/config.csv"
    islconf = os.path.dirname(os.path.realpath(__file__)) + "/islconf.csv"

    parser = argparse.ArgumentParser(description=description, epilog=epilog)
    parser.add_argument('configfile', default=config,
                        help='VM-VS-DP mapping configuration file')
    parser.add_argument('-i', '--islconfig', default=islconf,
                        help='ISL mapping configuration file')
    parser.add_argument('-m', '--multitabledps', default='',
                        help='List of datapaths that support multiple tables')
    parser.add_argument('-s', '--satellitedps', default='',
                        help='List of datapaths that default forward to ISL peer')

    args = parser.parse_args()
    rfserver = RFServer(args.configfile, args.islconfig, args.multitabledps, args.satellitedps)
    # Initialize RPC interface
    rpcserver = RFServerRPC(rfserver)
