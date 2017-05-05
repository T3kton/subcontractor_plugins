WARNING!!! this is not workable yet, hopfully soon.


Subcontractor Plugins
=====================

These plugins give subcontractor the ability to do things.
Which plugins depend on network access, network permissions, 
and design coderations.  For example, the network that has 
access to the IPMI's of the baremetal servers probably does
not also have access to vCenter.  So a instance in the
vCenter network would have the vcenter plugin and iputils
(for ping/socket tests of the installed vms) and another
instance in the out of band managment network would have
the IPMI and iputils (for ping testing the IPMI interfaces).
This way network segmentation can be maintained.  Each instance
will need HTTP(s) which can be proxied back to contractor.

