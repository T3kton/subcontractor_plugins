import logging
import docker


# http://docker-py.readthedocs.io/en/1.10.0/api/
def _connect():
  logging.debug( 'docker: connecting to docker' )
  return docker.from_env()


def create( paramaters ):
  container_name = paramaters[ 'name' ]
  logging.info( 'docker: creating container "{0}"'.format( container_name ) )
  client = _connect()

  container_paramaters = {
                          'image': paramaters[ 'docker_image' ],
                          'name': container_name,
                          'ports': [ 22 ],
                          'host_config': client.create_host_config( port_bindings={ 22: 4222 } )
                        }

  try:
    rc = client.create_container( **container_paramaters )
  except docker.APIError as e:
    raise Exception( 'Error Creating Container: {0}'.format( str( e ) ) )

  if rc[ 'Warnings' ]:
    logging.warn( 'docker: container creation had the foloowing warning(s): "{0}"'.format( rc[ 'Warnings' ] ) )
  container_id = rc[ 'Id' ]

  logging.info( 'docker: container "{0}" created'.format( container_name ) )
  return { 'done': True, 'id': container_id }


def create_rollback( paramaters ):
  container_name = paramaters[ 'name' ]
  logging.info( 'docker: rolling back container "{0}"'.format( container_name ) )

  raise Exception( 'docker rollback not implemented, yet' )

  logging.info( 'docker: container "{0}" rolledback'.format( container_name ) )
  return { 'rollback_done': True }


def destroy( paramaters ):
  container_id = paramaters[ 'container_id' ]
  container_name = paramaters[ 'name' ]
  logging.info( 'docker: destroying container "{0}"({1})'.format( container_name, container_id ) )
  client = _connect()

  client.stop( container=container_id )

  # try:
  #   instance.wait_for_termated()
  # except WaiterError:
  #   raise Exception( 'Timeout waiting for AWS EC2 instance "{0}" to be terminated'.format( container_name ) )

  client.remove_container( container=container_id )

  logging.info( 'docker: container "{0}" destroyed'.format( container_name ) )
  return { 'done': True }


def _power_state_convert( state ):
  if state[ 'Running' ]:
    return 'start'

  else:
    return 'stop'

  # else:
  #   return 'unknown "{0}"'.format( state )


def start_stop( paramaters ):
  container_id = paramaters[ 'container_id' ]
  container_name = paramaters[ 'name' ]
  desired_state = paramaters[ 'state' ]
  logging.info( 'docker: setting state of "{0}"({1}) to "{2}"...'.format( container_name, container_id, desired_state ) )
  client = _connect()

  curent_state = _power_state_convert( client.inspect_container( container=container_id )[ 'State' ] )
  if curent_state == desired_state:
    return { 'state': curent_state }

  if desired_state == 'start':
    client.start( container=container_id )

  elif desired_state == 'stop':
    client.stop( container=container_id )

  else:
    raise Exception( 'Unknown desired state "{0}"'.format( desired_state ) )

  logging.info( 'docker: setting state of "{0}"({1}) to "{2}" complete'.format( container_name, container_id, desired_state ) )
  return { 'state': desired_state }


def state( paramaters ):
  container_id = paramaters[ 'container_id' ]
  container_name = paramaters[ 'name' ]
  logging.info( 'docker: getting "{0}"({1}) power state...'.format( container_name, container_id ) )
  client = _connect()

  return { 'state': _power_state_convert( client.inspect_container( container=container_id )[ 'State' ] ) }
