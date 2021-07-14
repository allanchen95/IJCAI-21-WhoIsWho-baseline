import sys 
sys.path.append('..')
from character.feature_process import featureGeneration
from tqdm import tqdm
import json
import random
from xgboost import XGBClassifier
import numpy as np
from time import time
from collections import defaultdict
import pickle

class processFeature:
    def __init__(self, dataDir):
        with open("proNameAuthorPubs.json", 'r') as files:
            self.nameAidPid = json.load(files)
        
        with open(dataDir + "whole_author_profiles_pub.json", 'r') as files:
            self.prosInfo = json.load(files)

        with open("unassCandi.json", 'r') as files:
            self.unassCandi = json.load(files)

        with open(dataDir + "valid/cna_valid_unass_pub.json", 'r') as files:
            self.validUnassPub = json.load(files)
        
        # self.maxNames = 64
        self.maxPapers = 256
    
    def getPaperAtter(self, pids, pubDict):
        split_info = pids.split('-')
        pid = str(split_info[0])
        author_index = int(split_info[1])
        papers_attr = pubDict[pid]
        name_info = set()
        org_str = ""
        keywords_info = set()
        try:
            title = papers_attr["title"].strip().lower()
        except:
            title = ""

        try:
            venue = papers_attr["venue"].strip().lower()
        except:
            venue = ""
        try:
            abstract = papers_attr["abstract"]
        except:
            abstract = ""
        
        try:
            keywords = papers_attr["keywords"]
        except:
            keywords = []

        for ins in keywords:
            keywords_info.add(ins.strip().lower())

        paper_authors = papers_attr["authors"]
        for ins_author_index in range(len(paper_authors)):
            ins_author = paper_authors[ins_author_index]
            if(ins_author_index == author_index):
                try:
                    orgnizations =ins_author["org"].strip().lower()
                except:
                    orgnizations = ""

                if(orgnizations.strip().lower() != ""):
                    org_str = orgnizations
            else:
                try:
                    name = ins_author["name"].strip().lower()
                except:
                    name = ""
                if(name != ""):
                    name_info.add(name)
        keywords_str = " ".join(keywords_info).strip()
        return (name_info, org_str, venue, keywords_str, title)

    def getUnassFeat(self):
        tmp = []
        tmpCandi = []
        for insIndex in tqdm(range(len(self.unassCandi))):
            unassPid, candiName = self.unassCandi[insIndex]
            unassAttr = self.getPaperAtter(unassPid, self.validUnassPub)
            candiAuthors = list(self.nameAidPid[candiName].keys())
            
            tmpCandiAuthor = []
            tmpFeat = []
            for each in candiAuthors:
                totalPubs = self.nameAidPid[candiName][each]
                samplePubs = random.sample(totalPubs, min(len(totalPubs), self.maxPapers))
                candiAttrList = [(self.getPaperAtter(insPub, self.prosInfo)) for insPub in samplePubs]
                tmpFeat.append((unassAttr, candiAttrList))
                tmpCandiAuthor.append(each)

            tmp.append((insIndex, tmpFeat))
            tmpCandi.append((insIndex, unassPid, tmpCandiAuthor))
        return tmp, tmpCandi

if __name__ == "__main__":
    # parser = argparse.ArgumentParser()
    # parser.add_argument('model', metavar='N', type=int, nargs='+',
    #                     help='an integer for the accumulator')
    # parser.add_argument('--sum', dest='accumulate', action='store_const',
    #                     const=sum, default=max,
    #                     help='sum the integers (default: find the max)')

    # args = parser.parse_args()
    # print(args.accumulate(args.integers))
    dataDir = "./cna-track_1/"
    genRawFeat = processFeature(dataDir)
    genFeatures = featureGeneration()

    sT = time()
    rawFeatData, unassCandiAuthor = genRawFeat.getUnassFeat()
    # featureData = genFeatures.process_data(rawFeatData)
    featureData = genFeatures.multi_process_data(rawFeatData)
    assert len(featureData) == len(unassCandiAuthor)
    print("process data: %.6f"%(time() - sT))
    with open("featData.pkl", 'wb') as files:
        pickle.dump(featureData, files)
        
    #load model
    print("load model.")
    savedDir = "../"
    preModel = XGBClassifier(
        max_depth=7, learning_rate=0.01, n_estimators=1000, subsample=0.8,
        n_jobs=-1, min_child_weight=6, random_state=666
        )
    preModel.load_model(savedDir + "xgboost.json")

    authorUnass = defaultdict(list)
    candiScore = defaultdict(list)
    for insNum in tqdm(range(len(featureData))):
        tmpScore = []
        candiFeat = featureData[insNum][0]
        _, unassPid, candiAuthors = unassCandiAuthor[insNum]
        for each in candiFeat:
            preScore = preModel.predict_proba(np.array(each)[np.newaxis, :])[0][1]
            tmpScore.append(preScore)
        # exit()
        assert len(tmpScore) == len(candiAuthors)
        # print(tmpScore)
        rank = np.argsort(-np.array(tmpScore))
        # print(rank)
        preAuthor = candiAuthors[rank[0]]
        # print("Paper: %s Pre: %s Score: %.6f"%(unassPid, preAuthor, tmpScore[rank[0]]))    
        authorUnass[preAuthor].append(unassPid.split('-')[0])
        tmp = []
        for i in rank:
            pAuthor = candiAuthors[i]
            pScore = str(tmpScore[i])
            tmp.append((pAuthor, pScore))
        candiScore[unassPid] = tmp
    
    with open("result.json", 'w') as files:
        json.dump(authorUnass, files, indent=4, ensure_ascii = False)

    with open("resultScore.json", 'w') as files:
        json.dump(candiScore, files, indent=4, ensure_ascii = False)
    

    # process by threshold
    with open("resultScore.json", 'r') as files:
        preScore = json.load(files)

    print(len(preScore))
    count = 0
    thres = 0.8
    authorPid = defaultdict(list)
    for pid, pres in preScore.items():
        preAuthor, preScore = pres[0]
        if float(preScore) >= thres:
            authorPid[preAuthor].append(pid.split('-')[0])
            count += 1
    with open("result.json", 'w') as files:
        json.dump(authorPid, files, indent=4, ensure_ascii=False)
    print(count)
        # print(pres)
        # exit()