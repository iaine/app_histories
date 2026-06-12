## Downloader

The downloader tool enables a user to download from AndroZoo. It is now in its own repository, [Androozoo Downloader](https://github.com/iaine/androozoo_downloader). 

It requires a an azkey.ini file. This has the following fields:
key= "Your API key"
input_file= "The file of the hashes"
basedir= "The directory where the APK will be written" 

This will connect with up to 5 connections to download the data. 

On completion, it will check if the number of downloads matches what was expected.

It there is a failure, it will retry once. If it still fails, it will print the files. You will need to check these against the original file. 