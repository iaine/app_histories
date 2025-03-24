import re
import os

class Localisation():

    def __init__(self):
        self.langs = []
        with open('./interface/language.txt', 'r') as f:
            data = f.readlines()
            for d in data:
                self.langs.append(d.split(',')[0])

    def get_values(self, basepath):
        '''
        Method to get the personalisation folders

        :param basepath
        :return set of paths in res
        '''

        # search for value-en or mipmap-b+es to find everything from the - to a boundary. 
        iso_lang = re.compile(r"-(?:b\\+)?(" + "|".join(self.langs) +")\\b", flags=re.I)

        pkgs = set()
        #set to explicitly look in /res for localisation. 
        bpath = basepath + "/res/"
        for root, dirs, files in os.walk(bpath):
            path = root.split(os.sep)
            #iso = iso_lang.search(root)

            if iso_lang.search(root): 
                pkgs.add("/".join(path).replace(basepath.replace('/', '.'), ""))
        return pkgs