## CIM App Histories Tools

This an initial toolkit to work with decompiled apps. It is a more general package that can be called from Python.  

The initial focus is on A/B testing and Localisation. Current work is moving to explore the presence of AI. 

## Issues, Bugs, and Features

If you have any of the above, please raise them on the issue queue or send a pull request.

## Usage

An initial overview of using the library. Please note that this library is under development and likely to change. 

It assumes that you are using a tool like JADX, however it may work with Androguard. This is not fully tested yet. 

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