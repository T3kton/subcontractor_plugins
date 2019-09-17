import logging
import time
import subprocess

from subcontractor.credentials import getCredentials


IPMITOOL_CMD = '/usr/bin/ipmitool'

IPMI_CMD_MAX_RETRY = 3
IPMI_CMD_RETRY_DELAY = 5


def ignorable_errors( msg ):
  if msg.find( "Assertion `session->v2_data.session_state == LANPLUS_STATE_PRESESSION'" ) != -1:  # rc = -6
    return True
  if msg.find( "Assertion `session->v2_data.session_state == LANPLUS_STATE_RAKP_2_RECEIVED'" ) != -1:  # rc = -6
    return True
  if msg.find( "Error: Received an Unexpected Open Session Response" ) != -1:  # rc = -6
    return True
  if msg.find( "Out:Error in open session response message : insufficient resources for session" ) != -1:  # rc = 1
    return True
  if msg.find( "Error: Unable to establish IPMI v2 / RMCP+ session" ) != -1:  # rc = 1
    return True
  if msg.find( "ipmi_lanplus_send_payload: Assertion `session->v2_data.session_state == LANPLUS_STATE_OPEN_SESSION_RECEIEVED' failed." ) != -1:  # rc = -6
    return True
  if msg.find( "Unable to get Chassis Power Status" ) != -1:
    return True
  if msg.find( "Timeout Attempting power" ) != -1:
    return True
  if msg.find( "Unexpected Result \"Close Session command failed\"" ) != -1:
    return True
  if msg.find( "Unknown Error \"Set Session Privilege Level to ADMINISTRATOR failed \"" ) != -1:
    return True
  if msg.find( "Close Session command failed" ) != -1:
    return True

  return False


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

    for _ in range( 0, IPMI_CMD_MAX_RETRY ):
      logging.debug( 'IPMI: calling "{0}"'.format( cmd ) )
      proc = subprocess.run( cmd, shell=False, stdin=subprocess.PIPE, stdout=subprocess.STDOUT )
      lines = str( proc.stdout, 'utf-8' ).strip().splitlines()

      if proc.returncode == 0:
        return lines[0]

      if not ignorable_errors( lines[0] ):
        logging.error( 'IPMI: Unknown or Non-Ignorable error "{0}", rc: "{1}"'.format( lines, proc.returncode ) )
        return 'error'

      logging.warning( 'IPMI: got ignorable error "{0}", rc: "{1}"', format( lines, proc.returncode ) )
      time.sleep( IPMI_CMD_RETRY_DELAY )

    logging.warning( 'IPMI: Max retries, bailing' )
    return 'error'

  def getPower( self ):
    result = self._doCmd( 'status' )

    if result is None:
      return 'error'

    return result.split()[ -1 ]

  def setPower( self, state ):
    if state not in ( 'on', 'off', 'shutdown', 'cycle', 'reset' ):
      raise ValueError( 'Unknown power state "{0}"'.format( state ) )

    self._doCmd( state )


def link_test( paramaters ):
  connection_paramaters = paramaters[ 'connection' ]
  scaler = paramaters[ 'scaler' ]
  threshold = paramaters[ 'threshold' ]
  delay = paramaters[ 'delay' ]
  score = 1.0

  logging.info( 'IPMI: link test on "{0}"...'.format( connection_paramaters[ 'ip_address' ] ) )
  client = IPMIClient( connection_paramaters )

  for count in range( 0, paramaters[ 'count' ] ):
    score = score * scaler + ( scaler - 1 ) * ( 1 if client.getPower() == 'error' else 0 )

    if score < threshold:
      return { 'score': score }

    time.sleep( delay )

  return { 'score': score }


def set_power( paramaters ):
  connection_paramaters = paramaters[ 'connection' ]
  desired_state = paramaters[ 'state' ]

  logging.info( 'IPMI: setting power state of "{0}" to "{1}"...'.format( connection_paramaters[ 'ip_address' ], desired_state ) )
  client = IPMIClient( connection_paramaters )

  curent_state = client.getPower()

  if curent_state == desired_state or ( curent_state == 'off' and desired_state == 'soft_off' ):
    return { 'state': curent_state }

  if desired_state == 'soft_off':
    desired_state = 'shutdown'

  client.setPower( desired_state )  # TODO: do we want to do something if there is an error here?  the next call to getPower should pick up anything

  time.sleep( 1 )

  curent_state = client.getPower()
  logging.info( 'IPMI: setting power state of "{0}" to "{1}" complete'.format( connection_paramaters[ 'ip_address' ], desired_state ) )
  return { 'state': curent_state }


def power_state( paramaters ):
  connection_paramaters = paramaters[ 'connection' ]

  logging.info( 'IPMI: getting power state of "{0}"...'.format( connection_paramaters[ 'ip_address' ] ) )

  client = IPMIClient( connection_paramaters )

  curent_state = client.getPower()
  return { 'state': curent_state }
