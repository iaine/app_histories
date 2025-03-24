"""
This is the "personalisation" module.

The module provides functions to find styles in XML.

@todo: Look at Kotlin

"""
import xml.etree.ElementTree as ET


class Personalisation():
i
    def __init__(self):
        pass

    def get_colors(self, colours_xml):
        '''
        Method to get colours from res/value/color.xml
        :param colours_xml - Colours file
        '''
        colours = []
        if os.path.exists(colours_xml + "/resources/res/values/colors.xml"):
            tree = ET.parse(colours_xml)
            root = tree.getroot()

            for colour in root.findall('color'):
                colours.append((colour.get("name"), colour.text))

        return colours

    def styles(self, style_xml):
          '''
        Method to get styles from res/value/style.xml
        :param style_xml - Style file
        '''
        styles = []
        if os.path.exists(colours_xml):
            tree = ET.parse(colours_xml)
            root = tree.getroot()

            for style in root.findall('style'):
                styles.append((style.get("name"), colour.text))

        return styles  