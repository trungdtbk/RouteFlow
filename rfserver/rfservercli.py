#!/usr/bin/env python
#-*- coding:utf-8 -*-

import logging
from cliff.app import App
from cliff.commandmanager import CommandManager
from cliff.command import Command

import xmlrpclib
import json
import sys

import rflib.defs as defs

def format_id(value):
        try:
            value = int(value)
            return defs.format_id(value)
        except ValueError, TypeError:
            return value
        
class DeleteCommand(Command):
    log = logging.getLogger(__name__)

    def get_parser(self, prog_name):
        parser = super(DeleteCommand, self).get_parser(prog_name)
        parser.add_argument('-vm_id', '--vm_id', type=str, required=False, default=None)
        parser.add_argument('-vm_port', '--vm_port', type=str, required=False, default=None)
        parser.add_argument('-dp_id', '--dp_id', type=str, required=False, default=None)
        parser.add_argument('-dp_port', '--dp_port', type=str, required=False, default=None)
        parser.add_argument('-ct_id', '--ct_id', type=str, required=False, default=0)

        return parser
        
    def take_action(self, parsed_args):
        vm_id = None if parsed_args.vm_id is None else int(str(parsed_args.vm_id), 16)
        vm_port = None if parsed_args.vm_port is None else int(str(parsed_args.vm_port))
        
        dp_id = None if parsed_args.dp_id is None else int(str(parsed_args.dp_id), 16)
        dp_port = None if parsed_args.dp_port is None else int(str(parsed_args.dp_port))
        ct_id = None if parsed_args.ct_id is None else int(str(parsed_args.ct_id))
        
        rfserver = self.app.rfserver
        result = rfserver.delete_single_mapping(vm_id=vm_id, vm_port=vm_port, 
                                                ct_id=ct_id, dp_id=dp_id, dp_port=dp_port)
        if result:
            self.app.log.info("Delete operation successful")
        else:
            self.app.log.info("Delete operation failed")

class UpdateCommand(Command):
    log = logging.getLogger(__name__)

    def get_parser(self, prog_name):
        parser = super(UpdateCommand, self).get_parser(prog_name)
        parser.add_argument('-vm_id', '--vm_id', type=str, required=True, default=None)
        parser.add_argument('-vm_port', '--vm_port', type=str, required=True, default=None)
        parser.add_argument('-dp_id', '--dp_id', type=str, required=True, default=None)
        parser.add_argument('-dp_port', '--dp_port', type=str, required=True, default=None)
        parser.add_argument('-ct_id', '--ct_id', type=str, required=False, default=0)

        return parser
        
    def take_action(self, parsed_args):
        vm_id = None if parsed_args.vm_id is None else int(str(parsed_args.vm_id), 16)
        vm_port = None if parsed_args.vm_port is None else int(str(parsed_args.vm_port))
        
        dp_id = None if parsed_args.dp_id is None else int(str(parsed_args.dp_id), 16)
        dp_port = None if parsed_args.dp_port is None else int(str(parsed_args.dp_port))
        ct_id = None if parsed_args.ct_id is None else int(str(parsed_args.ct_id))
        
        rfserver = self.app.rfserver
        result = rfserver.update_single_mapping(vm_id=vm_id, vm_port=vm_port, ct_id=ct_id, dp_id=dp_id, dp_port=dp_port)
        if result:
            self.app.log.info("Delete operation successful")
        else:
            self.app.log.info("Delete operation failed")

class ViewCommand(Command):    
    def get_parser(self, prog_name):
        parser = super(ViewCommand, self).get_parser(prog_name)
        parser.add_argument('view', nargs='?', default='rftable')
        parser.add_argument('-filter', '--filter', type=str, required=False, default=None)

        return parser
    
    def take_action(self, parsed_args):
        view = str(parsed_args.view)
        filter = str(parsed_args.filter)
        
        if view == 'rftable':
            self.view_rftable()
        elif view == 'isltable':
            self.view_isltable();
        elif view == 'config':
            self.view_config()
        elif view == 'vmport':
            self.view_vmports()
        elif view == 'dpport':
            self.view_dpports()
        elif view == "islconfig":
            self.view_islconfig()
        else:
            self.app.stdout.write("Unknown option\n")
            
    def view_rftable(self, **kwargs):
        rfserver = self.app.rfserver
        entries = json.loads(rfserver.get_rftable())
        
        self.app.stdout.write("{:<18} {:<8} {:<18} {:<8} {:<8} {:<8} {:<18} {:<8}\n\n".\
                              format('vm_id', 'vm_port', 'eth_addr',\
                                     'ct_id', 'dp_id','dp_port', 'vs_id', 'vs_port'))
        for entry in entries:
            self.app.stdout.write("{:<18} {:<8} {:<18} {:<8} {:<8} {:<8} {:<18} {:<8}\n".\
                                  format(format_id(entry['vm_id']), entry['vm_port'], entry['eth_addr'],\
                                         entry['ct_id'], entry['dp_id'], entry['dp_port'], entry['vs_id'], entry['vs_port']))
         
        self.app.stdout.write("\n")
        
    def view_isltable(self, **kwargs):
        rfserver = self.app.rfserver
        entries = json.loads(rfserver.get_rfisltable())
        self.app.stdout.write("{:<18} {:<8} {:<8} {:<8} {:<18} {:<8} {:<8} {:<8} {:<18}\n\n".\
                              format('vm_id', 'ct_id', 'dp_id', 'dp_port',\
                                     'eth_addr', 'rem_ct','rem_dp', 'rm_port', 'rem_addr'))
        for entry in entries:
            self.app.stdout.write("{:<18} {:<8} {:<8} {:<8} {:<18} {:<8} {:<8} {:<8} {:<18}\n".\
                                  format(format_id(entry['vm_id']), entry['ct_id'], entry['dp_id'], entry['dp_port'],\
                                         entry['eth_addr'], entry['rem_ct'], entry['rem_id'], entry['rem_port'], entry['rem_eth_addr']))
         
        self.app.stdout.write("\n")
    
    def view_islconfig(self, **kwargs):
        rfserver = self.app.rfserver
        entries = json.loads(rfserver.get_rfislconfig())
        self.app.stdout.write("{:<18} {:<8} {:<8} {:<8} {:<18} {:<8} {:<8} {:<8} {:<18}\n\n".\
                              format('vm_id', 'ct_id', 'dp_id', 'dp_port',\
                                     'eth_addr', 'rem_ct','rem_dp', 'rm_port', 'rem_addr'))
        for entry in entries:
            self.app.stdout.write("{:<18} {:<8} {:<8} {:<8} {:<18} {:<8} {:<8} {:<8} {:<18}\n".\
                                  format(format_id(entry['vm_id']), entry['ct_id'], entry['dp_id'], entry['dp_port'],\
                                         entry['eth_addr'], entry['rem_ct'], entry['rem_id'], entry['rem_port'], entry['rem_eth_addr']))
         
        self.app.stdout.write("\n")
        
    def view_config(self, **kwargs):
        rfserver = self.app.rfserver
        entries = json.loads(rfserver.get_rfconfig())
        self.app.stdout.write("{:<18} {:<8} {:<8} {:<8} {:<8}\n\n".\
                              format('vm_id', 'vm_port', 'ct_id', 'dp_id', 'dp_port'))
        for entry in entries:
            self.app.stdout.write("{:<18} {:<8} {:<8} {:<8} {:<8}\n".\
                                  format(format_id(entry['vm_id']), entry['vm_port'], entry['ct_id'], entry['dp_id'], entry['dp_port']))
         
        self.app.stdout.write("\n")
        
    def view_vmports(self, **kwargs):
        rfserver = self.app.rfserver
        entries = json.loads(rfserver.get_rfvmports())
        self.app.stdout.write("{:<18} {:<8} {:<8} {:<8} {:<8}\n\n".\
                              format('vm_id', 'vm_port', 'vs_id', 'vs_port','eth_addr'))
        for entry in entries:
            self.app.stdout.write("{:<18} {:<8} {:<8} {:<8} {:<8}\n".\
                                  format(format_id(entry['vm_id']), entry['vm_port'], entry['vs_id'], entry['vs_port'], entry['eth_addr']))
         
        self.app.stdout.write("\n")
        
    def view_dpports(self, **kwargs):
        rfserver = self.app.rfserver
        entries = json.loads(rfserver.get_rfdpports())
        self.app.stdout.write("{:<8} {:<8} {:<8}\n\n".\
                              format('ct_id', 'dp_port', 'dp_port'))
        for entry in entries:
            self.app.stdout.write("{:<8} {:<8} {:<8}\n".\
                                  format(entry['ct_id'], entry['dp_id'], entry['dp_port']))
         
        self.app.stdout.write("\n")
      
class RFServerCLI(App):
    log = logging.getLogger(__name__)
    log.setLevel(logging.INFO)
    def __init__(self):
        self.rfserver = xmlrpclib.ServerProxy('http://localhost:8008')
        command = CommandManager('RFServer')
        super(RFServerCLI, self).__init__(
            description = 'RFServer',
            version = '0.1',
            command_manager = command,)
        commands = {
            'delete': DeleteCommand,
            'update': UpdateCommand,
            'view': ViewCommand,}
        for k,v in commands.iteritems():
            command.add_command(k, v)
    
    def initialize_app(self, argv):
        self.log.debug('initialize_app')
    def prepare_to_run_command(self, cmd):
        self.log.debug('prepare_to_run_command %s', cmd.__class__.__name__)
    
    def clean_up(self, cmd, result, err):
        self.log.debug('clean_up %s', cmd.__class__.__name__)
        if err:
            self.log.debug('got an error: %s', err)
            

def main(argv=sys.argv[1:]):
        myapp = RFServerCLI()
        return myapp.run(argv)
    
if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))