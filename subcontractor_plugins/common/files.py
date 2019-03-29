import logging
import http
import socket
from datetime import datetime, timedelta
from urllib import request
from tempfile import NamedTemporaryFile

from subcontractor_plugins.Packrat import PackratHandler

PROGRESS_INTERVAL = 10  # in seconds
WEB_HANDLE_TIMEOUT = 60  # in seconds


class FileRetrieveException( Exception ):
  pass


def file_retrieve( url, target_file, proxy ):
  logging.info( 'file_retrieve: Downloading "{0}"'.format( url ))
  opener = request.OpenerDirector()

  if proxy:  # not doing 'is not None', so empty strings don't try and proxy   # have a proxy option to take it from the envrionment vars
    opener.add_handler( request.ProxyHandler( { 'http': proxy, 'https': proxy } ) )
  else:
    opener.add_handler( request.ProxyHandler( {} ) )

  opener.add_handler( request.HTTPHandler() )
  if hasattr( http.client, 'HTTPSConnection' ):
    opener.add_handler( request.HTTPSHandler() )

  opener.add_handler( PackratHandler )
  opener.add_handler( request.FileHandler )
  opener.add_handler( request.FTPHandler )
  opener.add_handler( request.UnknownHandler() )

  try:
    resp = opener.open( url, timeout=WEB_HANDLE_TIMEOUT )
  except request.HTTPError as e:
    raise FileRetrieveException( 'HTTPError "{0}"'.format( e ) )

  except request.URLError as e:
    if isinstance( e.reason, socket.timeout ):
      raise FileRetrieveException( 'Request Timeout after {0} seconds'.format( WEB_HANDLE_TIMEOUT ) )

    raise FileRetrieveException( 'URLError "{0}" for "{1}" via "{2}"'.format( e, url, proxy ) )

  except socket.timeout:
    raise FileRetrieveException( 'Request Timeout after {0} seconds'.format( WEB_HANDLE_TIMEOUT ) )

  except socket.error as e:
    raise FileRetrieveException( 'Socket Error "{0}"'.format( e ) )

  if resp.code == 404:
    raise FileRetrieveException( 'File "{0}" not Found'.format( url ) )

  if resp.code != 200:
    raise FileRetrieveException( 'Invalid Response code "{0}"'.format( resp.code ) )

  if isinstance( target_file, str ):
    fp = open( target_file, 'wb' )
  else:
    fp = target_file

  size = int( resp.headers[ 'content-length' ] )

  buff = resp.read( 4096 * 1024 )
  cp = datetime.utcnow()
  while buff:
    if datetime.utcnow() > cp:
      cp = datetime.utcnow() + timedelta( seconds=PROGRESS_INTERVAL )
      logging.debug( 'file_retrieve: download at {0} of {1}'.format( fp.tell(), size ) )

    fp.write( buff )
    buff = resp.read( 4096 * 1024 )

  if isinstance( target_file, str ):
    fp.close()
  else:
    fp.flush()


def file_reader( url, proxy ):
  local_file = NamedTemporaryFile( mode='wb', prefix='subcontractor_' )

  file_retrieve( url, local_file, proxy )

  local_file.seek( 0 )

  return local_file
