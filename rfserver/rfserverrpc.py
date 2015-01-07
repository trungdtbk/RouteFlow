import logging

import json
from SimpleXMLRPCServer import SimpleXMLRPCServer

class RFServerRPC():
    def __init__(self, rfserver):
        self.rfserver = rfserver
        self.rpcserver = SimpleXMLRPCServer(("localhost", 8008))
        
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
    
    def delete_single_mapping(self, vm_id=None, vm_port=None, ct_id=None, dp_id=None, dp_port=None):
        return self.rfserver.delete_single_mapping(vm_id=vm_id, vm_port=vm_port,
                                                   ct_id=ct_id, dp_id=dp_id, dp_port=dp_port)
        #return True
    
    def update_single_mapping(self, vm_id=None, vm_port=None, ct_id=None, dp_id=None, dp_port=None):
        return self.rfserver.update_single_mapping(vm_id=vm_id, vm_port=vm_port,
                                                     ct_id=ct_id, dp_id=dp_id, dp_port=dp_port)