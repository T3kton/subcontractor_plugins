import logging
import time
from requests import exceptions

from subcontractor_plugins.amt.amt.client import Client
from subcontractor_plugins.amt.amt.wsman import POWER_STATES

POWER_STATE_LOOKUP = dict( zip( [ str( i ) for i in POWER_STATES.values() ], POWER_STATES.keys() ) )

MAX_RETRIES = 5


class AWTClient():
  def __init__( self, ip_address, password ):
    super().__init__()
    self.ip_address = ip_address
    self.password = password

  def connect( self ):
    self._conn = Client( self.ip_address, self.password )

  def disconnect( self ):
    pass

  def docmd( self, func ):  # some AMT baords take a bit to wake up
    counter = 0
    while counter < MAX_RETRIES:
      try:
        return func()
      except exceptions.ConnectionError:
        pass

      logging.debug( 'AMT: Connecting Refused, try {0} of {1}'.format( counter, MAX_RETRIES ) )
      time.sleep( 1 )
      counter += 1

    raise ConnectionRefusedError()

  def getPower( self ):
    result = self.docmd( self._conn.power_status )

    try:
      return POWER_STATE_LOOKUP[ result ]
    except KeyError:
      raise ValueError( 'Unknown power state "{0}"'.format( result ) )

  def setPower( self, state ):  # on, off, soft_off
    if state == 'on':
      self.docmd( self._conn.power_on )
    elif state == 'off':
      self.docmd( self._conn.power_off )
    elif state == 'soft_off':
      self.docmd( self._conn.power_off )
    else:
      raise ValueError( 'Unknown power stateu "{0}"'.format( state ) )


def set_power( paramaters ):
  ip_address = paramaters[ 'ip_address' ]
  password = paramaters[ 'password' ]
  desired_state = paramaters[ 'state' ]

  logging.info( 'AMT: setting power state of "{0}" to "{1}"...'.format( ip_address, desired_state ) )

  client = AWTClient( ip_address, password )
  client.connect()

  curent_state = client.getPower()

  if curent_state == desired_state or ( curent_state == 'off' and desired_state == 'soft_off' ):
    return { 'state': curent_state }

  client.setPower( desired_state )

  time.sleep( 1 )

  curent_state = client.getPower()
  client.disconnect()
  logging.info( 'AMT: setting power state of "{0}" to "{1}" complete'.format( ip_address, desired_state ) )
  return { 'state': curent_state }


def power_state( paramaters ):
  ip_address = paramaters[ 'ip_address' ]
  password = paramaters[ 'password' ]

  logging.info( 'AMT: getting power state of "{0}"...'.format( ip_address ) )

  client = AWTClient( ip_address, password )
  client.connect()

  curent_state = client.getPower()
  client.disconnect()
  return { 'state': curent_state }
