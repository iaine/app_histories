## Methods

An initial overview of using the library. Please note that this library is under development and likely to change. 

It assumes that you are using a tool like JADX, however it may wokr with Androguard. This is not fully tested yet. 

```
ab = Read_Interface()
ab.extract_ab_testing("./extracted/", apk_name, "./ab")
```

Get the localisation details

```
ab = Read_Interface()
ab.extract_localisation("./extracted/", apk_name, "./localisation")
```

[Personalisation](personalisation) tutorial