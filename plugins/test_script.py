#!/usr/bin/env python
import json
import os
import sys
import subprocess
from subprocess import call
import names

def add_switch(ls_name):
    call(['ovn-nbctl', DB, 'ls-add', ls_name])

def add_router(lr_name):
    call(['ovn-nbctl', DB, 'create', 'Logical_Router', 'name=%s' % lr_name])

def connect_switch_to_router(ls_name, lr_name):
    call(['ovn-nbctl', '--id=@lrp', 'create', DB, 'Logical_Router_port', 'name=%s' % ls_name,
          'network=%s' % SUBNET, 'mac="%s"' % LRP_MAC, '--', 'add', 'Logical_Router', lr_name,
          'ports', '@lrp', '--', 'lsp-add', ls_name, 'rp-"%s"' % ls_name], stdout=FNULL)
#    args = (DB, ls_name, SUBNET, LRP_MAC, lr_name, ls_name, ls_name
#    call(['`ovn-nbctl %s --id=@lrp create Logical_Router_port name=%s network=%s mac="%s" -- add Logical_Router %s ports @lrp -- lsp-add %s rp-"%s"`' % args])

def add_port(lp_name, ls_name):
    call(['ovn-nbctl', DB, 'lsp-add', ls_name, lp_name])
    call(['ovn-nbctl', DB, 'lsp-set-addresses', lp_name, "%s %s" % (MAC, IP_ONLY)])

    link_linux_ns_to_mesos_ns(lp_name)
    create_veth_pair(lp_name)

    call(['ovs-vsctl', '--may-exist', 'add-port', 'br-int', "%s_l" % lp_name])
    call(['ovs-vsctl', 'set', 'interface', "%s_l" % lp_name, 'external_ids:iface-id=%s' % lp_name])

    move_veth_pair_into_ns(lp_name)
    set_ns_addresses(lp_name)

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

#    call(['ovs-vsctl', 'set', 'Open_vSwitch', '.', 'external_ids:ovn-remote="tcp:%s:6642"' % IP_ONLY,
#      'external_ids:ovn-encap-ip=%s' % LOCAL_IP, 'external_ids:ovn-encap-type="%s"' % ENCAP_TYPE])
#    call(['/usr/share/openvswitch/scripts/ovn-ctl', 'start_controller'])

#    add_switch(config['bridge'])
#    add_router(config['router'])
#    connect_switch_to_router(config['bridge'], config['router'])
    add_port('test-%s' % names.get_first_name(), config['bridge'])

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
            "nameservers" : ["8.8.8.8", "8.8.4.4"],
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
    ENCAP_TYPE = "geneve"
    SUBNET = "192.168.100.0/24"
    MAC_LRP = "0A:00:00:00:00:02"
    main()
