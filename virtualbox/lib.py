import logging
import virtualbox
import time
import os

CLEAN_POWER_DOWN_COUNT = 20

def create( paramaters ):
  vm_name = paramaters[ 'name' ]
  logging.info( 'virtualbox: creating vm "{0}"'.format( vm_name ) )
  vbox = virtualbox.VirtualBox()

  settings_file = '{0}/{0}.vbox'.format( vm_name )
  groups = []
  os_type_id = 'Ubuntu_64'
  flags = ''
  vm = vbox.create_machine( settings_file, vm_name, groups, os_type_id, flags )
  controller_name = 'SCSI'
  storage_controller = vm.add_storage_controller( controller_name, virtualbox.library.StorageBus.scsi )

  logging.debug( 'virtualbox: regestering vm "{0}"'.format( vm_name ) )
  vbox.register_machine( vm )

  session = vm.create_session( virtualbox.library.LockType.write )
  vm2 = session.machine

  port = -1
  for disk in paramaters[ 'disk_list' ]:
    port += 1
    disk_name = disk[ 'name' ]
    logging.debug( 'vritualbox: adding disk "{0}" to "{1}"'.format( disk_name, vm_name ) )
    if 'file' in disk:
      disk_file = disk[ 'file' ]

      if disk_file.endswith( '.iso' ):
        medium = vbox.create_medium( 'RAW', disk_file, virtualbox.library.AccessMode.read_only, virtualbox.library.DeviceType.dvd )
        vm2.attach_device( controller_name, port, 0, virtualbox.library.DeviceType.dvd, medium )

      else:
        medium = vbox.create_medium( 'RAW', disk_file, virtualbox.library.AccessMode.read_write, virtualbox.library.DeviceType.hard_disk )
        vm2.attach_device( controller_name, port, 0, virtualbox.library.DeviceType.hard_disk, medium )

    else:
      disk_size = int( disk[ 'size' ] ) * 1024 * 1024 * 1024 # disk_size is in bytes, we were pass in G
      disk_format = 'vdi'
      location = '{0}/{1}.disk'.format( os.path.dirname( vm.settings_file_path ), disk_name )
      medium = vbox.create_medium( disk_format, location, virtualbox.library.AccessMode.read_write, virtualbox.library.DeviceType.hard_disk )
      progress = medium.create_base_storage( disk_size, [ virtualbox.library.MediumVariant.standard ] )
      while not progress.completed:
        logging.debug( 'virtualbox: creating storage for "{0}" disk "{1}" at {2}%'.format( vm_name, disk_name, progress.percent ) )
        time.sleep( 1 )

      vm2.attach_device( controller_name, port, 0, virtualbox.library.DeviceType.hard_disk, medium )

  vm2.save_settings()
  session.unlock_machine()
  logging.info( 'virtualbox: vm "{0}" created'.format( vm_name ) )

  return { 'done': True }

def create_rollback( paramaters ):
  vm_name = paramaters[ 'name' ]
  logging.info( 'virtualbox: rolling back vm "{0}"'.format( vm_name ) )
  vbox = virtualbox.VirtualBox()

  try:
    vm = vbox.find_machine( vm_name )
  except virtualbox.library.VBoxErrorObjectNotFound:
    return { 'rollback_done': True }

  media = vm.unregister( virtualbox.library.CleanupMode.detach_all_return_hard_disks_only )
  progress = vm.delete_config( media )
  while not progress.completed:
    logging.debug( 'virtualbox: deleting config "{0}" power on at {1}%'.format( vm_name, progress.percent ) )
    time.sleep( 1 )

  logging.info( 'virtualbox: vm "{0}" destroyed'.format( vm_name ) )
  return { 'rollback_done': True }

def destroy( paramaters ):
  vm_name = paramaters[ 'name' ]
  logging.info( 'virtualbox: destroying vm "{0}"'.format( vm_name ) )
  vbox = virtualbox.VirtualBox()

  vm = vbox.find_machine( vm_name )
  media = vm.unregister( virtualbox.library.CleanupMode.detach_all_return_hard_disks_only )
  progress = vm.delete_config( media )
  while not progress.completed:
    logging.debug( 'virtualbox: deleting config "{0}" power on at {1}%'.format( vm_name, progress.percent ) )
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
    logging.debug( 'virtualbox: vm "{0}" power on at {1}%'.format( vm_name, progress.percent ) )
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
    logging.debug( 'virtualbox: vm "{0}" power off at {1}%'.format( vm_name, progress.percent ) )
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
