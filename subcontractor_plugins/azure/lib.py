import logging
from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.compute import ComputeManagementClient
from msrestazure.azure_exceptions import CloudError

from subcontractor.credentials import getCredentials


POLL_INTERVAL = 4


class AzureClient():
  def __init__( self, credentials, subscription_id ):
    self.credentials = credentials
    self.subscription_id = subscription_id
    self._resource = None
    self._compute = None
    self._network = None

  @property
  def resource( self ):
    if self._resource is not None:
      return self._resource

    self._resource = ResourceManagementClient( self.credentials, self.subscription_id )
    return self._resource

  @property
  def compute( self ):
    if self._compute is not None:
      return self._compute

    self._compute = ComputeManagementClient( self.credentials, self.subscription_id )
    return self._compute

  @property
  def network( self ):
    if self._network is not None:
      return self._network

    self._network = NetworkManagementClient( self.credentials, self.subscription_id )
    return self._network


def _connect( connection_paramaters ):
  logging.debug( 'azure: connecting with client_id "{0}", tenant_id: "{1}"'.format( connection_paramaters[ 'client_id' ], connection_paramaters[ 'tenant_id' ] ) )
  password = getCredentials( connection_paramaters[ 'password' ] )

  credentials = ServicePrincipalCredentials( client_id=connection_paramaters[ 'client_id' ], secret=password, tenant=connection_paramaters[ 'tenant_id' ] )

  return AzureClient( credentials, connection_paramaters[ 'subscription_id' ] )


def create( paramaters ):
  vm_paramaters = paramaters[ 'vm' ]
  connection_paramaters = paramaters[ 'connection' ]
  vm_name = vm_paramaters[ 'name' ]
  resource_group = paramaters[ 'resource_group' ]
  location = paramaters[ 'location' ]

  logging.info( 'azure: creating vm "{0}" in "{1}"'.format( vm_name, resource_group ) )
  client = _connect( connection_paramaters )

  if 'image' not in vm_paramaters and 'disk_os' not in vm_paramaters:
    raise ValueError( 'image and/or disk_os need to be defined' )

  try:
    client.compute.virtual_machines.get( resource_group, vm_name )
    raise Exception( 'VM "{0}" in "{1}" allready exists'.format( vm_name, resource_group ) )

  except CloudError as e:
    if e.status_code != 404:
      raise e

  #  TODO: check to see if resource group exists, if not create it
  # logging.debug( 'azure: create/update resource group "{0}"'.format( resource_group ) )
  # client.resource.create_or_update( resource_group, { 'location': location } )

  nic_list = []
  for i in range( 0, len( vm_paramaters[ 'interface_list' ] ) ):
    interface = vm_paramaters[ 'interface_list' ][ i ]
    subnet = client.network.subnets.get( resource_group, interface[ 'network' ], 'default' )
    ip_config_list = []
    for config in interface[ 'config_list' ]:
      ip_config_list.append( {
                               'name': config[ 'name' ],
                               'properties': {
                                               'private_ip_address_version': 'IPv4',
                                               'private_ip_allocation_method': 'Static',
                                               'private_ip_address': config[ 'address' ],
                                               'subnet': { 'id': subnet.id }
                                             }
                              } )

    nic_spec = {
                 'location': location,
                 'ip_configurations': ip_config_list
               }

    try:
      worker = client.network.network_interfaces.create_or_update( resource_group, interface[ 'name' ], nic_spec )
    except CloudError as e:
      raise Exception( 'Error creating network interface "{0}":({1})"{2}"'.format( interface[ 'name' ], e.error.error, e.error.message ) )

    while not worker.done():
      logging.debug( 'azure: waiting for network interface creation...' )
      worker.wait( POLL_INTERVAL )

    if worker.status() != 'Succeeded':
      raise Exception( 'Network Interface creation Failed: "{0}"'.format( worker.status() ) )

    nic = worker.result()
    nic_list.append( { 'id': nic.id, 'properties': { 'primary': len( nic_list ) == 0 } } )

  storage_spec = {}
  if 'image' in vm_paramaters:
    image = vm_paramaters[ 'image' ]
    storage_spec[ 'image_reference' ] = {
                                            'publisher': image[ 'publisher' ],
                                            'offer': image[ 'offer' ],
                                            'sku': image[ 'sku' ],
                                            'version': image[ 'version' ]
                                        }

  for disk in vm_paramaters.get( 'disk_data_list', [] ):
    pass  # TODO

  if 'disk_os' in vm_paramaters:
    pass  # TODO

  vm_spec = {
              'location': location,
              'os_profile': {
                              'computer_name': vm_name,
                              'admin_username': vm_paramaters[ 'admin' ][ 'username' ],
                              'admin_password': vm_paramaters[ 'admin' ][ 'password' ]
                            },
              'hardware_profile':
              {
                  'vm_size': vm_paramaters[ 'size' ]
              },
              'storage_profile': storage_spec,
              'network_profile': { 'network_interfaces': nic_list }
            }

  worker = client.compute.virtual_machines.create_or_update( resource_group, vm_name, vm_spec )

  while not worker.done():
    logging.debug( 'azure: waiting for vm creation...' )
    worker.wait( POLL_INTERVAL )

  vm = worker.result()

  return { 'done': True, 'resource_name': vm.id.split( '/' )[ -1 ] }


def create_rollback( paramaters ):
  instance_name = paramaters[ 'name' ]
  logging.info( 'azure: rolling back instance "{0}"'.format( instance_name ) )

  raise Exception( 'azure rollback not implemented, yet' )

  logging.info( 'azure: instance "{0}" rolledback'.format( instance_name ) )
  return { 'rollback_done': True }


def destroy( paramaters ):
  resource_group = paramaters[ 'resource_group' ]
  resource_name = paramaters[ 'resource_name' ]
  connection_paramaters = paramaters[ 'connection' ]

  logging.info( 'azure: destroying vm "{0}" in "{1}"'.format( resource_name, resource_group ) )
  client = _connect( connection_paramaters )

  vm = client.compute.virtual_machines.get( resource_group, resource_name )

  worker = client.compute.virtual_machines.delete( resource_group, resource_name )
  while not worker.done():
    logging.debug( 'azure: waiting for vm delete...' )
    worker.wait( POLL_INTERVAL )

  for nic in vm.network_profile.network_interfaces:
    id = nic.id.split( '/' )[ -1 ]
    logging.debug( 'azure: deleting nic "{0}" in "{1}"'.format( id, resource_group ) )
    worker = client.network.network_interfaces.delete( resource_group, id )
    while not worker.done():
      logging.debug( 'azure: waiting for network interface delete...' )
      worker.wait( POLL_INTERVAL )

  id = vm.storage_profile.os_disk.managed_disk.id.split( '/' )[ -1 ]
  logging.debug( 'azure: deleting os disk "{0}" in "{1}"'.format( id, resource_group ) )
  worker = client.compute.disks.delete( resource_group, id )
  while not worker.done():
    logging.debug( 'azure: waiting for is disk delete...' )
    worker.wait( POLL_INTERVAL )

  for disk in vm.storage_profile.data_disks:
    id = disk.managed_disk.id.split( '/' )[ -1 ]
    logging.debug( 'azure: deleting data disk "{0}" in "{1}"'.format( id, resource_group ) )
    worker = client.compute.disks.delete( resource_group, id )
    while not worker.done():
      logging.debug( 'azure: waiting for data disk delete...' )
      worker.wait( POLL_INTERVAL )

  logging.info( 'azure: vm "{0}" in "{1}" destroyed'.format( resource_name, resource_group ) )
  return { 'done': True }


def _power_state_convert( instance_view ):
  code = None
  for status in instance_view.statuses:
    if status.code.startswith( 'PowerState/' ):
      code = status.code
      break

  code = instance_view.statuses[ -1 ].code
  if code in ( 'PowerState/deallocating', 'PowerState/deallocated', 'PowerState/stopped', 'PowerState/stopping' ):
    return 'off'

  elif code in ( 'PowerState/starting', 'PowerState/running' ):
    return 'on'

  else:
    return 'unknown "{0}"'.format( code )


def set_power( paramaters ):
  resource_group = paramaters[ 'resource_group' ]
  resource_name = paramaters[ 'resource_name' ]
  connection_paramaters = paramaters[ 'connection' ]
  desired_state = paramaters[ 'state' ]

  logging.info( 'azure: setting power state of "{0}" in "{1}" to "{2}"'.format( resource_name, resource_group, desired_state ) )
  client = _connect( connection_paramaters )

  curent_state = _power_state_convert( client.compute.virtual_machines.instance_view( resource_group, resource_name ) )
  if curent_state == desired_state or ( curent_state == 'off' and desired_state == 'soft_off' ):
    return { 'state': curent_state }

  if desired_state == 'on':
    client.compute.virtual_machines.start( resource_group, resource_name )
  elif desired_state == 'off':
    client.compute.virtual_machines.deallocate( resource_group, resource_name )  # doing deallocate instad of power_off to save $, mabey at some point have a option on the structure to do power off instead?
  elif desired_state == 'soft_off':
    client.compute.virtual_machines.deallocate( resource_group, resource_name )  # azure does the soft then 5 min later hard off for us
  else:
    raise Exception( 'Unknown desired state "{0}"'.format( desired_state ) )

  logging.info( 'azure: setting power state of "{0}" in "{1}" to "{2}" complete'.format( resource_name, resource_group, desired_state ) )
  return { 'state': _power_state_convert( client.compute.virtual_machines.instance_view( resource_group, resource_name ) ) }


def power_state( paramaters ):
  resource_group = paramaters[ 'resource_group' ]
  resource_name = paramaters[ 'resource_name' ]
  connection_paramaters = paramaters[ 'connection' ]

  logging.info( 'aws: get power state of "{0}" in "{1}"...'.format( resource_name, resource_group ) )
  client = _connect( connection_paramaters )

  return { 'state': _power_state_convert( client.compute.virtual_machines.instance_view( resource_group, resource_name ) ) }
