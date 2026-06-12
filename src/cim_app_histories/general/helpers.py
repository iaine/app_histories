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
        previous = None
        changes = {}
        for label, items in dict_of_lists.items():
            current = set(items)
            if previous is None:
                changes[label] = {"added": sorted(current), "removed": []}
            else:
                changes[label] = {
                    "added": sorted(current - previous),
                     "removed": sorted(previous - current),
                }
            previous = current
        return changes
            