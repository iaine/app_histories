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

    def extract_apk(self, path_to_apk):
        """
            Extract the APK using Androguard. 

            It will return the APK and dex classes.
        """
        if not os.path.exists(path_to_apk):
            raise Exception (f"APK does not exist {path_to_apk}. Please check the path.")

        apk, d, dex = AnalyzeAPK(path_to_apk)

        return (apk, d, dex)