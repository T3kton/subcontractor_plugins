import logging
import http
import socket
from threading import Timer
from datetime import datetime, timedelta
from urllib import request, parse
from tempfile import NamedTemporaryFile

from subcontractor_plugins.common.Packrat import PackratHandler, PackratsHandler, Packrat

PROGRESS_INTERVAL = 10  # in seconds
WEB_HANDLE_TIMEOUT = 60  # in seconds


class FileRetrieveException( Exception ):
  pass


def open_url( url, proxy, sslContext ):
  logging.info( 'opener: opening "{0}"'.format( url ) )

  opener = request.OpenerDirector()

  if proxy:  # not doing 'is not None', so empty strings don't try and proxy   # have a proxy option to take it from the envrionment vars
    opener.add_handler( request.ProxyHandler( { 'http': proxy, 'https': proxy } ) )
  else:
    opener.add_handler( request.ProxyHandler( {} ) )

  opener.add_handler( request.HTTPHandler() )
  opener.add_handler( PackratHandler() )

  if hasattr( http.client, 'HTTPSConnection' ):
    opener.add_handler( request.HTTPSHandler() )
    opener.add_handler( PackratsHandler() )

  opener.add_handler( request.FileHandler() )
  opener.add_handler( request.FTPHandler() )
  opener.add_handler( request.UnknownHandler() )

  try:
    resp = opener.open( url, timeout=WEB_HANDLE_TIMEOUT, context=sslContext )
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

  if resp.code is not None:  # FileHandler, FTPHandler do not have a response code
    if resp.code == 404:
      raise FileRetrieveException( 'File "{0}" not Found'.format( url ) )

    if resp.code != 200:
      raise FileRetrieveException( 'Invalid Response code "{0}"'.format( resp.code ) )

  return resp


def file_reader( url, proxy, sslContext ):
  local_file = NamedTemporaryFile( mode='wb', prefix='subcontractor_' )
  logging.debug( 'file_reader: downloading "{0}"'.format( url ) )
  resp = open_url( url, proxy, sslContext )

  size = int( resp.headers[ 'content-length' ] )

  buff = resp.read( 4096 * 1024 )
  cp = datetime.utcnow()
  while buff:
    if datetime.utcnow() > cp:
      cp = datetime.utcnow() + timedelta( seconds=PROGRESS_INTERVAL )
      logging.debug( 'file_reader: download at {0} of {1}'.format( local_file.tell(), size ) )

    local_file.write( buff )
    buff = resp.read( 4096 * 1024 )

  local_file.flush()
  local_file.seek( 0 )

  return local_file


class _file_writer_progress():
  def __init__( self, file, file_size ):
    self.file = file
    self.file_size = file_size
    self.cur_timer = None

  def start( self ):
    self.cur_timer = Timer( PROGRESS_INTERVAL, self._timer_cb ).start()

  def stop( self ):
    self.cur_timer.cancel()

  def _timer_cb( self ):
    self.cur_timer = Timer( PROGRESS_INTERVAL, self._timer_cb ).start()
    logging.debug( 'file_writer: uploaded at {0} of {1}'.format( self.local_file.tell(), self.file_size ) )


def file_writer( url, local_file, proxy, sslContext ):
  resp = open_url( url, proxy, sslContext )  # TODO: strip the query string from the url?
  logging.debug( 'file_writer: uploading to "{0}"'.format( url ) )

  file_size = local_file.seek( 0, 2 )
  local_file.seek( 0, 0 )

  headers = { 'Content-length': file_size }
  logger = _file_writer_progress( local_file, file_size )
  logger.start()
  try:
    req = request.Request( url, data=local_file, headers=headers, method='POST' )
    resp = request.urlopen( req, context=sslContext )

  finally:
    logger.stop()

  file_uri = resp.read()

  parts = parse.urlparse( url )
  if parts.scheme not in ( 'packrat', 'packrats' ):
    raise Exception( 'only packrat schema is curently supported' )

  if parts.schema == 'packrats':
    parts.schema = 'https'
  else:
    parts.schema = 'http'

  packagefile_name = parts.path
  options = parse.parse_qs( parts.query )
  parts.query = None
  parts.path = None

  packrat = Packrat( parse.urlunparse( parts ), 'nullunit', 'nullunit', proxy )

  logging.info( 'Packrat: Adding Packge File "{0}"'.format( packagefile_name ) )
  packrat.addPackageFile( file_uri, options[ 'justification' ], options[ 'provenance' ], options.get( 'type', None ), options.get( 'distroversion', None ))
