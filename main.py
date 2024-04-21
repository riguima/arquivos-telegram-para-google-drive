import asyncio
import re
import os
from pathlib import Path

import toml
from sqlalchemy import select
from telebot import asyncio_filters
from telebot.async_telebot import AsyncTeleBot
from telebot.asyncio_handler_backends import State, StatesGroup
from telebot.asyncio_storage import StateMemoryStorage
from telebot.util import quick_markup
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.types import PeerChannel

from arquivos_telegram_para_google_drive.config import config
from arquivos_telegram_para_google_drive.database import Session
from arquivos_telegram_para_google_drive.google_drive import upload_file
from arquivos_telegram_para_google_drive.models import Account

bot = AsyncTeleBot(config['BOT_TOKEN'], state_storage=StateMemoryStorage())
client = None


class MyStates(StatesGroup):
    on_phone_number = State()
    on_code = State()
    on_password = State()
    on_chat_id = State()
    on_message_link = State()
    on_downloads_number = State()
    on_folder_id = State()


@bot.message_handler(commands=['start', 'help'])
async def start(message):
    await bot.send_message(
        message.chat.id,
        'Como Usar:\n\n/configure - Para fazer login com a conta\n\n/batch - Para fazer os downloads para Google Drive\n\n/set_folder_id - Para definir a pasta para qual fazer o upload',
    )


@bot.message_handler(commands=['configure'])
async def configure(message):
    with Session() as session:
        query = select(Account).where(Account.user_id == str(message.chat.id))
        if session.scalars(query).first():
            await bot.send_message(
                message.chat.id,
                'Conta já está logada, deseja relogar?',
                reply_markup=quick_markup(
                    {
                        'Sim': {'callback_data': 'reconfigure'},
                        'Não': {'callback_data': 'return_to_main_menu'},
                    },
                    row_width=1,
                ),
            )
        else:
            await bot.send_message(
                message.chat.id,
                'Digite o número de telefone da conta no formato internacional: +5511999999999',
            )
            await bot.set_state(
                message.chat.id, MyStates.on_phone_number, message.chat.id
            )


@bot.callback_query_handler(func=lambda c: c.data == 'reconfigure')
async def reconfigure(callback_query):
    with Session() as session:
        query = select(Account).where(
            Account.user_id == str(callback_query.message.chat.id)
        )
        account_model = session.scalars(query).first()
        session.delete(account_model)
        session.commit()
        await bot.send_message(
            callback_query.message.chat.id,
            'Digite o número de telefone da conta no formato internacional: +5511999999999',
        )
        await bot.set_state(
            callback_query.message.chat.id,
            MyStates.on_phone_number,
            callback_query.message.chat.id,
        )


@bot.callback_query_handler(func=lambda c: c.data == 'return_to_main_menu')
async def return_to_main_menu(callback_query):
    await start(callback_query.message)


@bot.message_handler(state=MyStates.on_phone_number)
async def on_phone_number(message):
    global client
    client = TelegramClient(
        str(message.chat.id), config['API_ID'], config['API_HASH']
    )
    await client.connect()
    await client.send_code_request(message.text)
    async with bot.retrieve_data(message.chat.id, message.chat.id) as data:
        data['phone_number'] = message.text
    await bot.send_message(
        message.chat.id,
        'Digite o código de verificação enviado como no exemplo: a65777',
    )
    await bot.set_state(message.chat.id, MyStates.on_code, message.chat.id)


@bot.message_handler(state=MyStates.on_code)
async def on_code(message):
    async with bot.retrieve_data(message.chat.id, message.chat.id) as data:
        try:
            await client.sign_in(data['phone_number'], message.text[1:])
        except SessionPasswordNeededError:
            await bot.send_message(
                message.chat.id, 'Digite a senha de verificação de duas etapas'
            )
            await bot.set_state(
                message.chat.id, MyStates.on_password, message.chat.id
            )
            return
        with Session() as session:
            account = Account(user_id=str(message.chat.id))
            session.add(account)
            session.commit()
        await bot.send_message(message.chat.id, 'Conta configurada')
        await bot.delete_state(message.chat.id, message.chat.id)


@bot.message_handler(state=MyStates.on_password)
async def on_password(message):
    await client.sign_in(password=message.text)
    with Session() as session:
        account = Account(user_id=str(message.chat.id))
        session.add(account)
        session.commit()
    await bot.send_message(message.chat.id, 'Conta configurada')
    await bot.delete_state(message.chat.id, message.chat.id)


@bot.message_handler(commands=['batch'])
async def download_content(message):
    await bot.send_message(
        message.chat.id,
        'Escolha uma opção',
        reply_markup=quick_markup(
            {
                'Baixar todo o conteúdo': {
                    'callback_data': 'download_all_content'
                },
                'Baixar intervalo de conteúdo': {
                    'callback_data': 'download_interval_content'
                },
            },
            row_width=1,
        ),
    )


@bot.callback_query_handler(func=lambda c: c.data == 'download_all_content')
async def download_all_content(callback_query):
    await bot.send_message(
        callback_query.message.chat.id,
        'Digite o ID ou envie o link do Canal/Grupo',
    )
    await bot.set_state(
        callback_query.message.chat.id,
        MyStates.on_chat_id,
        callback_query.message.chat.id,
    )


@bot.message_handler(state=MyStates.on_chat_id)
async def on_chat_id(message):
    client = await get_client(message.chat.id)
    downloading_message = await bot.send_message(
        message.chat.id, 'Fazendo Downloads...'
    )
    async for group_message in client.iter_messages(message.text):
        await group_message.download_media(file='uploads')
        file_path = Path('uploads') / os.listdir('uploads')[0]
        upload_file(file_path.absolute())
        os.remove(file_path.absolute())
    await bot.send_message(message.chat.id, 'Downloads Concluídos')
    await bot.delete_message(message.chat.id, downloading_message.id)
    await bot.delete_state(message.chat.id, message.chat.id)
    await start(message)


@bot.callback_query_handler(
    func=lambda c: c.data == 'download_interval_content'
)
async def download_interval_content(callback_query):
    await bot.send_message(
        callback_query.message.chat.id,
        'Envie o link da postagem de inicio do intervalo',
    )
    await bot.set_state(
        callback_query.message.chat.id,
        MyStates.on_message_link,
        callback_query.message.chat.id,
    )


@bot.message_handler(state=MyStates.on_message_link)
async def on_message_link(message):
    async with bot.retrieve_data(message.chat.id, message.chat.id) as data:
        data['message_link'] = message.text
    await bot.send_message(
        message.chat.id, 'Digite a quantidade de arquivos que serão baixados'
    )
    await bot.set_state(
        message.chat.id, MyStates.on_downloads_number, message.chat.id
    )


@bot.message_handler(state=MyStates.on_downloads_number)
async def on_downloads_number(message):
    async with bot.retrieve_data(message.chat.id, message.chat.id) as data:
        client = await get_client(message.chat.id)
        downloading_message = await bot.send_message(
            message.chat.id, 'Fazendo Downloads...'
        )
        chat = '/'.join(data['message_link'].split('/')[:-1])
        if re.findall(r'/\d+$', chat):
            chat = PeerChannel(int(re.findall(r'/(\d+)$', chat)[0]))
        message_id = int(data['message_link'].split('/')[-1])
        for group_message in await client.get_messages(
            chat,
            limit=int(message.text),
            offset_id=message_id + int(message.text),
        ):
            await group_message.download_media(file='uploads')
            file_path = Path('uploads') / os.listdir('uploads')[0]
            upload_file(file_path.absolute())
            os.remove(file_path.absolute())
        await bot.send_message(message.chat.id, 'Downloads Concluídos')
        await bot.delete_message(message.chat.id, downloading_message.id)
        await bot.delete_state(message.chat.id, message.chat.id)
        await start(message)


async def get_client(user_id):
    user_client = TelegramClient(
        str(user_id), config['API_ID'], config['API_HASH']
    )
    await user_client.start()
    return user_client


@bot.message_handler(commands=['set_folder_id'])
async def set_folder_id(message):
    await bot.send_message(message.chat.id, 'Digite o ID da pasta')
    await bot.set_state(
        message.chat.id, MyStates.on_folder_id, message.chat.id
    )


@bot.message_handler(state=MyStates.on_folder_id)
async def on_folder_id(message):
    global config
    config['FOLDER_ID'] = message.text
    toml.dump(config, open('.config.toml', 'w'))
    await bot.send_message(message.chat.id, 'Pasta Alterada!')
    await start(message)


if __name__ == '__main__':
    bot.add_custom_filter(asyncio_filters.StateFilter(bot))
    asyncio.run(bot.polling())
