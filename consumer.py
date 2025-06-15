import os
import requests
import time
from datetime import datetime
import pytz
import gspread
from google.oauth2.service_account import Credentials
import tweepy

# --- 定数と設定 ---
SPREADSHEET_NAME = 'コスメ投稿案リスト'
SERVICE_ACCOUNT_FILE = 'google_credentials.json'

# --- APIクライアントとスプレッドシートクライアントの準備 ---
# (producer.pyと同様のsetup_apis, get_gspread_client関数をここに配置)
def setup_apis():
    try:
        X_API_KEY = os.getenv('X_API_KEY')
        X_API_SECRET = os.getenv('X_API_SECRET')
        X_ACCESS_TOKEN = os.getenv('X_ACCESS_TOKEN')
        X_ACCESS_TOKEN_SECRET = os.getenv('X_ACCESS_TOKEN_SECRET')
        client_v2 = tweepy.Client(
            consumer_key=X_API_KEY, consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN, access_token_secret=X_ACCESS_TOKEN_SECRET
        )
        print("✅ X APIクライアントの準備が完了しました。")
        return client_v2
    except Exception as e:
        print(f"🛑 エラー: X APIキーの読み込みエラー: {e}")
        return None

def get_gspread_client():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        return gspread.authorize(creds)
    return None

def post_to_x(client, text):
    """テキストツイートを投稿する"""
    try:
        response = client.create_tweet(text=text)
        print(f"✅ Xへの投稿に成功！ Tweet ID: {response.data['id']}")
        return True
    except Exception as e:
        print(f"🛑 Xへの投稿中にエラー: {e}")
        return False

def main():
    print("🚀 投稿ボットを実行します。")
    x_client = setup_apis()
    gc = get_gspread_client()

    if not x_client or not gc:
        print("🛑 クライアントの初期化に失敗。処理を終了します。")
        return

    try:
        worksheet = gc.open(SPREADSHEET_NAME).sheet1
        all_posts = worksheet.get_all_records() # 辞書形式で全レコードを取得

        jst = pytz.timezone('Asia/Tokyo')
        current_time_str = datetime.now(jst).strftime("%H:%M")
        print(f"現在の日本時間: {current_time_str}")
        
        for i, post in enumerate(all_posts):
            # スプレッドシートの行番号は、ヘッダー行があるのでi+2
            row_num = i + 2 
            if post.get('scheduled_time') == current_time_str and post.get('status') == 'pending':
                print(f"⏰ 投稿時間です！ {post.get('post_type')} の投稿を実行します...")
                print(f"投稿内容: {post.get('content')}")
                
                # Xに投稿
                if post_to_x(x_client, post.get('content')):
                    # 成功したら、ステータスを'posted'に更新
                    worksheet.update_cell(row_num, 4, 'posted') # 4は'status'列
                    print(f"✅ スプレッドシートのステータスを'posted'に更新しました。(行番号: {row_num})")
                    break # 1回の実行で1つの投稿のみ
                else:
                    # 失敗したら、ステータスを'failed'に更新
                    worksheet.update_cell(row_num, 4, 'failed')
                    print(f"⚠️ 投稿に失敗したため、ステータスを'failed'に更新しました。")
                    break
        print("✅ スケジュールチェック完了。")

    except Exception as e:
        print(f"🛑 投稿ボットのメイン処理でエラー: {e}")
        
    print("🏁 投稿ボットを終了します。")

if __name__ == "__main__":
    main()
