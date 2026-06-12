"""
This is the "helpers" module.

It contains a helper function for post-processing
"""

class Helper():

    def __init__(self):
        pass


    def list_similarity(self, dict_of_lists):
        '''
        Functions to compare lists to determine changes.
        Run this for post-processing as it relies on a list
        of permissions, activities, or intents to be present
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
                added = list(s2.intersection(s1))
                removed = list(s1.intersection(s2))
                changes[test] = {"added": ";".join(added), "remove":";".join(removed)}
            current = dict_of_lists[test]
        return changes
            