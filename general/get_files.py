import os

class GetFiles():

    def __init__(self):
        pass

    def getfiles(self, base):
        '''
            Function to get the file names
        '''

        pkgs = set()
        bpath = base + "sources/"
        for root, dirs, files in os.walk(bpath):
            path = root.split(os.sep)
            for f in files:
                path.append(f)
                pkgs.add(".".join(path).replace(basepath.replace('/', '.'), ""))
        return pkgs