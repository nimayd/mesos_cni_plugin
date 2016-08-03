#!/usr/bin/env python

import argparse
import json
import os
import random
import re

import ovnutil
from ovnutil import ovn_nbctl, ovs_vsctl

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
    needs to happend once. As of now, that only includes created the
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
    Parses a port range string of the form "<int>-<int>". Raises an exception
    if the string is not in the correct format.

    Returns a tuple of the range values.
    """
    # TODO implement this.
#    result = port_range.split('-')
#    regex = '[0-9]+-[0-9]+'
#    return (min(), max())

def node_init(args):
    """
    Creates a logical switch with the given subnet. Attaches switch to
    distributed router. Creates configuration file for Mesos CNI isolator.
    """
    OVN_REMOTE = ovnutil.get_ovn_remote()

    port_range = parse_port_range(args.port_range)
    create_cni_config(args)
    ls = CONFIG['switch']
    subnet = args.subnet

    # Add a logical switch for the agent. Connec the logical switch to a
    # distributed router.
    ovn_nbctl("ls-add %s -- set Logical_Switch %s other_config:subnet=%s"
              % (ls, ls, subnet), OVN_REMOTE)
    rp_ip4 = get_rp_ip4(subnet)
    ovnutil.connect_ls_to_lr(ls, OVN_DISTRIBUTED_LR, rp_ip4,
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
    ovnutil.call_popen(command.split())
    command = "ip link set dev %s up" % (ovs_lsp)
    ovnutil.call_popen(command.split())

    # TODO: Add routes to allow traffic from node.

def gateway_init(args):
    """
    Allow containers that are connected to the OVN network to access the
    outside world. Add new information (like port range) to configuration file.
    """
    OVN_REMOTE = get_ovn_remote()

    ovn_nbctl("ls-add join", OVN_REMOTE)
    ovnutil.connect_ls_to_lr("join", OVN_DISTRIBUTED_LR, "169.0.0.1/24",
                             random_mac(), OVN_REMOTE)
    ovn_nbctl("create Logical_Router name=%s" % OVN_GATEWAY_LR, OVN_REMOTE)
    ovnutil.connect_ls_to_lr("join", OVN_GATEWAY_LR, "169.0.0.2/24",
                             random_mac(), OVN_REMOTE)
    ovn_nbctl("ls-add external", OVN_REMOTE)
    ovnutil.connect_ls_to_lr("external", OVN_GATEWAY_LR, args.eth1_ip,
                             random_mac(), OVN_REMOTE)
    # TODO: Add load balancing rules using port range. Add info to ovsdb.

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
    parser_gateway_init.add_argument("--eth1_ip", help="eth1's ip address.",
                                     required=True)
    parser_gateway_init.set_defaults(func=gateway_init)

#    Include a flag to pass in DB
    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()
