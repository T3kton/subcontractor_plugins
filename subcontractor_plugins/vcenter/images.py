import ssl
import tarfile
import logging
import time
import os
import io
import tempfile
import http
import hashlib
from threading import Timer
from datetime import datetime, timedelta

from urllib import request
from pyVmomi import vim, vmodl

from subcontractor_plugins.common.files import file_reader, file_writer

"""
Initially derived from code from https://github.com/vmware/pyvmomi-community-samples/blob/master/samples/deploy_ova.py and deploy_ovf.py
"""

PROGRESS_INTERVAL = 10  # in seconds
DOWNLOAD_FILE_TIMEOUT = 60  # in seconds


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


class Lease():
  def __init__( self, nfc_lease ):
    super().__init__()
    self.lease = nfc_lease
    self.cont = False

  def start_wait( self ):
    count = 0
    while self.lease.state == vim.HttpNfcLease.State.initializing:
      count += 1
      if count > 60:
        raise Exception( 'Timeout waiting for least to be ready' )

      logging.info( 'Lease: Waiting for lease to be ready...' )
      time.sleep( 4 )

    if self.lease.state == vim.HttpNfcLease.State.error:
      raise Exception( 'Lease error: "{0}"'.format( self.lease.error ) )

    if self.lease.state == vim.HttpNfcLease.State.done:
      raise Exception( 'Lease done before we start?' )

  def complete( self ):
    self.lease.Complete()

  def abort( self, msg ):
    self.lease.Abort( msg )

  @property
  def state( self ):
    return self.lease.state

  @property
  def info( self ):
    return self.lease.info

  def start( self ):
    self.cont = True
    Timer( PROGRESS_INTERVAL, self._timer_cb ).start()

  def stop( self ):
    self.cont = False


class ImportLease( Lease ):
  def __init__( self, nfc_lease, file_handle ):
    super().__init__( nfc_lease )
    self.file_handle = file_handle
    self.file_size = os.stat( file_handle.name ).st_size

  def get_device_url( self, fileItem ):
    for device in self.lease.info.deviceUrl:
      if device.importKey == fileItem.deviceId:
        return device

    raise Exception( 'Failed to find device.url for file {0}'.format( fileItem.path ) )

  def _timer_cb( self ):
    if not self.cont:
      return

    try:
      cur_pos = self.file_handle.tell()
      prog = cur_pos * 100 / self.file_size  # interestingly the progres is the offset position in the file, not how much has been uploaded, so if the vmdks are uploaded out of order, the progress is going to jump arround
      self.lease.Progress( int( prog ) )
      logging.debug( 'Lease: import progress at {0}%'.format( prog ) )
      if self.lease.state == vim.HttpNfcLease.State.ready:
        Timer( PROGRESS_INTERVAL, self._timer_cb ).start()

      else:
        self.cont = False

    except Exception as e:  # don't renew the timer
      logging.warning( 'ImportLease: Exception during _timer_cb: "{0}"'.format( e ) )
      self.cont = False


class ExportLease( Lease ):
  def __init__( self, nfc_lease ):
    super().__init__( nfc_lease )
    self.progress = 0

  def _timer_cb( self ):
    if not self.cont:
      return

    try:
      self.lease.Progress( int( self.progress )  )
      logging.debug( 'ExportLease: export progress at {0}%'.format( self.progress  ) )
      if self.lease.state == vim.HttpNfcLease.State.ready:
        Timer( PROGRESS_INTERVAL, self._timer_cb ).start()

      else:
        self.cont = False

    except Exception as e:  # don't renew the timer
      logging.warning( 'ExportLease: Exception during _timer_cb: "{0}"'.format( e ) )
      self.cont = False


#  TODO: validate the hashes against the .mf file, so far SHA256 and SHA1 hashes are used
class OVAImportHandler():
  """
  OVAImportHandler handles most of the OVA operations.
  It processes the tarfile, matches disk keys to files and
  uploads the disks, while keeping the progress up to date for the lease.
  """
  def __init__( self, ova_file, sslContext ):
    """
    Performs necessary initialization, opening the OVA file,
    processing the files and reading the embedded ovf file.
    """
    self.handle = file_reader( ova_file, None, sslContext )
    self.tarfile = tarfile.open( fileobj=self.handle, mode='r' )
    ovf_filename = list( filter( lambda x: x.endswith( '.ovf' ), self.tarfile.getnames() ) )[0]
    ovf_file = self.tarfile.extractfile( ovf_filename )
    self.descriptor = ovf_file.read().decode()

  def _get_disk( self, fileItem ):
    """
    Does translation for disk key to file name, returning a file handle.
    """
    ovf_filename = list( filter( lambda x: x == fileItem.path, self.tarfile.getnames() ) )[0]
    return self.tarfile.extractfile( ovf_filename )

  def _upload_disk( self, fileItem, lease, host ):
    """
    Upload an individual disk. Passes the file handle of the
    disk directly to the urlopen request.
    """
    logging.info( 'OVAImportHandler: Uploading "{0}"...'.format( fileItem ) )
    file = self._get_disk( fileItem )
    if file is None:
        return

    device = lease.get_device_url( fileItem )
    url = device.url.replace( '*', host )
    headers = { 'Content-length': _get_tarfile_size( file ) }
    if hasattr( ssl, '_create_unverified_context' ):
      sslContext = ssl._create_unverified_context()
    else:
      sslContext = None

    try:
      req = request.Request( url, data=file, headers=headers, method='POST' )
      request.urlopen( req, context=sslContext )

    except Exception as e:
      logging.error( 'OVAImportHandler: Exception Uploading "{0}", lease info: "{1}": "{2}"'.format( e, lease.info, fileItem ) )
      raise e

  def upload( self, host, resource_pool, import_spec_result, datacenter ):
    """
    Uploads all the disks, with a progress keep-alive.

    return uuid of vm
    """
    lease = ImportLease( resource_pool.ImportVApp( spec=import_spec_result.importSpec, folder=datacenter.vmFolder ), self.handle )
    lease.start_wait()
    uuid = lease.info.entity.config.instanceUuid

    try:
      lease.start()
      logging.debug( 'OVAImportHandler: Starting file upload(s)...' )
      for fileItem in import_spec_result.fileItem:
        self._upload_disk( fileItem, lease, host )

      logging.debug( 'OVAImportHandler: File upload(s) complete' )
      lease.complete()

    except Exception as e:
      logging.error( 'OVAImportHandler: Exception uploading files' )
      lease.abort( vmodl.fault.SystemError( reason=str( e ) ) )
      raise e

    finally:
      lease.stop()

    return uuid


class OVAExportHandler():
  def __init__( self, ovf_manager, url, sslContext ):
    super().__init__()
    self.ovf_manager = ovf_manager
    self.url = url
    self.sslContext = sslContext

  def _downloadFiles( self, wrk_dir, lease, host, header_map, proxy ):
    ovf_files = []

    opener = request.OpenerDirector()
    if proxy:  # not doing 'is not None', so empty strings don't try and proxy   # have a proxy option to take it from the envrionment vars
      opener.add_handler( request.ProxyHandler( { 'http': proxy, 'https': proxy } ) )
    else:
      opener.add_handler( request.ProxyHandler( {} ) )
    opener.add_handler( request.HTTPHandler() )
    if hasattr( http.client, 'HTTPSConnection' ):
      opener.add_handler( request.HTTPSHandler() )  # context=self.sslContext

    opener.add_handler( request.UnknownHandler() )

    logging.debug( 'OVAExportHandler: Starting file downloads(s)...' )
    for device in lease.info.deviceUrl:
      url = device.url.replace( '*', host )
      if not device.targetId:
        logging.debug( 'ExportLease: No targetId for "{0}", skipping...'.format( url ) )
        continue

      logging.debug( 'OVAExportHandler: Downloading "{0}"...'.format( device.url ) )
      req = request.Request( url, headers=header_map, method='GET' )
      resp = opener.open( req, timeout=DOWNLOAD_FILE_TIMEOUT )
      try:
        content_length = int( resp.headers[ 'content-length' ] )
      except TypeError:  # ESX dosen't supply contect-length?
        content_length = '<unknwon>'

      file_hash = hashlib.sha256()
      local_file = open( os.path.join( wrk_dir, device.targetId ), 'wb' )
      buff = resp.read( 4096 * 1024 )
      cp = datetime.utcnow()
      while buff:
        if datetime.utcnow() > cp:
          cp = datetime.utcnow() + timedelta( seconds=PROGRESS_INTERVAL )
          logging.debug( 'OVAExportHandler: download at {0} of {1}'.format( local_file.tell(), content_length ) )

        local_file.write( buff )
        file_hash.update( buff )
        buff = resp.read( 4096 * 1024 )

      ovf_file = vim.OvfManager.OvfFile()
      ovf_file.deviceId = device.key
      ovf_file.path = device.targetId
      ovf_file.size = local_file.tell()
      ovf_files.append( ( ovf_file, file_hash.hexdigest() ) )

      local_file.close()

    return ovf_files

  def export( self, host, vm, vm_name ):
    headers = {}
    proxy = None
    ova_file = tempfile.NamedTemporaryFile( mode='w+b', dir='/tmp', prefix='subcontractor_vcenter_' )
    wrk_dir = tempfile.TemporaryDirectory( prefix='subcontractor_vcenter_', dir='/tmp' )
    try:
      nfc_lease = vm.ExportVm()
      lease = ExportLease( nfc_lease )
      lease.start_wait()

      try:
        lease.start()
        ovf_file_list = self._downloadFiles( wrk_dir.name, lease, host, headers, proxy )
        logging.debug( 'OVAExportHandler: File download(s) complete' )
        lease.complete()

      except Exception as e:
        logging.error( 'OVAExportHandler: Exception downloading files' )
        lease.abort( vmodl.fault.SystemError( reason=str( e ) ) )
        raise e

      finally:
        lease.stop()

      logging.debug( 'OVAExportHandler: Generating OVF...' )
      ovf_parameters = vim.OvfManager.CreateDescriptorParams()
      ovf_parameters.name = vm_name
      ovf_parameters.ovfFiles = [ i[0] for i in ovf_file_list ]
      ovf_descriptor = self.ovf_manager.CreateDescriptor( obj=vm, cdp=ovf_parameters )

      if ovf_descriptor.error:
        msg = '"{0}"'.format( '", "'.join( [ i.fault for i in ovf_descriptor.error ] ) )
        logging.error( 'vcenter: error creating ovf descriptor ' + msg )
        raise Exception( 'Error createing ovf descriptor: ' + msg )

      if ovf_descriptor.warning:
        msg = '"{0}"'.format( '", "'.join( [ i.fault for i in ovf_descriptor.warning ] ) )
        logging.warning( 'vcenter: warning creating ovf descriptor ' + msg )

      ova_tarfile = tarfile.open( fileobj=ova_file, mode='w' )
      ovf_file = tarfile.TarInfo( name='{0}.ovf'.format( vm_name ) )
      bytes = ovf_descriptor.ovfDescriptor.encode( 'utf-8' )
      ovf_file.size = len( bytes )
      ova_tarfile.addfile( ovf_file, fileobj=io.BytesIO( bytes ) )
      ovf_hash = hashlib.sha256( bytes ).hexdigest()

      logging.debug( 'OVAExportHandler: Generating mf...' )
      mf = 'SHA256({0}.ovf)={1}\n'.format( vm_name, ovf_hash )
      for item, hash in ovf_file_list:
        mf += 'SHA256({0})={1}\n'.format( item.path, hash )
      mf_file = tarfile.TarInfo( name='{0}.mf'.format( vm_name ) )
      bytes = mf.encode( 'utf-8' )
      mf_file.size = len( bytes )
      ova_tarfile.addfile( mf_file, fileobj=io.BytesIO( bytes ) )

      for item, _ in ovf_file_list:
        logging.debug( 'OVAExportHandler: adding "{0}"...'.format( item.path ) )
        item_file = tarfile.TarInfo( name=item.path )
        item_file.size = item.size
        ova_tarfile.addfile( item_file, fileobj=open( os.path.join( wrk_dir.name, item.path ), 'rb' ) )
      ova_tarfile.close()

    finally:
      wrk_dir.cleanup()

    ova_file.flush()
    ova_file.seek( 0 )
    file_writer( self.url, ova_file, '{0}.ova'.format( vm_name ), None, self.sslContext )
    ova_file.close()

    return 'http://somplace/somepath/{0}.ova'.format( vm_name )


class VMDKHandler():
  def __init__( self, vmdk_file, sslContext ):
    super().__init__()
    self.handle = file_reader( vmdk_file, None, sslContext )

  def upload( self, host, resource_pool, datacenter ):
    raise Exception( 'Not implemented' )
