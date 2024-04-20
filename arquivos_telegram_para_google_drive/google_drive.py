import toml
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

gauth = GoogleAuth()
gauth.LocalWebserverAuth()
drive = GoogleDrive(gauth)


def upload_file(file_path):
    config = toml.load(open('.config.toml', 'r'))
    file = drive.CreateFile(
        {'title': file_path.name, 'parents': [{'id': config['FOLDER_ID']}]}
    )
    file.SetContentFile(str(file_path.absolute()))
    file.Upload()
