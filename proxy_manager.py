import random
import base64
import re
from selenium import webdriver
import requests
import logging

class ProxyManager:
    def __init__(self, proxy_file, max_retries=3):
        self.proxy_file = proxy_file
        self.proxy_list = self.load_proxies()
        self.max_retries = max_retries

    def load_proxies(self):
        try:
            with open(self.proxy_file, 'r') as file:
                return [line.strip() for line in file if line.strip() and not line.startswith('#')]
        except FileNotFoundError:
            logging.error(f"プロキシファイル '{self.proxy_file}' が見つかりません。")
            return []
        except Exception as e:
            logging.error(f"プロキシファイルの読み込み中にエラーが発生しました: {e}")
            return []

    def get_random_proxy(self):
        if not self.proxy_list:
            logging.warning("利用可能なプロキシがありません。")
            return None
        
        for _ in range(len(self.proxy_list)):
            proxy = random.choice(self.proxy_list)
            if test_proxy(proxy):
                return proxy
            else:
                self.proxy_list.remove(proxy)

        return random.choice(self.proxy_list)

    def get_next_proxy(self, current_proxy):
        """現在のプロキシの次のプロキシを取得する"""
        if current_proxy in self.proxy_list:
            current_index = self.proxy_list.index(current_proxy)
            next_index = (current_index + 1) % len(self.proxy_list)
            return self.proxy_list[next_index]
        else:
            return self.get_random_proxy()
        
def test_proxy(proxy):
    try:
        proxy_parts = proxy.split(':')
        if len(proxy_parts) != 4:
            raise ValueError(f"Invalid proxy format: {proxy}")

        proxy_url = f"http://{proxy_parts[0]}:{proxy_parts[1]}@{proxy_parts[2]}:{proxy_parts[3]}"
        proxy_dict = {
            "http": proxy_url,
            "https": proxy_url
        }
        response = requests.get("http://api.ipify.org", proxies=proxy_dict, timeout=10)
        if response.status_code == 200:
            logging.info(f"プロキシ {proxy} は正常に機能しています。IP: {response.text}")
            return True
        else:
            logging.warning(f"プロキシ {proxy} は応答しましたが、ステータスコードが異常です: {response.status_code}")
            logging.info(f"レスポンス内容: {response.text}")
            return False
    except requests.exceptions.ProxyError as e:
        logging.error(f"プロキシ {proxy} との接続中にエラーが発生しました: {str(e)}")
    except requests.exceptions.ConnectionError as e:
        logging.error(f"プロキシ {proxy} を使用した接続中にエラーが発生しました: {str(e)}")
    except Exception as e:
        logging.error(f"プロキシ {proxy} のテスト中に予期せぬエラーが発生しました: {str(e)}")
    return False
        
def parse_proxy_string(proxy_string):
    parts = proxy_string.split(':')
    if len(parts) == 4:
        username, password, hostname, port = parts
        scheme = 'http'
    elif len(parts) == 5:
        scheme, username, password, hostname, port = parts
    else:
        raise ValueError(f"Invalid proxy string format: {proxy_string}")

    # セッション情報を処理
    if '_country-' in password:
        password, session = password.split('_country-', 1)
        session = f'_country-{session}'
    else:
        session = ''

    return {
        'scheme': scheme,
        'username': username,
        'password': password,
        'session': session,
        'hostname': hostname,
        'port': int(port)
    }
    
def setup_proxy_for_driver(proxy):
    if proxy:
        try:
            proxy_info = parse_proxy_string(proxy)
            proxy_url = f"{proxy_info['scheme']}://{proxy_info['username']}:{proxy_info['password']}{proxy_info['session']}@{proxy_info['hostname']}:{proxy_info['port']}"
            
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument(f'--proxy-server={proxy_url}')
            
            logging.info(f"プロキシ {proxy_url} を設定しました。")
            return chrome_options
        except Exception as e:
            logging.error(f"プロキシの設定中にエラーが発生しました: {str(e)}")
            return None
    else:
        logging.warning("プロキシが指定されていません。直接接続を使用します。")
        return None