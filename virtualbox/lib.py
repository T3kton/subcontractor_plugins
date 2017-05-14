import logging
import virtualbox
import time
import os

CLEAN_POWER_DOWN_COUNT = 20

CREATE_GROUP = ''
CREATE_GROUPS = []
CREATE_FLAGS = ''
CREATE_OS_TYPE_ID = 'Ubuntu_64'

BOOT_ORDER_MAP = { 'hdd': virtualbox.library.DeviceType.hard_disk, 'net': virtualbox.library.DeviceType.network, 'cd': virtualbox.library.DeviceType.dvd, 'usb': virtualbox.library.DeviceType.usb }


def create( paramaters ):
  vm_name = paramaters[ 'name' ]
  logging.info( 'virtualbox: creating vm "{0}"'.format( vm_name ) )
  vbox = virtualbox.VirtualBox()

  settings_file = vbox.compose_machine_filename( vm_name, CREATE_GROUP, CREATE_FLAGS, vbox.system_properties.default_machine_folder )
  vm = vbox.create_machine( settings_file, vm_name, CREATE_GROUPS, CREATE_OS_TYPE_ID, CREATE_FLAGS )
  vm.memory_size = int( paramaters.get( 'memory_size', 512 ) )  # in Meg

  disk_controller_name = 'SCSI'
  vm.add_storage_controller( disk_controller_name, virtualbox.library.StorageBus.scsi )
  cd_controller_name = 'SATA'
  vm.add_storage_controller( cd_controller_name, virtualbox.library.StorageBus.sata )

  vm.save_settings()
  logging.debug( 'virtualbox: regestering vm "{0}"'.format( vm_name ) )
  vbox.register_machine( vm )

  session = vm.create_session( virtualbox.library.LockType.write )
  vm2 = session.machine

  for i in range( 0, vbox.system_properties.max_boot_position  ):
    vm2.set_boot_order( i + 1, virtualbox.library.DeviceType.null )

  for i in range( 0, 4 ):
    adapter = vm2.get_network_adapter( i  )
    adapter.enabled = False

  disk_port = 0
  cd_port = 0
  for disk in paramaters[ 'disk_list' ]:
    disk_name = disk[ 'name' ]
    logging.debug( 'vritualbox: creating disk "{0}" on "{1}"'.format( disk_name, vm_name ) )
    if 'file' in disk:
      disk_file = disk[ 'file' ]

      if disk_file.endswith( '.iso' ):
        medium = vbox.open_medium( disk_file, virtualbox.library.DeviceType.dvd, virtualbox.library.AccessMode.read_only, True )
        vm2.attach_device( cd_controller_name, cd_port, 0, virtualbox.library.DeviceType.dvd, medium )
        cd_port += 1

      else:
        medium = vbox.open_medium( disk_file, virtualbox.library.DeviceType.hard_disk, virtualbox.library.AccessMode.read_write, True )
        vm2.attach_device( disk_controller_name, disk_port, 0, virtualbox.library.DeviceType.hard_disk, medium )
        disk_port += 1

    else:
      disk_size = int( disk[ 'size' ] ) * 1024 * 1024 * 1024  # disk_size is in bytes, we were pass in G
      disk_format = 'vdi'
      location = '{0}/{1}.vdi'.format( os.path.dirname( vm.settings_file_path ), disk_name )
      medium = vbox.create_medium( disk_format, location, virtualbox.library.AccessMode.read_write, virtualbox.library.DeviceType.hard_disk )
      progress = medium.create_base_storage( disk_size, [ virtualbox.library.MediumVariant.standard ] )
      while not progress.completed:
        logging.debug( 'virtualbox: creating storage for "{0}" disk "{1}" at {2}%, {3} seconds left'.format( vm_name, disk_name, progress.percent, progress.time_remaining ) )
        time.sleep( 1 )

      if medium.state != virtualbox.library.MediumState.created:
        raise Exception( 'disk "{0}" for vm "{1}" faild to create: "{2}"'.format( disk_name, vm_name, progress.error_info.text ) )

      vm2.attach_device( disk_controller_name, disk_port, 0, virtualbox.library.DeviceType.hard_disk, medium )
      disk_port += 1

  interface_list = []
  for i in range( 0, 4 ):
    adapter = vm2.get_network_adapter( i )
    if i < len( paramaters[ 'interface_list' ] ):
      iface = paramaters[ 'interface_list' ][ i ]
      adapter.enabled = True
      adapter.mac_address = iface[ 'mac' ]

      if iface[ 'type' ] == 'host':
        adapter.attachment_type = virtualbox.library.NetworkAttachmentType.host_only
        adapter.host_only_interface = iface[ 'name' ]

      elif iface[ 'type' ] == 'bridge':
        adapter.attachment_type = virtualbox.library.NetworkAttachmentType.bridged
        adapter.bridged_interface = iface[ 'name' ]

      elif iface[ 'type' ] == 'nat':
        adapter.attachment_type = virtualbox.library.NetworkAttachmentType.nat_network
        adapter.nat_network = iface[ 'name' ]

      elif iface[ 'type' ] == 'internal':
        adapter.attachment_type = virtualbox.library.NetworkAttachmentType.internal
        adapter.internal_network = iface[ 'name' ]

      else:
        raise Exception( 'Unknown interface type "{0}"'.format( iface[ 'type' ] ) )

    else:
      adapter.enabled = False

    interface_list.append( { 'name': 'eth{0}'.format( i + 1 ), 'mac': iface[ 'mac' ] } )

  for i in range( 0, vbox.system_properties.max_boot_position  ):
    if i < len( paramaters[ 'boot_order' ] ):
      try:
        vm2.set_boot_order( i + 1, BOOT_ORDER_MAP[ paramaters[ 'boot_order' ][ i ] ] )
      except KeyError:
        raise Exception( 'Unknown boot item "{0}"'.format( paramaters[ 'boot_order' ][ i ] ) )

  vm2.save_settings()
  session.unlock_machine()
  logging.info( 'virtualbox: vm "{0}" created'.format( vm_name ) )

  return { 'done': True, 'uuid': vm.hardware_uuid, 'interface_list': interface_list }


def create_rollback( paramaters ):
  vm_name = paramaters[ 'name' ]
  logging.info( 'virtualbox: rolling back vm "{0}"'.format( vm_name ) )
  vbox = virtualbox.VirtualBox()

  try:
    vm = vbox.find_machine( vm_name )
  except virtualbox.library.VBoxErrorObjectNotFound:
    vm = None

  if vm is not None:
    media = vm.unregister( virtualbox.library.CleanupMode.detach_all_return_hard_disks_only )
    progress = vm.delete_config( media )
    while not progress.completed:
      logging.debug( 'virtualbox: deleting config "{0}" power off at {1}%, {2} seconds left'.format( vm_name, progress.percent, progress.time_remaining ) )
      time.sleep( 1 )

  # make a list of files that needs to be cleaned up, just incase they are created an not attached, or vm wasn't registerd
  file_list = [ vbox.compose_machine_filename( vm_name, CREATE_GROUP, CREATE_FLAGS, vbox.system_properties.default_machine_folder ) ]

  for disk in paramaters[ 'disk_list' ]:
    disk_name = disk[ 'name' ]
    if 'file' not in disk:
      file_list.append( '{0}/{1}.vdi'.format( os.path.dirname( file_list[0] ), disk_name ) )

  logging.debug( 'virtualbox: rollback cleanup file list "{0}"'.format( file_list ) )
  for file_name in file_list:
    try:
      os.unlink( file_name )
    except OSError as e:
      if e.errno != 2:  # no such file or directory
        raise e

  # would be nice to clean up temp files and dirs, but really don't know what is safe,
  # this is rollback anyway, hopfully it get's created right  the next time and everything
  # get's cleaned up anyway.

  logging.info( 'virtualbox: vm "{0}" rolledback'.format( vm_name ) )
  return { 'rollback_done': True }


def destroy( paramaters ):
  vm_uuid = paramaters[ 'uuid' ]
  vm_name = paramaters[ 'name' ]
  logging.info( 'virtualbox: destroying vm "{0}"'.format( vm_name ) )
  vbox = virtualbox.VirtualBox()

  try:
    vm = vbox.find_machine( vm_uuid )
  except virtualbox.library.VBoxErrorObjectNotFound:
    return { 'done': True }  # it's gone, we are donne

  media = vm.unregister( virtualbox.library.CleanupMode.detach_all_return_hard_disks_only )
  progress = vm.delete_config( media )
  while not progress.completed:
    logging.debug( 'virtualbox: deleting config "{0}"({1}) at {2}%, {3} seconds left'.format( vm_name, vm_uuid, progress.percent, progress.time_remaining ) )
    time.sleep( 1 )

  logging.info( 'virtualbox: vm "{0}" destroyed'.format( vm_name ) )
  return { 'done': True }


def _power_state_convert( state ):
  if state in ( virtualbox.library.MachineState.powered_off, virtualbox.library.MachineState.saved ):
    return 'off'

  elif state in ( virtualbox.library.MachineState.running, virtualbox.library.MachineState.starting, virtualbox.library.MachineState.stopping ):
    return 'on'

  else:
    return 'unknown "{0}"'.format( state )


def set_power( paramaters ):
  vm_uuid = paramaters[ 'uuid' ]
  vm_name = paramaters[ 'name' ]
  desired_state = paramaters[ 'state' ]
  logging.info( 'virtualbox: setting power state of "{0}"({1}) to "{2}"...'.format( vm_name, vm_uuid, desired_state ) )
  vbox = virtualbox.VirtualBox()

  vm = vbox.find_machine( vm_name )

  curent_state = _power_state_convert( vm.state )
  if curent_state == desired_state or ( curent_state == 'off' and desired_state == 'soft_off' ):
    return { 'state': curent_state }

  session = None
  if desired_state in ( 'off', 'soft_off' ):
    session = vm.create_session()

  progress = None
  if desired_state == 'on':
    progress = vm.launch_vm_process()
  elif desired_state == 'off':
    session.console.power_down()
  elif desired_state == 'soft_off':
    progress = session.console.power_button()

  if progress is not None:
    while not progress.completed:
      logging.debug( 'virtualbox: vm "{0}"({1}) power "{2}" at {3}%, {4} seconds left'.format( vm_name, vm_uuid, desired_state, progress.percent, progress.time_remaining ) )
      time.sleep( 1 )

  # if failed???

  logging.info( 'virtualbox: setting power state of "{0}"({1}) to "{2}" complete'.format( vm_name, vm_uuid, desired_state ) )
  return { 'state': _power_state_convert( vm.state ) }


def power_state( paramaters ):
  vm_uuid = paramaters[ 'uuid' ]
  vm_name = paramaters[ 'name' ]
  logging.info( 'virtualbox: getting "{0}"({1}) power state...'.format( vm_name, vm_uuid ) )
  vbox = virtualbox.VirtualBox()

  vm = vbox.find_machine( vm_uuid )

  return { 'state': _power_state_convert( vm.state ) }
