import logging
import requests

class ProxyManager:
    def __init__(self):
        pass

    def test_proxy(self, proxy):
        """
        プロキシのテスト

        :param proxy: テストするプロキシ (形式: username:password:ip:port)
        :return: プロキシが機能する場合はTrue、そうでない場合はFalse
        """
        try:
            proxy_parts = proxy.split(':')
            if len(proxy_parts) != 4:
                raise ValueError(f"Invalid proxy format: {proxy}")

            username, password, ip, port = proxy_parts
            proxy_url = f"http://{username}:{password}@{ip}:{port}"
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
                return False
        except Exception as e:
            logging.error(f"プロキシ {proxy} のテスト中にエラーが発生しました: {str(e)}")
            return False