native_virtualbox = False
try:
  import virtualbox
  vbox = virtualbox.VirtualBox()
  native_virtualbox = True
except:
  pass

MODULE_NAME = 'virtualbox'

if native_virtualbox:
  from subcontractor_plugins.virtualbox.lib import create, create_rollback, destroy, set_power, power_state

  MODULE_FUNCTIONS = {
                       'create': create,
                       'create_rollback': create_rollback,
                       'destroy': destroy,
                       'set_power': set_power,
                       'power_state': power_state
                     }

else:
  import subprocess
  import os
  import pickle
  import logging

  MAGIC_LOCATOR = b'\x01DATA\x02'

  def python_wrap( function_name, paramaters ):
    request = { 'function': function_name, 'paramaters': paramaters }
    proc = subprocess.run( [ os.path.join( os.path.dirname( __file__ ), 'systemPythonWrapper' ) ], shell=False, input=pickle.dumps( request, protocol=0 ), stdout=subprocess.PIPE )
    if proc.returncode != 0:
      raise Exception( 'Error calling systemPythonWrapper, rc: {0}, stdout: "{1}"'.format( proc.returncode, proc.stdout ) )

    result = proc.stdout
    try:
      pos = result.index( MAGIC_LOCATOR )
    except ValueError:
      raise ValueError( 'MAGIC_LOCATOR not found in output' )

    logging.debug( 'virtualbox subproc: output:\n{0}'.format( result[ :pos ] ) )
    try:
      result = pickle.loads( result[ pos + len( MAGIC_LOCATOR ): ] )
    except Exception as e:
      raise Exception( 'Exception unpickleing result "{0}"({1})'.format( e, type( e ).__name__ ) )

    if isinstance( result, Exception ):
      raise result

    logging.debug( 'virtualbox subproc: result: "{0}"'.format( result ) )

    return result

  MODULE_FUNCTIONS = {
                     'create': lambda paramaters: python_wrap( 'create', paramaters ),
                     'create_rollback': lambda paramaters: python_wrap( 'create_rollback', paramaters ),
                     'destroy': lambda paramaters: python_wrap( 'destroy', paramaters ),
                     'set_power': lambda paramaters: python_wrap( 'set_power', paramaters ),
                     'power_state': lambda paramaters: python_wrap( 'power_state', paramaters )
                   }
