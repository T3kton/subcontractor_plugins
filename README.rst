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

see http://t3kton.github.io



virtualbox
----------

start the web service::

  vboxwebsrv -H 127.0.0.1



libvirt
-------

Make sure you install the 

libvirt-clients libvirt-daemon libvirt-daemon-system-systemd libvirt-daemon-system

You will need to create the directory for the vms to live, by
default that is `/var/lib/libvirt/t3kton` (DISK_IMAGE_DIR in 
libvirt/lib.py).  You will also need to create a virtual network
for example, create a .xml file with ::

  <network>
    <name>virtnet</name>
    <forward dev="eth0" mode="route"/>
    <bridge name="virtnet"/>
    <dns enable="no"/>
    <ip address="192.168.100.1" netmask="255.255.255.0"/>
  </network>

and run::

  sudo virsh net-create <file.xml>


then run these to add to contrctor::

  contractorcli network create -n virtnet -o <your site name>

note the network id returned::

  contractorcli addressblock create -n virtnet -p 24 -u 192.168.100.0 -g 1 -s <your site name>

note the subnet id returned::

  contractorcli network link create -a <addressblock id> <network id>


You should be ready to go
