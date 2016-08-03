#!/usr/bin/env python

import argparse
import json
import os
import random
import re

import ovnutil
from ovnutil import ovn_nbctl, ovs_vsctl, call_popen

# OVN network configuration information.
OVN_REMOTE = ""
OVN_BRIDGE = "br-int"
OVN_GATEWAY_LR = "mesos-gw-router"
OVN_DISTRIBUTED_LR = "mesos-router"

# For the CNI plugin configuration file.
CONFIG_FNAME = "ovn-mesos-config.json"
CONFIG = {}
CNI_VERSION = "0.1.0"
CNI_NETWORK = "ovn"
CNI_TYPE = "./plugin.py"
IPV6_DUMMY = "::1/0"

def plugin_init(args):
    """
    Takes care of everything that isn't handled by gateway-init() and only
    needs to happend once. As of now, that only includes creating the
    distributed router to connect node logical switches.
    """
    OVN_REMOTE = ovnutil.get_ovn_remote()
    ovn_nbctl("create Logical_Router name=%s" % OVN_DISTRIBUTED_LR,
              OVN_REMOTE)

def create_cni_config(args):
    """
    Creates and initializes a configuration file for the CNI plugin.
    """
    CONFIG['cniVersion'] = CNI_VERSION
    CONFIG['name'] = CNI_NETWORK
    CONFIG['type'] = CNI_TYPE
    CONFIG['db'] = OVN_REMOTE
    CONFIG['subnet'] = args.subnet
    CONFIG['ipv6'] = args.ipv6 if args.ipv6 else IPV6_DUMMY
    CONFIG['port_range'] = args.port_range
    CONFIG['switch'] = ovs_vsctl("get Open_vSwitch . external_ids:system-id")
    with open(CONFIG_FNAME, 'w') as config_file:
        json.dump(CONFIG, config_file)

def random_mac():
    """
    Generates a random MAC address. Used when dynamic addressing is not
    possible (logical router ports for example).
    """
    return '"02:%02x:%02x:%02x:%02x:%02x"' % (random.randint(0,255),
                                              random.randint(0,255),
                                              random.randint(0,255),
                                              random.randint(0,255),
                                              random.randint(0,255))

def get_rp_ip4(subnet):
    """
    Returns the IPv4 address in the given subnet with a host number of one,
    i.e. if subnet="192.168.162.0/24" the returned address will be
    "192.168.162.1/24"
    """
    # TODO Implement this.
    return subnet

def parse_port_range(port_range):
    """
    Parses a port range string of the form "%d-%d". Raises an exception
    if the string is not in the correct format.
    """
    result = port_range.split('-')
    err_str = "Invalid port range format: %s" % (port_range)
    if (len(result) != 2):
        raise Exception(err_str)
    try:
        x, y = int(result[0]), int(result[1])
    except ValueError:
        print(err_str)
        raise
    if x < 0 or y < 0:
        raise Exception(err_str)

def node_init(args):
    """
    Creates a logical switch with the given subnet. Attaches switch to
    distributed router. Creates configuration file for Mesos CNI isolator.
    """
    OVN_REMOTE = ovnutil.get_ovn_remote()

    port_range = args.port_range
    parse_port_range(port_range)
    ovs_vsctl("set Open_vSwitch . external_ids:port_range=%s" % (port_range))
    create_cni_config(args)
    ls = CONFIG['switch']
    subnet = args.subnet

    # Add a logical switch for the agent. Connect the logical switch to a
    # distributed router.
    ovn_nbctl("ls-add %s -- set Logical_Switch %s other_config:subnet=%s"
              % (ls, ls, subnet), OVN_REMOTE)
    rp_ip4 = get_rp_ip4(subnet)
    ovnutil.connect_ls_to_lr(ls, OVN_DISTRIBUTED_LR, ls, rp_ip4,
                             random_mac(), OVN_REMOTE)

    # Add a logical switch port for the agent.
    lsp = "%s_agent" % ls
    ovn_nbctl("lsp-add %s %s -- lsp-set-addresses %s dynamic" % (ls, lsp, lsp),
              OVN_REMOTE)
    mac, ip4 = ovnutil.get_lsp_dynamic_address(lsp, OVN_REMOTE)
    ip4 = ovnutil.append_subnet_mask(ip4, subnet)
    # TODO find a better way of naming ports than truncating for ifconfig.
    ovs_lsp = lsp[0:8]
    ovs_vsctl("add-port %s %s -- set interface %s type=internal mac=%s "
              "external_ids:iface-id=%s"
              % (OVN_BRIDGE, ovs_lsp, ovs_lsp, mac, lsp))
    command = "ip address add %s dev %s" % (ip4, ovs_lsp)
    call_popen(command.split())
    command = "ip link set dev %s up" % (ovs_lsp)
    call_popen(command.split())

    # TODO Remove default route added with lport creation.
    # TODO: Add routes to allow traffic from node.

def gateway_init(args):
    """
    Allow containers that are connected to the OVN network to access the
    outside world.
    """
    OVN_REMOTE = ovnutil.get_ovn_remote()

    cluster_subnet = args.cluster_subnet
    eth1_ip = args.eth1_ip

    # Create a logical switch "join" and connect it to the DR.
    ovn_nbctl("ls-add join", OVN_REMOTE)
    ovnutil.connect_ls_to_lr("join", OVN_DISTRIBUTED_LR, "join0", "169.0.0.1/24",
                             random_mac(), OVN_REMOTE)

    # Create a gateway router and connect "join" to it.
    ovn_nbctl("create Logical_Router name=%s" % OVN_GATEWAY_LR, OVN_REMOTE)
    ovnutil.connect_ls_to_lr("join", OVN_GATEWAY_LR, "join1", "169.0.0.2/24",
                             random_mac(), OVN_REMOTE)

    # Install static routes.
    ovn_nbctl("-- --id=@lrt create Logical_Router_Static_Route "
              "ip_prefix=%s nexthop=169.0.0.1 -- add Logical_Router "
              "%s static_routes @lrt" % (cluster_subnet, OVN_GATEWAY_LR),
              OVN_REMOTE)
    ovn_nbctl("-- --id=@lrt create Logical_Router_Static_Route "
              "ip_prefix=0.0.0.0/0 nexthop=%s -- add Logical_Router "
              "%s static_routes @lrt" % (eth1_ip, OVN_GATEWAY_LR), OVN_REMOTE)
    ovn_nbctl("-- --id=@lrt create Logical_Router_Static_Route "
              "ip_prefix=0.0.0.0/0 nexthop=169.0.0.2 -- add Logical_Router "
              "%s static_routes @lrt" % (OVN_DISTRIBUTED_LR), OVN_REMOTE)

    # Create a logical switch "external" and connect it to GWR using eth1's IP
    # for the logical router port. Add eth1 as a logical switch port to
    # "external" and set its address to "unknown".
    ovn_nbctl("ls-add external", OVN_REMOTE)
    ovnutil.connect_ls_to_lr("external", OVN_GATEWAY_LR, "external", eth1_ip,
                             random_mac(), OVN_REMOTE)
    ovn_nbctl("lsp-add external eth1 -- lsp-set-addresses eth1 unknown",
              OVN_REMOTE)
    command = "ifconfig eth1 0.0.0.0"
    call_popen(command.split())
    ovs_vsctl("add-port %s eth1 -- set interface eth1 "
              "external_ids:iface-id=eth1" % (OVN_BRIDGE))

    # Create a load balancer for "external".
    ovn_nbctl("-- --id=@lb create Load_Balancer -- set Logical_Switch "
              "external load_balancer @lb", OVN_REMOTE)

def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(title='Subcommands',
                                       dest='command_name')

    # Parser for sub-command init
    parser_plugin_init = subparsers.add_parser('plugin-init',
                                               help="Initialize OVN network")
    parser_plugin_init.set_defaults(db=None, func=plugin_init)

    # Parser for sub-command node-init
    parser_node_init = subparsers.add_parser('node-init',
                                             help="Initialize a node")
    parser_node_init.add_argument('--subnet', help="Node's IPv4 subnet.",
                                  required=True)
    parser_node_init.add_argument('--ipv6', help="Node's IPv6 address.")
    parser_node_init.add_argument('--port_range', required=True,
                                  help="Port range for port mapping.")
    parser_node_init.set_defaults(func=node_init)

    # Parser for sub-command init
    parser_gateway_init = subparsers.add_parser('gateway-init',
                                                help="Initialize gateway")
    parser_gateway_init.add_argument("--cluster_subnet", help="Cluster subnet",
                                    required=True)
    parser_gateway_init.add_argument("--eth1_ip", help="eth1's ip address.",
                                     required=True)
    parser_gateway_init.set_defaults(func=gateway_init)

#    Include a flag to pass in DB
    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()
