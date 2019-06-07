import logging
import paramiko
from datetime import datetime, timedelta

from subcontractor.credentials import getCredential
from subcontractor_plugins.common.files import file_reader


def _command_shorten( command ):
  return ( command[ :50 ] + '..' ) if len( command ) > 50 else command


def _connect( paramaters ):
  client = paramiko.SSHClient()
  client.set_missing_host_key_policy( paramiko.AutoAddPolicy() )

  password = getCredential( paramaters.get( 'password', None ) )
  kwargs = {
             'hostname': paramaters[ 'host' ],
             'username': paramaters.get( 'username', None ),
             'password': password,
            }

  client.connect( **kwargs )

  return client


def execute( paramaters ):
  command = paramaters[ 'command' ]
  logging.info( 'ssh: executing "{0}" on "{1}"...'.format( _command_shorten( command ), paramaters[ 'host' ] ) )

  client = _connect( paramaters )
  try:
    transport = client.get_transport()
    session = transport.open_channel( 'session' )
    session.set_combine_stderr( True )
    session.exec_command( command )

    finish_by = timedelta( seconds=paramaters[ 'timeout' ] ) + datetime.utcnow()
    while not session.exit_status_ready():
      buff = session.recv( 4096 )
      if buff:
        logging.debug( 'ssh: executing "{0}" on "{1}":"{2}"'.format( _command_shorten( command ), paramaters[ 'host' ], buff ) )
      if datetime.utcnow() > finish_by:
        raise Exception( 'timeout waiting for command to finish' )

    rc = session.recv_exit_status()

  finally:
    client.close()

  logging.info( 'ssh: execed "{0}" on "{1}" rc: "{2}"'.format( _command_shorten( command ), paramaters[ 'host' ], rc ) )
  return { 'rc': rc }


def _file_cb( sent, total ):
  logging.debug( 'ssh: transfer sent "{0}" of "{1}"'.format( sent, total ) )


def file( paramaters ):
  source = paramaters[ 'source' ]
  logging.info( 'ssh: transfering "{0}"-"{1}" to "{2}"...'.format( source, paramaters[ 'destination' ], paramaters[ 'host' ] ) )

  logging.debug( 'ssh: retreiving "{0}"'.format( paramaters[ 'destination' ] ) )
  local_file = file_reader( source, None )

  client = _connect( paramaters )
  try:
    sftp = client.open_sftp()
    sftp.putfo( local_file, paramaters[ 'destination' ], callback=_file_cb )
    sftp.close()

  finally:
    client.close()

  return { 'rc': True }
