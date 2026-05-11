import os
import re

import pandas as pd

class Locales():

    def __init__(self):
        #self.langs = []
        with open('./localisation/language.txt', 'r') as f:
            data = f.readlines()
            #for d in data:
            #    #self.langs.append(d.split(',')[0])
            self.langs = [ d.split(',')[0]for d in f.readlines() ]

    def get_files(self, apk):
        '''
        Function to read the source files, find XMl files. 
        We'll use this to read the filenames. 
        '''
        iso_lang = re.compile(r"-(?:b\\+)?(" + "|".join(self.langs) +")\\b", flags=re.I)
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


    def get_values(self, basepath):
        '''
        Method to get the personalisation folders

        :param basepath
        :return set of paths in res
        '''

        # search for value-en or mipmap-b+es to find everything from the - to a boundary. 
        iso_lang = re.compile(r"-(?:b\\+)?(" + "|".join(self.langs) +")\\b", flags=re.I)

        pkgs = set()
        #set to explicitly look in /res for localisation. 
        bpath = basepath + "/res/"
        for root, dirs, files in os.walk(bpath):
            path = root.split(os.sep)

            if iso_lang.search(root): 
                pkgs.add("/".join(path).replace(basepath.replace('/', '.'), ""))
        return pkgs

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
        
        if len(device) > 1:
            return "".join(device)

        return device