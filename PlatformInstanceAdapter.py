import ansys.platform.instancemanagement as pypim
import os
import sys

import pyaedt
import pyaedt.common_rpc


# Initializes PyAedt scripting environment
# PlatformInstanceAdapter.create_instance creates a new instance
# PlatformInstanceAdapter.reconnect reuses a running instance

# - PyAedt interface is a layer on top of AnsysEDT python objects 
# - PlatformInstanceAdapter (creates and) connects to AnsysEDT container  
# - AnsysEDT python objects are custom dynamic CPython objects 
#      - correspond to AnsysEDT's COM objects whose interface pointers are held inside the ansysedt process. 
#      - Python doesn't hold interface pointers, just an ID.
#      - GRPC used to make calls from CPython to ansysedt process

# Assumptions:
# pypim must create an instance using AnsysEM 2023 R1 image 
# The container must run:
#        ansysedt process as a grpc server
#        PyAEDT's service manager as a rpyc server
# The container must expose another port for rpyc session

# Ports:
# servicemanager :port 17878,
# rpyc :  port 17880,
# grpc :  port 17881


class PlatformInstanceAdapter:
    pim_object = None
    def __init__(self):
        self.services = []
        self.service_manager_connection = None
        self.session_connection = None
        self.grpc_connection = None
        self.aedt = None

    @property
    def pim(self):
        return PlatformInstanceAdapter.pim_object
        
    def init_vars(self,connection):
        name = connection.name
        if name == "servicemanager":
            self.service_manager_connection = connection
        elif name == "rpyc":
            self.session_connection = connection
        elif name == "grpc":
            self.grpc_connection = connection            
                   
    def create_pim_instance(self,product_name="aedt-pyaedt"):
        if not self.pim:
            return None
        self.pim.list_definitions()
        aedt = self.pim.create_instance(product_name=product_name)
        if aedt:
            aedt.wait_for_ready()
        else:
            print("Unable to create an instance for %s" % product_name)
        self.aedt = aedt
        return aedt
                        
    def delete(self):
        global oDesktop
        if not self.aedt:
            return False
        print("About to delete the instance: %s" % str(self))
        oDesktop = None
        self.aedt.delete()
        print("Deleted the instance")
        
        self.services = []
        self.service_manager_connection = None
        self.session_connection = None
        self.grpc_connection = None
        self.aedt = None
        
        
    def get_desktop_plugin_path(self):
        desktopPluginDir = ""
        ansysedt_client_basedir = os.path.join(os.getcwd(),'client231')
        if os.path.exists(ansysedt_client_basedir):
            desktopPluginDir = os.path.join(ansysedt_client_basedir,'PythonFiles/DesktopPlugin')
        else:
            ansysedt_client_basedir = os.path.dirname(__file__)
            if os.path.exists(ansysedt_client_basedir):
                desktopPluginDir = os.path.join(ansysedt_client_basedir,'client231/PythonFiles/DesktopPlugin')
            
        return desktopPluginDir
            
    def connect_to_aedt(self):
        """Initializes AEDT scripting environment, specially the oDesktop object"""
        # Add the location of DesktopPlugin python files to system path which is needed to import ScriptEnv module 
        # Change the ansysedt_client_basedir path as needed
        desktopPluginDir = self.get_desktop_plugin_path()
        if desktopPluginDir:
            if not (desktopPluginDir in sys.path):
                sys.path.append(desktopPluginDir)
        else:
            return False
        try:
            print("AnsysEDT to be connected using grpc : %s" % str(self.grpc_connection))
            import ScriptEnv
            ScriptEnv.Initialize("",machine=self.grpc_connection.machine,port=self.grpc_connection.port)
            self.grpc_connection.connected = True
            print("Connected to AnsysEDT using grpc : %s" % str(self.grpc_connection))
        except:
            print("Failed to connect to AnsysEDT using %s" % str(self.grpc_connection))
        return self.grpc_connection.connected

    def connect_to_pyaedt(self):
        """Initializes PyAEDT scripting environment using  connect_to_aedt. Also connects to a PyAEDT session running on the container"""
        if not self.grpc_connection:
            print("Invalid disconnected instance." )
            return False

        if self.grpc_connection.connected:
            print("Already connected to PyAEDT session" )
            return self.session_connection
        
        
        self.connect_to_aedt()
        client1 = None
        if self.grpc_connection.connected:
            pyaedt.settings.remote_rpc_service_manager_port = self.service_manager_connection.port
            client1 = pyaedt.common_rpc.create_session(self.service_manager_connection.machine,client_port=self.session_connection.port)    
            self.service_manager_connection.connected = True
            if client1:
                pyaedt.settings.use_grpc_api = True
                client1.aedt(port=self.grpc_connection.port,non_graphical=True)            
                self.session_connection.connected = True
            
        self.session_connection.client = client1
        print("Connected to PyAEDT session" )
        return self.session_connection
            
    def __repr__(self):
        if not self.grpc_connection:
            return "PlatformInstanceAdapter: not yet connected to an instance of AEDT" 
        return "%s \n %s" % (str(self.aedt), str(self.grpc_connection))

        
    @classmethod       
    def select_instance(cls,name):
        if not self.pim:
            return None
        instances = list(cls.list_instances())
        ## if no name is provided, select the first one
        if instances and not name:
            return instances[0]
        
        # select the specified one
        for inst in instances:
            if name == inst.name:
                return inst
        return None
        
    @classmethod
    def list_instances(cls,substring="aedt"):
        if cls.connect():
            for inst in cls.pim_object.list_instances():
                if inst.ready and substring in inst.name:
                    yield inst

    @classmethod
    def print_instances(cls):
        if not cls.connect():
            return 
        print("\nAll AnsysEDT instances:")
        for inst in cls.list_instances():
            print(["Definition: %s, Name: %s, address=%s    " % 
                   (inst.definition_name.split("/")[1],
                    inst.name.split("/")[1],
                    inst.services["grpc"].uri.split(":")) ])                    
                   
                    
    @classmethod
    def connect(cls):
        temporary_config = False
        if temporary_config:
            # target the PIM with AEDT configured
            os.environ["ANSYS_PLATFORM_INSTANCEMANAGEMENT_CONFIG"]="/home/jovyan/shared/plule/pypim-aedt.json"
        if not cls.pim_object:
            cls.pim_object = pypim.connect()     
        return cls.pim_object
            
            
    @classmethod
    def create_instance(cls):
        """Creates a new instance using PIM and returns an instance adapter"""
        pim_adapter = cls()
        cls.connect()
        aedt = pim_adapter.create_pim_instance()
        if aedt:
            pim_adapter.services = [ServiceConnection(aedt.services,service)  for service in aedt.services]        
            for conn in pim_adapter.services:
                pim_adapter.init_vars(conn)
        
        return pim_adapter

    @classmethod
    def reconnect(cls,instance_name=""):
        """Not yet tested. Connects to the instance of name instance_name using PIM, and returns an instance adapter"""
        pim_adapter = cls()
        cls.connect()
        aedt = cls.select_instance(instance_name)
        if aedt:
            pim_adapter.services = [ServiceConnection(aedt.services,service)  for service in aedt.services]        
            for conn in pim_adapter.services:
                pim_adapter.init_vars(conn)
        
        return pim_adapter

        
class ServiceConnection:
    def __init__(self, services, service_name):
        self.name = service_name
        connection_info = services[service_name].uri.split(":")
        self.machine = connection_info[-2]
        self.port = int(connection_info[-1])
        self.connected = False
        self.client = None ## only for session connection
        

    def __repr__(self):
        if self.connected:
            state =  "connected" 
        else:
            state = "not connected"
        return "%s : IP address: %s, port %d, state: %s" % (self.name, self.machine, self.port, state)

