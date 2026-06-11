from androguard.core.apk import APK

class extractAPK():

    def extract(self, apkname):
        '''
        Function to extract the data from the APK
        '''
        return APK(apkname)

    def permissions(self, apk):
        '''
        Extract permissoins
        '''
        return ";".join(apk.get_permissions()) 

    def activities (self, apk):
        '''
        Get intentions from manifest
        '''
        return ";".join(apk.get_activities())

    def packagename (self, apk):
        '''
        Get intentions from manifest
        '''
        return apk.get_package() 

    def applicationname (self, apk):
        '''
        Get intentions from manifest
        '''
        return apk.get_app_name()

    def android_version_code(self, apk):
        '''
        Get version code for this version
        '''
        return apk.get_androidversion_code()

    def android_version_name(self, apk):
        '''
        Get name code for this version
        '''
        return apk.get_androidversion_name()