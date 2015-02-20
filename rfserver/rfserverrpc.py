import logging

import json
from SimpleXMLRPCServer import SimpleXMLRPCServer

class RFServerRPC():
    def __init__(self, rfserver):
        self.rfserver = rfserver
        self.rpcserver = SimpleXMLRPCServer(("", 8008), logRequests=False, allow_none=True)
        
        self.rpcserver.register_instance(RPC_processor(self.rfserver))
        print "RPC server started"
        self.rpcserver.serve_forever()
            
class RPC_processor():
    def __init__(self, rfserver):
        self.rfserver = rfserver
        
    def get_rftable(self):
        entries = self.rfserver.rftable.get_entries()
        results = []
        for entry in entries:
            results.append(entry.to_dict())
            
        return json.dumps(results)
    
    def get_rfconfig(self):
        entries = self.rfserver.config.get_entries()
        results = []
        for entry in entries:
            results.append(entry.to_dict())
            
        return json.dumps(results)
    
    def get_rfislconfig(self):
        entries = self.rfserver.islconf.get_entries()
        results = []
        for entry in entries:
            results.append(entry.to_dict())
            
        return json.dumps(results)
    
    def get_rfisltable(self):
        entries = self.rfserver.isltable.get_entries()
        results = []
        for entry in entries:
            results.append(entry.to_dict())
            
        return json.dumps(results)
    
    def get_rfvmports(self):
        entries = self.rfserver.vmporttable.get_entries()
        results = []
        for entry in entries:
            results.append(entry.to_dict())
            
        return json.dumps(results)
    
    def get_rfdpports(self):
        entries = self.rfserver.dpporttable.get_entries()
        results = []
        for entry in entries:
            results.append(entry.to_dict())
            
        return json.dumps(results)
    
    def delete_map_configs(self, vm_id=None, vm_port=None, ct_id=None, dp_id=None, dp_port=None):        
        kwargs = {}
        
        if vm_id is not None:
            kwargs['vm_id'] = int(vm_id, 16)
        
        if vm_port is not None:
            kwargs['vm_port'] = vm_port
            
        if ct_id is not None:
            kwargs['ct_id'] = ct_id
            
        if dp_id is not None:
            kwargs['dp_id'] = int(dp_id, 16)
        
        if dp_port is not None:
            kwargs['dp_port'] = dp_port
            
        return self.rfserver.delete_map_configs(**kwargs)
    
    def add_map_config(self, vm_id, vm_port, ct_id, dp_id, dp_port):
        if (vm_id is None or vm_port is None or
            ct_id is None or
            dp_id is None or dp_port is None):
            return False
        try:
            vm_id = int(vm_id, 16)
            dp_id = int(dp_id, 16)
            ct_id = int(ct_id)
            vm_port = int(vm_port)
            dp_port = int(dp_port)
        except:
            return False
            
        return self.rfserver.add_map_config(vm_id=vm_id, vm_port=vm_port, 
                                            ct_id=ct_id, 
                                            dp_id=dp_id, dp_port=dp_port)
    
    def update_map_config(self, vm_id, vm_port, ct_id, dp_id, dp_port):
        if vm_id is not None:
            vm_id = int(vm_id, 16)
        if dp_id is not None:
            dp_id = int(dp_id, 16)
        return self.rfserver.update_map_config(vm_id=vm_id, vm_port=vm_port,
                                               ct_id=ct_id,
                                               dp_id=dp_id, dp_port=dp_port)

    def delete_isl_configs(self, vm_id=None, ct_id=None, dp_id=None, dp_port=None, eth_addr=None,
                                 rem_ct=None, rem_id=None, rem_port=None, rem_eth_addr=None):        
        kwargs = {}
        
        if vm_id is not None:
            kwargs['vm_id'] = int(vm_id, 16)
        
        if ct_id is not None:
            kwargs['ct_id'] = ct_id
            
        if dp_id is not None:
            kwargs['dp_id'] = int(dp_id, 16)
        
        if dp_port is not None:
            kwargs['dp_port'] = dp_port
        
        if eth_addr is not None:
            kwargs['eth_addr'] = eth_addr
   
        if rem_ct is not None:
            kwargs['rem_ct'] = rem_ct

        if rem_id is not None:
            kwargs['rem_id'] = rem_id

        if rem_port is not None:
            kwargs['rem_port'] = rem_port

        if rem_eth_addr is not None:
            kwargs['rem_eth_addr'] = rem_eth_addr

        return self.rfserver.delete_isl_configs(**kwargs)
    
    def add_isl_config(self, vm_id, ct_id, dp_id, dp_port, eth_addr,
                             rem_ct, rem_id, rem_port, rem_eth_addr):
        if (vm_id is None or 
            ct_id is None or
            dp_id is None or 
            dp_port is None or
            eth_addr is None or
            rem_ct is None or
            rem_id is None or
            rem_port is None or
            rem_eth_addr is None):
            return False
        try:
            vm_id = int(vm_id, 16)
            dp_id = int(dp_id, 16)
            ct_id = int(ct_id)
            dp_port = int(vm_port)
            rem_id = int(rem_id, 16)
            rem_ct = int(rem_ct)
            rem_port = int(dp_port)
        except:
            return False
            
        return self.rfserver.add_isl_config(vm_id=vm_id, vm_port=vm_port, 
                                            ct_id=ct_id, 
                                            dp_id=dp_id, dp_port=dp_port,
                                            eth_addr=eth_addr,
                                            rem_ct=rem_ct,
                                            rem_id=rem_id,
                                            rem_port=rem_port,
                                            rem_eth_addr=rem_eth_addr)
 
