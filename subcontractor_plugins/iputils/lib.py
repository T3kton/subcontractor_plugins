import socket
import logging
# pysnmp 4.4.12 smi/builder.py only does "import importlib", and falls back to the removed "imp" module (py3.12+) if importlib.util isn't already loaded
import importlib.util  # noqa: F401
import importlib.machinery  # noqa: F401
from pysnmp import hlapi

from subcontractor_plugins.iputils.pyping import ping as pyping


def ping( parameters ):
  target = parameters[ 'target' ]
  count = parameters[ 'count' ]
  logging.debug( 'iputils: pinging "{0}" "{1}" times...'.format( target, count ) )

  pinger = pyping( target )
  pinger.run( count=count )

  logging.info( 'iputils: pinged "{0}", send: "{1}" recieved "{2}"'.format( target, pinger.send_count, pinger.receive_count ) )
  return { 'result': ( pinger.receive_count * 100.0 ) / pinger.send_count }


def port_state( parameters ):
  target = parameters[ 'target' ]
  try:
    port = parameters[ 'port' ]
  except TypeError:
    raise ValueError( 'Port parameter must be an integer' )

  logging.debug( 'iputils: checking port "{0}" on "{1}"...'.format( port, target ) )

  sock = socket.socket()
  sock.settimeout( 5 )  # TODO: also do 'noroute to host'
  try:
    sock.connect( ( target, port ) )
    state = 'open'
  except socket.timeout:
    state = 'timeout'
  except socket.error as e:
    if e.errno == 113:
      state = 'no route to host'
    else:
      state = 'closed'
  except Exception as e:
    state = 'exception: "{0}"({1})'.format( str( e ), type( e ).__name__ )

  logging.info( 'iputils: checking port "{0}" on "{1}" is "{2}"'.format( port, target, state ) )
  return { 'state': state }


def _snmp_connection( connection_parameters ):
  creds = connection_parameters[ 'creds' ]
  protocol = connection_parameters.get( 'protocol', 'SNMPv2c' )
  if protocol == 'SNMPv1':
    data = hlapi.CommunityData( creds[ 'community' ], mpModel=0 )
  elif protocol == 'SNMPv2c':
    data = hlapi.CommunityData( creds[ 'community' ], mpModel=1 )
  elif protocol == 'SNMPv3':
    try:
      auth_key = creds[ 'auth_key' ]
      priv_key = creds[ 'priv_key' ]
    except KeyError:
      auth_key = None

    if auth_key is not None:
      data = hlapi.UsmUserData( creds[ 'user' ], auth_key, priv_key )
    else:
      data = hlapi.UsmUserData( creds[ 'user' ] )

  else:
    raise ValueError( 'Unknown protocol "{0}"'.format( protocol ) )

  return ( hlapi.SnmpEngine(),
           data,
           hlapi.UdpTransportTarget(( connection_parameters[ 'host' ], connection_parameters.get( 'port', 161 ) )),
           hlapi.ContextData()
           )


def snmp_get( parameters ):
  connection_parameters = parameters[ 'connection' ]
  oid = parameters[ 'oid' ]
  logging.debug( 'iputils: SNMP get OID "{0}" from "{1}"...'.format( oid, connection_parameters[ 'host' ] ) )

  cmd = hlapi.getCmd( *_snmp_connection( connection_parameters ), hlapi.ObjectType( hlapi.ObjectIdentity( oid ) ) )

  error, errorStatus, errorIndex, result = next( cmd )
  if error is not None:
    raise Exception( 'Error with SNMP get: "{0}", Error Status: "{1}", Error Index: {2}'.format( error, errorStatus, errorIndex ) )

  value = result[0]._ObjectType__args[1].prettyPrint()  # there has to be a better way to get the value from ObjecType than this

  logging.info( 'iputils: SNMP get OID "{0}" from "{1}" is "{2}"'.format( oid, connection_parameters[ 'host' ], value ) )

  return { 'value': value }


def snmp_set( parameters ):
  connection_parameters = parameters[ 'connection' ]
  oid = parameters[ 'oid' ]
  value = parameters[ 'value' ]

  logging.debug( 'iputils: SNMP set OID "{0}" on "{1}" to "{2}"...'.format( oid, connection_parameters[ 'host' ], value ) )

  cmd = hlapi.setCmd( *_snmp_connection( connection_parameters ), hlapi.ObjectType( hlapi.ObjectIdentity( oid ), value ) )

  error, errorStatus, errorIndex, result = next( cmd )
  if error is not None:
    raise Exception( 'Error with SNMP Set: "{0}", Error Status: "{1}", Error Index: {2}'.format( error, errorStatus, errorIndex ) )

  logging.info( 'iputils: SNMP set OID "{0}" on "{1}" to "{2}"'.format( oid, connection_parameters[ 'host' ], value ) )

  return { 'done': True }
