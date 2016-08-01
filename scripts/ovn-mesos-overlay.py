#!/usr/bin/env python

import argparse
import ovnutil

OVN_REMOTE = ""
OVN_BRIDGE = "br-int"

def init(args):
    # Create distributed router.
    # Connect to router.
    pass

def master_init(args):
    pass

def agent_init(args):
    """
    Creates logical switch with given subnet. Attaches switch to
    distributed router.
    """
    ovn_nbctl("ls-add %s -- set Logical_Switch %s other_config:subnet=%s",
              OVN_REMOTE)
    connect_ls_to_lr()
    # add subnet to cni config file
    # Add agent to ovn network. Give agent dynamically allocated MAC and IPv4
    # address.
    ovnutil.ovn_nbctl("lsp-add %s %s -- lsp-set-addresses %s dynamic"
              % (ls_name, lsp_name, lsp_name), OVN_REMOTE)
    mac, ip4 = ovnutil.get_lsp_dynamic_address(lsp_name)
    ovnutil.ovs_vsctl("add-port %s -- set interface type=internal mac=%s "
                      "external_ids:iface-id=%s" % (lsp_name, mac, lsp_name))
    call(("ifconfig %s %s up" % (lsp_name, ip4_with_subnet)).split())

def gateway_init(args):
    # Create join switch
    # Connect to DR
    # Create GWR
    # Connect to join switch
    # Create external switch
    # Connect to GWR
    pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", help="Initialize OVN network.", type=init,
                        action='store_true')
#    Include a flag to pass in DB
#    parser.add_argument("--master-init", help="Initialize master.")
#    parser.add_argument("--agent-init", help="Initialize agent.")
#    parser.add_argument("--gateway-init", help="Initialize gateway.")
    args = parser.parse_args()

if __name__ == '__main__':
    main()
