from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from email.mime.text import MIMEText

import base64
import os

scriptDir = os.path.dirname(os.path.realpath(__file__))
defaultAppCredsLoc = f"{scriptDir}/AppToken.json"
defaultUserCredsLoc = f"{scriptDir}/UserToken.json"
appScope = ['openid', 'https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/userinfo.email']

class GmailSender:
    def __init__(self, appCredsLoc=defaultAppCredsLoc, userCredsLoc=defaultUserCredsLoc, debugOnly=False, authorizeOnStart=False):
        self.appCredsLoc = appCredsLoc
        self.userCredsLoc = userCredsLoc
        self.userToken = Credentials(None)

        self.debugOnly = debugOnly

        if authorizeOnStart:
            self.get_authorization()

    def is_authorized(self):
        return self.userToken.valid

    def authorize(func):
        def wrapper(self, *args, **kwargs):
            funcReturn = None
            if self.get_authorization():
                funcReturn = func(self, *args, **kwargs)
            else:
                print(f"Authorization failed. Unable to call {func.__name__}.")
                
            return funcReturn
        return wrapper

    def generate_token_via_user(self):
        try:
            # TODO, I think we can put this message up on the oauth consent thingy
            print("WARNING: THIS APP DOES NOT ENCRYPT OR MAKE ANY EFFORT TO PROTECT YOUR CREDENTIALS. USE AT YOUR OWN RISK.")
            self.userToken = InstalledAppFlow.from_client_secrets_file(self.appCredsLoc, appScope).run_local_server(port=0)
        except:
            print("All permissions are needed to properly run at the moment. (Maybe later we can feature piece meal.)")
            self.userToken = Credentials(None)
            return
        try:
            with open(self.userCredsLoc, 'w') as tokenFile:
                tokenFile.write(self.userToken.to_json())
        except:
            print(f"Unable to save user credentials. Ensure that {os.path.normpath(self.userCredsLoc)} is not open elsewhere. You will need to sign in again next restart.")

    def load_token_from_file(self):
        if os.path.exists(self.userCredsLoc):
            try:
                self.userToken = Credentials.from_authorized_user_file(self.userCredsLoc, appScope)
            except:
                print(f"Unable to open existing user credentials. Ensure that this script has read/write permissions for {self.userCredsLoc}")

    def get_authorization(self):
        if self.userToken.valid:
            return True

        self.load_token_from_file()
        if self.userToken.valid:
            return True

        if self.userToken.expired and self.userToken.refresh_token:
            self.userToken.refresh(Request())
            if self.userToken.valid:
                return True

        self.generate_token_via_user()
        if self.userToken.valid:
            return True
        else:
            return False
   
    @authorize
    def create_message(self, rxEmail, subject, messageText):
        userinfo = build('oauth2', 'v2', credentials=self.userToken).userinfo().get().execute()
        txEmail = userinfo.get('email')
        message = MIMEText(messageText)
        message['to'] = rxEmail
        message['from'] = txEmail
        message['subject'] = subject
        return {'raw': base64.urlsafe_b64encode(message.as_bytes('utf-8')).decode()}

    @authorize
    def send_message(self, rxEmail:str, subject:str, messageText:str):
        rawMessage = self.create_message(rxEmail, subject, messageText)
        try:
            if self.debugOnly:
                print("I am not actually going to send that email. I am in debug only mode!")
                return 0

            message = (build('gmail', 'v1', credentials=self.userToken).users().messages().send(userId='me', body=rawMessage).execute())
            return message['id']
        except Exception as error:
            print(error)
            return None

if __name__ == "__main__":
    mailer = GmailSender(authorizeOnStart=True)
    messageId = mailer.send_message("RECEIVEREMAIL@", "This is another message!", "Hello there! I hope this message finds you well! Good luck out there!")
    if messageId == None:
        print("An error occurred while sending the message.")
