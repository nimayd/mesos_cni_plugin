#!/usr/bin/env python
import json
import os
import sys
import subprocess
from subprocess import call
import names

def add_port(lp_name, ls_name):
    call(['ovn-nbctl', DB, 'lsp-add', ls_name, lp_name])
    call(['ovn-nbctl', DB, 'lsp-set-addresses', lp_name, "%s %s" % (MAC, IP_ONLY)])

#     cmd = "ovn-nbctl get Logical-Switch-Port %s addresses" % lp_name
#     child = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#     stdout, stderr = child.communicate()
#     if child.returncode:
#         raise RuntimeError(stderr)
# 
#     # TODO: Make this read from the dynamic addresses column when that is implemented.
#     mac, ip4 = stdout.strip("[]\n").split()

    link_linux_ns_to_mesos_ns(lp_name)
    create_veth_pair(lp_name)

    call(['ovs-vsctl', '--may-exist', 'add-port', 'br-int', "%s_l" % lp_name])
    call(['ovs-vsctl', 'set', 'interface', "%s_l" % lp_name, 'external_ids:iface-id=%s' % lp_name])

    move_veth_pair_into_ns(lp_name)
    set_ns_addresses(lp_name)

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

    add_port('test-ns0', config['bridge'])
#     mac, ip4 = add_port('test-ns0', config['bridge'])

    ip_info = {
        "cniVersion" : "0.1.0",
        "ip4" : {
            "ip" : IP,
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

if __name__ == '__main__':
    IP_ONLY = "192.168.100.3"
    IP = "%s/24" % IP_ONLY
    MAC = "0A:00:00:00:00:01"
    GATEWAY = "192.168.100.1"
    DB = "--db=tcp:192.168.162.139:6641"
    LOCAL_IP = "192.168.162.131"
    SUBNET = "192.168.100.0/24"
    MAC_LRP = "0A:00:00:00:00:02"
    main()
