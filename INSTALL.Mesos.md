How to Use Open vSwitch with Apache Mesos
=========================================

This document describes how to use Open Virtual Networking with Apache Mesos .
This document assumes that you installed Open vSwitch by following [INSTALL.md]
or by using the distribution packages such as .deb or .rpm.  Consult
www.mesos.apache.org for instructions on how to install Mesos.


Setup
=====

* Start the central components.

OVN architecture has a central component which stores your networking intent
in a database.  On one of your machines, with an IP Address of $CENTRAL_IP,
where you have installed and started Open vSwitch, you will need to start some
central components.

Start ovn-northd daemon.  This daemon translates networking intent from Mesos
stored in the OVN_Northbound database to logical flows in OVN_Southbound
database.  It is also responsible for managing and dynamically allocating
IP/MAC addresses for Mesos containers.

```
/usr/share/openvswitch/scripts/ovn-ctl start_northd
```

* One time setup.

On each host, where you plan to spawn your containers, you will need to
run the following command once.  (You need to run it again if your OVS database
gets cleared.  It is harmless to run it again in any case.)

$LOCAL_IP in the below command is the IP address via which other hosts
can reach this host.  This acts as your local tunnel endpoint.

$ENCAP_TYPE is the type of tunnel that you would like to use for overlay
networking.  The options are "geneve" or "stt".  (Please note that your
kernel should have support for your chosen $ENCAP_TYPE.  Both geneve
and stt are part of the Open vSwitch kernel module that is compiled from this
repo.  If you use the Open vSwitch kernel module from upstream Linux,
you will need a minumum kernel version of 3.18 for geneve.  There is no stt
support in upstream Linux.  You can verify whether you have the support in your
kernel by doing a "lsmod | grep $ENCAP_TYPE".)

```
ovs-vsctl set Open_vSwitch . external_ids:ovn-remote="tcp:$CENTRAL_IP:6641" \
  external_ids:ovn-nb="tcp:$CENTRAL_IP:6641" external_ids:ovn-encap-ip=$LOCAL_IP external_ids:ovn-encap-type="$ENCAP_TYPE"
```

And finally, start the ovn-controller.  (You need to run the below command
on every boot)

```
/usr/share/openvswitch/scripts/ovn-ctl start_controller
```

* Initialize the OVN network using the OVN network driver.

Run the OVN network driver with the "plugin-init" subcommand once on any host.
Running "ovn-nbctl show" should now display a single logical router called
"mesos-router."

```
PYTHONPATH=$OVS_PYTHON_LIBS_PATH ovn-mesos-overlay-driver plugin-init
```

* Add each of the hosts to the OVN network.

On each host where you will have a Mesos agent/master running, run the
OVN network driver with the "node-init" subcommand. $SUBNET is the subnet
(e.g. 172.16.1.0/24) of your host, $CLUSTER_SUBNET is the subnet of your entire
Mesos cluster (e.g. 172.16.0.0/16), gateway will be the IPv4 address of your
host's router port (e.g. 172.16.1.1/24), and $PATH_TO_CNI_CONFIG_DIR is the
absolute path to the directory where you would like the CNI configuration file
to be created.

```
PYTHONPATH=$OVS_PYTHON_LIBS_PATH ovn-mesos-overlay-driver node-init \
--subnet=$SUBNET --cluster_subnet=$CLUSTER_SUBNET --gateway=$GATEWAY_IP \
--config_dir=$PATH_TO_CNI_CONFIG_DIR
```

The driver will take the necessary steps to connect a host to mesos-router,
allowing for basic-east west traffic.  At this point, running an
"ovn-nbctl show", should now also display a logical switch with the name
"${OVS_SYSTEM_ID}_agent" and a logical port called "ovn-mesos" for each host
that the "node-init" subcommand was run on.

* Configure a gateway host for South-North traffic.

WARNING: The following command will cause you to lose connectivity through
eth1 on the host which it is executed on.  Do not execute this command if
you require connectivity through eth1 for other purposes (e.g. SSH connection
to your host).

If you want to configure a gateway to allow South-North traffic for your
containers, run the OVN network driver with the "gateway-init" subcommand on
your gateway host.  You will need to provide the cluster subnet, the IPv4
address of your eth1 device (with subnet mask), and the IPv4 address of your
eth1's gateway (with subnet mask) as command line arguments.  North-South
traffic is not currently supported.  See "Note on North-Sourth traffic" to
learn why.

```
PYTHONPATH=$OVS_PYTHON_LIBS_PATH ovn-mesos-overlay-driver gateway-init \
--cluster_subnet=$CLUSTER_SUBNET --eth1_ip=$ETH1_IP --eth1_gw_ip=$ETH1_GW_IP
```

* Create a CNI plugin directory on agent nodes.

On each node where you plan to run a Mesos agent, create a directory for the
CNI plugin and copy the plugin executable along with the ovnutil file into the
new directory.

```
mkdir -p $PATH_TO_CNI_PLUGIN_DIR
cp $PATH_TO_OVS_DIR/ovn/utilities/ovn-mesos-plugin $PATH_TO_CNI_PLUGIN_DIR/ovn-mesos-plugin
cp $OVS_PYTHON_LIBS_PATH/ovn/mesos/ovnutil.py $PATH_TO_CNI_PLUGIN_DIR/ovnutil.py
```

Running Mesos
=============

To run Mesos, you will need know the IP addresses of your master and agent
nodes.  $MASTER_IP and $AGENT_IP are dynamically allocated, so you can find
them with the following commands, respectively:

```
ovn-nbctl list Logical-Switch-Port master
ovn-nbctl list Logical-Switch-Port ${OVS_SYSTEM_ID}_agent
```

The addresses will be under the "dynamic_addresses" column.

The following commands require you to be in the Mesos "build" directory, i.e.
$MESOS_ROOT_DIRECTORY/build.

* Start a Mesos master.

```
./src/mesos-master --ip=$MASTER_IP --work_dir=/var/lib/mesos/master
```

* Start a Mesos agent.

```
./src/mesos-agent --ip=$AGENT_IP --master=$MASTER_IP:5050 \
--work_dir=/var/lib/mesos/agent --isolation=filesystem/linux,docker/runtime \
--image_providers=docker --network_cni_config_dir=$PATH_TO_CNI_CONFIG_DIR \
--network_cni_plugins_dir=$PATH_TO_CNI_PLUGIN_DIR --launcher_dir=`pwd` \
--executor_registration_timeout=5mins
```

Note on North-South traffic
===========================

As of now, Mesos does not support port-mapping.  As a result, we cannot direct
North-South traffic to the correct container.  In the future, one could imagine
Mesos providing some sort of API to allow access to container-host port
mappings.  These port mappings could be used to create load balancing rules to
direct North-South traffic to the appopriate containers.

Note on $OVS_PYTHON_LIBS_PATH
=============================

$OVS_PYTHON_LIBS_PATH should point to the directory where Open vSwitch
python modules are installed.  If you installed Open vSwitch python
modules via the debian package of 'python-openvswitch' or via pip by
running 'pip install ovs', you do not need to specify the path.
If you installed it by following the instructions in INSTALL.md, you
should specify the path.  The path in that case depends on the options passed
to ./configure.  (It is usually either '/usr/share/openvswitch/python' or
'/usr/local/share/openvswitch/python'.)

[INSTALL.md]: INSTALL.md
[openvswitch-switch.README.Debian]: debian/openvswitch-switch.README.Debian
[README.RHEL]: rhel/README.RHEL
