'''
Extract files
'''

class Decompile():

    def __init__(self):
        pass

    def extract_all(self, filesdir, extractdir):
        '''
        Extract all files
        '''

        if filesdir == "" or filesdir is None:
            raise Exception("No file selected")

        for f in filesdir:
            pass

    def extract(self, filedir):
        '''
           Extract a single file
        '''
        pass