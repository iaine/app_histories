import os
import re

import pandas as pd

class Localisation():

    def __init__(self):
        self.langs = []
        with open('./localisation/language.txt', 'r') as f:
            data = f.readlines()
            for d in data:
                self.langs.append(d.split(',')[0])

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
            #iso = iso_lang.search(root)

            if iso_lang.search(root): 
                pkgs.add("/".join(path).replace(basepath.replace('/', '.'), ""))
        return pkgs

    def merge_localise(self, main, local):
        """
            Merge the localised file with the main files
        """
        return pd.merge(main, locatl, on="sha")

    def extract_locales(self, localised_file):
        """
            Extract local data from file
        """

        local_df = localised_df

        local_df["language"] = local_df["local"].map(extract_language)
        local_df["country"] = local_df["local"].map(extract_country)

        return local_df

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