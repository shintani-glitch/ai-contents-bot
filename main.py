import os
import random
import json
import requests
import time
import re
from datetime import datetime
import pytz
import gspread
import google.generativeai as genai
from google.oauth2.service_account import Credentials
import tweepy

# --- 定数設定 ---
SPREADSHEET_NAME = 'コスメ投稿案リスト'
SERVICE_ACCOUNT_FILE = 'google_credentials.json'

# --- スケジュール定義 ---
WEEKDAY_SCHEDULE = {
    "07:00": "planner", "07:30": "planner", "08:30": "planner", "12:05": "planner", "12:30": "planner",
    "16:00": "planner", "17:30": "planner", "19:00": "affiliate", "20:00": "affiliate", "21:00": "affiliate",
    "21:45": "planner", "22:15": "affiliate", "23:00": "planner", "23:45": "planner", "00:30": "planner"
}
HOLIDAY_SCHEDULE = {
    "09:30": "planner", "10:30": "planner", "11:30": "affiliate", "13:00": "planner", "14:30": "planner",
    "16:00": "affiliate", "17:30": "planner", "19:00": "planner", "20:00": "affiliate", "21:00": "affiliate",
    "21:45": "planner", "22:30": "affiliate", "23:15": "planner", "23:50": "affiliate", "00:30": "planner"
}

# --- 初期セットアップとクライアント取得 ---
def setup_apis():
    """APIキーの読み込みと設定を行う"""
    try:
        # Gemini & Rakuten
        GEMINI_API_KEY = os.getenv('GEMINI_API_KEY2')
        RAKUTEN_APP_ID = os.getenv('RAKUTEN_APP_ID')
        RAKUTEN_AFFILIATE_ID = os.getenv('RAKUTEN_AFFILIATE_ID')
        genai.configure(api_key=GEMINI_API_KEY)
        
        # X (Twitter)
        X_API_KEY = os.getenv('X_API_KEY')
        X_API_SECRET = os.getenv('X_API_SECRET')
        X_ACCESS_TOKEN = os.getenv('X_ACCESS_TOKEN')
        X_ACCESS_TOKEN_SECRET = os.getenv('X_ACCESS_TOKEN_SECRET')
        
        # Tweepy v2 and v1.1 clients
        client_v2 = tweepy.Client(
            consumer_key=X_API_KEY, consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN, access_token_secret=X_ACCESS_TOKEN_SECRET
        )
        auth_v1 = tweepy.OAuth1UserHandler(X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET)
        api_v1 = tweepy.API(auth_v1)

        print("✅ 全てのAPIクライアントの準備が完了しました。")
        return RAKUTEN_APP_ID, RAKUTEN_AFFILIATE_ID, client_v2, api_v1
    except Exception as e:
        print(f"🛑 エラー: 環境変数からAPIキーを読み込めませんでした。エラー詳細: {e}")
        return None, None, None, None

def get_gspread_client():
    """サービスアカウントを使ってgspreadクライアントを認証・取得する"""
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        return gspread.authorize(creds)
    return None

# ★★★★★ Xへの投稿関数 ★★★★★
def post_to_x(client, text):
    """テキストツイートを投稿する"""
    try:
        response = client.create_tweet(text=text)
        print(f"✅ Xへのテキスト投稿に成功しました！ Tweet ID: {response.data['id']}")
        return True
    except Exception as e:
        print(f"🛑 Xへのテキスト投稿中にエラー: {e}")
        return False

def post_image_to_x(client_v2, api_v1, text, image_url):
    """画像付きツイートを投稿する"""
    temp_image_path = "/tmp/temp_image.jpg"
    try:
        response = requests.get(image_url, stream=True)
        response.raise_for_status()
        with open(temp_image_path, 'wb') as f:
            f.write(response.content)
        media = api_v1.media_upload(filename=temp_image_path)
        media_id = media.media_id
        response = client_v2.create_tweet(text=text, media_ids=[media_id])
        print(f"✅ Xへの画像付き投稿に成功しました！ Tweet ID: {response.data['id']}")
        return True
    except Exception as e:
        print(f"🛑 Xへの画像付き投稿中にエラー: {e}")
        return False
    finally:
        if os.path.exists(temp_image_path):
            os.remove(temp_image_path)

# ==============================================================================
# プログラム１：価値提供ツイート案（スレッド形式）を生成するプログラム
# ==============================================================================
def run_content_planner(worksheet, x_client):
    print("--- 価値提供ツイート案の生成を実行します ---")
    # ... (この関数のロジックは前回とほぼ同じ) ...
    # 最後に投稿と記録を行う
    # (ここでは簡略化のため、最初の投稿のみを自動投稿する例とします)
    try:
        # ... (テーマ生成のロジックは前回と同じ) ...
        # (ここでは1つのテーマだけを生成して投稿する簡略版ロジックにします)
        theme_prompt = "..." # (前回と同じプロンプト)
        model = genai.GenerativeModel('gemini-1.5-flash')
        # ... (テーマを1つ生成) ...
        topic = "梅雨の湿気で髪が爆発する人必見！うねり対策ヘアケア術" # 例
        
        post_prompt = f"..." # (前回と同じプロンプト)
        response = model.generate_content(post_prompt)
        threaded_posts = [post.strip() for post in response.text.strip().split('---') if post.strip()]

        if threaded_posts:
            # 最初のツイートを投稿
            if post_to_x(x_client, threaded_posts[0]):
                # スプレッドシートに記録
                jst = pytz.timezone('Asia/Tokyo')
                timestamp = datetime.now(jst).strftime('%Y-%m-%d %H:%M:%S')
                row_to_add = [timestamp, topic] + threaded_posts
                worksheet.append_row(row_to_add)
                print(f"✅ 価値提供ツイートを投稿し、スプレッドシートに記録しました。")
    except Exception as e:
        print(f"🛑 価値提供ツイートの処理中にエラー: {e}")

# ==============================================================================
# プログラム２：アフィリエイト投稿案を生成するプログラム
# ==============================================================================
def run_affiliate_bot(worksheet, RAKUTEN_APP_ID, RAKUTEN_AFFILIATE_ID, client_v2, api_v1):
    print("--- アフィリエイト投稿案の生成を実行します ---")
    # ... (この関数のロジックは前回とほぼ同じ) ...
    # 最後に投稿と記録を行う
    try:
        # ... (キーワード生成、楽天検索、ツイート文生成のロジックは前回と同じ) ...
        keyword = "KATE リップモンスター" # 例
        # (楽天検索とGemini生成をここに記述)
        result = { # ダミーデータ
            "tweet_text": "＼落ちないリップの代名詞💄／ KATEのリップモンスターは、つけたての色が長時間続く優れもの✨ジェル膜技術で唇の水分を活用し、密着ジェル膜に変化！マスクにもつきにくく、美発色がずっと続くよ💖 #PR #プチプラコスメ",
            "affiliate_url": "http://example.com",
            "image_url": "https://thumbnail.image.rakuten.co.jp/@0_mall/rakuten24/cabinet/587/4973167827587.jpg"
        }

        short_url = requests.get(f"http://tinyurl.com/api-create.php?url={result['affiliate_url']}").text
        full_tweet = f"{result['tweet_text']}\n\n👇商品の詳細はこちらからチェック✨\n{short_url}"
        
        # 画像付きでXに投稿
        if post_image_to_x(client_v2, api_v1, full_tweet, result['image_url']):
            # スプレッドシートに記録
            jst = pytz.timezone('Asia/Tokyo')
            timestamp = datetime.now(jst).strftime('%Y-%m-%d %H:%M:%S')
            row_to_add = [timestamp, f"アフィリエイト投稿: {keyword}", full_tweet]
            worksheet.append_row(row_to_add)
            print("✅ アフィリエイト投稿を投稿し、スプレッドシートに記録しました。")
    except Exception as e:
        print(f"🛑 アフィリエイト投稿の処理中にエラー: {e}")

# ==============================================================================
# メインの実行ロジック
# ==============================================================================
if __name__ == "__main__":
    print("🚀 スケジュール実行を開始します。")
    RAKUTEN_APP_ID, RAKUTEN_AFFILIATE_ID, client_v2, api_v1 = setup_apis()

    if not all([RAKUTEN_APP_ID, client_v2, api_v1]):
        raise SystemExit("APIクライアントのセットアップに失敗したため、処理を終了します。")

    jst = pytz.timezone('Asia/Tokyo')
    now = datetime.now(jst)
    current_time_str = now.strftime("%H:%M")
    weekday = now.weekday()
    
    print(f"現在の日本時間: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    schedule = HOLIDAY_SCHEDULE if weekday >= 5 else WEEKDAY_SCHEDULE
    
    if current_time_str in schedule:
        task = schedule[current_time_str]
        print(f"⏰ スケジュールされた時刻です！タスク「{task}」を実行します。")
        
        gc = get_gspread_client()
        if gc:
            try:
                sh = gc.open(SPREADSHEET_NAME)
                worksheet = sh.sheet1
                if not worksheet.get_all_values():
                    worksheet.append_row(['生成日時', 'テーマ', '投稿1', '投稿2', '投稿3', '投稿4'])

                if task == "planner":
                    run_content_planner(worksheet, client_v2)
                elif task == "affiliate":
                    run_affiliate_bot(worksheet, RAKUTEN_APP_ID, RAKUTEN_AFFILIATE_ID, client_v2, api_v1)
            except Exception as e:
                print(f"🛑 スプレッドシートの処理中にエラー: {e}")
    else:
        print("現在の時刻は、指定された投稿スケジュールにありません。")

    print("🏁 処理を終了します。")

# 最終デプロイ
