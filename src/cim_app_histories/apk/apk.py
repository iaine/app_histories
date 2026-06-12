"""
Methods on the APK class. This is the highest level of extractin. 
Usually to get metadata and format it.
"""
import sys

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
    
    #---------------------------------------
    # Methods
    #---------------------------------------
    def get_software_version(self, softver):
        '''
            Helper function to get software version
            Software might be semantically versioned - 7.12.34 -
            or 7.1234. The former stops this form being plotted on
            a graph as it is read incorrectly. So here we provide a
            flattened version for plotting as well as the "real" version.

            :param softver - the retrieved version, 
        '''
        spl_ver = softver.split(".")

        if len(spl_ver) > 1:
            if "_" in spl_ver[-1]:
                _end = spl_ver[-1].split("_")[0]
                spl_ver[1:] += _end
            
            return float(spl_ver[0] +  "." + "".join(spl_ver[1:]) )

        return float(softver)
