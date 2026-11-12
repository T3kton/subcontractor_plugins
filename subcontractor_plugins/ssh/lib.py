import logging
import paramiko
from datetime import datetime, timedelta

from subcontractor.credentials import getCredentials
from subcontractor_plugins.common.files import file_reader


def _command_shorten( command ):
  return ( command[ :50 ] + '..' ) if len( command ) > 50 else command


def _connect( parameters ):
  client = paramiko.SSHClient()
  client.set_missing_host_key_policy( paramiko.AutoAddPolicy() )

  password = getCredentials( parameters.get( 'password', None ) )
  kwargs = {
             'hostname': parameters[ 'host' ],
             'username': parameters.get( 'username', None ),
             'password': password,
            }

  client.connect( **kwargs )

  return client


def execute( parameters ):
  command = parameters[ 'command' ]
  logging.info( 'ssh: executing "{0}" on "{1}"...'.format( _command_shorten( command ), parameters[ 'host' ] ) )

  client = _connect( parameters )
  try:
    transport = client.get_transport()
    session = transport.open_channel( 'session' )
    session.set_combine_stderr( True )
    session.exec_command( command )

    finish_by = timedelta( seconds=parameters[ 'timeout' ] ) + datetime.utcnow()
    while not session.exit_status_ready():
      buff = session.recv( 4096 )
      if buff:
        logging.debug( 'ssh: executing "{0}" on "{1}":"{2}"'.format( _command_shorten( command ), parameters[ 'host' ], buff ) )
      if datetime.utcnow() > finish_by:
        raise Exception( 'timeout waiting for command to finish' )

    rc = session.recv_exit_status()

  finally:
    client.close()

  logging.info( 'ssh: execed "{0}" on "{1}" rc: "{2}"'.format( _command_shorten( command ), parameters[ 'host' ], rc ) )
  return { 'rc': rc }


def _file_cb( sent, total ):
  logging.debug( 'ssh: transfer sent "{0}" of "{1}"'.format( sent, total ) )


def file( parameters ):
  source = parameters[ 'source' ]
  logging.info( 'ssh: transfering "{0}"-"{1}" to "{2}"...'.format( source, parameters[ 'destination' ], parameters[ 'host' ] ) )

  logging.debug( 'ssh: retreiving "{0}"'.format( parameters[ 'destination' ] ) )
  local_file = file_reader( source, None )

  client = _connect( parameters )
  try:
    sftp = client.open_sftp()
    sftp.putfo( local_file, parameters[ 'destination' ], callback=_file_cb )
    sftp.close()

  finally:
    client.close()

  return { 'rc': True }
