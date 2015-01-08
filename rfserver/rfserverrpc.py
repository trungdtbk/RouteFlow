import logging

import json
from SimpleXMLRPCServer import SimpleXMLRPCServer

class RFServerRPC():
    def __init__(self, rfserver):
        self.rfserver = rfserver
        self.rpcserver = SimpleXMLRPCServer(("localhost", 8008), allow_none=True)
        
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
        if vm_id is not None:
            vm_id = int(vm_id, 16)
        if dp_id is not None:
            dp_id = int(dp_id, 16)
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