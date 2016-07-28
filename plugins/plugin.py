#!/usr/bin/env python
import json
import os
import sys
import subprocess
from subprocess import call

def add_port(lp_name, ls_name):
    call(['ovn-nbctl', DB, 'lsp-add', ls_name, lp_name])
    call(['ovn-nbctl', DB, 'lsp-set-addresses', lp_name, "dynamic"]) 

    cmd = "get Logical-Switch-Port %s dynamic_addresses" % lp_name
    stdout, stderr = ovn_nbctl(cmd, DB)

    # Address is of the form: (MAC, IP)
    address = stdout.strip('""\n').split()

    return address

#    link_linux_ns_to_mesos_ns(lp_name)
#    create_veth_pair(lp_name)

#    call(['ovs-vsctl', '--may-exist', 'add-port', 'br-int', "%s_l" % lp_name])
#    call(['ovs-vsctl', 'set', 'interface', "%s_l" % lp_name, 'external_ids:iface-id=%s' % lp_name])

#    move_veth_pair_into_ns(lp_name)
#    set_ns_addresses(lp_name)

#     return (mac, ip4)

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

def set_ns_addresses(ns_name):
    call(['ip', 'netns', 'exec', ns_name, 'ip', 'addr', 'add', IP, 'dev', 'eth0'])
    call(['ip', 'netns', 'exec', ns_name, 'ip', 'link', 'set', 'dev', 'eth0', 'address', MAC])
    call(['ip', 'netns', 'exec', ns_name, 'ip', 'route', 'add', 'default', 'via', GATEWAY])

def main():
    config = json.loads(''.join(sys.stdin.readlines()).replace('\n', '').replace('\t', ''))

#    mac, ip4 = add_port('test-ns0', config['bridge'])
    mac, ip4 = add_port(os.environ['CNI_CONTAINERID'], config['bridge'])

    ip_info = {
        "cniVersion" : "0.1.0",
        "ip4" : {
            "ip" : ip4,
            "gateway" : GATEWAY
        },
        "ip6" : {
            "ip" : "fd71:c650:3e0e::/48"
        },
        "dns" : {
            "nameservers" : ["127.0.1.1"],
        }
    }
    print json.dumps(ip_info)

def ovn_nbctl(cmd_str, db):
    cmd = ("ovn-nbctl %s %s" % (db, cmd_str)).split()
    child = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = child.communicate()
    if child.returncode:
#        call(['ovn-nbctl', DB, 'lsp-del', "test-ns0"])
        call(['ovn-nbctl', DB, 'lsp-del', os.environ['CNI_CONTAINERID']])
        raise RuntimeError(stderr)
    return (stdout, stderr)

if __name__ == '__main__':
#    IP_ONLY = "192.168.200.3"
#    IP = "%s/24" % IP_ONLY
#    MAC = "0A:00:00:00:00:01"
    GATEWAY = "192.168.100.1"
    DB = "--db=tcp:192.168.162.139:6641"
    main()
