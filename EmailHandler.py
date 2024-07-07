from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import GAPIHelper

from email.mime.text import MIMEText

import base64
import os

scriptDir = os.path.dirname(os.path.realpath(__file__))

class GmailSender:
    def __init__(self, debugOnly=False):
        self.debugOnly = debugOnly
   
    @GAPIHelper.authorize
    def create_message(self, rxEmail, subject, messageText):
        userinfo = build('oauth2', 'v2', credentials=GAPIHelper.userToken).userinfo().get().execute()
        txEmail = userinfo.get('email')
        message = MIMEText(messageText)
        message['to'] = rxEmail
        message['from'] = txEmail
        message['subject'] = subject
        return {'raw': base64.urlsafe_b64encode(message.as_bytes('utf-8')).decode()}

    @GAPIHelper.authorize
    def send_message(self, rxEmail:str, subject:str, messageText:str):
        rawMessage = self.create_message(rxEmail, subject, messageText)
        try:
            if self.debugOnly:
                print("I am not actually going to send that email. I am in debug only mode!")
                return 0

            message = (build('gmail', 'v1', credentials=GAPIHelper.userToken).users().messages().send(userId='me', body=rawMessage).execute())
            return message['id']
        except Exception as error:
            print(error)
            return None