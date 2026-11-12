import zeep
import logging
import socket
import re
from urllib import request
from functools import cached_property
from subcontractor_plugins.virtualbox import constants

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

    version_parts = self.service.IVirtualBox_getVersion( self.handle ).split( '.' )
    if version_parts[0] < '7' or version_parts[1] < '1':  # need at least version 7.1
      raise ValueError( 'Unsupported VirtualBox Version: "{0}"'.format( '.'.join( version_parts ) ) )

    logging.debug( 'virtualbox: server version: "{0}"'.format( '.'.join( version_parts ) ) )

    self.session = Session( self.service, self.service.IWebsessionManager_getSessionObject( self.handle ) )
    self.system_properties_handle = self.service.IVirtualBox_getSystemProperties( self.handle )
    self.platform_properties_handle = self.service.ISystemProperties_getPlatform( self.system_properties_handle )

  def logout( self ):
    self.service.IWebsessionManager_logoff( self.handle )

  @cached_property
  def system_properties( self ):
    result = {}
    for name, SOAPName in ( ( 'default_machine_folder', 'DefaultMachineFolder' ), ):
      result[ name ] = getattr( self.service, 'ISystemProperties_get' + SOAPName )( self.system_properties_handle )

    return result

  @cached_property
  def platform_properties( self ):
    result = {}
    for name, SOAPName in ( ( 'max_boot_position', 'MaxBootPosition' ), ):
      result[ name ] = getattr( self.service, 'IPlatformProperties_get' + SOAPName )( self.platform_properties_handle )

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

  def create_machine( self, settings_file, name, platform, group_list, os_type, flags ):
    cipher = ''
    passwordid = ''
    password = ''
    handle = self.service.IVirtualBox_createMachine( self.handle, settings_file, name, platform, group_list, os_type, flags, cipher, passwordid, password )
    return Machine( self.service, handle )

  def register_machine( self, vm ):
    self.service.IVirtualBox_registerMachine( self.handle, vm.handle )

  def open_medium( self, path, device_type, access_mode, force_new_uuid ):
    return Medium( self.service, self.service.IVirtualBox_openMedium( self.handle, path, device_type, access_mode, force_new_uuid ) )

  def find_medium( self, path, device_type ):
    try:
      return Medium( self.service, self.service.IVirtualBox_openMedium( self.handle, path, device_type, constants.AccessMode.ReadOnly, False ) )
    except zeep.exceptions.Fault as e:
      if error_rc( e ) == VBOX_E_OBJECT_NOT_FOUND:
        return None
      raise

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
  memory_size = soap_property( 'IMachine', 'MemorySize' )
  cpu_count = soap_property( 'IMachine', 'CPUCount' )

  def __init__( self, service, handle ):
    self.service = service
    self.handle = handle

  @cached_property
  def firmware_settings( self ):
    return FirmwareSettings( self.service, self.service.IMachine_getFirmwareSettings( self.handle ) )

  def add_storage_controller( self, name, connection_type ):
    return self.service.IMachine_addStorageController( self.handle, name, connection_type )

  def get_network_adapter( self, index ):
   return NetworkAdapter( self.service, self.service.IMachine_getNetworkAdapter( self.handle, index ) )

  def get_graphics_adapter( self ):
   return GraphicsAdapter( self.service, self.service.IMachine_getGraphicsAdapter( self.handle ) )

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

  def launch_vm_process( self, frontend, session ):
    return Progress( self.service, self.service.IMachine_launchVMProcess( self.handle, session.handle, frontend, [] ) )

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

  def delete_storage( self ):
    return Progress( self.service, self.service.IMedium_deleteStorage( self.handle ) )


class GraphicsAdapter:
  graphics_controller_type = soap_property( 'IGraphicsAdapter', 'GraphicsControllerType' )
  video_memory_size = soap_property( 'IGraphicsAdapter', 'VRAMSize' )

  def __init__( self, service, handle ):
    self.service = service
    self.handle = handle


class FirmwareSettings:
  firmware_type = soap_property( 'IFirmwareSettings', 'FirmwareType' )
  time_offset = soap_property( 'IFirmwareSettings', 'TimeOffset' )

  def __init__( self, service, handle ):
    self.service = service
    self.handle = handle
