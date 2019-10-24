import logging
import http
import socket
import json
from threading import Timer
from datetime import datetime, timedelta
from urllib import request, parse
from tempfile import NamedTemporaryFile

from subcontractor_plugins.common.Packrat import PackratHandler, PackratsHandler, Packrat

PROGRESS_INTERVAL = 10  # in seconds
WEB_HANDLE_TIMEOUT = 60  # in seconds


class FileRetrieveException( Exception ):
  pass


def open_url( url, proxy, resp_code, sslContext ):
  if isinstance( url, request.Request ):
    logging.info( 'opener: opening "{0}"'.format( url.full_url ) )
  else:
    logging.info( 'opener: opening "{0}"'.format( url ) )

  opener = request.OpenerDirector()

  if proxy:  # not doing 'is not None', so empty strings don't try and proxy   # have a proxy option to take it from the envrionment vars
    opener.add_handler( request.ProxyHandler( { 'http': proxy, 'https': proxy } ) )
  else:
    opener.add_handler( request.ProxyHandler( {} ) )

  opener.add_handler( request.HTTPHandler() )
  opener.add_handler( PackratHandler() )

  if hasattr( http.client, 'HTTPSConnection' ):
    opener.add_handler( request.HTTPSHandler() )  # context=sslContext
    opener.add_handler( PackratsHandler() )  # context=sslContext

  opener.add_handler( request.FileHandler() )
  opener.add_handler( request.FTPHandler() )
  opener.add_handler( request.UnknownHandler() )

  try:
    resp = opener.open( url, timeout=WEB_HANDLE_TIMEOUT )
  except request.HTTPError as e:
    raise FileRetrieveException( 'HTTPError "{0}"'.format( e ) )

  except request.URLError as e:
    if isinstance( e.reason, socket.timeout ):
      raise FileRetrieveException( 'Request Timeout after {0} seconds'.format( WEB_HANDLE_TIMEOUT ) )

    raise FileRetrieveException( 'URLError "{0}" for "{1}" via "{2}"'.format( e, url.full_url, proxy ) )

  except socket.timeout:
    raise FileRetrieveException( 'Request Timeout after {0} seconds'.format( WEB_HANDLE_TIMEOUT ) )

  except socket.error as e:
    raise FileRetrieveException( 'Socket Error "{0}"'.format( e ) )

  if resp.code is not None:  # FileHandler, FTPHandler do not have a response code
    if resp.code == 404:
      raise FileRetrieveException( 'File "{0}" not Found'.format( url ) )

    if resp.code != resp_code:
      raise FileRetrieveException( 'Invalid Response code "{0}"'.format( resp.code ) )

  return resp


def file_reader( url, proxy, sslContext ):
  local_file = NamedTemporaryFile( mode='w+b', prefix='subcontractor_' )
  logging.debug( 'file_reader: downloading "{0}"'.format( url ) )
  resp = open_url( url, proxy, 200, sslContext )

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
    self.cur_timer = Timer( PROGRESS_INTERVAL, self._timer_cb )
    self.cur_timer.start()

  def stop( self ):
    if self.cur_timer is not None:
      self.cur_timer.cancel()
      self.cur_timer = None

  def _timer_cb( self ):
    self.cur_timer = Timer( PROGRESS_INTERVAL, self._timer_cb )
    self.cur_timer.start()
    logging.debug( 'file_writer: uploaded at {0} of {1}'.format( self.file.tell(), self.file_size ) )


def file_writer( url, local_file, filename, proxy, sslContext ):
  logging.debug( 'file_writer: uploading to "{0}"'.format( url ) )

  file_size = local_file.seek( 0, 2 )
  local_file.seek( 0, 0 )

  header_map = {
                 'Content-Length': file_size,
                 'Content-Disposition': 'inline: filename="{0}"'.format( filename ),
                 'Content-Type': 'application/octet-stream'
               }

  logger = _file_writer_progress( local_file, file_size )
  logger.start()
  try:
    req = request.Request( url, data=local_file, headers=header_map, method='POST' )
    resp = open_url( req, proxy, 202, sslContext )  # TODO: strip the query string from the url?

  finally:
    logger.stop()

  # TODO: the rest of this should be in the handler some how, see if there is some hook that happens when the writing is closed or something
  result = resp.read()
  file_uri = json.loads( str( result, 'utf-8' ) )[ 'uri' ]  # TODO: need some error checking and such here

  parts = parse.urlparse( url )
  if parts.scheme not in ( 'packrat', 'packrats' ):
    raise Exception( 'only packrat scheme is curently supported' )

  packagefile_name = parts.path
  options = parse.parse_qs( parts.query )

  if parts.scheme == 'packrats':
    parts = parts._replace( scheme='https', query=None, path='' )
  else:
    parts = parts._replace( scheme='http', query=None, path='' )

  packrat = Packrat( parse.urlunparse( parts ), 'nullunit', 'nullunit', proxy )  # TODO: get username and password from URL?

  logging.info( 'file_writer: Adding Packge File "{0}"'.format( packagefile_name ) )
  packrat.addPackageFile( file_uri, options[ 'justification' ][0], options[ 'provenance' ][0], options.get( 'type', None ), options.get( 'distroversion', None ))
