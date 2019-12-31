import zeep
import logging
import socket
import re
from urllib import request

VBOX_SOAP_BINDING = '{http://www.virtualbox.org/}vboxBinding'

VBOX_E_OBJECT_NOT_FOUND = '0x80bb0001'


class VirtualBoxNotFound( Exception ):
  pass


def error_rc( e ):
  parts = re.search( 'rc=(0x[a-f0-9]{8})', e.message )
  if parts is None:
    raise ValueError( 'Unreconised Exception: "{0}"'.format( e.message ) )

  return parts.group( 1 ).lower()


def soap_property( object, name, readonly=False ):
  if readonly:
    return property(
                     lambda self: getattr( self.service, '{0}_get{1}'.format( object, name ) )( self.handle ),
                   )
  else:
    return property(
                     lambda self: getattr( self.service, '{0}_get{1}'.format( object, name ) )( self.handle ),
                     lambda self, value: getattr( self.service, '{0}_set{1}'.format( object, name ) )( self.handle, value )
                   )


class VirtualBox:
  def __init__( self, host, username, password, proxy=None ):
    if not host.startswith( ( 'http:', 'https:' ) ):
      raise ValueError( 'hostname must start with http(s):' )

    if host[-1] != '/':
      raise ValueError( 'hostname must end with "/"' )

    logging.debug( 'virtualbox: new client host: "{0}", via: "{1}"'.format( host, proxy ) )

    try:
      self.client = zeep.Client( '{0}?wsdl'.format( host ) )

    except request.HTTPError as e:
      raise Exception( 'HTTPError "{0}"'.format( e ) )

    except socket.timeout:
      raise Exception( 'Request Timeout' )

    except socket.error as e:
      raise Exception( 'Socket Error "{0}"'.format( e ) )

    self.location = '{0}?wsdl'.format( host )
    self.service = self.client.create_service( VBOX_SOAP_BINDING, self.location )
    try:
      self.handle = self.service.IWebsessionManager_logon( username, password )

    except zeep.exceptions.Fault:
      raise Exception( 'Invalid Credentials' )

    self.system_properties_handle = self.service.IVirtualBox_getSystemProperties( self.handle )
    self.session = Session( self.service, self.service.IWebsessionManager_getSessionObject( self.handle ) )

  def logout( self ):
    self.service.IWebsessionManager_logoff( self.handle )

  @property
  def system_properties( self ):
    result = {}
    for name, SOAPName in ( ( 'max_boot_position', 'MaxBootPosition' ), ( 'default_machine_folder', 'DefaultMachineFolder' ) ):
      result[ name ] = getattr( self.service, 'ISystemProperties_get' + SOAPName )( self.system_properties_handle )

    return result

  def find_machine( self, vm_name ):
    try:
      handle = self.service.IVirtualBox_findMachine( self.handle, vm_name )

    except zeep.exceptions.Fault as e:
      if error_rc( e ) == VBOX_E_OBJECT_NOT_FOUND:
        raise VirtualBoxNotFound( 'No VM "{0}"'.format( vm_name ) )
      else:
        raise ValueError( 'Unknown Error: "{0}"'.format( e ) )

    return Machine( self.service, handle )

  def compose_machine_filename( self, name, group, create_flags, base_folder ):
    return self.service.IVirtualBox_composeMachineFilename( self.handle, name, group, create_flags, base_folder )

  def create_machine( self, settings_file, name, group_list, os_type, flags ):
    handle = self.service.IVirtualBox_createMachine( self.handle, settings_file, name, group_list, os_type, flags )
    return Machine( self.service, handle )

  def register_machine( self, vm ):
    self.service.IVirtualBox_registerMachine( self.handle, vm.handle )

  def open_medium( self, path, device_type, access_mode, force_new_uuid ):
    return Medium( self.service, self.service.IVirtualBox_openMedium( self.handle, path, device_type, access_mode, force_new_uuid ) )

  def create_medium( self, format, location, access_mode, device_type ):
    return Medium( self.service, self.service.IVirtualBox_createMedium( self.handle, format, location, access_mode, device_type ) )


class Session:
  state = soap_property( 'ISession', 'State', True )
  console = soap_property( 'ISession', 'Console', True )

  def __init__( self, service, handle ):
    self.service = service
    self.handle = handle

  @property
  def machine( self ):
    return Machine( self.service, self.service.ISession_getMachine( self.handle ) )

  def unlock_machine( self ):
    self.service.ISession_unlockMachine( self.handle )


class Progress:
  completed = soap_property( 'IProgress', 'Completed', True )
  canceled = soap_property( 'IProgress', 'Canceled', True )
  percent = soap_property( 'IProgress', 'Percent', True )
  time_remaining = soap_property( 'IProgress', 'TimeRemaining', True )
  result_code = soap_property( 'IProgress', 'ResultCode', True )

  def __init__( self, service, handle ):
    self.service = service
    self.handle = handle

  @property
  def error_info( self ):
    handle = self.service.IProgress_getErrorInfo( self.handle )

    result = {}
    result[ 'text' ] = self.service.IVirtualBoxErrorInfo_getText( handle )

    return result


class Machine:
  state = soap_property( 'IMachine', 'State', True )
  hardware_uuid = soap_property( 'IMachine', 'HardwareUUID' )
  settings_file_path = soap_property( 'IMachine', 'SettingsFilePath', True )
  RTC_use_UTC = soap_property( 'IMachine', 'RTCUseUTC' )
  memory_size = soap_property( 'IMachine', 'MemorySize' )

  def __init__( self, service, handle ):
    self.service = service
    self.handle = handle

  def add_storage_controller( self, name, connection_type ):
    return self.service.IMachine_addStorageController( self.handle, name, connection_type )

  def get_network_adapter( self, index ):
   return NetworkAdapter( self.service, self.service.IMachine_getNetworkAdapter( self.handle, index ) )

  def attach_device( self, name, port, device, device_type, medium ):
    self.service.IMachine_attachDevice( self.handle, name, port, device, device_type, medium.handle )

  def set_boot_order( self, position, device_type ):
    self.service.IMachine_setBootOrder( self.handle, position, device_type )

  def save_settings( self ):
    return self.service.IMachine_saveSettings( self.handle )

  def unregister( self, cleanup_mode ):
    return self.service.IMachine_unregister( self.handle, cleanup_mode )

  def delete_config( self, media_list ):
    return Progress( self.service, self.service.IMachine_deleteConfig( self.handle, media_list ) )

  def lock( self, session, lock_type ):
    self.service.IMachine_lockMachine( self.handle, session.handle, lock_type )

  def launch_vm_process( self, session ):
    return Progress( self.service, self.service.IMachine_launchVMProcess( self.handle, session.handle, '', '' ) )

  def power_down( self, session ):
    return Progress( self.service, self.service.IConsole_powerDown( session.console ) )

  def power_button( self, session ):
    self.service.IConsole_powerButton( session.console )


class NetworkAdapter:
  enabled = soap_property( 'INetworkAdapter', 'Enabled' )
  mac_address = soap_property( 'INetworkAdapter', 'MACAddress' )
  adapter_type = soap_property( 'INetworkAdapter', 'AdapterType' )
  attachment_type = soap_property( 'INetworkAdapter', 'AttachmentType' )
  host_only_interface = soap_property( 'INetworkAdapter', 'HostOnlyInterface' )
  bridged_interface = soap_property( 'INetworkAdapter', 'BridgedInterface' )
  nat_network = soap_property( 'INetworkAdapter', 'NATNetwork' )
  internal_network = soap_property( 'INetworkAdapter', 'InternalNetwork' )

  def __init__( self, service, handle ):
    self.service = service
    self.handle = handle


class Medium:
  state = soap_property( 'IMedium', 'State', True )

  def __init__( self, service, handle ):
    self.service = service
    self.handle = handle

  def create_base_storage( self, logical_size, variant_list ):
    return Progress( self.service, self.service.IMedium_createBaseStorage( self.handle, logical_size, variant_list ) )
