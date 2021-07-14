import sys 
sys.path.append('..')
import json
from collections import defaultdict
from tqdm import tqdm
from character.name_match.tool.interface import FindMain



def printInfo(dicts):
    aNum = 0
    pNum = 0
    for name, aidPid in dicts.items():
        aNum += len(aidPid)
        for aid, pids in aidPid.items():
            pNum += len(pids)
    
    print("#Name %d, #Author %d, #Paper %d"%(len(dicts), aNum, pNum))

dataDir = "cna-track_1/"

with open(dataDir + "whole_author_profiles.json", 'r') as files:
    pros = json.load(files)

with open(dataDir + "whole_author_profiles_pub.json", 'r') as files:
    prosInfo = json.load(files)



# Merge all authors under the same name.
nameAidPid = defaultdict(dict)
for aid, info in pros.items():
    name = info["name"]
    pubs = info["pubs"]
    nameAidPid[name][aid] = pubs


printInfo(nameAidPid)

# Find the main author index for each paper
keyNames = list(nameAidPid.keys())
newIndex = {}
errCount = 0
for i in tqdm(range(len(keyNames))):
    tmpName = defaultdict(list)
    name = keyNames[i]
    aidPid = nameAidPid[name]
    for aid, pids in aidPid.items():
        tmpPubs = []
        for each in pids:
            coauthors = [tmp["name"] for tmp in prosInfo[each]["authors"]]
            res = FindMain(name, coauthors)
            try:
                newPid = each + '-' + str(res[0][0][1])
                tmpPubs.append(newPid)
            except:
                # print(name, coauthors, res)
                errCount += 1

        tmpName[aid] = tmpPubs
    newIndex[name] = tmpName

printInfo(newIndex)
print("errCount: ", errCount)
with open("proNameAuthorPubs.json", 'w') as files:
    json.dump(newIndex, files, indent=4, ensure_ascii = False)

# Find candidates for unass papers
with open("proNameAuthorPubs.json", 'r') as files:
    nameAidPid = json.load(files)


with open(dataDir + "valid/cna_valid_unass.json", 'r') as files:
    validUnass = json.load(files)

with open(dataDir + "valid/cna_valid_unass_pub.json", 'r') as files:
    validUnassPub = json.load(files)

candiNames = list(nameAidPid.keys())
print("#Unass: %d #candiNames: %d"%(len(validUnass), len(candiNames)))


unassCandi = []
notMatch = 0
for each in tqdm(validUnass):
    pid, index = each.split('-')
    mainName = validUnassPub[pid]["authors"][int(index)]["name"]
    res = FindMain(mainName, candiNames)
    try:
        # newPid = each + '-' + str(res[0][0][0])
        unassCandi.append((each, res[0][0][0]))
        # print(mainName, res)
    except:
        notMatch += 1
    # exit()
print("Matched: %d Not Match: %d"%(len(unassCandi), notMatch))
with open("unassCandi.json", 'w') as files:
    json.dump(unassCandi, files, indent=4, ensure_ascii= False)