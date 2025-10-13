"""
Function to parse the software history files. 

Mainly it removes the references to Firebase and Android to focus on the sources. 
"""

with open ('./data/software_history.txt', 'r') as fh:
    data = fh.readlines()

fh = open('./data/cleaned_history.csv', "w+")
for ln in data:
    if "com/google/android" not in ln and "com/google/firebase" not in ln and "/sources/" in ln and "kotlinx/" not in ln and "android/support" not in ln  and  "androidx/" not in ln:
        cleaning = ln.split("/sources/")
        slash = cleaning[1].split('/')
        fh.write("{}, {}, {}\n".format(cleaning[0].replace('./',''), "/".join(slash[:-1]), slash[-1:][0]))
fh.close()