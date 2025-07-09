import os

import pymysql
from dotenv import load_dotenv


def make_connect():
    load_dotenv()
    env_db_host = os.getenv('db_host')
    env_db_name = os.getenv('db_name')
    env_db_user = os.getenv('db_user')
    env_db_port = os.getenv('db_port')
    env_db_password = os.getenv('db_password')
    connect = pymysql.connect(host=env_db_host,
                              user=env_db_user,
                              password=env_db_password,
                              db=env_db_name,
                              port=int(env_db_port),
                              charset='utf8')
    return connect


def connect_dict():
    connect = make_connect()
    connect_dict = {
        'connect': connect,
        'cursor': connect.cursor(),
        'dict_cursor': connect.cursor(pymysql.cursors.DictCursor)
    }
    return connect_dict


connect = make_connect
if __name__ == '__main__':
    connect()
