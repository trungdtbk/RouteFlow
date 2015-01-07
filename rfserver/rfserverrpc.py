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
    
    def delete_single_mapping(self, vm_id=None, vm_port=None, ct_id=0, dp_id=None, dp_port=None):
        if vm_id is not None:
            vm_id = int(vm_id, 16)
        if dp_id is not None:
            dp_id = int(dp_id, 16)
        return self.rfserver.delete_single_mapping(vm_id=vm_id, vm_port=vm_port,
                                                   ct_id=ct_id, dp_id=dp_id, dp_port=dp_port)
    
    def update_single_mapping(self, vm_id=None, vm_port=None, ct_id=0, dp_id=None, dp_port=None):
        if vm_id is not None:
            vm_id = int(vm_id, 16)
        if dp_id is not None:
            dp_id = int(dp_id, 16)
        return self.rfserver.update_single_mapping(vm_id=vm_id, vm_port=vm_port,
                                                   ct_id=ct_id, dp_id=dp_id, dp_port=dp_port)