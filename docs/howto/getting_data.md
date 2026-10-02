## Retrieving Data

Reading and working with Android APK files relies on building a collection. 

This how-to shows how to use the AppStudies DRI toolkit and assicated tools to retrieve data using AndroZoo.

AndroZoo is an archival resource for finding current and historical APK files. There are two paths to this:

* Using the catalogue to create a list of suitable hashes.

* Using a list of APK hashes

Both paths are using rely on using a hash, namely SHA-256, to retrive the files from the archive. You will also an AndroZoo API key. [More information](https://androzoo.uni.lu/access) from here. 

Here the key can be given to the [AndroZoo downloader](https://github.com/iaine/androozoo_downloader). It will download APK files when given a key and a list of hashes into a defined directory. 

This directory can be passed to this tool using ```--apk-dir``` for processing. 