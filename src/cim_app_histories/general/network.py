"""
Get the hosts and geolocations for host addresses
"""

import socket


class NetworkAddr():
    """
    Get the IP address from the hostname"""

    def addr_from_name(self, host):
        '''
        Get the IP address from the hostname
        :param host: hostname
        :return: IP address
        '''
        sockip = socket.gethostbyname(host)
        return sockip
    
    def addr_from_names(self, hostnames):
        '''
        Get the IP addresses from the hostname list. 

        :param hostnames: list of hostnames
        :return: list of IP addresses
        '''
        sockip = [socket.gethostbyname(host) for host in hostnames]
        return sockip