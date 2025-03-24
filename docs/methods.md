# Methods

An initial overview of using the library. Please note that this library is under development and likely to change. 

It assumes that you are using a tool like JADX, however it may work with Androguard. This is not fully tested yet. 

## Quickstart

### Finding AB libraries

```
ab = Read_Interface()
ab.extract_ab_testing("./extracted/", apk_name, "./ab")
```

Further details:
[AB Tutorial](../tutorials/ab) tutorial

#### Localisation details

```
ab = Read_Interface()
ab.extract_localisation("./extracted/", apk_name, "./localisation")
```
Further details:
[Localisation](../tutorials/localisation) tutorial

#### Manifest

```
ab = Manifest()
ab.get_manifest("./extracted/", apk_name, "./localisation")
```
Further details:
[Manifests](../tutorials/manifest) tutorial

#### Personalisation

Extracting colours used in an app. 

```
colours_xml_file = apk_name
personal = Personalisation()
all_colours = personal.get_colours(apk_name)
```
Further details:
[Personalisation](../tutorials/personalisation) tutorial