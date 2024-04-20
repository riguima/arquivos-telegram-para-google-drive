from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from arquivos_telegram_para_google_drive.database import db


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = 'accounts'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str]


Base.metadata.create_all(db)
