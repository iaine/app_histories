"""
This is the "helpers" module.

It contains a helper function.
"""
import sys

class Helper():

    def __init__(self):
        pass

    def write_pkg_csv(self, pkg_name, data, filename):
        """
        
        :param pkg_name - Package Name
        :param data - data to be written
        :param filename - CSV filename
        """
        if type(data) != list:
            print("Incorrect type. ")
            sys.exit(2)

        with open(os.path.join(filename + ".csv"), "w+") as fh:
            if len(p[0]) == 1:
                for p in data:
                    if p != "": fh.write("{}, {}\n".format(pkg_name, p))
            elif len(p[0]) == 2:
                for p in data:
                    if p != "": fh.write("{}, {}, {}\n".format(pkg_name, p[0],p[1]))

    def list_similarity(self, dict_of_lists):
        '''
        Functions to compare lists to determine changes
        :param dict_of_lists - dictionary of lists
        '''
        current = []
        changes = {}
        for test in dict_of_lists.keys():
            if current == []: 
                changes[test] = {"added": ";".join(dict_of_lists[test]), "remove":""}
            else:
                s1 = set(current)
                s2 = set(test)
                added = list(s1.intersection(s2))
                removed = list(s2.intersection(s1))
                changes[test] = {"added": ";".join(added), "remove":";".join(removed)}
            current = dict_of_lists[test]
        return changes
            