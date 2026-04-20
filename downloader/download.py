from multiprocessing import Process
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
import configparser


def download(args:tuple)-> None:
    '''
      Function to download the APKs from AndroZoo and 
      write to disk to be moved to the pipeline. 

      :param args a tuple of the hash, key and base directory
    '''

    try:
        apk_hash, api_key, basedir = args
        _apk = urlopen(f"https://androzoo.uni.lu/api/download?apikey=${api_key}&sha256=${apk_hash}")
        with open(basedir + "/" + apk_hash, 'w') as f:
            f.write(_apk.read())

    except URLError, HTTPError, Exception as e:
        print(e)


if __name__ == '__main__':
    basedir = ""
    if not os.path.exists(basedir): 
        os.mkdir(basedir)

    with open("", "r") as fh:
        apks = fh.readlines()

    if len(apks) < 100:
        print("Downloading. Not really appropriate for HPC. \
            Consider using a high thoughput machine.")

    config = configparser.ConfigParser(allow_unnamed_section=True)
    config.read("azkey.ini")
    api_key = config.get(configparser.UNNAMED_SECTION, 'key')
    basedir = config.get(configparser.UNNAMED_SECTION, 'basedir')
    # pass multiple args?
    # https://pytutorial.com/python-pool-map-pass-variables-efficiently-in-parallel-processing/
    args_list = [(apk, api_key, basedir) for apk in apks]
    with Pool(5) as p:
        p.map(download, args_list)