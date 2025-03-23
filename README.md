## CIM App Studies Toolkit

Initial toolkit to work with decompiled apps. 

Initial focus is on A/B testing; Personalisation; and Localisation.

## Issues, Bugs, and Features

If you have any of the above, please raise them on the issue queue or send a pull request.

## Usage

Get the AB libraries

```
ab = Read_Interface()
ab.extract_ab_testing("./extracted/", apk_name, "./ab")
```

Get the localisation details

```
ab = Read_Interface()
ab.extract_localisation("./extracted/", apk_name, "./localisation")
```