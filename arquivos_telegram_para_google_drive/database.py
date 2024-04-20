from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from arquivos_telegram_para_google_drive.config import config

db = create_engine(config['DATABASE_URI'])
Session = sessionmaker(db)
