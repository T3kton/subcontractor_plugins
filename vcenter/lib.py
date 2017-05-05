import logging
import time

from pyVim import connect
from pyVmomi import vim

CLEAN_POWER_DOWN_COUNT = 20

CREATE_GROUP = ''
CREATE_GROUPS = []
CREATE_FLAGS = ''
CREATE_OS_TYPE_ID = 'Ubuntu_64'

BOOT_ORDER_MAP = { 'hdd': 'HDD', 'net': 'NET', 'cd': 'CD', 'usb': 'USB' }


def _connect( paramaters ):
  logging.debug( 'vcenter: connecting to "{0}" with user "{1}"'.format( paramaters[ 'host' ], paramaters[ 'username' ] ) )
  return connect.SmartConnect( host=paramaters[ 'host' ], user=paramaters[ 'username' ], pwd=paramaters[ 'password' ] )


def _disconnect( si ):
  connect.Disconnect( si )


def create( paramaters ):
  vm_name = paramaters[ 'name' ]
  logging.info( 'vcenter: creating vm "{0}"'.format( vm_name ) )

  return { 'done': True, 'uuid': '0000-0000-0000000' }


def create_rollback( paramaters ):
  vm_name = paramaters[ 'name' ]
  logging.info( 'vcenter: rolling back vm "{0}"'.format( vm_name ) )

  logging.info( 'vcenter: vm "{0}" rolledback'.format( vm_name ) )
  return { 'rollback_done': True }


def destroy( paramaters ):
  vm_uuid = paramaters[ 'uuid' ]
  vm_name = paramaters[ 'name' ]
  logging.info( 'vcenter: destroying vm "{0}"'.format( vm_name ) )
  si = _connect( paramaters )
  vm = si.content.searchIndex.FindByUuid( None, vm_uuid, True, True )

  if vm is None:
    return { 'done': True }  # it's gone, we are donne

  # destroy the vm

  _disconnect( si )
  logging.info( 'vcenter: vm "{0}" destroyed'.format( vm_name ) )
  return { 'done': True }


def _power_state_convert( state ):
  if state in ( vim.VirtualMachinePowerState.poweredOff, vim.VirtualMachinePowerState.suspended ):
    return 'off'

  elif state in ( vim.VirtualMachinePowerState.poweredOn, ):
    return 'on'

  else:
    return 'unknown "{0}"'.format( state )


def set_power( paramaters ):
  vm_uuid = paramaters[ 'uuid' ]
  vm_name = paramaters[ 'name' ]
  desired_state = paramaters[ 'state' ]
  logging.info( 'vcenter: setting power state of "{0}"({1}) to "{2}"...'.format( vm_name, vm_uuid, desired_state ) )
  si = _connect( paramaters )
  vm = si.content.searchIndex.FindByUuid( None, vm_uuid, True, True )

  if vm is None:
    raise Exception( 'vcenter: unable to find vm "{0}"({1})'.format( vm_name, vm_uuid ) )

  curent_state = _power_state_convert( vm.runtime.powerState )
  if curent_state == desired_state or ( curent_state == 'off' and desired_state == 'soft_off' ):
    return { 'state': curent_state }

  task = None
  if desired_state == 'on':
    task = vm.PowerOn()
  elif desired_state == 'off':
    task = vm.PowerOff()
  elif desired_state == 'soft_off':
    task = vm.Shutdown()

  if task is not None:
    while task.info.state not in ( vim.TaskInfo.State.success, vim.TaskInfo.State.error ):
      logging.debug( 'vcenter: vm "{0}"({1}) power "{2}" at {3}%'.format( vm_name, vm_uuid, desired_state, task.info.progress ) )
      time.sleep( 1 )

  if task.info.state == vim.TaskInfo.State.error:
    raise Exception( 'vcenter: Unable to set power state of "{0}"({1}) to "{2}"'.format( vm_name, vm_uuid, desired_state ) )

  _disconnect( si )
  logging.info( 'vcenter: setting power state of "{0}"({1}) to "{2}" complete'.format( vm_name, vm_uuid, desired_state ) )
  return { 'state': _power_state_convert( vm.state ) }


def power_state( paramaters ):
  vm_uuid = paramaters[ 'uuid' ]
  vm_name = paramaters[ 'name' ]
  logging.info( 'vcenter: getting "{0}"({1}) power state...'.format( vm_name, vm_uuid ) )
  si = _connect( paramaters )
  vm = si.content.searchIndex.FindByUuid( None, vm_uuid, True, True )

  if vm is None:
    raise Exception( 'vcenter: unable to find vm "{0}"({1})'.format( vm_name, vm_uuid ) )

  _disconnect( si )
  return { 'state': _power_state_convert( vm.runtime.powerState ) }
