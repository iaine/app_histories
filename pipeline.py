from multiprocessing import Process
from glob import glob
from 

def interface(apk_name):
    """
        Function to do the extractions in one. 
    """
    extracted = "ab"
    
    try:
        based = ""
        #subprocess.run(["jadx -d {} {}".format(apk_name[:-4], sha)], capture_output=True, shell=True)
        if os.path.exists("{}".format(os.path.join(based, sha[:-4])) ):
            ab = Read_Interface()
            ab.extract_ab_testing("./extracted/", apk_name, "./ab")

    except Exception as e:
        print(apk_name)
        print(e)

if __name__ == '__main__':
    extracted = "ab"
    if not os.path.exists(extracted): 
        os.mkdir(extracted)

    basedir = ""
    apks = glob(basedir + "/*.apk")
    with Pool(5) as p:
        p.map(interface, apks)