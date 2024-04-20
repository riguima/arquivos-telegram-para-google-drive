from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

gauth = GoogleAuth()
gauth.LocalWebserverAuth()
drive = GoogleDrive(gauth)


def upload_file(file_path):
    file = drive.CreateFile({'title': file_path.name})
    file.SetContentFile(str(file_path.absolute()))
    file.Upload()
