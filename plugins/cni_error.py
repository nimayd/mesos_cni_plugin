import json

def cni_error(err_code, err_msg, err_details=None): 
    error_json = {
        "cniVersion" : "0.1.0",
        "code" : err_code,
        "msg" : err_msg,
        "details" : err_details
    }
    print json.dumps(error_json)

class CniError(Exception):
    def __init__(self, err_msg, err_code, err_details=None):
        self.err_msg = err_msg
        self.err_code = err_code
        self.err_details = err_details
