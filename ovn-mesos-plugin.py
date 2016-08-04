#!/usr/bin/env python
import json
import os
import subprocess
import sys
from subprocess import call

import ovnutil
from ovnutil import ovn_nbctl, ovs_vsctl, call_popen

OVN_REMOTE = ""
OVN_BRIDGE = "br-int"

def add_port(lsp, ls, gw):
    OVN_REMOTE = ovnutil.get_ovn_remote()
    ovn_nbctl("lsp-add %s %s" % (ls, lsp), OVN_REMOTE)
    ovn_nbctl("lsp-set-addresses %s dynamic" % (lsp), OVN_REMOTE)

    # Address is of the form: (MAC, IP)
    address = ovnutil.get_lsp_dynamic_address(lsp, OVN_REMOTE)
    subnet = ovn_nbctl("get Logical-Switch %s other_config:subnet" % ls,
                       OVN_REMOTE)
    ovnutil.append_subnet_mask(address[1], subnet)

    link_linux_ns_to_mesos_ns(lsp)
    create_veth_pair(lsp)

    ovs_vsctl("--may-exist add-port %s %s_l" % (OVN_BRIDGE, lsp))
    ovs_vsctl("set interface %s_l external_ids:iface-id=%s" % (lsp, lsp))

    move_veth_pair_into_ns(lsp)
    set_ns_addresses(lsp, address[0], address[1], gw)

    return address

def link_linux_ns_to_mesos_ns(ns_name):
    mesos_ns_path = '/var/run/mesos/isolators/network/cni/%s/ns'
                    % os.environ['CNI_CONTAINERID']
    ns_path = '/var/run/netns/%s' % ns_name
    call_popen(['ln', '-s', mesos_ns_path, ns_path])

def create_veth_pair(ns_name):
    command = "ip link add %s_l type veth peer name %s_c" % (ns_name, ns_name)
    call(command.split())

def move_veth_pair_into_ns(ns_name):
    call_popen(['ip', 'link', 'set', "%s_l" % ns_name, 'up'])
    call_popen(['ip', 'link', 'set', "%s_c" % ns_name, 'netns', ns_name])
    ip_netns_exec(ns_name, "ip link set dev %s_c name eth0" % (ns_name))
    ip_netns_exec(ns_name, "ip link set eth0 up")
    ip_netns_exec(ns_name, "ip link set dev eth0 mtu 1440")

def set_ns_addresses(ns_name, mac, ip, gw):
    ip_netns_exec(ns_name, "ip addr add %s dev eth0" % (ip))
    ip_netns_exec(ns_name, "ip addr add %s ip link set dev eth0 address %s"
                  % (ip, mac))
    ip_netns_exec(ns_name, "ip route add default via %s" % gw)

def del_port(lsp):
    ovn_nbctl("lsp-del %s" % lsp, DB)
    ovs_port = "%s_l" % lsp
    ovs_vsctl("del-port %s" % ovs_port)
#    delete_ns(lsp_name)

def delete_ns(ns_name):
    cmd = 'ip netns delete %s' % ns_name
    call(cmd.split())

def ip_netns_exec(ns_name, cmd):
    arg_list = ['ip', 'netns', 'exec', ns_name] + cmd.split()
    call_popen(arg_list)

def main():
    raw_config = ''.join(sys.stdin.readlines())
    config = json.loads(raw_config.replace('\n', '').replace('\t', ''))

    if (os.environ['CNI_COMMAND'] == 'ADD'):
        mac, ip4 = add_port(os.environ['CNI_CONTAINERID'], config['switch'],
                            config['gateway'])

        ip_info = {
            "cniVersion" : "0.1.0",
            "ip4" : {
                "ip" : ip4,
                "gateway" : config['gateway'],
                "routes" : [
                    { "dst" : "0.0.0.0/0" }
                ]
            },
            "ip6" : {
                "ip" : ""
            },
            "dns" : {
                "nameservers" : ["127.0.1.1"],
            }
        }
        print json.dumps(ip_info)

    elif (os.environ['CNI_COMMAND'] == 'DEL'):
        del_port(os.environ['CNI_CONTAINERID'])

if __name__ == '__main__':
    main()
