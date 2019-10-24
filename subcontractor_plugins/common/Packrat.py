import socket
import json
import logging
from cinp import client
from urllib import request, parse


PACKRAT_API_VERSION = '2.0'


class Packrat():
  def __init__( self, host, username, password, proxy ):
    self.cinp = client.CInP( host, '/api/v2/', proxy )

    root = self.cinp.describe( '/api/v2/' )
    if root[ 'api-version' ] != PACKRAT_API_VERSION:
      raise Exception( 'Expected API version "{0}" found "{1}"'.format( PACKRAT_API_VERSION, root[ 'api-version' ] ) )

    self.token = self.cinp.call( '/api/v2/Auth/User(login)', { 'username': username, 'password': password } )
    self.cinp.setAuth( username, self.token )

  def addPackageFile( self, file_uri, justification, provenance, type, distroversion ):
    distroversion_list = self.cinp.call( '/api/v2/Package/PackageFile(distroversionOptions)', { 'file': file_uri } )
    if distroversion is not None:
      if distroversion not in distroversion_list:
        raise Exception( 'distroversion "{0}" not in aviable distroverison list "{1}"'.format( distroversion, distroversion_list ) )

    else:
      if len( distroversion_list ) != 1:
        raise Exception( 'Unable to auto-detect distroversion, options: "{0}"'.format( distroversion_list ) )
      else:
        distroversion = distroversion_list[0]

    logging.info( 'Packrat: Adding file "{0}", justification: "{1}", provenance: "{2}", '
                  'distroversion: "{3}", type: "{4}"'.format( file_uri, justification, provenance, distroversion, type ) )

    result = self.cinp.call( '/api/v2/Package/PackageFile(create)',
                             {
                                 'file': file_uri,
                                 'justification': justification,
                                 'provenance': provenance,
                                 'distroversion': distroversion,
                                 'type': type
                             }, timeout=300 )  # it can sometimes take a while for packrat to commit large files, thus the long timeout
    return result


# TODO: study the way the proxy handler works and make this act more like that, we are carying way to much old baggage here
# schema:   packrat(s)://host/repo/type/package[?version]  if version is omitted, then the latest version
class PackratHandler( request.BaseHandler ):
  handler_order = 500  # same as regular http handler, mabey just before?

  def __init__( self, check_hash=True, gpg_key_file=None ):
    super().__init__()
    self.timeout = socket._GLOBAL_DEFAULT_TIMEOUT
    self.check_hash = check_hash
    self.gpg_key_file = gpg_key_file

  def add_parent( self, parent ):  # TODO: Until the proxy stuff is figured out, make sure to add PackratHandler after HTTP(s) and Proxy Handlers
    super().add_parent( parent )

    handler_name_list = [ i.__class__.__name__ for i in self.parent.handlers ]

    self.opener = request.OpenerDirector()
    if 'ProxyHandler' in handler_name_list:
      self.opener.add_handler( request.ProxyHandler( self.parent.handlers[ handler_name_list.index( 'ProxyHandler' ) ].proxies ) )

    self.opener.add_handler( request.HTTPHandler() )
    if 'HTTPSHandler' in handler_name_list:
      self.opener.add_handler( request.HTTPSHandler() )

    self.opener.addheaders = [ ( 'User-agent', 'subcontractor_plugin' ) ]

  def packrat_open( self, req ):
    return self._open( req, False, None )

  def _open( self, req, ssl, sslContext ):
    if not req.host:
      raise request.URLError( 'packrat error: no host given' )

    method = getattr( req, 'method', 'GET' )
    if method == 'GET':
      return self._open_get( req, ssl, sslContext )
    elif method == 'POST':
      return self._open_post( req, ssl, sslContext )
    else:
      raise ValueError( 'Invalid Method "{0}"'.format( method ) )

  def _open_get( self, req, ssl, sslContext ):
    header_map = {}
    package, version = parse.splitquery( req.selector )
    try:
      _, repo, file_type, package = package.split( '/' )
    except ValueError:
      raise ValueError( 'Unable to parse repo, type, and package' )

    # TODO: somekind of manifest caching?
    file_map = self._getFileList( req.host, repo, file_type, package, req.timeout )
    if not file_map:
      raise Exception( 'Entries for Package "{0}" of type "{1}" not found in repo "{2}"'.format( package, file_type, repo ) )

    if version is None:
      version_list = file_map.keys()
      entry = file_map[ sorted( version_list )[-1] ]

    else:
      try:
        entry = file_map[ version ]
      except KeyError:
        raise Exception( 'Version "{0}" for Package "{1}" of type "{2}" not found in repo "{3}"'.format( version, package, file_type, repo ) )

    if ssl:
      url = 'https://{0}/{1}/{2}'.format( req.host, repo, entry[ 'path' ] )
    else:
      url = 'http://{0}/{1}/{2}'.format( req.host, repo, entry[ 'path' ] )

    return self.opener.open( request.Request( url, headers=header_map, method='GET' ), timeout=req.timeout )

  def _open_post( self, req, ssl, sslContext ):
    header_map = req.headers

    if ssl:
      url = 'https://{0}/api/upload'.format( req.host )
    else:
      url = 'http://{0}/api/upload'.format( req.host )

    return self.opener.open( request.Request( url, data=req.data, headers=header_map, method='POST' ), timeout=req.timeout )

  def _request( self, host, repo, file, timeout ):
    url = 'http://{0}/{1}/{2}'.format( host, repo, file )

    try:
      resp = self.opener.open( url, timeout=timeout )
    except request.HTTPError as e:
      raise Exception( 'HTTPError "{0}"'.format( e ) )

    except request.URLError as e:
      if isinstance( e.reason, socket.timeout ):
        raise Exception( 'Request Timeout after {0} seconds'.format( timeout ) )

      raise Exception( 'URLError "{0}" for "{1}" via "{2}"'.format( e, url, self.proxy ) )

    except socket.timeout:
      raise Exception( 'Request Timeout after {0} seconds'.format( self.timeout ) )

    except socket.error as e:
      raise Exception( 'Socket Error "{0}"'.format( e ) )

    if resp.code == 404:
      raise Exception( 'File "{0}" not Found'.format( url ) )

    if resp.code != 200:
      raise Exception( 'Invalid Response code "{0}"'.format( resp.code ) )

    return resp.read()

  def _getFileList( self, host, repo, file_type, package, timeout ):
    result = {}
    manifest = json.loads( self._request( host, repo, '_repo_main/MANIFEST_all.json', timeout ).decode() )  # TODO: remove decode when newer version of python
    try:
      entry_list = manifest[ package ]
    except KeyError:
      return {}

    for entry in entry_list:
      if entry[ 'type' ] == file_type:
        result[ entry[ 'version' ] ] = entry

    return result


class PackratsHandler( PackratHandler ):
  def packrats_open( self, req, context=None ):
    return self._open( req, True, context )
