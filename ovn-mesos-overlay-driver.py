#!/usr/bin/env python

import argparse
import json
import os

import ovnutil
from ovnutil import ovn_nbctl, ovs_vsctl, call_popen

# OVN network configuration information.
OVN_NB = ""
OVN_BRIDGE = "br-int"
OVN_GATEWAY_LR = "mesos-gw-router"
OVN_DISTRIBUTED_LR = "mesos-router"
OVS_PORT = "ovs-mesos"

# For the CNI plugin configuration file.
CONFIG_FNAME = "ovn-mesos-config.json"
CONFIG = {}
CNI_VERSION = "0.1.0"
CNI_NETWORK = "ovn"
CNI_TYPE = "./ovn-mesos-plugin"

def plugin_init(args):
    """
    Takes care of anything that needs to happen once and isn't handled by 
    gateway-init(). As of now, that only includes creating the distributed
    router to connect node logical switches.
    """
    OVN_NB = ovnutil.get_ovn_nb()
    ovn_nbctl("create Logical_Router name=%s" % OVN_DISTRIBUTED_LR,
              OVN_NB)

def create_cni_config(args):
    """
    Creates and initializes a configuration file for the CNI plugin.
    """
    CONFIG['cniVersion'] = CNI_VERSION
    CONFIG['name'] = CNI_NETWORK
    CONFIG['type'] = CNI_TYPE
    CONFIG['db'] = ovnutil.get_ovn_nb()
    CONFIG['gateway'] = args.gateway.split('/')[0]
    CONFIG['subnet'] = args.subnet
    CONFIG['switch'] = ovs_vsctl("get Open_vSwitch . external_ids:system-id")

    if not os.path.exists(args.config_dir):
        os.makedirs(args.config_dir)
    config_path = os.path.join(args.config_dir, CONFIG_FNAME)
    with open(config_path, 'w') as config_file:
        json.dump(CONFIG, config_file)

def node_init(args):
    """
    Creates a logical switch with the given subnet. Attaches switch to
    distributed router. Creates configuration file for Mesos CNI isolator.
    """
    OVN_NB = ovnutil.get_ovn_nb()

    create_cni_config(args)
    ls = CONFIG['switch']
    subnet = args.subnet
    cluster_subnet = args.cluster_subnet
    gateway = args.gateway
    gw_ip_only = args.gateway.split('/')[0]

    # Add a logical switch for the agent. Connect the logical switch to a
    # distributed router.
    ovn_nbctl("ls-add %s -- set Logical_Switch %s other_config:subnet=%s"
              % (ls, ls, subnet), OVN_NB)
    ovnutil.connect_ls_to_lr(ls, OVN_DISTRIBUTED_LR, ls, gateway,
                             ovnutil.random_mac(), OVN_NB)

    # Add a logical switch port for the agent.
    lsp = "%s_agent" % ls
    ovn_nbctl("lsp-add %s %s -- lsp-set-addresses %s dynamic" % (ls, lsp, lsp),
              OVN_NB)
    mac, ip4 = ovnutil.get_lsp_dynamic_address(lsp, OVN_NB)
    ip4 = ovnutil.append_subnet_mask(ip4, subnet)
    ovs_vsctl("add-port %s %s -- set interface %s type=internal mac=%s "
              "external_ids:iface-id=%s"
              % (OVN_BRIDGE, OVS_PORT, OVS_PORT, mac, lsp))
    command = "ip address add %s dev %s" % (ip4, OVS_PORT)
    call_popen(command.split())
    command = "ip link set dev %s up" % (OVS_PORT)
    call_popen(command.split())

    command = "ip route add %s via %s" % (cluster_subnet, gw_ip_only)
    call_popen(command.split())

def gateway_init(args):
    """
    Setup gateway router.
    """
    OVN_NB = ovnutil.get_ovn_nb()

    ovs_sysid = ovs_vsctl("get Open_vSwitch . external_ids:system-id")
    cluster_subnet = args.cluster_subnet
    eth1_ip = args.eth1_ip

    # Create a logical switch "join" and connect it to the DR.
    ovn_nbctl("ls-add join", OVN_NB)
    ovnutil.connect_ls_to_lr("join", OVN_DISTRIBUTED_LR, "join0",
                             "20.0.0.1/24", ovnutil.random_mac(), OVN_NB)

    # Create a gateway router and connect "join" to it.
    ovn_nbctl("create Logical_Router name=%s options:chassis=%s"
              % (OVN_GATEWAY_LR, ovs_sysid), OVN_NB)
    ovnutil.connect_ls_to_lr("join", OVN_GATEWAY_LR, "join1", "20.0.0.2/24",
                             ovnutil.random_mac(), OVN_NB)

    # Install static routes.
    ovn_nbctl("-- --id=@lrt create Logical_Router_Static_Route "
              "ip_prefix=%s nexthop=20.0.0.1 -- add Logical_Router "
              "%s static_routes @lrt" % (cluster_subnet, OVN_GATEWAY_LR),
              OVN_NB)
    ovn_nbctl("-- --id=@lrt create Logical_Router_Static_Route "
              "ip_prefix=0.0.0.0/0 nexthop=%s -- add Logical_Router "
              "%s static_routes @lrt" % (eth1_ip, OVN_GATEWAY_LR), OVN_NB)
    ovn_nbctl("-- --id=@lrt create Logical_Router_Static_Route "
              "ip_prefix=0.0.0.0/0 nexthop=20.0.0.2 -- add Logical_Router "
              "%s static_routes @lrt" % (OVN_DISTRIBUTED_LR), OVN_NB)

    # Create a logical switch "external" and connect it to GWR using eth1's IP
    # for the logical router port. Add eth1 as a logical switch port to
    # "external" and set its address to "unknown".
    ovn_nbctl("ls-add external", OVN_NB)
    ovnutil.connect_ls_to_lr("external", OVN_GATEWAY_LR, "external", eth1_ip,
                             ovnutil.random_mac(), OVN_NB)
    ovn_nbctl("lsp-add external eth1 -- lsp-set-addresses eth1 unknown",
              OVN_NB)
    command = "ifconfig eth1 0.0.0.0"
    call_popen(command.split())
    ovs_vsctl("add-port %s eth1 -- set interface eth1 "
              "external_ids:iface-id=eth1" % (OVN_BRIDGE))

def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(title='Subcommands',
                                       dest='command_name')

    # Parser for sub-command plugin-init
    parser_plugin_init = subparsers.add_parser('plugin-init',
                                               help="Initialize OVN network")
    parser_plugin_init.set_defaults(db=None, func=plugin_init)

    # Parser for sub-command node-init
    parser_node_init = subparsers.add_parser('node-init',
                                             help="Initialize a node")
    parser_node_init.add_argument('--subnet', help="Node's IPv4 subnet.",
                                  required=True)
    parser_node_init.add_argument("--cluster_subnet", help="Cluster subnet",
                                  required=True)
    parser_node_init.add_argument("--config_dir", required=True,
                                  help="CNI configuration file directory")
    parser_node_init.add_argument('--gateway', required=True,
                                  help="Node's gateway IPv4 address.")
    parser_node_init.set_defaults(func=node_init)

    # Parser for sub-command gateway-init
    parser_gateway_init = subparsers.add_parser('gateway-init',
                                                help="Initialize gateway")
    parser_gateway_init.add_argument("--cluster_subnet", help="Cluster subnet",
                                    required=True)
    parser_gateway_init.add_argument("--eth1_ip", help="eth1's ip address.",
                                     required=True)
    parser_gateway_init.set_defaults(func=gateway_init)

    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()
