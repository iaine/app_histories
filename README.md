## CIM App Studies Tools

Initial toolkit to work with decompiled apps. 

Initial focus is on A/B testing; Personalisation; and Localisation.

## Issues, Bugs, and Features

If you have any of the above, please raise them on the issue queue or send a pull request.

## Usage

An initial overview of using the library. Please note that this library is under development and likely to change. 

It assumes that you are using a tool like JADX, however it may wokr with Androguard. This is not fully tested yet. 

Get the AB libraries using our [list](ab). 

```
ab = Read_Interface()
ab.extract_ab_testing("./extracted/", apk_name, "./ab")
```

Get the localisation details

```
ab = Read_Interface()
ab.extract_localisation("./extracted/", apk_name, "./localisation")
```