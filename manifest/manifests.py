"""
Functions for Manifests
"""
import os
import xml.etree.ElementTree as ET

class Manifest():

    def __init__(self):
        pass

    def get_manifest(self, base_dir, manifestfile, extract_dir):
        '''
            Read the manifest file. Extract permissions, features, version, code
        '''
        if os.path.exists(base_dir + "{}.xml".format(directory)):
            tree = ET.parse(base_dir + "/{}.xml".format(directory))
            root = tree.getroot()

            permissions = []
            for permission in root.findall('uses-permission'):
                permissions.append(permission.get('{http://schemas.android.com/apk/res/android}name'))

            features = []
            for feature in root.findall('uses-feature'):
                feature_name = ""
                if feature.get('{http://schemas.android.com/apk/res/android}name'):
                    feature_name = feature.get('{http://schemas.android.com/apk/res/android}name')
                features.append(feature_name)

            package = root.get('package')
            version = root.get('{http://schemas.android.com/apk/res/android}versionName')

            ps = self.list_to_string(permissions)
            fs = self.list_to_string(features)

        self.write_manifest(directory, ps, fs, package, version)

    def list_to_string(self, list_elements):
        '''
        Format the list into string for CSV
        '''
        elements = ""

        if list_elements is not None and len(list_elements) > 0:
            elements = ';'.join(features)

        return elements

    def write_manifest(self, directory, ps, fs, package, version):

        fh = open(extract_dir + "/manifest_" + directory + ".csv", 'w')
        data = "{0}, {1}, {2}, {3}, {4}".format(directory, ps, fs, package, version)
        fh.write(data)
        fh.close()