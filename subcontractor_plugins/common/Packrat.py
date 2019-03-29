import socket
import json
from urllib import request, parse


# TODO: packratS handler
# TODO: study the way the proxy handler works and make this act more like that, we are carying way to much old baggage here
# schema:   packrat(s)://host/repo/type/package[?version]  if version is omitted, then the latest version
class PackratHandler( request.BaseHandler ):
  def __init__( self, check_hash=True, gpg_key_file=None ):
    super().__init__()
    self.timeout = socket._GLOBAL_DEFAULT_TIMEOUT
    self.check_hash = check_hash
    self.gpg_key_file = gpg_key_file

  def packrat_open( self, req ):
    if not req.host:
      raise request.URLError( 'packrat error: no host given' )

    package, file_type, version = parse.splitquery( req.selector )
    try:
      repo, package = package.split( '/' )
    except ValueError:
      raise ValueError( 'Unable to parse repo, type, and package' )

    # TODO: somekind of manifest caching?
    file_map = self._getPackageFiles( req.host, repo, file_type, package, req.timeout )
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

    url = 'http://{0}/{1}/{2}'.format( req.host, repo, entry[ 'path' ] )

    self.opener = request.OpenerDirector()
    self.opener.add_handler( request.ProxyHandler( self.parent.handlers[ 'proxyHandler'].proxies ) )
    self.opener.add_handler( request.HTTPHandler() )
    if 'HTTPSHandler' in self.parent.handlers:
      self.opener.add_handler( request.HTTPSHandler() )

    self.opener.addheaders = [ ( 'User-agent', 'subcontractor_plugin' ) ]

    return self.opener.open.open( url, timeout=req.timeout )

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
      entry_list = manifest[ 'package' ]
    except KeyError:
      return []

    for entry in entry_list:
      if entry[ 'type' ] == file_type:
        result[ entry[ 'version' ] ] = entry

    return result
