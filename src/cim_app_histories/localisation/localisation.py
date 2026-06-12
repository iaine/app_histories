"""
    The resource files hold some information in their name
    that can be used to trace specific language personalisation. 

    The methods here focus on getting language, country, and the 
    beginnings of device. 
"""
import re

class Locales():

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

    def __init__(self):
        pass

    def get_files(self, apk):
        '''
        Function to read the source files, find XMl files. 
        We'll use this to read the filenames. 
        '''
        iso_lang = re.compile(r"-(?:b\\+)?(" + "|".join(self.LANGUAGE_CODES) +")\\b", flags=re.I)
        #test run with both regex.
        content = [self.get_locale_values(file_name) for file_name in apk.get_files()\
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