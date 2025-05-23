import os
import time
import logging
import sys
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot, apihelper

from exceptions import EndpointErrorException

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

stream_handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    '%(asctime)s line %(lineno)d '
    'in function "%(funcName)s" [%(levelname)s] %(message)s'
)
stream_handler.setFormatter(formatter)

logger.addHandler(stream_handler)

def check_tokens():
    """Check whether environment variables are available.

    Notify which ones are absent.
    """
    mandatory_variables = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }
    missing_variables = [
        key for key, value in mandatory_variables.items() if not value
    ]
    if missing_variables:
        error_message = (
            'Отсутствует(ют) обязательная(ые) переменная(ые) '
            f'окружения: {", ".join(missing_variables)}\n'
            'Программа принудительно остановлена.'
        )
        logger.critical(error_message)
        raise EnvironmentError(error_message)


def send_message(bot, message):
    """Send a message to Telegram chat."""
    logger.debug('Начата отправка сообщения.')
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except (apihelper.ApiException, requests.RequestException) as e:
        logger.error(f'Ошибка при отправке сообщения в Telegram: {e}')
    logger.debug(f'Бот отправил сообщение: {message}')


def get_api_answer(timestamp):
    """Make a request to the API."""
    logger.debug(f'Начат запрос к {ENDPOINT}/?from_date={timestamp}.')

    try:
        response = requests.get(
            ENDPOINT, headers=HEADERS, params={'from_date': timestamp}
        )
    except requests.RequestException:
        raise ConnectionError(f'Эндпоинт {ENDPOINT} недоступен.')

    if response.status_code != HTTPStatus.OK:
        raise EndpointErrorException(
            f'Эндпоинт {ENDPOINT} недоступен. '
            f'Код ответа API: {response.status_code}',
        )
    logger.debug('Запрос успешно выполнен.')
    return response.json()


def check_response(response):
    """Check the API response."""
    logger.debug('Начата проверка ответа сервера.')
    if not isinstance(response, dict):
        raise TypeError(
            f'Результат запроса {type(response)} '
            'вместо ожидаемого <class \'dict\'>.'
        )

    if 'homeworks' not in response:
        raise KeyError('Отсутствует ключ "homeworks" в ответе API.')

    if not isinstance(response['homeworks'], list):
        raise TypeError(
            'Ключ "homeworks" имеет тип '
            f'{type(response['homeworks'])} '
            'вместо ожидаемого <class \'list\'>.'
        )

    logger.debug('Проверка ответа сервера успешно выполнена.')
    return response['homeworks']


def parse_status(homework):
    """Retrieve the job status from the homework information."""
    logger.debug('Начата проверка статуса работы.')
    if 'homework_name' not in homework:
        raise KeyError('Отсутствует ключ "homework_name" в ответе API.')

    if 'status' not in homework:
        raise KeyError('Отсутствует ключ "status" в ответе API.')

    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')

    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(
            f'Неожиданный статус домашней работы: {homework_status}'
        )

    verdict = HOMEWORK_VERDICTS[homework_status]
    logger.debug('Проверка статуса работы успешно выполнена.')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()

    logger.debug('Бот успешно запущен.')
    bot = TeleBot(TELEGRAM_TOKEN)
    timestamp = int(time.time())
    previous_message = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)

            if homeworks:
                message = parse_status(homeworks[0])
                send_message(bot, message)
                previous_message = message
            else:
                logger.debug('Отсутствуют новые статусы.')

            if 'current_date' not in response:
                timestamp = int(time.time())
            else:
                timestamp = response.get('current_date', timestamp)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if message != previous_message:
                send_message(bot, message)
                previous_message = message
            logger.error(message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
