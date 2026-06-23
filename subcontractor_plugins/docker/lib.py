import logging
import docker


# http://docker-py.readthedocs.io/en/1.10.0/api/
def _connect( connection_parameters ):
  try:
    host = connection_parameters[ 'host' ]
  except KeyError:
    raise ValueError( '\'host\' is required' )

  logging.debug( 'docker: connecting to docker at "{0}"'.format( host ) )

  return docker.DockerClient( base_url='tcp://{0}:2376'.format( host ) )


def create( parameters ):
  container_name = parameters[ 'name' ]
  connection_parameters = parameters[ 'connection' ]
  logging.info( 'docker: creating container "{0}"'.format( container_name ) )
  client = _connect( connection_parameters )

  logging.debug( 'docker: pulling "{0}"'.format( parameters[ 'docker_image' ] ) )
  try:
    client.images.pull( parameters[ 'docker_image' ] )
  except Exception as e:
    raise Exception( 'Error Creating Container: {0}'.format( str( e ) ) )

  container_parameters = {
                          'auto_remove': False,
                          'detach': True,
                          'image': parameters[ 'docker_image' ],
                          'name': container_name,
                          'ports': parameters[ 'port_map' ],
                          'environment': parameters[ 'environment_map' ],
                          'command': parameters[ 'command' ]
                         }

  logging.debug( 'docker: creating "{0}"'.format( container_parameters ) )
  try:
    container = client.containers.create( **container_parameters )
  except Exception as e:
    raise Exception( 'Error Creating Container: {0}'.format( str( e ) ) )

  docker_id = container.id

  logging.info( 'docker: container "{0}" created'.format( container_name ) )
  return { 'done': True, 'id': docker_id }


def create_rollback( parameters ):
  container_name = parameters[ 'name' ]
  # connection_parameters = parameters[ 'connection' ]

  logging.info( 'docker: rolling back container "{0}"'.format( container_name ) )

  raise Exception( 'docker rollback not implemented, yet' )
  # client = _connect( connection_parameters )

  logging.info( 'docker: container "{0}" rolledback'.format( container_name ) )
  return { 'rollback_done': True }


def destroy( parameters ):
  docker_id = parameters[ 'docker_id' ]
  connection_parameters = parameters[ 'connection' ]
  container_name = parameters[ 'name' ]
  logging.info( 'docker: destroying container "{0}"({1})'.format( container_name, docker_id ) )
  client = _connect( connection_parameters )
  try:
    container = client.containers.get( docker_id )
  except Exception as e:
    raise Exception( 'Error Getting Container "{0}": {1}'.format( docker_id, str( e ) ) )

  try:
    container.remove( force=True )
  except Exception as e:
    raise Exception( 'Error Removing Container "{0}": {1}'.format( docker_id, str( e ) ) )

  logging.info( 'docker: container "{0}" destroyed'.format( container_name ) )
  return { 'done': True }


def _power_state_convert( state ):
  print( '****************** {0}'.format(state))
  if state == 'running':
    return 'start'

  else:
    return 'stop'

  # else:
  #   return 'unknown "{0}"'.format( state )


def start_stop( parameters ):
  docker_id = parameters[ 'docker_id' ]
  connection_parameters = parameters[ 'connection' ]
  container_name = parameters[ 'name' ]
  desired_state = parameters[ 'state' ]
  logging.info( 'docker: setting state of "{0}"({1}) to "{2}"...'.format( container_name, docker_id, desired_state ) )
  client = _connect( connection_parameters )
  try:
    container = client.containers.get( docker_id )
  except Exception as e:
    raise Exception( 'Error Getting Container "{0}": {1}'.format( docker_id, str( e ) ) )

  curent_state = _power_state_convert( container.status )
  if curent_state == desired_state:
    return { 'state': curent_state }

  if desired_state == 'start':
    try:
      container.start()
    except Exception as e:
      raise Exception( 'Error Starting Container "{0}": {1}'.format( docker_id, str( e ) ) )

  elif desired_state == 'stop':
    try:
      container.stop()
    except Exception as e:
      raise Exception( 'Error Stopping Container "{0}": {1}'.format( docker_id, str( e ) ) )

  else:
    raise Exception( 'Unknown desired state "{0}"'.format( desired_state ) )

  logging.info( 'docker: setting state of "{0}"({1}) to "{2}" complete'.format( container_name, docker_id, desired_state ) )
  return { 'state': desired_state }


def state( parameters ):
  docker_id = parameters[ 'docker_id' ]
  connection_parameters = parameters[ 'connection' ]
  container_name = parameters[ 'name' ]
  logging.info( 'docker: getting "{0}"({1}) power state...'.format( container_name, docker_id ) )
  client = _connect( connection_parameters )
  try:
    container = client.containers.get( docker_id )
  except Exception as e:
    raise Exception( 'Error Getting Container "{0}": {1}'.format( docker_id, str( e ) ) )

  return { 'state': _power_state_convert( container.status ) }
