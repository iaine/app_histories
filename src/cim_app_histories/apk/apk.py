"""
Methods on the APK class. This is the highest level of extractin. 
Usually to get metadata and format it.
"""
import re

from androguard.core.apk import APK

class extractAPK():

    def __init__(self, apkname):
        """
            Extract the APK
        """
        self.apk = APK(apkname)

    def permissions(self):
        '''
        Extract permissoins
        '''
        return ";".join(self.apk.get_permissions()) 

    def activities (self):
        '''
        Get intentions from manifest
        '''
        return ";".join(self.apk.get_activities())

    def intents (self):
        '''
        Get intentions from manifest
        '''
        return ";".join(self.apk.get_intents()) 
    
    def packagename (self):
        '''
        Get intentions from manifest
        '''
        return self.apk.get_package() 

    def applicationname (self):
        '''
        Get intentions from manifest
        '''
        return self.apk.get_app_name()

    def android_version_code(self):
        '''
        Get version code for this version
        '''
        return self.apk.get_androidversion_code()

    def android_version_name(self):
        '''
        Get name code for this version
        '''
        return self.apk.get_androidversion_name()
    
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
    
    # ------ Localisation ----------------

    LANGUAGE_CODES= ['aa', 'ab', 'ae', 'af', 'ak', 'am', 'an', 'ar', 'as',
                     'av', 'ay', 'az', 'ba', 'be', 'bg', 'bi', 'bm', 'bn',
                     'bo', 'br', 'bs', 'ca', 'ce', 'ch', 'co', 'cr', 'cs',
                     'cu', 'cv', 'cy', 'da', 'de', 'dv', 'dz', 'ee', 'el',
                     'en', 'eo', 'es', 'et', 'eu', 'fa', 'ff', 'fi', 'fj',
                     'fo', 'fr', 'fy', 'ga', 'gd', 'gl', 'gn', 'gu', 'gv',
                     'ha', 'he', 'hi', 'ho', 'hr', 'ht', 'hu', 'hy', 'hz',
                     'ia', 'id', 'ie', 'ig', 'ii', 'ik', 'io', 'is', 'it',
                     'iu', 'ja', 'jv', 'ka', 'kg', 'ki', 'kj', 'kk', 'kl',
                     'km', 'kn', 'ko', 'kr', 'ks', 'ku', 'kv', 'kw', 'ky',
                     'la', 'lb', 'lg', 'li', 'ln', 'lo', 'lt', 'lu', 'lv',
                     'mg', 'mh', 'mi', 'mk', 'ml', 'mn', 'mr', 'ms', 'mt',
                     'my', 'na', 'nb', 'nd', 'ne', 'ng', 'nl', 'nn', 'no', 
                     'nr', 'nv', 'ny', 'oc', 'oj', 'om', 'or', 'os', 'pa',
                     'pi', 'pl', 'ps', 'pt', 'qu', 'rm', 'rn', 'ro', 'ru',
                     'rw', 'sa', 'sc', 'sd', 'se', 'sg', 'si', 'sk', 'sl',
                     'sm', 'sn', 'so', 'sq', 'sr', 'ss', 'st', 'su', 'sv',
                     'sw', 'ta', 'te', 'tg', 'th', 'ti', 'tk', 'tl', 'tn',
                     'to', 'tr', 'ts', 'tt', 'tw', 'ty', 'ug', 'uk', 'ur',
                     'uz', 've', 'vi', 'vo', 'wa', 'wo', 'xh', 'yi', 'yo',
                     'za', 'zh', 'zu']
    
    def get_files(self):
        '''
        Function to read the source files, find XMl files. 
        We'll use this to read the filenames. 
        '''
        iso_lang = re.compile(r"-(?:b\\+)?(" + "|".join(self.LANGUAGE_CODES) +")\\b", flags=re.I)
        #test run with both regex.
        content = [self.get_locale_values(file_name) for file_name in self.apk.get_files()\
                    if "/res/" in file_name and iso_lang.search(file_name)]
        return content

    def get_locale_values (self, filename):
        """
        Get the local values from the APK
        """

        language = self.extract_language(filename)
        country = self.extract_country(filename)
        device = self.extract_device(filename)

        return (language, country, device)

    def extract_language (self, values):
        """
            Extract the language from the values
        """
        if len(values.split('-')) > 1:
            return values.split('-')[1]

        return ""

    def extract_country (self, values):
        """
            Extract the language from the values
        """
        c = values.split('-')

        if len(c) < 3: 
            country = ""
        else:
            if c[2] in ["xlarge", 'mdpi']: country = ""
            else:
                country = c[2].strip()

                if country.startswith("r"): 
                    country = country.replace("r","")
        return country

    def extract_device(self, values):
        '''
          Find device specific aspects within the resource filenames. 
        '''
        device = []
        device_vals = ["hdpi", 'xxhdpi', "v4", 'land', 'night']

        for d in device_vals:
            if d in values:
                device.append(d)

        return "".join(device)
