#!/usr/bin/env python
"""
Derived from code from https://github.com/vmware/pyvmomi-community-samples/blob/master/samples/deploy_ova.py and deploy_ovf.py
"""
import os
import ssl
import tarfile
import logging
import time
import socket
from datetime import datetime, timedelta
from threading import Timer

from urllib import request
from pyVmomi import vim, vmodl
from tempfile import NamedTemporaryFile

from subcontractor_plugins.common.Packrat import HTTPErrorProcessorPassthrough, packrat_from_url

PROGRESS_INTERVAL = 10  # in seconds
WEB_HANDLE_TIMEOUT = 60  # in seconds


def _get_tarfile_size( tarfile ):
  """
  Determine the size of a file inside the tarball.
  If the object has a size attribute, use that. Otherwise seek to the end
  and report that.
  """
  try:
    return tarfile.size
  except AttributeError:
    pass

  size = tarfile.seek( 0, 2 )
  tarfile.seek( 0, 0 )
  return size


def _create_file_handle( url ):
  if url.startswith( ( 'packrat://', 'packrats://' ) ):
    return PackratHandle( url )

  elif url.startswith( ( 'http://', 'https://' ) ):
    return WebHandle( url )

  elif url.startswith( 'file://' ):
    return FileHandle( url[ 7: ] )

  else:
    raise ValueError( 'Unknown scheme' )


class Lease:
  def __init__( self, nfc_lease, handler ):
    self.lease = nfc_lease
    self.handler = handler
    self.cont = False

  def start_wait( self ):
    count = 0
    while self.lease.state == vim.HttpNfcLease.State.initializing:
      count += 1
      if count > 60:
        raise Exception( 'Timeout waiting for least to be ready' )

      logging.info( 'Waiting for lease to be ready...' )
      time.sleep( 2 )

    if self.lease.state == vim.HttpNfcLease.State.error:
      raise Exception( 'Lease error: "{0}"'.format( self.lease.error ) )

    if self.lease.state == vim.HttpNfcLease.State.done:
      raise Exception( 'Lease done before we start?' )

  def get_device_url( self, fileItem ):
    for deviceUrl in self.lease.info.deviceUrl:
      if deviceUrl.importKey == fileItem.deviceId:
        return deviceUrl

    raise Exception( 'Failed to find deviceUrl for file {0}'.format( fileItem.path ) )

  def complete( self ):
    self.lease.Complete()

  def abort( self, msg ):
    self.lease.Abort( msg )

  @property
  def info( self ):
    return self.lease.info

  def start( self ):
    self.cont = True
    Timer( PROGRESS_INTERVAL, self._timer_cb ).start()

  def stop( self ):
    self.cont = False

  def _timer_cb( self ):
    if not self.cont:
      return

    try:
      prog = self.handler.progress
      self.lease.Progress( prog )
      if self.lease.state == vim.HttpNfcLease.State.ready:
        Timer( PROGRESS_INTERVAL, self._timer_cb ).start()

      else:
        self.cont = False

    except Exception as e:  # don't renew the timer
      logging.warning( 'Lease: Exception during _timer_cb: "{0}"'.format( e ) )
      self.cont = False


#  TODO: validate the hashes against the .mf file, so far SHA256 and SHA1 hashes are used
class OVAHandler:
  """
  OVAHandler handles most of the OVA operations.
  It processes the tarfile, matches disk keys to files and
  uploads the disks, while keeping the progress up to date for the lease.
  """
  def __init__( self, ova_file ):
    """
    Performs necessary initialization, opening the OVA file,
    processing the files and reading the embedded ovf file.
    """
    self.handle = _create_file_handle( ova_file )
    self.tarfile = tarfile.open( fileobj=self.handle, mode='r' )
    ovf_filename = list( filter( lambda x: x.endswith( '.ovf' ), self.tarfile.getnames() ) )[0]
    ovf_file = self.tarfile.extractfile( ovf_filename )
    self.descriptor = ovf_file.read().decode()

  def get_disk( self, fileItem ):
    """
    Does translation for disk key to file name, returning a file handle.
    """
    ovf_filename = list( filter( lambda x: x == fileItem.path, self.tarfile.getnames() ) )[0]
    return self.tarfile.extractfile( ovf_filename )

  def upload( self, host, resource_pool, import_spec_result, datacenter ):
    """
    Uploads all the disks, with a progress keep-alive.

    return uuid of vm
    """
    lease = Lease( resource_pool.ImportVApp( spec=import_spec_result.importSpec, folder=datacenter.vmFolder ), self.handle )
    lease.start_wait()

    try:
      lease.start()
      logging.debug( 'OVAHandler: Starting file upload(s)...' )
      for fileItem in import_spec_result.fileItem:
        self.upload_disk( fileItem, lease, host )

      logging.debug( 'OVAHandler: File upload(s) complete' )
      lease.complete()

    except Exception as e:
      logging.error( 'OVAHandler: Exception uploading files' )
      lease.abort( vmodl.fault.SystemError( reason=str( e ) ) )
      raise e

    finally:
      lease.stop()

    return lease.info.entity.config.instanceUuid

  def upload_disk( self, fileItem, lease, host ):
    """
    Upload an individual disk. Passes the file handle of the
    disk directly to the urlopen request.
    """
    logging.info( 'OVAHandler: Uploading "{0}"...'.format( fileItem ) )
    file = self.get_disk( fileItem )
    if file is None:
        return

    deviceUrl = lease.get_device_url( fileItem )
    url = deviceUrl.url.replace( '*', host )
    headers = { 'Content-length': _get_tarfile_size( file ) }
    if hasattr( ssl, '_create_unverified_context' ):
      sslContext = ssl._create_unverified_context()
    else:
      sslContext = None

    try:
      req = request.Request( url, file, headers )
      request.urlopen( req, context=sslContext )

    except Exception as e:
      logging.error( 'OVAHandler: Exception Uploading "{0}", lease info: "{1}": "{2}"'.format( e, lease.info, fileItem ) )
      raise e


class VMDKHandler:
  def __init__( self, vmdk_file ):
    self.handle = _create_file_handle( vmdk_file )

  def upload( self, host, resource_pool, datacenter ):
    raise Exception( 'Not implemented' )

    # headers = { 'Content-length': self.handle.st_size }
    # if hasattr( ssl, '_create_unverified_context' ):
    #   sslContext = ssl._create_unverified_context()
    # else:
    #   sslContext = None
    #
    # try:
    #   req = request.Request( url, self.handle, headers )
    #   request.urlopen( req, context=sslContext )
    #
    # except Exception as e:
    #   logging.error( 'OVAHandler: Exception Uploading "{0}"'.format( e ) )
    #   raise e


class FileHandle:
  def __init__( self, filename ):
    logging.debug( 'FileHandle: filename: "{0}"'.format( filename ) )
    self.filename = filename
    self.fh = open( filename, 'rb')

    self.st_size = os.stat( filename ).st_size
    self.offset = 0

  def __del__( self ):
    try:
      self.fh.close()
    except AttributeError:
      pass

  def tell( self ):
    return self.fh.tell()

  def seek( self, offset, whence=0 ):
    if whence == 0:
      self.offset = offset
    elif whence == 1:
      self.offset += offset
    elif whence == 2:
      self.offset = self.st_size - offset

    return self.fh.seek( offset, whence )

  def seekable( self ):
    return True

  def read( self, amount ):
    self.offset += amount
    result = self.fh.read( amount )
    return result

  # A slightly more accurate percentage
  @property
  def progress( self ):
    return int( 100.0 * self.offset / self.st_size )


class WebSourceException( Exception ):
  pass


class WebHandle( FileHandle ):
  def __init__( self, url ):
    logging.debug( 'WebHandle: url: "{0}"'.format( url ) )
    proxy = None
    self.url = url

    if proxy:  # not doing 'is not None', so empty strings don't try and proxy   # have a proxy option to take it from the envrionment vars
      self.opener = request.build_opener( HTTPErrorProcessorPassthrough, request.ProxyHandler( { 'http': proxy, 'https': proxy } ) )
    else:
      self.opener = request.build_opener( HTTPErrorProcessorPassthrough, request.ProxyHandler( {} ) )

    logging.info( 'WebHandle: Downloading "{0}"'.format( url ))

    try:
      resp = self.opener.open( self.url, timeout=WEB_HANDLE_TIMEOUT )
    except request.HTTPError as e:
      raise WebSourceException( 'HTTPError "{0}"'.format( e ) )

    except request.URLError as e:
      if isinstance( e.reason, socket.timeout ):
        raise WebSourceException( 'Request Timeout after {0} seconds'.format( WEB_HANDLE_TIMEOUT ) )

      raise WebSourceException( 'URLError "{0}" for "{1}" via "{2}"'.format( e, self.url, proxy ) )

    except socket.timeout:
      raise WebSourceException( 'Request Timeout after {0} seconds'.format( WEB_HANDLE_TIMEOUT ) )

    except socket.error as e:
      raise WebSourceException( 'Socket Error "{0}"'.format( e ) )

    if resp.code == 404:
      raise WebSourceException( 'OVA file "{0}" not Found'.format( self.url ) )

    if resp.code != 200:
      raise WebSourceException( 'Invalid Response code "{0}"'.format( resp.code ) )

    self.cache_file = NamedTemporaryFile( mode='wb', prefix='subcontractor_vmware_' )
    size = int( resp.headers[ 'content-length' ] )

    buff = resp.read( 4096 * 1024 )
    cp = datetime.utcnow()
    while buff:
      if datetime.utcnow() > cp:
        cp = datetime.utcnow() + timedelta( seconds=PROGRESS_INTERVAL )
        logging.debug( 'WebHandle: at {0} of {1}'.format( self.cache_file.tell(), size ) )

      self.cache_file.write( buff )
      buff = resp.read( 4096 * 1024 )

    self.cache_file.flush()

    super().__init__( self.cache_file.name )

  def __del__( self ):
    super().__del__()
    try:
      self.cache_file.close()
    except AttributeError:
      pass


class PackratHandle( WebHandle ):
  def __init__( self, url ):
    proxy = None
    logging.debug( 'PackratHandle: url: "{0}"'.format( url ) )
    packrat, file = packrat_from_url( url, 'rsc', proxy )  # TODO: chage to 'ova'
    url = packrat.fileURL( file )
    if url is None:
      raise ValueError( 'Unable to get file url' )
    super().__init__( url )
