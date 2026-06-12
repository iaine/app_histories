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

    def find_ab_by_package(self, classes):
        '''
            Files to Inspect: Look for experimentation frameworks, often indicated by the use of libraries like Firebase A/B Testing or flag-based components in the code.
        
            Also look at the tracker listing from Python. 

            :param classes - DEX classes from dex package. 
            :return list of common packages from AB testing
        '''

        common = []
        for tr in self.data:
            if any(tr in x for x in classes):
                common.append(tr)

        return common

    def find_ab_by_string(self, basepath, string_to_find):
        '''
        Use grep to search decompiled technologies
        '''
        re.compile(r'"'+string_to_find+'"', flags = re.I)
        files = self.get_files(basepath)
        found = []
        for f in files:
            with open(files, 'r') as fh:
                found_str = re.search(fh.read())
                if len(found_str) > 0: found = found + found_str
