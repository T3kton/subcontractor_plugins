import socket
import logging

from subcontractor_plugins.iputils.pyping import ping


def ping( paramaters ):
  target = paramaters[ 'target' ]
  count = paramaters[ 'count' ]
  logging.info( 'iputils: pinging "{0}" "{1}" times...'.format( target, count ) )

  pinger = ping( target )
  pinger.run( count=count )

  logging.info( 'iputils: pinged "{0}", send: "{1}" recieved "{2}"'.format( target, pinger.send_count, pinger.receive_count ) )
  return { 'result': ( pinger.receive_count * 100.0 ) / pinger.send_count }


def port_state( paramaters ):
  target = paramaters[ 'target' ]
  port = paramaters[ 'port' ]
  logging.info( 'iputils: checking port "{0}" on "{1}"...'.format( port, target ) )

  sock = socket.socket()
  sock.sdttimeout( 5 )
  try:
    sock.connect( target, port )
    state = 'open'
  except socket.timeout:
    state = 'timeout'
  except socket.error:
    state = 'closed'
  except Exception as e:
    state = 'exception: "{0}"({1})'.format( str( e ), type( e ).__name__ )

  logging.info( 'iputils: checking port "{0}" on "{1}" is "{2}"'.format( port, target, state ) )
  return { 'result': state }
