import logging
import time
import subprocess

from subcontractor.credentials import getCredentials


IPMITOOL_CMD = '/usr/bin/ipmitool'


class IPMIClient():
  def __init__( self, connection_paramaters ):
    super().__init__()
    self.ip_address = connection_paramaters[ 'ip_address' ]
    creds = connection_paramaters[ 'credentials' ]
    if isinstance( creds, str ):
      creds = getCredentials( creds )

    self.username = creds[ 'username' ]
    self.password = creds[ 'password' ]

  def _doCmd( self, cmd ):
    cmd = [ IPMITOOL_CMD, '-I', 'lanplus', '-H', self.ip_address, '-U', self.username, '-P', self.password, 'chassis', 'power', cmd ]

    return subprocess.check_output( cmd, shell=False )

  def getPower( self ):
    output = self._doCmd( 'status' )

    return output.split()[ -1 ]

  def setPower( self, state ):
    if state not in ( 'on', 'off', 'shutdown', 'cycle', 'reset' ):
      raise ValueError( 'Unknown power state "{0}"'.format( state ) )

    self._doCmd( state )


def set_power( paramaters ):
  connection_paramaters = paramaters[ 'connection' ]
  desired_state = paramaters[ 'state' ]

  logging.info( 'IPMI: setting power state of "{0}" to "{1}"...'.format( connection_paramaters[ 'ip_address' ], desired_state ) )
  client = IPMIClient( connection_paramaters )
  client.connect()

  curent_state = client.getPower()

  if curent_state == desired_state or ( curent_state == 'off' and desired_state == 'soft_off' ):
    return { 'state': curent_state }

  if desired_state == 'soft_off':
    desired_state = 'shutdown'

  client.setPower( desired_state )

  time.sleep( 1 )

  curent_state = client.getPower()
  logging.info( 'IPMI: setting power state of "{0}" to "{1}" complete'.format( connection_paramaters[ 'ip_address' ], desired_state ) )
  return { 'state': curent_state }


def power_state( paramaters ):
  connection_paramaters = paramaters[ 'connection' ]

  logging.info( 'IPMI: getting power state of "{0}"...'.format( connection_paramaters[ 'ip_address' ] ) )

  client = IPMIClient( connection_paramaters )
  client.connect()

  curent_state = client.getPower()
  return { 'state': curent_state }
