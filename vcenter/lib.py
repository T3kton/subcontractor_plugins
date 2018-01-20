import logging
import time
import re

from pyVim import connect
from pyVmomi import vim

CLEAN_POWER_DOWN_COUNT = 20

CREATE_GROUP = ''
CREATE_GROUPS = []
CREATE_FLAGS = ''
CREATE_OS_TYPE_ID = 'Ubuntu_64'

BOOT_ORDER_MAP = { 'hdd': 'HDD', 'net': 'NET', 'cd': 'CD', 'usb': 'USB' }

NET_CLASS_LIST = ( 'vim.vm.device.VirtualE1000',
                   'vim.vm.device.VirtualE1000e',
                   'vim.vm.device.VirtualPCNet32',
                   'vim.vm.device.VirtualVmxnet',
                   'vim.vm.device.VirtualVmxnet2',
                   'vim.vm.device.VirtualVmxnet3'
                 )


class MOBNotFound( Exception ):
  pass


def _connect( paramaters ):
  # work arround invalid SSL
  import ssl
  _create_unverified_https_context = ssl._create_unverified_context
  ssl._create_default_https_context = _create_unverified_https_context
  # TODO: flag fortrusting SSL of connection, also there is a paramater to Connect for verified SSL

  logging.debug( 'vcenter: connecting to "{0}" with user "{1}"'.format( paramaters[ 'host' ], paramaters[ 'username' ] ) )

  return connect.Connect( host=paramaters[ 'host' ], user=paramaters[ 'username' ], pwd=paramaters[ 'password' ] )


def _disconnect( si ):
  connect.Disconnect( si )


def _taskWait( task ):
  while True:
    if task.info.state not in ( 'running', 'queued' ):
      return

    try:
      logging.debug( 'vmware: Waiting {0}% Complete ...'.format( task.info.progress ) )
    except AttributeError:
      logging.debug( 'vmware: Waiting ...' )

    time.sleep( 1 )


def _getDatacenter( si, name ):
  for item in si.content.rootFolder.childEntity:
    if item.__class__.__name__ == 'vim.Datacenter' and item.name == name:
      return item

  raise MOBNotFound( 'Datacenter "{0}" not found'.format( name ) )


def _getResourcePool( dc, name ):  # TODO: recursive folder search
  for item in dc.hostFolder.childEntity:
    if item.__class__.__name__ in ( 'vim.ComputeResource', 'vim.ClusterComputeResource' ) and item.name == name:
      return item.resourcePool

    if item.__class__.__name__ in ( 'vim.ResourcePool', ) and item.name == name:
      return item

  raise MOBNotFound( 'Cluster/ResourcePool "{0}" not found'.format( name ) )


def _getHost( rp, name ):
  for host in rp.owner.host:
    if host.name == name:
      return host

  raise MOBNotFound( 'Host "{0}" in "{0}" not found'.format( name, rp.name ) )


def _getDatastore( dc, name ):
  for ds in dc.datastore:
    if ds.name == name:
      return ds

  raise MOBNotFound( 'Datastore "{0}" in "{0}" not found'.format( name, dc.name ) )


def _getNetwork( host, name ):
  for network in host.network:
    if network.name == name:
      return network

  raise MOBNotFound( 'Network "{0}" in "{0}" not found'.format( name, host.name ) )


def _getVM( si, vm_uuid ):
  cont = si.RetrieveContent()
  vm = cont.searchIndex.FindByUuid( None, vm_uuid, True, True )

  if vm is None:
    raise MOBNotFound( 'vcenter: unable to find vm "{0}"'.format( vm_uuid ) )

  return vm


def _genPaths( vm_name, disk_list, datastore ):
  vmx_file_path = '[{0}] {1}/{1}.vmx'.format( datastore.name, vm_name )

  disk_filepath_list = []
  for disk in disk_list:
    disk_filepath_list.append( '[{0}] {1}/{2}.vmdk'.format( datastore.name, vm_name, disk[ 'name' ] ) )

  logging.debug( 'vcenter: vm path: "{0}", disk Paths {1}'.format( vmx_file_path, disk_filepath_list ) )

  return vmx_file_path, disk_filepath_list


def host_list( paramaters ):
  # returns a list of hosts in a resource
  # host must have paramater[ 'min_memory' ] aviable in MB
  # orderd by paramater[ 'cpu_scaler' ] * % cpu remaning + paramater[ 'memory_scaler' ] * % mem remaning
  connection_paramaters = paramaters[ 'connection' ]
  logging.info( 'vcenter: getting Host List for dc: "{0}"  rp: "{1}"'.format( paramaters[ 'datacenter' ], paramaters[ 'cluster' ] ) )
  paramaters[ 'min_memory' ] = int( paramaters[ 'min_memory' ] )
  si = _connect( connection_paramaters )
  try:
    dataCenter = _getDatacenter( si, paramaters[ 'datacenter' ] )
    resourcePool = _getResourcePool( dataCenter, paramaters[ 'cluster' ] )

    host_map = {}
    for host in resourcePool.owner.host:
      total_memory = host.summary.hardware.memorySize / 1024.0 / 1024.0
      memory_aviable = total_memory - host.summary.quickStats.overallMemoryUsage
      if memory_aviable < paramaters[ 'min_memory' ]:
        logging.debug( 'vcenter: host "{0}", low aviable ram: "{1}"'.format( host.name, memory_aviable ) )
        continue

      total_cpu = host.summary.hardware.numCpuCores * host.summary.hardware.cpuMhz
      cpu_aviable = total_cpu - host.summary.quickStats.overallCpuUsage

      host_map[ host.name ] = ( int( paramaters[ 'memory_scaler' ] ) * ( memory_aviable / total_memory ) ) + ( int( paramaters[ 'cpu_scaler' ] ) * ( cpu_aviable / total_cpu ) )

    logging.debug( 'vcenter: host_map {0}'.format( host_map ) )

    result = list( host_map.keys() )
    result.sort( key=lambda a: host_map[ a ] )

    return { 'host_list': result }

  finally:
    _disconnect( si )


def create_datastore( paramaters ):
  connection_paramaters = paramaters[ 'connection' ]
  logging.info( 'vcenter: creating datastores: "{0}"'.format( paramaters[ 'name' ] ) )
  si = _connect( connection_paramaters )
  try:
    dataCenter = _getDatacenter( si, paramaters[ 'datacenter' ] )
    resourcePool = _getResourcePool( dataCenter, paramaters[ 'host' ] )
    host = _getHost( resourcePool, paramaters[ 'host' ] )

    dss = host.configManager.datastoreSystem
    ss = host.configManager.storageSystem

    disk_list = []
    for lun in ss.storageDeviceInfo.scsiLun:
      disk_list.append( { 'model': lun.model, 'path': lun.devicePath } )

    spec = None
    for i in range( 0, len( disk_list ) ):
      disk = disk_list[ i ]
      if disk[ 'model' ] == paramaters[ 'model' ]:
        spec = dss.QueryVmfsDatastoreCreateOptions( disk[ 'path' ] )[0].spec
        del disk_list[ i ]
        break

    if spec is None:
      raise ValueError( 'Unable to find an aviable disk with model "{0}"'.format( paramaters[ 'model' ] ) )

    spec.vmfs.volumeName = paramaters[ 'name' ]

    dss.CreateVmfsDatastore( spec )

    return { 'done': True }

  finally:
    _disconnect( si )


def datastore_list( paramaters ):
  # returns a list of hosts in a resource
  # host must have paramater[ 'min_memory' ] aviable in MB
  # orderd by paramater[ 'cpu_scaler' ] * % cpu remaning + paramater[ 'memory_scaler' ] * % mem remaning
  connection_paramaters = paramaters[ 'connection' ]
  logging.info( 'vcenter: getting Datastore List for dc: "{0}" rp: "{1}" host: "{2}"'.format( paramaters[ 'datacenter' ], paramaters[ 'cluster' ], paramaters[ 'host' ] ) )
  paramaters[ 'min_free_space' ] = int( paramaters[ 'min_free_space' ] )
  try:
    paramaters[ 'name_regex' ] = re.compile( paramaters[ 'name_regex' ] )
  except TypeError:
    pass

  si = _connect( connection_paramaters )
  try:
    dataCenter = _getDatacenter( si, paramaters[ 'datacenter' ] )
    resourcePool = _getResourcePool( dataCenter, paramaters[ 'cluster' ] )
    host = _getHost( resourcePool, paramaters[ 'host' ] )

    result = []
    for datastore in host.datastore:
      if datastore.summary.freeSpace / 1024.0 / 1024.0 / 1024.0 < paramaters[ 'min_free_space' ]:
        continue

      if paramaters[ 'name_regex' ] is not None and not paramaters[ 'name_regex' ].match( datastore.name ):
        continue

      result.append( datastore.name )

    return { 'datastore_list': result }

  finally:
    _disconnect( si )


def _createDisk( si, dc, disk, datastore, file_path ):
  ( dir_name, _ ) = file_path.rsplit( '/', 1 )

  spec = vim.host.DatastoreBrowser.SearchSpec()
  spec.query.append( vim.host.DatastoreBrowser.FolderQuery() )
  task = datastore.browser.SearchDatastore_Task( datastorePath=dir_name, searchSpec=spec )
  _taskWait( task )

  if task.info.state == 'error':
    if task.info.error.__class__.__name__ == 'vim.fault.FileNotFound':
      logging.debug( 'vcenter: making dir "{0}"'.format( dir_name ) )
      si.content.fileManager.MakeDirectory( name=dir_name, datacenter=dc, createParentDirectories=True )
    else:
      raise Exception( 'Unknown Task Error when checking directory: "{0}"'.format( task.info.error ) )

  elif task.info.state != 'success':
    raise Exception( 'Unexpected Task State when checking directory: "{0}"'.format( task.info.state ) )

  spec = vim.VirtualDiskManager.FileBackedVirtualDiskSpec()
  spec.diskType = 'thin'  # 'eagerZeroedThick', 'preallocate'
  spec.adapterType = 'busLogic'  # 'ide', 'lsiLogic'
  spec.capacityKb = int( disk[ 'size' ] ) * 1024 * 1024

  logging.debug( 'vcenter: creating disk "{0}"'.format( file_path ) )

  task = si.content.virtualDiskManager.CreateVirtualDisk( name=file_path, datacenter=dc, spec=spec )
  _taskWait( task )

  if task.info.state == 'error':
    raise Exception( 'Unknown Task Error when Creating Disk: "{0}"'.format( task.info.error ) )

  if task.info.state != 'success':
    raise Exception( 'Unexpected Task State when Creating Disk: "{0}"'.format( task.info.state ) )


def create( paramaters ):  # NOTE: the picking of the cluster/host and datastore should be done prior to calling this, that way rollback can know where it's at
  vm_paramaters = paramaters[ 'vm' ]
  connection_paramaters = paramaters[ 'connection' ]
  vm_name = vm_paramaters[ 'name' ]

  logging.info( 'vcenter: creating vm "{0}"'.format( vm_name ) )
  si = _connect( connection_paramaters )
  try:
    dataCenter = _getDatacenter( si, vm_paramaters[ 'datacenter' ] )
    resourcePool = _getResourcePool( dataCenter, vm_paramaters[ 'cluster' ] )
    folder = dataCenter.vmFolder
    host = _getHost( resourcePool, vm_paramaters[ 'host' ] )
    datastore = _getDatastore( dataCenter, vm_paramaters[ 'datastore' ] )

    vmx_file_path, disk_filepath_list = _genPaths( vm_paramaters[ 'name' ], vm_paramaters[ 'disk_list' ], datastore )

    for i in range( 0, len( vm_paramaters[ 'disk_list' ] ) ):
      disk = vm_paramaters[ 'disk_list' ][ i ]
      _createDisk( si, dataCenter, disk, datastore, disk_filepath_list[ i ] )

    configSpec = vim.vm.ConfigSpec()
    configSpec.name = vm_name
    configSpec.memoryMB = int( vm_paramaters[ 'memory_size' ] )
    configSpec.numCPUs = int( vm_paramaters[ 'cpu_count' ] )
    configSpec.guestId = 'debian5_64Guest'

    configSpec.files = vim.vm.FileInfo()
    configSpec.files.vmPathName = vmx_file_path

    configSpec.bootOptions = vim.vm.BootOptions()
    configSpec.bootOptions.bootDelay = 5000
    configSpec.bootOptions.bootRetryEnabled = True
    configSpec.bootOptions.bootRetryDelay = 50000

    devSpec = vim.vm.device.VirtualDeviceSpec()
    devSpec.operation = 'add'
    devSpec.device = vim.vm.device.VirtualLsiLogicController()
    devSpec.device.key = 1000
    devSpec.device.sharedBus = 'noSharing'
    devSpec.device.busNumber = 0
    devSpec.device.controllerKey = 100
    devSpec.device.unitNumber = 0
    configSpec.deviceChange.append( devSpec )

    for i in range( 0, len( vm_paramaters[ 'disk_list' ] ) ):
      disk = vm_paramaters[ 'disk_list' ][ i ]
      devSpec = vim.vm.device.VirtualDeviceSpec()
      devSpec.operation = 'add'
      devSpec.device = vim.vm.device.VirtualDisk()
      devSpec.device.key = 2000 + i
      devSpec.device.controllerKey = 1000
      devSpec.device.capacityInKB = int( disk[ 'size' ] ) * 1024 * 1024
      devSpec.device.unitNumber = i + 1
      devSpec.device.backing = vim.vm.device.VirtualDisk.FlatVer2BackingInfo()
      devSpec.device.backing.fileName = disk_filepath_list[ i ]
      devSpec.device.backing.datastore = datastore
      devSpec.device.backing.diskMode = 'persistent'
      configSpec.deviceChange.append( devSpec )

    for i in range( 0, len( vm_paramaters[ 'interface_list' ] ) ):
      interface = vm_paramaters[ 'interface_list' ][ i ]
      network = _getNetwork( host, interface[ 'network' ] )

      devSpec = vim.vm.device.VirtualDeviceSpec()
      devSpec.operation = 'add'
      devSpec.device = vim.vm.device.VirtualE1000()  # look up the class from the interface[ 'type' ] in NET_CLASS_LIST
      devSpec.device.key = 4000 + i
      devSpec.device.controllerKey = 100
      devSpec.device.addressType = 'Manual'
      devSpec.device.macAddress = interface[ 'mac' ]
      devSpec.device.unitNumber = i + 7
      devSpec.device.backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo()
      devSpec.device.backing.deviceName = network.name
      configSpec.deviceChange.append( devSpec )

    configSpec.bootOptions.bootOrder.append( vim.vm.BootOptions.BootableEthernetDevice( deviceKey=4000 ) )  # TODO: figure out which is the boot drive and put it here
    configSpec.bootOptions.bootOrder.append( vim.vm.BootOptions.BootableDiskDevice( deviceKey=2000 ) )  # TODO: figure out which is the provisinioning interface and set it here

    task = folder.CreateVm( config=configSpec, pool=resourcePool, host=host )

    _taskWait( task )

    if task.info.state == 'error':
      raise Exception( 'Error With VM Create Task: "{0}"'.format( task.info.error ) )

    if task.info.state != 'success':
      raise Exception( 'Unexpected Task State With VM Create: "{0}"'.format( task.info.state ) )

    vm_uuid = task.info.result.config.instanceUuid

    logging.info( 'vcenter: vm "{0}" created, uuid: "{1}"'.format( vm_name, vm_uuid ) )

    return { 'done': True, 'uuid': vm_uuid }

  finally:
    _disconnect( si )


def create_rollback( paramaters ):
  vm_paramaters = paramaters[ 'vm' ]
  connection_paramaters = paramaters[ 'connection' ]
  vm_name = vm_paramaters[ 'name' ]
  logging.info( 'vcenter: rolling back vm "{0}"'.format( vm_name ) )

  si = _connect( connection_paramaters )
  try:
    dataCenter = _getDatacenter( si, vm_paramaters[ 'datacenter' ] )
    datastore = _getDatastore( dataCenter, vm_paramaters[ 'datastore' ] )

    vmx_file_path, disk_filepath_list = _genPaths( vm_paramaters[ 'name' ], vm_paramaters[ 'disk_list' ], datastore )

    file_list = disk_filepath_list + [ vmx_file_path ]

    for item in file_list:
      logging.debug( 'vcenter: deleting "{0}"'.format( item ) )
      task = si.content.fileManager.DeleteFile( name=item, datacenter=dataCenter )
      _taskWait( task )
      if task.info.state == 'error':
        if task.info.error.__class__.__name__ == 'vim.fault.FileNotFound':
          continue
        else:
          raise Exception( 'Unknown Task Error when Deleting "{0}": "{1}"'.format( item, task.info.error ) )

      if task.info.state != 'success':
        raise Exception( 'Unexpected Task State when Deleting "{0}": "{1}"'.format( task.info.state ) )

    # remove all the folders if empty

    return { 'rollback_done': True }

  finally:
    _disconnect( si )


def destroy( paramaters ):
  connection_paramaters = paramaters[ 'connection' ]
  vm_uuid = paramaters[ 'uuid' ]
  vm_name = paramaters[ 'name' ]

  logging.info( 'vcenter: destroying vm "{0}"({1})'.format( vm_name, vm_uuid ) )
  si = _connect( connection_paramaters )
  try:
    try:
      vm = _getVM( si, vm_uuid )
    except MOBNotFound:
      return { 'done': True }  # it's gone, we are donne

    task = vm.Destroy()

    _taskWait( task )

    if task.info.state == 'error':
      raise Exception( 'Error With VM Destroy Task: "{0}"'.format( task.info.error ) )

    if task.info.state != 'success':
      raise Exception( 'Unexpected Task State With VM Destroy: "{0}"'.format( task.info.state ) )

    logging.info( 'vcenter: vm "{0}" destroyed'.format( vm_name ) )
    return { 'done': True }

  finally:
    _disconnect( si )


def get_interface_map( paramaters ):
  connection_paramaters = paramaters[ 'connection' ]
  vm_uuid = paramaters[ 'uuid' ]
  vm_name = paramaters[ 'name' ]

  logging.info( 'vcenter: getting interface map "{0}"({1})'.format( vm_name, vm_uuid ) )
  si = _connect( connection_paramaters )
  try:
    vm = _getVM( si, vm_uuid )

    interface_map = {}
    for device in vm.config.hardware.device:
      if device.__class__.__name__ in NET_CLASS_LIST:
        i = device.key - 4000
        if i < 0 or i > 64:
          raise ValueError( 'Invalid device key "{0}"'.format( device.key ) )

        interface = paramaters[ 'interface_list' ][ i ]
        interface_map[ interface[ 'name' ] ] = device.macAddress

    return { 'interface_map': interface_map }

  finally:
    _disconnect( si )


def _power_state_convert( state ):
  if state in ( vim.VirtualMachinePowerState.poweredOff, vim.VirtualMachinePowerState.suspended ):
    return 'off'

  elif state in ( vim.VirtualMachinePowerState.poweredOn, ):
    return 'on'

  else:
    return 'unknown "{0}"'.format( state )


def set_power( paramaters ):
  connection_paramaters = paramaters[ 'connection' ]
  vm_uuid = paramaters[ 'uuid' ]
  vm_name = paramaters[ 'name' ]
  desired_state = paramaters[ 'state' ]

  logging.info( 'vcenter: setting power state of "{0}"({1}) to "{2}"...'.format( vm_name, vm_uuid, desired_state ) )
  si = _connect( connection_paramaters )
  try:
    vm = _getVM( si, vm_uuid )

    curent_state = _power_state_convert( vm.runtime.powerState )
    if curent_state == desired_state or ( curent_state == 'off' and desired_state == 'soft_off' ):
      return { 'state': curent_state }

    task = None
    if desired_state == 'on':
      task = vm.PowerOn()
    elif desired_state == 'off':
      task = vm.PowerOff()
    elif desired_state == 'soft_off':
      vm.ShutdownGuest()

    if task is not None:
      while task.info.state not in ( vim.TaskInfo.State.success, vim.TaskInfo.State.error ):
        logging.debug( 'vcenter: vm "{0}"({1}) power "{2}" at {3}%'.format( vm_name, vm_uuid, desired_state, task.info.progress ) )
        time.sleep( 1 )

      if task.info.state == vim.TaskInfo.State.error:
        raise Exception( 'vcenter: Unable to set power state of "{0}"({1}) to "{2}"'.format( vm_name, vm_uuid, desired_state ) )

    logging.info( 'vcenter: setting power state of "{0}"({1}) to "{2}" complete'.format( vm_name, vm_uuid, desired_state ) )
    return { 'state': _power_state_convert( vm.runtime.powerState ) }

  finally:
    _disconnect( si )


def power_state( paramaters ):
  connection_paramaters = paramaters[ 'connection' ]
  vm_uuid = paramaters[ 'uuid' ]
  vm_name = paramaters[ 'name' ]

  logging.info( 'vcenter: getting "{0}"({1}) power state...'.format( vm_name, vm_uuid ) )
  si = _connect( connection_paramaters )
  try:
    vm = _getVM( si, vm_uuid )

    return { 'state': _power_state_convert( vm.runtime.powerState ) }

  finally:
    _disconnect( si )

"""
from pyVim.connect import Connect

for unverified ssl:

import ssl
_create_unverified_https_context = ssl._create_unverified_context
ssl._create_default_https_context = _create_unverified_https_context

Other wise there is  a paramater to Connect for verified SSL


In [18]: c = Connect( host='192.168.200.101', user='root', pwd='0skin3rd')

In [22]: cont = c.RetrieveContent()

# should use the UUID instead
In [24]: cont.searchIndex.FindByInventoryPath( '/ha-datacenter/vm/mcp-preallocate--5421431c93-2.test' )
Out[24]: 'vim.VirtualMachine:32'

"""
