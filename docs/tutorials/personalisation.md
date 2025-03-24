## Personalisation

Apps may be personalised by developers. This is an initial approach to identifying such changes in the UI using static methods. 

### Extracting Colour changes

Apps can use different colours in different territories.

One way of finding changes is to extract the colours from the XML files and compare them. 

```
colours_xml_file = apk_name
personal = Personalisation()
all_colours = personal.get_colours(apk_name)
```

This will return a list of app against the colours and values. 