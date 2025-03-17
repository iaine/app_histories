"""
Methods for tracking AB testing
"""
import os
import re

class AB():

    def __init__(self):
        self.data = []
        with open("ab_testing.csv", "r") as fh:
            data = fh.readlines()
            for l in data:
                ln = l.split('\n')
                self.data.append(ln[0].split(',')[0].replace('\ufeff','').replace('.*',''))

    def find_ab_by_package(self, basepath, classes):
        '''
        •	Files to Inspect: Look for experimentation frameworks, often indicated by the use of libraries like Firebase A/B Testing or flag-based components in the code.
        •	Tools: JADX for code analysis and grep for finding feature flags.
        o	Process:
        1.	Decompile APKs with JADX to inspect code directly. Search for keywords like "featureFlag" or specific A/B testing libraries.
        2.	Compare findings across versions to identify when features were in experimental phases or eventually deployed.


        Also look at the tracker listing from Python. 

        :param basepath - string for the directory
        :return list of common packages from AB testing
        '''
        if basepath == "" or basepath is None:
            raise Exception("No basepath supplied")

        common = []
        for tr in self.data:
            if any(tr in x for x in classes):
                common.append(tr)

        return common

    def get_classes(self, basepath):
        '''
           Function to get the classes from the source folder

           :param basepath
        '''
        #let's assume jadx is used and walk the os path. 
        pkgs = set()
        bpath = basepath + "sources/"
        for root, dirs, files in os.walk(bpath):
            path = root.split(os.sep)
            pkgs.add(".".join(path).replace(basepath.replace('/', '.'), ""))
        return pkgs

    def get_files(self, basepath):
        '''
           Function to get the files from the source folder

           :param basepath
           :return list_of_files
        '''
        #let's assume jadx is used and walk the os path. 
        pkgs = set()
        bpath = basepath + "sources/"
        for root, dirs, files in os.walk(bpath):
            if files:
                path = root.replace('/', '.') + files
                pkgs.add(".".join(path).replace(basepath, ""))
        return pkgs

    def find_ab_by_string(self, basepath, string_to_find):
        '''
        Use grep to search decompiled technologies
        '''
        re.compile(string_to_find, flags = re.I)
        files = self.get_files(basepath)
        found = []
        for f in files:
            with open(files, 'r') as fh:
                found_str = re.search(fh.read())
                if len(found_str) > 0: found = found + found_str
        pass
