'''
Stand Alone Python script to search for ab_testing

@todo: set up command line
'''

from androguard import Analyze
from androguard.core.analysis.analysis import StringAnalysis, ClassAnalysis

ab_pkgs = []
a, d, dx = AnalyzeAPK("examples/android/abcore/app-prod-debug.apk")


def find_all():
    #get all classes
    classes = d.get_classes()

    #get the AB package
    ab = []

    for clazz in classes:

        if clazz in ab: ap_pkgs.append(clazz)

    return ab_pkgs

def find_pkg(pkgname):
    '''
    Search for a particular package
    '''

    classes = dx.get_classes()
    if pkgname in  classes: return True

    return False

def find_string(search):

    strings = d.find_string(search)

    original = strings.get_orig_value()

    for string in strings:
        print(string)
