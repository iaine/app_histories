"""
Get the hosts and geolocations for host addresses
"""

import socket


class NetworkAddr():

    def addr_from_name(self, host):
        '''
        Get the IP(s) from the hostname
        '''
        sockip = socket.gethostbyname(host)
        return sockip
    
    def addr_from_names(self, hostnames):
        '''
        Get the IP(s) from the hostname
        '''
        for host in hostnames:
            sockip = socket.gethostbyname(host)
        return sockip