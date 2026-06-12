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
    
    # NB raw string with single escapes: r"\+" is a literal plus and
    # r"\b" a word boundary; the previous double backslashes made both
    # literal backslashes, so b+ qualifiers were never matched.
    ISO_LANG_RE = re.compile(
        r"-(?:b\+)?(" + "|".join(LANGUAGE_CODES) + r")(?:\b|\+)", re.I)

    NON_REGION_QUALIFIERS = re.compile(
        r"^(?:[a-z]+dpi|sw\d+dp|w\d+dp|h\d+dp|v\d+|land|port|night|notnight|"
        r"small|normal|large|xlarge|long|notlong|ldltr|ldrtl|round|notround|"
        r"car|desk|television|watch|appliance|vrheadset)$", re.I)

    def get_files(self):
        '''
        Locale qualifiers found in resource paths, deduplicated.

        Parses the resource DIRECTORY segment (values-zh-rCN), not the
        full path: splitting the whole path on "-" returned fragments
        like "es/strings.xml" as a language.
        '''
        seen = set()
        for file_name in self.apk.get_files():
            if not (file_name.startswith("res/") or "/res/" in file_name):
                continue
            parts = file_name.split("/")
            if len(parts) < 2:
                continue
            segment = parts[-2]
            if self.ISO_LANG_RE.search("-" + segment.split("-", 1)[-1]
                                       if "-" in segment else segment):
                values = self.get_locale_values(segment)
                if values[0]:
                    seen.add(values)
        return sorted(seen)

    def get_locale_values (self, segment):
        """
        Parse one resource directory segment, e.g. "values-zh-rCN".
        """
        language = self.extract_language(segment)
        country = self.extract_country(segment)
        device = self.extract_device(segment)

        return (language, country, device)

    def extract_language (self, values):
        """
        Extract the language: "values-es" -> "es",
        "values-b+es+419" -> "es", "values-zh-rCN" -> "zh".
        """
        parts = values.split('-')
        if len(parts) < 2:
            return ""

        token = parts[1].strip()
        if token.startswith("b+"):
            return token.split("+")[1] if "+" in token else ""
        return token if token.lower() in self.LANGUAGE_CODES else ""

    def extract_country (self, values):
        """
        Extract the region: "values-zh-rCN" -> "CN",
        "values-b+es+419" -> "419". Device qualifiers (sw600dp, v26,
        night, ...) and script subtags (Latn) are not regions.
        """
        parts = values.split('-')

        if len(parts) > 1 and parts[1].startswith("b+"):
            sub = parts[1].split("+")
            if len(sub) >= 3 and (sub[2].isdigit() or sub[2].isupper()):
                return sub[2]
            return ""

        if len(parts) < 3:
            return ""

        token = parts[2].strip()
        if self.NON_REGION_QUALIFIERS.match(token):
            return ""
        if re.fullmatch(r"r[A-Z]{2}", token) or re.fullmatch(r"r\d{3}", token):
            return token[1:]
        return ""

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
