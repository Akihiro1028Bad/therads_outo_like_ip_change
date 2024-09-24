import os
import pickle
import logging

# ロギングの設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_cookie_file_path(username):
    """
    ユーザー名に基づいてクッキーファイルのパスを生成する

    :param username: ユーザー名
    :return: クッキーファイルのパス
    """
    return f"cookies_{username}.pkl"

def save_cookies(driver, username):
    """
    ブラウザのクッキーを保存する

    :param driver: WebDriverオブジェクト
    :param username: ユーザー名
    """
    cookie_path = get_cookie_file_path(username)
    try:
        with open(cookie_path, "wb") as file:
            pickle.dump(driver.get_cookies(), file)
        logging.info(f"ユーザー {username} のクッキーを {cookie_path} に保存しました。")
    except Exception as e:
        logging.error(f"ユーザー {username} のクッキー保存中にエラーが発生しました: {e}")

def load_cookies(driver, username):
    """
    保存されたクッキーをロードする

    :param driver: WebDriverオブジェクト
    :param username: ユーザー名
    :return: クッキーのロードに成功したかどうか (bool)
    """
    cookie_path = get_cookie_file_path(username)
    if not os.path.exists(cookie_path):
        logging.info(f"ユーザー {username} のクッキーファイルが見つかりません。")
        return False

    try:
        with open(cookie_path, "rb") as file:
            cookies = pickle.load(file)
        for cookie in cookies:
            driver.add_cookie(cookie)
        logging.info(f"ユーザー {username} のクッキーを正常にロードしました。")
        return True
    except Exception as e:
        logging.error(f"ユーザー {username} のクッキーロード中にエラーが発生しました: {e}")
        return False

def delete_cookies(username):
    """
    保存されたクッキーファイルを削除する

    :param username: ユーザー名
    """
    cookie_path = get_cookie_file_path(username)
    try:
        os.remove(cookie_path)
        logging.info(f"ユーザー {username} のクッキーファイルを削除しました。")
    except FileNotFoundError:
        logging.info(f"ユーザー {username} のクッキーファイルが見つかりません。削除をスキップします。")
    except Exception as e:
        logging.error(f"ユーザー {username} のクッキーファイル削除中にエラーが発生しました: {e}")