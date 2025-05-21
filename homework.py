import os
import time
import logging
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot

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

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(message)s',
    level=logging.DEBUG,
    datefmt='%Y-%m-%d %H:%M:%S',
    encoding='utf-8',
)


def check_tokens():
    """Check whether environment variables are available."""
    mandatory_variables = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }
    if not all(mandatory_variables.values()):
        missing_variables = [
            key for key, value in mandatory_variables.items() if not value
        ]
        if len(missing_variables) == 1:
            error_message = 'Отсутствует обязательная переменная окружения: '
        else:
            error_message = 'Отсутствуют обязательные переменные окружения:'
        error_message += f'{", ".join(missing_variables)}\n'
        error_message += 'Программа принудительно остановлена.'
        logging.critical(error_message)
        return False
    return True


def send_message(bot, message):
    """Send a message to Telegram chat."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logging.debug(f'Бот отправил сообщение: {message}')
    except Exception as error:
        logging.error(f'Ошибка при отправке сообщения в Telegram: {error}')


def get_api_answer(timestamp):
    """Make a request to the API."""
    try:
        response = requests.get(
            ENDPOINT, headers=HEADERS, params={'from_date': timestamp}
        )
        if response is not None:
            if response.status_code != HTTPStatus.OK:
                error_message = f'Эндпоинт {ENDPOINT} недоступен.'
                error_message += f'Код ответа API: {response.status_code}'
                logging.error(error_message)
                raise EndpointErrorException(error_message)
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        error_message = f'Эндпоинт {ENDPOINT} недоступен.'
        if response is not None:
            error_message += f'Код ответа API: {response.status_code}'
        logging.error(error_message)
        raise EndpointErrorException(error_message) from http_err
    except requests.RequestException as e:
        error_message = f'Ошибка запроса: {e}'
        logging.error(error_message)
        raise EndpointErrorException(error_message) from e


def check_response(response):
    """Check the API response."""
    if not isinstance(response, dict):
        error_message = 'Результат запроса не является словарем.'
        logging.error(error_message)
        raise TypeError(error_message)

    if 'homeworks' not in response:
        error_message = 'Отсутствует ключ "homeworks" в ответе API.'
        logging.error(error_message)
        raise KeyError(error_message)

    if 'current_date' not in response:
        error_message = 'Отсутствует ключ "current_date" в ответе API.'
        logging.error(error_message)
        raise KeyError(error_message)

    if not isinstance(response['homeworks'], list):
        error_message = 'Ключ "homeworks" должен быть списком.'
        logging.error(error_message)
        raise TypeError(error_message)

    return response['homeworks']


def parse_status(homework):
    """Retrieve the job status from the homework information."""
    if 'homework_name' not in homework:
        error_message = 'Отсутствует ключ "homework_name" в ответе API.'
        logging.error(error_message)
        raise KeyError(error_message)

    if 'status' not in homework:
        error_message = 'Отсутствует ключ "status" в ответе API.'
        logging.error(error_message)
        raise KeyError(error_message)

    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')

    if homework_status not in HOMEWORK_VERDICTS:
        error_message = (
            f'Неожиданный статус домашней работы: {homework_status}'
        )
        logging.error(error_message)
        raise ValueError(error_message)

    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        return

    bot = TeleBot(TELEGRAM_TOKEN)
    timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)

            if homeworks:
                for homework in homeworks:
                    message = parse_status(homework)
                    send_message(bot, message)
            else:
                logging.debug('Отсутствуют новые статусы.')

            timestamp = response.get('current_date', timestamp)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
            logging.error(message)

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
