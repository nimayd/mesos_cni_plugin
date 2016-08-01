def get_lsp_dynamic_address(lsp_name):
    """
    Returns a lsp's dynamic addresses in the form (mac_str, ip_str).
    """
    # TODO error checking if no address returned.
    cmd = "get Logical-Switch-Port %s dynamic_addresses" % lp_name
    stdout, stderr = ovn_nbctl(cmd, DB)
    return stdout.strip('"\n').split()

def ovn_nbctl(cmd_str, db=None):
    cmd = ("ovn-nbctl %s %s" % (db, cmd_str)).split()
    child = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = child.communicate()
    if child.returncode:
        # TODO use cni error.
        raise RuntimeError(stderr)
    return (stdout, stderr)

def ovs_vsctl(cmd_str):
    #TODO error checking
    cmd = ("ovs-vsctl %s" % cmd_str).split()
    call(cmd)
