#!/usr/bin/env python
import json
import os
import subprocess
import sys
from subprocess import call

import cni_error

def add_port(lp_name, ls_name, gw):
    call(['ovn-nbctl', DB, 'lsp-add', ls_name, lp_name])
    call(['ovn-nbctl', DB, 'lsp-set-addresses', lp_name, "dynamic"]) 

    cmd = "get Logical-Switch-Port %s dynamic_addresses" % lp_name
    stdout, stderr = ovn_nbctl(cmd, DB)
    cmd = "get Logical-Switch %s other_config:subnet" % ls_name
    subnet, stderr = ovn_nbctl(cmd, DB)

    # Address is of the form: (MAC, IP)
    address = stdout.strip('"\n').split()
    subnet_mask_str = subnet.split('/')[1].strip('"\n')
    address[1] = "%s/%s" % (address[1], subnet_mask_str)

    link_linux_ns_to_mesos_ns(lp_name)
    create_veth_pair(lp_name)

    call(['ovs-vsctl', '--may-exist', 'add-port', 'br-int', "%s_l" % lp_name])
    call(['ovs-vsctl', 'set', 'interface', "%s_l" % lp_name, 'external_ids:iface-id=%s' % lp_name])

    move_veth_pair_into_ns(lp_name)
    set_ns_addresses(lp_name, address[0], address[1], gw)

    return address

def link_linux_ns_to_mesos_ns(ns_name):
    mesos_ns_path = '/var/run/mesos/isolators/network/cni/%s/ns' % os.environ['CNI_CONTAINERID']
    ns_path = '/var/run/netns/%s' % ns_name
    call(['ln', '-s', mesos_ns_path, ns_path])

def create_veth_pair(ns_name):
    call(['ip', 'link', 'add', "%s_l" % ns_name, 'type', 'veth', 'peer', 'name', "%s_c" % ns_name])

def move_veth_pair_into_ns(ns_name):
    call(['ip', 'link', 'set', "%s_l" % ns_name, 'up'])
    call(['ip', 'link', 'set', "%s_c" % ns_name, 'netns', ns_name])
    call(['ip', 'netns', 'exec', ns_name, 'ip', 'link', 'set', 'dev', '%s_c' % ns_name, 'name', 'eth0'])
    call(['ip', 'netns', 'exec', ns_name, 'ip', 'link', 'set', 'eth0', 'up'])
    call(['ip', 'netns', 'exec', ns_name, 'ip', 'link', 'set', 'dev', 'eth0', 'mtu', '1440'])

def set_ns_addresses(ns_name, mac, ip, gw):
    call(['ip', 'netns', 'exec', ns_name, 'ip', 'addr', 'add', ip, 'dev', 'eth0'])
    call(['ip', 'netns', 'exec', ns_name, 'ip', 'link', 'set', 'dev', 'eth0', 'address', mac])
    call(['ip', 'netns', 'exec', ns_name, 'ip', 'route', 'add', 'default', 'via', gw])

def del_port(lp_name):
    ovn_nbctl("lsp-del %s" % lp_name, DB)
    ovs_port_name = "%s_l" % lp_name
    ovs_vsctl("del-port %s" % ovs_port_name)
#    delete_ns(lp_name)

def delete_ns(ns_name):
    cmd = 'ip netns delete %s' % ns_name
    call(cmd.split())

def main():
    config = json.loads(''.join(sys.stdin.readlines()).replace('\n', '').replace('\t', ''))

    if (os.environ['CNI_COMMAND'] == 'ADD'):
        mac, ip4 = add_port(os.environ['CNI_CONTAINERID'], config['bridge'], config['gateway'])

        ip_info = {
            "cniVersion" : "0.1.0",
            "ip4" : {
                "ip" : ip4,
                "gateway" : config['gateway'],
                "routes" : [
                    { "dst" : "0.0.0.0/0"}
                ]
            },
            "ip6" : {
                "ip" : "fd71:c650:3e0e::/48"
            },
            "dns" : {
                "nameservers" : ["127.0.1.1"],
            }
        }
        print json.dumps(ip_info)

    elif (os.environ['CNI_COMMAND'] == 'DEL'):
        del_port(os.environ['CNI_CONTAINERID'])

def ovn_nbctl(cmd_str, db=None):
    cmd = ("ovn-nbctl %s %s" % (db, cmd_str)).split()
    child = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = child.communicate()
    if child.returncode:
        err
        raise RuntimeError(stderr)
    return (stdout, stderr)

def ovs_vsctl(cmd_str):
    cmd = ("ovs-vsctl %s" % cmd_str).split()
    call(cmd)

if __name__ == '__main__':
    DB = "--db=tcp:192.168.162.139:6641"
    main()
