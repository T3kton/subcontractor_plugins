import logging
import asyncio
from requests import exceptions

from subcontractor.credentials import getCredentials
from subcontractor_plugins.amt.amt.client import Client
from subcontractor_plugins.amt.amt.wsman import POWER_STATES

POWER_STATE_LOOKUP = dict( zip( [ str( i ) for i in POWER_STATES.values() ], POWER_STATES.keys() ) )

MAX_RETRIES = 5


class AWTClient():
  def __init__( self, connection_parameters ):
    super().__init__()
    self.ip_address = connection_parameters[ 'ip_address' ]
    creds = connection_parameters[ 'credentials' ]
    if isinstance( creds, str ):
      creds = getCredentials( creds )

    self.username = creds[ 'username' ]
    self.password = creds[ 'password' ]

  def connect( self ):
    self._conn = Client( self.ip_address, self.password, self.username )

  def disconnect( self ):
    pass

  async def _doCmd( self, func ):  # some AMT baords take a bit to wake up
    counter = 0
    while counter < MAX_RETRIES:
      try:
        return func()
      except exceptions.ConnectionError:
        pass

      logging.debug( 'AMT: Connecting Refused, try {0} of {1}'.format( counter, MAX_RETRIES ) )
      await asyncio.sleep( 1 )
      counter += 1

    raise ConnectionRefusedError()

  async def getPower( self ):
    result = await self._doCmd( self._conn.power_status )

    try:
      return POWER_STATE_LOOKUP[ result ]
    except KeyError:
      raise ValueError( 'Unknown power state "{0}"'.format( result ) )

  async def setPower( self, state ):  # on, off, soft_off
    if state == 'on':
      await self._doCmd( self._conn.power_on )
    elif state == 'off':
      await self._doCmd( self._conn.power_off )
    elif state == 'soft_off':
      await self._doCmd( self._conn.power_off )
    else:
      raise ValueError( 'Unknown power state "{0}"'.format( state ) )


async def set_power( parameters ):
  connection_parameters = parameters[ 'connection' ]
  desired_state = parameters[ 'state' ]

  logging.info( 'AMT: setting power state of "{0}" to "{1}"...'.format( connection_parameters[ 'ip_address' ], desired_state ) )
  client = AWTClient( connection_parameters )
  client.connect()

  curent_state = client.getPower()

  if curent_state == desired_state or ( curent_state == 'off' and desired_state == 'soft_off' ):
    return { 'state': curent_state }

  client.setPower( desired_state )

  await asyncio.sleep( 1 )

  curent_state = client.getPower()
  client.disconnect()
  logging.info( 'AMT: setting power state of "{0}" to "{1}" complete'.format( connection_parameters[ 'ip_address' ], desired_state ) )
  return { 'state': curent_state }


def power_state( parameters ):
  connection_parameters = parameters[ 'connection' ]

  logging.info( 'AMT: getting power state of "{0}"...'.format( connection_parameters[ 'ip_address' ] ) )

  client = AWTClient( connection_parameters )
  client.connect()

  curent_state = client.getPower()
  client.disconnect()
  return { 'state': curent_state }
