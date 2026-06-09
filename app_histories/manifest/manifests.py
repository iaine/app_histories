"""
Functions for Manifests
"""
import os
import xml.etree.ElementTree as ET

class Manifest():

    def __init__(self):
        pass

    def get_manifest(self, apk):
        """
            Read disassemble manifest from Androguard
        """
        return (self._get_permissions,self._get_features, self._get_version, self._get_package)

    def _get_permissions(self, apk):
        """
            Get the app permissions
        """
        return apk.get_permissions()

    def _get_features(self, apk):
        """
            Get the app features 
        """
        return apk.get_features()

    def _get_version(self, apk):
        """
            Get the app features 
        """
        return apk.get_version()

    def _get_package(self, apk):
        """
            Get the app features 
        """
        return apk.get_package()

    def _get_activities(self, apk):

        return a.get_activities()

    def get_manifest_xml(self, base_dir, directory, extract_dir):
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
            
            ps = []
            fs = []

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