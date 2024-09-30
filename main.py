import sys
import time
import logging
import json
import pickle
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException, WebDriverException
from bs4 import BeautifulSoup
import time
from cookie_manager import save_cookies, load_cookies, delete_cookies
import random
from proxy_manager import ProxyManager
import zipfile
import os
import requests
import json
from selenium.webdriver.common.proxy import Proxy, ProxyType
from result_manager import ResultManager
import re


# 429エラーを示す定数を定義
HTTP_429_TOO_MANY_REQUESTS = 429

# ログの設定：日時、ログレベル、メッセージを表示
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_driver(proxy, headless_mode):
    """
    Chromeドライバーを設定し、初期化する関数
    
    :param proxy: プロキシ設定 (形式: username:password:ip:port)
    :return: 設定済みのWebDriverオブジェクト
    """
    chrome_options = Options()
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    chrome_options.add_argument(f"user-agent={user_agent}")
    
    logging.info(f"Headless mode value: {headless_mode}")  # この行を追加
    if headless_mode:
        chrome_options.add_argument("--headless")
        logging.info("ヘッドレスモードが有効化されました。")
    else:
        logging.info("通常モードで実行します。")

    if proxy:
        proxy_parts = proxy.split(':')
        if len(proxy_parts) == 4:
            username, password, ip, port = proxy_parts
            
            # プロキシ認証拡張機能を作成
            plugin_path = create_proxy_auth_extension(
                proxy_host=ip,
                proxy_port=port,
                proxy_username=username,
                proxy_password=password
            )
            chrome_options.add_extension(plugin_path)

            logging.info(f"プロキシ設定を適用しました: {ip}:{port}")
        else:
            logging.warning(f"無効なプロキシ形式です: {proxy}")

    service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(service=service, options=chrome_options)

    # プロキシ設定の確認
    try:
        driver.get("https://api.ipify.org")
        ip = driver.find_element(By.TAG_NAME, "body").text
        logging.info(f"現在のIPアドレス: {ip}")
    except Exception as e:
        logging.error(f"IPアドレスの取得中にエラーが発生しました: {str(e)}")
        logging.info("ページソース:")
        logging.info(driver.page_source)

    return driver

def create_proxy_auth_extension(proxy_host, proxy_port, proxy_username, proxy_password, scheme='http', plugin_path=None):
    if plugin_path is None:
        plugin_path = 'proxy_auth_plugin.zip'

    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "minimum_chrome_version":"22.0.0"
    }
    """

    background_js = """
    var config = {
            mode: "fixed_servers",
            rules: {
              singleProxy: {
                scheme: "%s",
                host: "%s",
                port: parseInt(%s)
              },
              bypassList: ["localhost"]
            }
          };

    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});

    function callbackFn(details) {
        return {
            authCredentials: {
                username: "%s",
                password: "%s"
            }
        };
    }

    chrome.webRequest.onAuthRequired.addListener(
                callbackFn,
                {urls: ["<all_urls>"]},
                ['blocking']
    );
    """ % (scheme, proxy_host, proxy_port, proxy_username, proxy_password)

    with zipfile.ZipFile(plugin_path, 'w') as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)

    return plugin_path

def check_for_429_error(driver, timeout=10):
    """
    Threadsの429エラーページを確実に検出する関数
    
    :param driver: Seleniumのwebdriverオブジェクト
    :param timeout: タイムアウト時間（秒）
    :return: 429エラーが検出された場合はTrue、それ以外はFalse
    """
    try:
        # 1. エラーメッセージの検出
        error_message = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, 
                "//*[contains(text(), 'このページは動作していません')]"
            ))
        )
        
        # 2. HTTP ERROR 429の検出
        error_code = driver.find_element(By.XPATH, "//*[contains(text(), 'HTTP ERROR 429')]")
        
        if error_message and error_code:
            logging.error("429エラーページが検出されました。")
            return True
    except (TimeoutException, NoSuchElementException):
        return False

    return False

def login_to_threads(driver, username, password):
    """
    Threadsにログインする関数
    
    引数:
    - driver: WebDriverオブジェクト
    - username: ログイン用のユーザー名
    - password: ログイン用のパスワード
    
    戻り値:
    - bool: ログイン成功時はTrue、失敗時はFalse
    """
    url = "https://www.threads.net/login/"
    try:
        driver.get(url)
        logging.info(f"ログインページにアクセスしています: {url}")

        logging.info(f"引数ユーザ名情報: {username}")
        logging.info(f"引数パスワード情報: {password}")

        # 保存されたクッキーをロード
        if load_cookies(driver, username):
            driver.get(url)
            # クッキーでのログインが成功したかチェック
            if check_login_status(driver):
                logging.info(f"ユーザー {username} はクッキーを使用して正常にログインしました。")
                return True
            else:
                logging.info(f"ユーザー {username} のクッキーが無効です。処理を終了します。")
                return False
        
        # ユーザー名入力フィールドを待機し、入力
        #username_field = WebDriverWait(driver, 60).until(
            #EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'][class*='x1i10hfl'][class*='x1a2a7pz']"))
        #)
        #username_field.clear()
        #username_field.send_keys(username)
        #logging.info("ユーザー名を入力しました")
        
        # パスワード入力フィールドを見つけ、入力
        #password_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
        #password_field.clear()
        #password_field.send_keys(password)
        #logging.info("パスワードを入力しました")
        
        # 入力後、短い待機時間を設定
        #time.sleep(2)
        
        # ログインボタンを見つけてクリック
        #login_button_xpath = "//div[@role='button' and contains(@class, 'x1i10hfl') and contains(@class, 'x1qjc9v5')]//div[contains(text(), 'Log in') or contains(text(), 'ログイン')]"
        #login_button = WebDriverWait(driver, 10).until(
            #EC.element_to_be_clickable((By.XPATH, login_button_xpath))
        #)
        #driver.execute_script("arguments[0].click();", login_button)
        #logging.info("ログインボタンをクリックしました")

        #time.sleep(20)
        
        # ページの読み込みを待機
        #WebDriverWait(driver, 120).until(
            #EC.presence_of_element_located((By.TAG_NAME, "body"))
        #)
        #logging.info("ログインが完了し、ページが正常に読み込まれました")

        #time.sleep(5)
    except Exception as e:
        logging.error(f"ログイン処理中にエラーが発生しました: {e}")
        return False

# ログイン状態をチェックする関数
def check_login_status(driver, timeout=120):
    """
    'Post'または'投稿'要素の存在に基づいてログイン状態を確認する

    :param driver: WebDriverオブジェクト
    :param timeout: 要素を待機する最大時間（秒）
    :return: ログインしている場合はTrue、そうでない場合はFalse
    """
    logging.info("ログイン状態のチェックを開始します。")
    try:
        # 'Post'または'投稿'要素を探す
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, 
                "//div[contains(@class, 'xc26acl') and contains(@class, 'x6s0dn4') and contains(@class, 'x78zum5') and (contains(text(), 'Post') or contains(text(), '投稿'))]"
            ))
        )
        logging.info(f"'Post'または'投稿'要素が見つかりました。テキスト: '{element.text}'")
        logging.info("ログイン状態が確認されました。")
        return True
    except TimeoutException:
        logging.warning(f"'Post'または'投稿'要素が {timeout} 秒以内に見つかりませんでした。")
        logging.info("ログアウト状態であると判断します。")
        return False
    except NoSuchElementException:
        logging.warning("'Post'または'投稿'要素が存在しません。")
        logging.info("ログアウト状態であると判断します。")
        return False
    except Exception as e:
        logging.error(f"ログイン状態の確認中に予期せぬエラーが発生しました: {str(e)}")
        logging.info("ログアウト状態であると判断します。")
        return False

def get_recommended_posts(driver, username, num_posts=10):
    """
    おすすめ投稿を取得する関数
    
    引数:
    - driver: WebDriverオブジェクト
    - username: ユーザー名（クッキーの読み込みに使用）
    - num_posts: 取得する投稿の数（デフォルト: 10）
    
    戻り値:
    - list: 取得した投稿のURLリスト
    """
    url = "https://www.threads.net"
    post_hrefs = []
    last_height = 0
    reload_counter = 0

    while len(post_hrefs) < num_posts:

        if reload_counter == 0:
            driver.get(url)
            if load_cookies(driver, username):
                logging.info(f"ユーザー {username} のクッキーを正常にロードしました。")
                time.sleep(30)
            else:
                logging.warning(f"ユーザー {username} のクッキーのロードに失敗しました。既存のセッションを使用します。")

        # 10投稿ごと、または初回にページをロード/リロード
        if reload_counter % 10 == 0:
            driver.refresh()
            logging.info(f"ページをロード/リロードしました。現在の投稿数: {len(post_hrefs)}")
            time.sleep(30)
            last_height = driver.execute_script("return document.body.scrollHeight")
            reload_counter = 0

        # ページの最下部までスクロール
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(30)  # コンテンツの読み込みを待機
        
        # 新しい投稿URLを取得
        new_hrefs = get_post_hrefs(driver.page_source)
        for href in new_hrefs:
            if href not in post_hrefs:
                post_hrefs.append(href)
                reload_counter += 1
                if len(post_hrefs) >= num_posts:
                    break
                if reload_counter % 10 == 0:
                    break  # 10投稿取得したらすぐにリロード

        # スクロールが最下部に達したかチェック
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            logging.info("ページの最下部に到達しました。これ以上の投稿は読み込めません。")
            break
        last_height = new_height

    logging.info(f"合計 {len(post_hrefs)} 件のおすすめ投稿URLを取得しました")
    # 取得したURLをすべて表示
    logging.info("取得した投稿のURL一覧:")
    for i, href in enumerate(post_hrefs, 1):
        logging.info(f"{i}. https://www.threads.net{href}")
        
    return post_hrefs[:num_posts]

def get_follower_count(driver, username):
    """
    ユーザーのフォロワー数を取得する関数
    
    :param driver: WebDriverオブジェクト
    :param username: 対象ユーザーのユーザー名
    :return: フォロワー数（整数）、取得に失敗した場合は None
    """
    logging.info(f"アカウント {username} のフォロワー数取得を開始します。")
    follower_text = None
    follower_count = None
    
    try:
        # プロフィールページにアクセス
        profile_url = f"https://www.threads.net/@{username}"
        driver.get(profile_url)
        logging.info(f"アカウント {username} のプロフィールページにアクセスしました: {profile_url}")

        # フォロワー数を含む要素を待機して取得（英語と日本語に対応）
        follower_element = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, "//span[contains(@class, 'x1lliihq') and (contains(text(), 'followers') or contains(text(), 'フォロワー'))]"))
        )
        
        # フォロワー数を取得
        follower_text = follower_element.get_attribute('title')
        if not follower_text:
            follower_text = follower_element.text
        
        logging.info(f"アカウント {username} のフォロワー情報を取得: {follower_text}")

        # フォロワー数を抽出して整数に変換
        match = re.search(r'\d+', follower_text.replace(',', ''))
        if match:
            follower_count = int(match.group())
            logging.info(f"アカウント {username} のフォロワー数: {follower_count}")
        else:
            logging.error(f"アカウント {username} のフォロワー数の解析に失敗しました。取得したテキスト: {follower_text}")
    
    except TimeoutException:
        logging.error(f"アカウント {username} のフォロワー数取得中にタイムアウトが発生しました。")
    except NoSuchElementException:
        logging.error(f"アカウント {username} のフォロワー数を含む要素が見つかりませんでした。")
    except Exception as e:
        logging.error(f"アカウント {username} のフォロワー数取得中に予期せぬエラーが発生しました: {str(e)}")
    
    finally:
        if follower_text:
            logging.info(f"取得したフォロワーテキスト: {follower_text}")
        if follower_count is not None:
            logging.info(f"最終的に取得したフォロワー数: {follower_count}")
        else:
            logging.warning(f"アカウント {username} のフォロワー数取得に失敗しました。")
    
    return follower_count

def get_post_hrefs(html_content):
    """
    HTML内の投稿URLを抽出する関数
    
    引数:
    - html_content: 解析するHTMLコンテンツ
    
    戻り値:
    - list: 抽出された投稿URLのリスト
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    post_hrefs = []
    elements = soup.find_all('a', class_=['x1i10hfl', 'x1lliihq'], href=True)
    for element in elements:
        href = element['href']
        if '/post/' in href and href not in post_hrefs:
            post_hrefs.append(href)
    return post_hrefs

def click_all_like_buttons(driver, post_url, total_likes, login_username, max_scroll_attempts=5, scroll_pause_time=20):
    """
    指定された投稿ページ内のすべての「いいね！」ボタンをクリックする関数。
    
    :param driver: Seleniumのウェブドライバーインスタンス
    :param post_url: 処理する投稿のURL
    :param max_scroll_attempts: 最大スクロール試行回数（デフォルト: 5）
    :param scroll_pause_time: スクロール後の待機時間（秒）（デフォルト: 2）
    :return: クリックした「いいね！」ボタンの合計数
    """
    logging.info(f"投稿 {post_url} の「いいね！」ボタンクリック処理を開始します。")
    new_post_url = f"https://www.threads.net{post_url}" if not post_url.startswith("https://") else post_url

    def safe_click(element):
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception as e:
            logging.error(f"クリック中に予期せぬエラーが発生しました: {str(e)}")
            return False

    try:
        driver.get(new_post_url)
        logging.info(f"アカウント {login_username}:投稿ページにアクセスしています: {new_post_url}")

        # 429エラーのチェックを追加
        if check_for_429_error(driver):
            logging.error(f"アカウント {login_username}: 429エラーが検出されたため、処理を中止します。")
            return HTTP_429_TOO_MANY_REQUESTS

        # ページの読み込みを待機（タイムアウト処理付き）
        try:
            WebDriverWait(driver, 120).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            logging.info(f"アカウント {login_username}:投稿ページが正常に読み込まれました")
        except TimeoutException:
            logging.warning(f"アカウント {login_username}:投稿ページの読み込みがタイムアウトしました。次の投稿にスキップします。")
            return 0  # 0を返してこの投稿をスキップ

        click_count = 0
        new_total_likes = total_likes

        for scroll_attempt in range(max_scroll_attempts):
            logging.info(f"アカウント {login_username}:スクロール試行 {scroll_attempt + 1}/{max_scroll_attempts}")
            
            # 更新されたセレクタを使用して「いいね！」ボタンを探す
            like_buttons = driver.find_elements(By.CSS_SELECTOR, "div[role='button'][tabindex='0'] div.x6s0dn4")

            #制限チェック用
            count = 0
            check_interval = 10
            
            if not like_buttons:
                logging.info(f"「アカウント {login_username}:いいね！」ボタンが見つかりません。スクロールを続行します。")
            else:
                for button in like_buttons:
                    try:
                        # SVG要素を探してフィル状態を確認
                        svg = button.find_element(By.CSS_SELECTOR, "svg[aria-label='「いいね！」']")
                        fill_value = svg.find_element(By.TAG_NAME, "path").get_attribute("fill")
                        
                        if fill_value == "transparent" or not fill_value:
                            if safe_click(button):
                                click_count += 1
                                logging.info(f"アカウント {login_username}:「いいね！」ボタンをクリックしました。合計: {click_count}")

                                # ランダムな待機時間を設定（1秒から10秒の間）
                                random_wait = random.uniform(1, 10)
                                logging.info(f"アカウント {login_username}: {random_wait:.2f}秒待機します。")
                                time.sleep(random_wait)

                                count = count + 1
                                new_total_likes = new_total_likes + 1

                            # 10回ごとに制限チェック
                            if new_total_likes % check_interval == 0:
                                logging.info(f"アカウント:{login_username}:10いいねしたので制限チェックします") 
                                time.sleep(2)
                                
                                # SVG要素を探してフィル状態を確認
                                try:
                                    svg = button.find_element(By.CSS_SELECTOR, "svg[aria-label='「いいね！」']")
                                    
                                    if svg:
                                        logging.info("=" * 50)
                                        logging.info(f"アカウント:{login_username}:制限を感知しました")
                                        logging.info(f"ユーザー名:{login_username}")
                                        logging.info(f"アカウント:{login_username}:合計いいね数: {new_total_likes}")
                                        logging.info(f"アカウント:{login_username}:制限が感知されたため、処理を中止します。")
                                        logging.info("=" * 50)
                                        return -1  # 制限を示す特別な値を返す

                                except NoSuchElementException:
                                    logging.info(f"アカウント:{login_username}:制限は感知されませんでした。処理を続行します。")

                        else:
                            logging.info(f"アカウント:{login_username}:既にいいね済みのボタンをスキップしました")

                    except StaleElementReferenceException:
                        #logging.warning("要素が古くなっています。スキップして次に進みます。")
                        continue
                    except NoSuchElementException:
                        #logging.warning("SVG要素が見つかりませんでした。スキップします。")
                        continue
                    except Exception as e:
                        logging.error(f"ボタンクリック中に予期せぬエラーが発生しました: {str(e)}")

            # ページをスクロール
            last_height = driver.execute_script("return document.body.scrollHeight")
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(scroll_pause_time)

            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                logging.info("これ以上スクロールできません。処理を終了します。")
                break
        
        logging.info("=" * 50)
        logging.info(f"アカウント {login_username}:合計 {click_count} 件の「いいね！」ボタンをクリックしました。")
        logging.info("=" * 50)
        return click_count

    except TimeoutException:
        logging.error(f"ページの読み込みがタイムアウトしました: {new_post_url}")
        return 0
    except Exception as e:
        logging.error(f"予期せぬエラーが発生しました: {str(e)}")
        return 0

def auto_like_comments_on_posts(driver, post_urls, login_username, delay=2):
    """
    複数の投稿のコメントに自動でいいねをする関数

    :param driver: WebDriverオブジェクト
    :param post_urls: いいねを押す投稿URLのリスト
    :param delay: 各投稿処理の間の待機時間（秒、デフォルト: 2）
    :return: いいねした合計コメント数
    """
    total_likes = 0
    total_posts = len(post_urls)

    for index, url in enumerate(post_urls, start=1):
        logging.info(f"アカウント {login_username}:処理中: {index}/{total_posts} - {url}")
        
        likes = click_all_like_buttons(driver, url, total_likes, login_username)

        if likes == HTTP_429_TOO_MANY_REQUESTS:
            return HTTP_429_TOO_MANY_REQUESTS, total_likes
        
        if likes == -1:  # 制限が検知された場合
            return False, total_likes  # メイン関数に制限を通知

        total_likes += likes
        
        logging.info(f"アカウント {login_username}:投稿 {url} で {likes} 件のコメントにいいねしました。")
        
        # レート制限を回避するための待機
        time.sleep(delay)
        
        # 進捗報告
        logging.info("=" * 50)
        logging.info(f"アカウント {login_username}:進捗: 合計 {total_likes} 件のコメントにいいねしました（{index}/{total_posts} 投稿処理済み）")
        logging.info("=" * 50)

    logging.info(f"アカウント {login_username}:すべての投稿の処理が完了しました。合計 {total_likes} 件のコメントにいいねしました。")
    return True, total_likes

# main.py の末尾に以下のコードを追加

def run_single_account():
    """
    単一アカウントでの実行（既存の動作）
    """
    login_username = input("Threadsのログインユーザー名を入力してください: ").strip()
    login_password = input("Threadsのパスワードを入力してください: ").strip()
    num_likes = int(input("「いいね」する投稿数を入力してください: ").strip())
    
    driver = setup_driver()
    
    try:
        if login_to_threads(driver, login_username, login_password):
            post_urls = get_recommended_posts(driver, num_likes)
            result = auto_like_comments_on_posts(driver, post_urls, login_username)

            if result == -1:
                logging.warning("制限が検知されたため、処理を終了します。")
            else:
                logging.info(f"処理が正常に完了しました。合計 {result} 件のいいねを行いました。")

        else:
            logging.error("ログインに失敗したため、自動「いいね」を実行できません。")
    except Exception as e:
        logging.error(f"予期せぬエラーが発生しました: {e}")
    finally:
        driver.quit()
        logging.info("ブラウザを終了しました。プログラムを終了します。")

def get_user_input(prompt, value_type=int, min_value=1):
    while True:
        try:
            value = value_type(input(prompt))
            if value < min_value:
                print(f"{min_value}以上の値を入力してください。")
            else:
                return value
        except ValueError:
            print("有効な値を入力してください。")

def get_user_input_headless(prompt, value_type=str):
    while True:
        try:
            user_input = input(prompt).strip()
            if value_type == bool:
                if user_input.lower() in ['y', 'yes']:
                    return True
                elif user_input.lower() in ['n', 'no']:
                    return False
                else:
                    raise ValueError
            return value_type(user_input)
        except ValueError:
            print("無効な入力です。もう一度お試しください。")

if __name__ == "__main__":
    import sys
    #if len(sys.argv) > 1 and sys.argv[1] == "--multi":
        
    #else:
        # 単一アカウントモード（既存の動作）
        #run_single_account()

    # 複数アカウントモード
    from account_manager import load_accounts, run_accounts_in_batches

    # ユーザーに同時処理数を入力させる
    concurrent_count = get_user_input("同時処理数を指定してください（1以上の整数）: ")
    max_delay = get_user_input("各アカウントの処理開始の最大遅延時間を指定してください（秒、0以上の整数）: ", min_value=0)
    # ヘッドレスモードの選択
    headless_mode = get_user_input_headless("ヘッドレスモードを有効にしますか？ (y/n): ", bool)
    accounts = load_accounts("accounts.json")
    if accounts:
        proxy_manager = ProxyManager()  # 最大3回再試行
        # バッチサイズを5に設定してアカウントを処理
        run_accounts_in_batches(accounts, headless_mode, batch_size=concurrent_count, proxy_manager=proxy_manager, max_delay=max_delay)
    else:
        logging.error("アカウント情報の読み込みに失敗しました。処理を終了します。")

    input("Enterキーを押して終了してください...")  # コマンドプロンプトを開いたままにする

    