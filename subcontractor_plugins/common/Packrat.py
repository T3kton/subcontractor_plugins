import os
import socket
import json
from urllib import request, parse


PACKRAT_TIMEOUT = 60


class PackratException( Exception ):
  pass


class HTTPErrorProcessorPassthrough( request.HTTPErrorProcessor ):
  def http_response( self, request, response ):
    return response


def packrat_from_url( url, type, proxy ):
  if not url.startswith( ( 'packrat://', 'packrats://' ) ):
    raise ValueError( 'not a packrat url' )

  parts = parse.urlsplit( url )

  packrat = Packrat( parts.netloc, os.path.dirname( parts.path ), type, proxy, url.startswith( 'packrats://' ) )

  return packrat, os.path.basename( parts.path )


class Packrat():
  def __init__( self, host, repo, type, proxy=None, tls=False ):
    super().__init__()
    self.type = type
    if proxy:  # not doing 'is not None', so empty strings don't try and proxy   # have a proxy option to take it from the envrionment vars
      self.proxy = proxy
      self.opener = request.build_opener( HTTPErrorProcessorPassthrough, request.ProxyHandler( { 'http': proxy, 'https': proxy } ) )
    else:
      self.proxy = None
      self.opener = request.build_opener( HTTPErrorProcessorPassthrough, request.ProxyHandler( {} ) )

    self.opener.addheaders = [ ( 'User-agent', 'subcontractor_plugin' ) ]

    if tls:
      host = 'https://{0}'.format( host )
    else:
      host = 'http://{0}'.format( host )

    self.root = '{0}{1}/'.format( host, repo )
    self._loadManifest()

  def _request( self, file ):
    url = '{0}{1}'.format( self.root, file )

    try:
      resp = self.opener.open( url, timeout=PACKRAT_TIMEOUT )
    except request.HTTPError as e:
      raise PackratException( 'HTTPError "{0}"'.format( e ) )

    except request.URLError as e:
      if isinstance( e.reason, socket.timeout ):
        raise PackratException( 'Request Timeout after {0} seconds'.format( PACKRAT_TIMEOUT ) )

      raise PackratException( 'URLError "{0}" for "{1}" via "{2}"'.format( e, url, self.proxy ) )

    except socket.timeout:
      raise PackratException( 'Request Timeout after {0} seconds'.format( PACKRAT_TIMEOUT ) )

    except socket.error as e:
      raise PackratException( 'Socket Error "{0}"'.format( e ) )

    if resp.code == 404:
      raise PackratException( 'File "{0}" not Found'.format( url ) )

    if resp.code != 200:
      raise PackratException( 'Invalid Response code "{0}"'.format( resp.code ) )

    return resp.read()

  def _loadManifest( self ):
    self.manifest = {}
    manifest = json.loads( self._request( '_repo_main/MANIFEST_all.json' ).decode() )  # TODO: remove decode when newer version of python
    for package, entry_list in manifest.items():
      self.manifest[ package ] = {}
      for entry in entry_list:
        if entry[ 'type' ] != self.type:
          continue

        self.manifest[ package ][ entry[ 'version' ] ] = entry

  def lookup( self, package, version ):
    version_list = []
    if package not in self.manifest:
      return None

    if version is None:
      version_list = self.manifest[ package ].keys()
      return self.manifest[ package ][ sorted( version_list )[-1] ]

    else:
      try:
        return self.manifest[ package ][ version ]
      except KeyError:
        return None

  def fileURL( self, package, version=None ):
    entry = self.lookup( package, version )
    if entry is None:
      return None

    return '{0}{1}'.format( self.root, entry[ 'path' ] )
