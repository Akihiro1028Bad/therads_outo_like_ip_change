import json
import threading
from main import setup_driver, login_to_threads, get_recommended_posts, auto_like_comments_on_posts
import logging
from cookie_manager import save_cookies, load_cookies, delete_cookies
import time
from collections import defaultdict
from proxy_manager import ProxyManager
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
from concurrent.futures import ThreadPoolExecutor, as_completed


# ロギングの設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_accounts(file_path):
    """
    JSONファイルからアカウント情報を読み込む

    :param file_path: JSONファイルのパス
    :return: アカウント情報のリスト
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            accounts = json.load(file)
        logging.info(f"{len(accounts)}件のアカウント情報を読み込みました。")
        return accounts
    except FileNotFoundError:
        logging.error(f"ファイル {file_path} が見つかりません。")
        return []
    except json.JSONDecodeError:
        logging.error(f"ファイル {file_path} の解析に失敗しました。JSONフォーマットを確認してください。")
        return []

# process_account 関数を以下のように修正
def process_account(account, proxy_manager):
    username = account['username']
    password = account['password']
    num_likes = account.get('num_likes', 10)

    logging.info(f"----------------------------------------")
    logging.info(f"ユーザ名：{username} ")
    logging.info(f"パスワード：{password} ")
    logging.info(f"投稿数：{num_likes} ")
    logging.info(f"----------------------------------------")

    for attempt in range(proxy_manager.max_retries):
        proxy = proxy_manager.get_random_proxy()
        if not proxy:
            logging.error(f"アカウント {username}: 利用可能なプロキシがありません。処理をスキップします。")
            return 0, "プロキシなし"

        logging.info(f"アカウント {username} の処理を開始します。プロキシ: {proxy}")

        driver = setup_driver(proxy)
        try:
            driver.set_page_load_timeout(60)  # ページロードのタイムアウトを30秒に設定
            if login_to_threads(driver, username, password):
                post_urls = get_recommended_posts(driver, username, num_likes)
                success, likes_count = auto_like_comments_on_posts(driver, post_urls, account['username'])

                if not success:
                    logging.info(f"アカウント {username}: 制限が検知されたため、処理を終了します。")
                    save_cookies(driver, username)
                    return likes_count, "制限検知"
                else:
                    logging.info(f"アカウント {username}: 処理が正常に完了しました。合計 {likes_count} 件のいいねを行いました。")
                    save_cookies(driver, username)
                    return likes_count, "処理成功"
            else:
                logging.error(f"アカウント {username}: ログインに失敗したため、自動「いいね」を実行できません。")
                continue  # 次のプロキシを試す
        except Exception as e:
            logging.error(f"アカウント {username}: 予期せぬエラーが発生しました: {e}")
            continue  # 次のプロキシを試す
        finally:
            driver.quit()
            logging.info(f"アカウント {username}: ブラウザを終了しました。")

    return 0, "処理失敗"  # すべての試行が失敗した場合

def process_account_with_delay(account, proxy_manager, delay):
    """
    遅延を加えてアカウントを処理する関数

    :param account: 処理するアカウント情報
    :param proxy_manager: プロキシマネージャーのインスタンス
    :param delay: 処理開始前の遅延時間（秒）
    :return: 処理結果のタプル (いいね数, ステータス)
    """
    logging.info(f"アカウント {account['username']} の処理を {delay:.2f} 秒後に開始します。")
    time.sleep(delay)
    return process_account(account, proxy_manager)

def process_account_batch(batch, proxy_manager, max_delay=30):
    """
    アカウントのバッチを並列処理する関数（各アカウントの開始をずらす）

    :param batch: 処理するアカウントのリスト
    :param proxy_manager: プロキシマネージャーのインスタンス
    :param max_delay: 最大遅延時間（秒）
    :return: アカウントごとの処理結果を含む辞書
    """
    batch_results = {}
    with ThreadPoolExecutor(max_workers=len(batch)) as executor:
        future_to_account = {
            executor.submit(
                process_account_with_delay, 
                account, 
                proxy_manager, 
                random.uniform(0, max_delay)
            ): account for account in batch
        }
        for future in as_completed(future_to_account):
            account = future_to_account[future]
            try:
                likes_count, status = future.result()
                batch_results[account['username']] = {"likes": likes_count, "status": status}
            except Exception as e:
                logging.error(f"アカウント {account['username']} の処理中に予期せぬエラーが発生しました: {str(e)}")
                batch_results[account['username']] = {"likes": 0, "status": "処理失敗"}
    return batch_results

def display_all_results(results):
    """
    全アカウントの処理結果を表示する関数

    :param results: アカウントごとの処理結果を含む辞書
    """
    logging.info("=" * 70)
    logging.info("全アカウントの処理結果:")
    logging.info("=" * 70)
    logging.info(f"{'アカウント':<20} {'状態':<15} {'いいね数':<10}")
    logging.info("-" * 70)
    
    total_likes = 0
    total_restricted = 0
    total_failed = 0
    
    for username, result in results.items():
        status = result['status']
        likes = result['likes']
        
        if status == "制限検知":
            total_restricted += 1
            total_likes += likes
        elif status == "処理失敗":
            total_failed += 1
            total_likes += likes
        else:
            total_likes += likes
        
        logging.info(f"{username:<20} {status:<15} {likes:<10}")
    
    logging.info("=" * 70)
    logging.info(f"総いいね数: {total_likes}")
    logging.info(f"制限検知アカウント数: {total_restricted}")
    logging.info(f"処理失敗アカウント数: {total_failed}")
    logging.info("=" * 70)

def run_accounts_in_batches(accounts, batch_size=5, proxy_manager=None, max_delay=30):
    """
    アカウントを指定された同時処理数で並列実行する関数

    :param accounts: 全アカウントのリスト
    :param batch_size: 同時に処理するアカウント数
    :param proxy_manager: プロキシマネージャーのインスタンス
    :param max_delay: 各アカウントの処理開始の最大遅延時間（秒）
    """
    total_accounts = len(accounts)
    results = {}

    for i in range(0, total_accounts, batch_size):
        batch = accounts[i:i+batch_size]
        logging.info(f"処理開始: アカウント {i+1} から {min(i+batch_size, total_accounts)} まで（全 {total_accounts} アカウント中）")
        try:
            batch_results = process_account_batch(batch, proxy_manager, max_delay)
            results.update(batch_results)
        except Exception as e:
            logging.error(f"処理中に予期せぬエラーが発生しました: {str(e)}")
        
        display_all_results(results)
        
        if i + batch_size < total_accounts:
            wait_time = 60  # バッチ間の待機時間（秒）
            logging.info(f"次の処理まで {wait_time} 秒待機します。")
            time.sleep(wait_time)

    display_all_results(results)

        