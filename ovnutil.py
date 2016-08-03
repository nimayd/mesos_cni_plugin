import subprocess
from subprocess import call

def append_subnet_mask(ip, subnet):
    mask = subnet.split("/")[1].strip('"\n')
    return "%s/%s" % (ip, mask)

def call_popen(cmd):
    child = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = child.communicate()
    if child.returncode:
        raise RuntimeError("Fatal error executing %s: %s" % (cmd, output[1]))
    if len(output) == 0 or output[0] == None:
        output = ""
    else:
        output = output[0].strip()
    return output

def call_prog(prog, args_list):
    #TODO incorporate this in ovn_nbctl and ovs_vsctl.
    cmd = [prog, "--timeout=5", "-vconsole:off"] + args_list
    return call_popen(cmd)

def ovn_nbctl(cmd_str, db=None):
    db_arg = "--db=%s" % (db) if db else ""
    cmd = ("ovn-nbctl %s %s" % (db_arg, cmd_str)).split()
    return call_popen(cmd)

def ovs_vsctl(cmd_str):
    #TODO error checking
    cmd = ("ovs-vsctl %s" % cmd_str).split()
    return call_popen(cmd).strip('"\n')

def get_ovn_remote():
    #TODO error checking
    return ovs_vsctl("get Open_vSwitch . external_ids:ovn-remote")

def get_lsp_dynamic_address(lsp, db):
    """
    Returns a lsp's dynamic addresses in the form (mac_str, ip_str).
    """
    # TODO error checking if no address returned.
    cmd = "get Logical-Switch-Port %s dynamic_addresses" % lsp
    result = ovn_nbctl(cmd, db)
    address = result.strip('"\n').split()
    # Wrap MAC in quotes so that the shell doesn't complain when we string
    # substitute it in a command.
    address[0] = '"%s"' % (address[0])
    return address

def connect_ls_to_lr(ls, lr, rp_ip, rp_mac, db):
    """
    Connect a logical switch to a logical router by creating a logical switch
    port and a logical router port peer.
    """
    ovn_nbctl("-- --id=@lrp create Logical_Router_port name=%s network=%s "
              "mac=%s -- add Logical_Router %s ports @lrp -- lsp-add %s "
              "rp-%s" % (ls, rp_ip, rp_mac, lr, ls, ls), db)
    ovn_nbctl("set Logical-Switch-Port rp-%s type=router "
              "options:router-port=%s addresses=%s" % (ls, ls, rp_mac), db)
