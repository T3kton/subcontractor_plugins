import logging
import virtualbox
import time
import os

CLEAN_POWER_DOWN_COUNT = 20

CREATE_GROUP = ''
CREATE_GROUPS = []
CREATE_FLAGS = ''
CREATE_OS_TYPE_ID = 'Ubuntu_64'

def create( paramaters ):
  vm_name = paramaters[ 'name' ]
  logging.info( 'virtualbox: creating vm "{0}"'.format( vm_name ) )
  vbox = virtualbox.VirtualBox()

  settings_file = vbox.compose_machine_filename( vm_name, CREATE_GROUP, CREATE_FLAGS, vbox.system_properties.default_machine_folder )
  vm = vbox.create_machine( settings_file, vm_name, CREATE_GROUPS, CREATE_OS_TYPE_ID, CREATE_FLAGS )
  vm.memory_size = int( paramaters.get( 'memory_size', 512 ) ) # in Meg

  disk_controller_name = 'SCSI'
  vm.add_storage_controller( disk_controller_name, virtualbox.library.StorageBus.scsi )
  cd_controller_name = 'SATA'
  vm.add_storage_controller( cd_controller_name, virtualbox.library.StorageBus.sata )

  vm.save_settings()
  logging.debug( 'virtualbox: regestering vm "{0}"'.format( vm_name ) )
  vbox.register_machine( vm )

  session = vm.create_session( virtualbox.library.LockType.write )
  vm2 = session.machine

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
      disk_size = int( disk[ 'size' ] ) * 1024 * 1024 * 1024 # disk_size is in bytes, we were pass in G
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

  vm2.save_settings()
  session.unlock_machine()
  logging.info( 'virtualbox: vm "{0}" created'.format( vm_name ) )

  return { 'done': True, 'uuid': vm.hardware_uuid }

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
      logging.debug( 'virtualbox: deleting config "{0}" power on at {1}%, {2} seconds left'.format( vm_name, progress.percent, progress.time_remaining ) )
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
      if e.errno != 2: # no such file or directory
        raise e

  # would be nice to clean up temp files and dirs, but really don't know what is safe,
  # this is rollback anyway, hopfully it get's created right  the next time and everything
  # get's cleaned up anyway.

  logging.info( 'virtualbox: vm "{0}" rolledback'.format( vm_name ) )
  return { 'rollback_done': True }

def destroy( paramaters ):
  vm_name = paramaters[ 'name' ]
  logging.info( 'virtualbox: destroying vm "{0}"'.format( vm_name ) )
  vbox = virtualbox.VirtualBox()

  try:
    vm = vbox.find_machine( vm_name )
  except virtualbox.library.VBoxErrorObjectNotFound:
    return { 'done': True } # it's gone, we are donne

  media = vm.unregister( virtualbox.library.CleanupMode.detach_all_return_hard_disks_only )
  progress = vm.delete_config( media )
  while not progress.completed:
    logging.debug( 'virtualbox: deleting config "{0}" power on at {1}%, {2} seconds left'.format( vm_name, progress.percent, progress.time_remaining ) )
    time.sleep( 1 )

  logging.info( 'virtualbox: vm "{0}" destroyed'.format( vm_name ) )
  return { 'done': True }

def power_on( paramaters ):
  vm_name = paramaters[ 'name' ]
  logging.info( 'virtualbox: powering on "{0}"...'.format( vm_name ) )
  vbox = virtualbox.VirtualBox()

  vm = vbox.find_machine( vm_name )

  progress = vm.launch_vm_process()

  while not progress.completed:
    logging.debug( 'virtualbox: vm "{0}" power on at {1}%, {2} seconds left'.format( vm_name, progress.percent, progress.time_remaining ) )
    time.sleep( 1 )

  logging.info( 'virtualbox: power on "{0}" complete'.format( vm_name ) )
  return { 'done': True }

def power_off( paramaters ):
  vm_name = paramaters[ 'name' ]
  logging.info( 'virtualbox: powering off "{0}"...'.format( vm_name ) )
  vbox = virtualbox.VirtualBox()

  vm = vbox.find_machine( vm_name )

  console.power_button()

  for _  in range( 0, CLEAN_POWER_DOWN_COUNT ):
    if vm.state == virtualbox.library.MachineState.powered_off:
      logging.info( 'virtualbox: clean shutdown on "{0}" complete'.format( vm_name ) )
      return { 'done': True }

    time.sleep( 1 )

  progress = console.power_down()
  while not progress.completed:
    logging.debug( 'virtualbox: vm "{0}" power off at {1}%, {2} seconds left'.format( vm_name, progress.percent, progress.time_remaining ) )
    time.sleep( 1 )

  logging.info( 'virtualbox: power off "{0}" complete'.format( vm_name ) )
  return { 'done': True }

def power_status( paramaters ):
  vm_name = paramaters[ 'name' ]
  logging.info( 'virtualbox: getting "{0}" power status...'.format( vm_name ) )
  vbox = virtualbox.VirtualBox()

  vm = vbox.find_machine( vm_name )

  state = vm.state
  if state in ( virtualbox.library.MachineState.powered_off, virtualbox.library.MachineState.saved ):
    return { 'state': 'off' }

  elif state in ( virtualbox.library.MachineState.running, virtualbox.library.MachineState.starting, virtualbox.library.MachineState.stopping ):
    return { 'state': 'off' }

  else:
    return { 'state': 'unknown {0}'.format( state ) }
