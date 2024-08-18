import google.auth.exceptions as g_exception
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

import csv
import os
import time
import random

from enum import Enum
from io import StringIO

import Log

class obj(Enum):
    folder = "application/vnd.google-apps.folder"
    sheet = "application/vnd.google-apps.spreadsheet"
    text = "text/plain"

scriptDir = os.path.dirname(os.path.realpath(__file__))
defaultAppTokenLoc = f"{scriptDir}/AppToken.json"
defaultUserTokenLoc = f"{scriptDir}/UserToken.json"
appScope = ['openid', 'https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']


appTokenLoc = defaultAppTokenLoc
userTokenLoc = defaultUserTokenLoc

userToken = Credentials(None)
resourcesValid = False

driveService = None
sheetsService = None
infoService = None
gmailService = None

retryLimit = 3

def change_app_token_location(path):
    global appTokenLoc
    appTokenLoc = path

def change_user_token_location(path):
    global userTokenLoc
    userTokenLoc = path

def is_authorized():
    return userToken.valid

def backoff_retry(func):
    def wrapper(*args, **kwargs):
        numRetries = 0
        while numRetries < retryLimit:
            try:
                funcReturn = func(*args, **kwargs)
                return funcReturn
            except Exception as e:
                numRetries+=1
                if(numRetries >= retryLimit):
                    Log.log(f"Maximum retries exceeded for {func.__name__}")
                    raise(e)
                Log.log(f"{func.__name__}: {str(e)}")
                time.sleep((random.randint(500,1000)*numRetries)/1000) #Probably can pick a number between 1 and 1000, but I am being conservative
    return wrapper

def authorize(func):
    def wrapper(*args, **kwargs):
        funcReturn = None
        
        if get_valid_token():
            create_resources()
            funcReturn = func(*args, **kwargs)
        else:
            raise Exception(f"Unable to find/create a valid token. Call to {func.__name__} halted.")

        return funcReturn
    return wrapper

#TODO: Might want to consider what happens if the user intentionally exits the prompt.
@backoff_retry
def generate_token_via_user():
    global userToken
    try:
        # TODO, I think we can put this message up on the oauth consent thingy
        print("WARNING: THIS APP DOES NOT ENCRYPT OR MAKE ANY EFFORT TO PROTECT YOUR CREDENTIALS. USE AT YOUR OWN RISK.")
        userToken = InstalledAppFlow.from_client_secrets_file(appTokenLoc, appScope).run_local_server(port=0)
    except Exception as e:
        userToken = Credentials(None)
        raise e
    try:
        with open(userTokenLoc, 'w') as tokenFile:
            tokenFile.write(userToken.to_json())
    except:
        #No need to re-raise. Just doesn't get saved this time.
        Log.log(f"Unable to save user credentials. Ensure that {os.path.normpath(userTokenLoc)} is not open elsewhere. You will need to sign in again next restart.")
    
    return userToken.valid

def load_token_from_file():
    global userToken
    if os.path.exists(userTokenLoc):
        try:
            userToken = Credentials.from_authorized_user_file(userTokenLoc, appScope)
        except:
            Log.log(f"Unable to open existing user credentials. Ensure that this script has read/write permissions for {userTokenLoc}")
    return userToken.valid

@backoff_retry
def refresh_token():
    if userToken.expired and userToken.refresh_token:
        try:
            userToken.refresh(Request())
        except g_exception.RefreshError as e:
            Log.log(f"refresh_token: {str(e)}") #Assumed no way to fix this without user intervention.
    return userToken.valid

def get_valid_token():
    global resourcesValid
    if userToken.valid:
        return True

    resourcesValid = False #TODO: Check if it is necessary to rebuild these if the token is invalidated in the middle of the program execution

    if load_token_from_file():
        return True
    
    if refresh_token():
        return True

    return generate_token_via_user()

@backoff_retry
def create_drive_service():
    global driveService
    driveService = build('drive', 'v3', credentials=userToken)

@backoff_retry
def create_info_service():
    global infoService
    infoService = build('oauth2', 'v2', credentials=userToken)

@backoff_retry
def create_sheets_service():
    global sheetsService
    sheetsService = build('sheets', 'v4', credentials=userToken)

@backoff_retry
def create_gmail_service():
    global gmailService
    gmailService = build('gmail', 'v1', credentials=userToken)

def create_resources():
    global resourcesValid
    if resourcesValid:
        return

    if not userToken.valid:
        resourcesValid = False
        raise(Exception("Token invalid. Cannot create resources."))

    create_drive_service()
    create_info_service()
    create_sheets_service()
    create_gmail_service()
    resourcesValid = True

@authorize
@backoff_retry
def find_object(objType:obj, objName:str, parentFolderId:str):
    objectId = None
    query = f"name = '{objName}' and mimeType = '{objType.value}' and '{parentFolderId}' in parents and trashed = false"
    response = driveService.files().list(q=query, fields="files(id, name)").execute()
    respFiles = response.get('files', [])
    if respFiles:
        objectId = respFiles[0]['id']
    return objectId

@authorize
@backoff_retry
def create_object(objType:obj, objName:str, parentFolderId:str)->str:
    metadata = {'name': objName, 'mimeType': f'{objType.value}', 'parents': [parentFolderId]}
    response = driveService.files().create(body=metadata, fields='id').execute()
    if 'id' in response:
        objectId = response['id']
    return objectId

#Data should be a comma seperated list (For example "A,B,C")
@authorize
@backoff_retry
def write_to_sheet(fileId, lineNum, data):
    cellRange = f"Sheet1!A{lineNum}"
    listifiedData = list(csv.reader(StringIO(data)))
    toWrite = {'values': listifiedData}
    response = sheetsService.spreadsheets().values().update(
        spreadsheetId=fileId, range=cellRange,
        valueInputOption='USER_ENTERED', body=toWrite).execute()
    if 'updatedCells' in response:
        return fileId
    else:
        return 0

@authorize
@backoff_retry
def get_full_sheet(fileId, sheetName):
    cellRange = sheetName
    response = sheetsService.spreadsheets().values().get(spreadsheetId=fileId, range=cellRange).execute()
    return response.get("values", [[]])

#If fileId is '0', it will find/make the file. This function will return the fileId for the file it wrote to. 0 if failed
@authorize
@backoff_retry
def append_to_sheet(listifiedData:list, fileId:str):
    body = {'values': listifiedData}

    try:
        response = sheetsService.spreadsheets().values().append(
            spreadsheetId=fileId,
            range=f'Sheet1!A1',
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()
    except Exception as e:
        if type(e) == HttpError and e.resp.status == 404:
            return 0
        raise(e)

    return fileId

def append_to_sheet_make_if_dne(headerLine, dataLine, fileId, folderName, fileName):
    listifiedData = list(csv.reader(StringIO(dataLine)))
    fileId = append_to_sheet(listifiedData, fileId)
    #TODO: Turn this logic into a function which can handle a parentFolder names like "/base/folder/sub/"
    if not fileId:
        folderId = find_object(obj.folder, folderName, 'root')
        if not folderId:
            folderId = create_object(obj.folder, folderName, 'root')
        fileId = find_object(obj.sheet, fileName, folderId)
        if not fileId:
            fileId = create_object(obj.sheet, fileName, folderId)
            listifiedHeader = list(csv.reader(StringIO(headerLine)))
            append_to_sheet(listifiedHeader, fileId) #Append our header into the newly created file

        # Try appending our data again.
        if not append_to_sheet(listifiedData, fileId):
            raise(Exception("Something strange happened in between sheet creation and appending"))

    return fileId
        
@authorize
@backoff_retry
def update_file(pathToFile:str, fileId:str):
    baseName = os.path.basename(pathToFile)
    metadata = {'name': baseName}
    media = MediaFileUpload(pathToFile)
    driveService.files().update(fileId=fileId, body=metadata, media_body=media).execute()

def upload_text_from_file(pathToText:str):
    if not os.path.exists(pathToText):
        return
    baseName = os.path.basename(pathToText)
    fileId = find_object(obj.text, baseName, 'root')
    if not fileId:
        fileId = create_object(obj.text, baseName, 'root')
    update_file(pathToText, fileId)

if __name__ == "__main__":
    parentFolderId = find_object(obj.folder, "config", "root")
    if not parentFolderId:
        parentFolderId = create_object(obj.folder, "config", "root")
    sheetId = find_object(obj.sheet, "RuuviConfig", parentFolderId)
    if not sheetId:
        parentFolderId = create_object(obj.sheet, "RuuviConfig", parentFolderId)

    latestConfig = get_full_sheet(sheetId, "sheet1")