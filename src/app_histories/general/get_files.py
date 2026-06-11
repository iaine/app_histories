import os

class GetFiles():

    def __init__(self):
        pass

    def get_source_dirs(self, base):
        '''
            Function to get the surce directory names. 
        '''

        pkgs = set()
        bpath = base + "sources/"
        for root, dirs, files in os.walk(bpath):
            pkgs.add(root.replace(basepath, ""))
        return pkgs