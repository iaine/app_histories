'''
Functions read interface
'''
import glob
import os

from ab import AB
from localisation import Localisation

class Read_Interface():

    def __init__(self):
        pass

    def extract_personalisation(self, uipath):
        '''
        •	Files to Inspect: Customization settings are typically found in res/xml for settings and res/values for theme attributes.
•	Tools: APKTool for extracting XML files, JADX for deeper code analysis, and Android Studio for settings layout.
o	Process:
1.	Decompile and inspect XML files in res/xml for options related to themes, personalization (color pickers, profile settings), or user preferences.
2.	Use res/values/colors.xml or styles.xml to analyze theme changes, noting if new color schemes or dark modes were added.

        '''
        pass

    def extract_localisation(self,basepath, pkg_name, extracted):
        '''
        •	Files to Inspect: res/values-<language> folders contain strings for different languages.
•	Tools: APKTool and Android Studio for language comparison.
o	Process:
1.	Check res/values-<language> folders for language support. Compare versions for expanded language support, indicating broader localization efforts.
2.	Look for region-specific text or UI elements, such as currency or date formats.

        '''
        local = Localisation()
        localised = local.get_values(basepath + pkg_name)

        #read the package and then write to CSV file
        with open(os.path.join(extracted, pkg_name[:-4] + ".csv"), "w+") as fh:
            for p in localised:
                if p != "": fh.write("{}, {}\n".format(pkg_name, p))

    def extract_ab_testing(self, basepath, pkg_name, extracted):
        ab = AB()
        pkgs = ab.get_classes(basepath + pkg_name)
        pkg = ab.find_ab_by_package(basepath, pkgs)
        
        #read the pacakge and then write to CSV file
        with open(os.path.join(extracted, pkg_name[:-4] + ".csv"), "w+") as fh:
            for p in pkg:
                if p != "": fh.write("{}, {}\n".format(pkg_name, p))