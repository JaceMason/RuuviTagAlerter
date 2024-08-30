import csv
import os
from dataclasses import dataclass

import GAPIHelper as gapi
from Log import log

scriptDir = os.path.dirname(os.path.realpath(__file__))

@dataclass
class RuuviConfig:
    #We don't need to hold the Mac because that is our dict key.
    name:str = ""
    lowerThresholdF:float = float("-inf")
    upperThresholdF:float = float("inf")
    enabled:bool = False

    def __init__(self, name=None, lowerF=None, upperF=None, enabled=None):
        if(enabled==None): #discount default constructor.
            return
        self.name = name

        try:
            self.lowerThresholdF = float(lowerF)
        except:
            self.lowerThresholdF = float("-inf")

        try:
            self.upperThresholdF = float(upperF)
        except:
            self.upperThresholdF = float("inf")

        if type(enabled) == str:
            enTxt = enabled.lower()
            if enTxt=="true" or enTxt=="yes" or enTxt == "1":
                self.enabled = True
        else:
            self.enabled = bool(enabled)

    def stringify(self, mac):
        return f"{mac},{self.name},{self.lowerThresholdF},{self.upperThresholdF},{self.enabled}\n"

configFileHeaders = "Mac,Name,Lower_Threshold_F,Upper_Threshold_F,Enabled\n"
configFileName = "RuuviConfig.csv"

tagConfigs:dict[str, RuuviConfig] = {}
firstTimeStart = True

def create_config_from_csv_list(listifiedData):
    config = {}
    for row in listifiedData[1:]:
        config[row[0]] = RuuviConfig(row[1], row[2], row[3], row[4])
    return config

def load_local_file():
    global tagConfigs
    try:
        with open(scriptDir + "/" + configFileName, 'r') as localConfig:
            listifiedData = list(csv.reader(localConfig))
            tagConfigs = create_config_from_csv_list(listifiedData)
    except FileNotFoundError:
        pass #Will be made later

def get_config_csv():
    csvString = configFileHeaders
    for mac in tagConfigs:
        csvString += tagConfigs[mac].stringify(mac)
    return csvString

def write_local_config(csvString):
    global firstTimeStart
    try:
        with open(scriptDir + "/" + configFileName, 'w') as localConfig:
            localConfig.write(csvString)
            firstTimeStart = False
    except:
        pass

def get_latest_config(recentMacs):
    global tagConfigs
    if recentMacs == []:
        return #If we didn't get any tags this round, then there is nothing to be done here.

    for tag in recentMacs:
        tagConfigs.setdefault(tag, RuuviConfig())

    parentFolderId = gapi.find_object(gapi.obj.folder, "config", "root")
    if not parentFolderId:
        parentFolderId = gapi.create_object(gapi.obj.folder, "config", "root")

    sheetId = gapi.find_object(gapi.obj.sheet, "RuuviConfig", parentFolderId)
    if not sheetId:
        sheetId = gapi.create_object(gapi.obj.sheet, "RuuviConfig", parentFolderId)

    if not sheetId:
        log("Unable to generate the RuuviConfig on Drive for the first time.")
        return

    latestConfig = gapi.get_full_sheet(sheetId, "sheet1")

    #Latest config is built up from the web first (taking priority), then anything local is added which should be just completely new tags.
    #The result is saved off in program memory, locally, and online
    configFromOnline = create_config_from_csv_list(latestConfig)

    configToUpload = configFromOnline.copy()
    for tag in tagConfigs:
        if tag not in configToUpload:
            configToUpload[tag] = tagConfigs[tag]

    tagConfigs = configToUpload
    if configToUpload == configFromOnline:
        if firstTimeStart:
            #This fixes an edge case where if you start up and your config never changes, your local file will never write.
            #I also didn't want to write to the local file every time because it is likely an SD card and technically has limited writes.
            write_local_config(get_config_csv())
        return

    csvString = get_config_csv()

    write_local_config(csvString)
    gapi.write_to_sheet(sheetId, 1, csvString)
