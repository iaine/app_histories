from string import Template

testlibs = {}
with open('../ab_testing.csv', 'r') as fh:
    data = fh.readlines()

for ln in data:
    line = ln.replace('\n', '').split(',')
    if line[1] not in testlibs.keys():
        testlibs[line[1]] = {'signatures': [line[0]], 'library':line[2], 'company':line[3] }
    else:
       testlibs[line[1]]['signatures'].append(line[0]) 

for key in testlibs.keys():

    testlibs[key]['signatures'] = ";".join(testlibs[key]['signatures'])

    with open('ab.md', 'r') as fh:
        src = Template(fh.read())
        result = src.substitute(testlibs[key])
        with open("../docs/content/ab/" + testlibs[key]['library'].replace("?", "").lower() + ".md", "w") as f:
            f.write(result)