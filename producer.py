import os
import sys
import random
import json
import time
import re
from datetime import datetime, date
import pytz

# --- どのライブラリの読み込みで問題が起きるかチェック ---
print("--- SCRIPT START ---")
sys.stdout.flush()

try:
    print("Importing: gspread")
    import gspread
    sys.stdout.flush()

    print("Importing: google.generativeai")
    import google.generativeai as genai
    sys.stdout.flush()

    print("Importing: google.oauth2.service_account")
    from google.oauth2.service_account import Credentials
    sys.stdout.flush()
    
    print("Importing: requests")
    import requests
    sys.stdout.flush()

    print("✅ All libraries imported successfully.")
    sys.stdout.flush()
except ImportError as e:
    print(f"🛑 FATAL: Library import failed: {e}")
    sys.stdout.flush()
    raise SystemExit()


# --- 定数と設定 ---
SPREADSHEET_NAME = 'コスメ投稿案リスト'
SERVICE_ACCOUNT_FILE = 'google_credentials.json'
WEEKDAY_SCHEDULE = {"07:00":"planner", "07:30":"planner", "08:30":"planner", "12:05":"planner", "12:30":"planner", "16:00":"planner", "17:30":"planner", "19:00":"affiliate", "20:00":"affiliate", "21:00":"affiliate", "21:45":"planner", "22:15":"affiliate", "23:00":"planner", "23:45":"planner", "00:30":"planner"}
HOLIDAY_SCHEDULE = {"09:30":"planner", "10:30":"planner", "11:30":"affiliate", "13:00":"planner", "14:30":"planner", "16:00":"affiliate", "17:30":"planner", "19:00":"planner", "20:00":"affiliate", "21:00":"affiliate", "21:45":"planner", "22:30":"affiliate", "23:15":"planner", "23:50":"affiliate", "00:30":"planner"}


# --- 初期セットアップ ---
def setup_and_get_clients():
    print("デバッグ: setup_and_get_clients() 関数を開始します。")
    sys.stdout.flush()
    
    # APIキーの読み込み
    gemini_api_key = os.getenv('GEMINI_API_KEY2')
    rakuten_app_id = os.getenv('RAKUTEN_APP_ID')
    rakuten_affiliate_id = os.getenv('RAKUTEN_AFFILIATE_ID')
    
    if not all([gemini_api_key, rakuten_app_id, rakuten_affiliate_id]):
        print("🛑 エラー: Geminiまたは楽天のAPIキーが環境変数に設定されていません。")
        return None, None
        
    print("デバッグ: Geminiと楽天のAPIキーを環境変数から取得しました。")
    sys.stdout.flush()
    
    genai.configure(api_key=gemini_api_key)
    print("デバッグ: genai.configure() が完了しました。")
    sys.stdout.flush()
    
    # gspreadクライアントのセットアップ
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        print("デバッグ: サービスアカウントファイルが見つかりました。認証を開始します。")
        sys.stdout.flush()
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        print("デバッグ: gspread.authorize() が完了しました。")
        sys.stdout.flush()
        return gc, rakuten_app_id, rakuten_affiliate_id
    else:
        print(f"🛑 エラー: サービスアカウントのキーファイル '{SERVICE_ACCOUNT_FILE}' が見つかりません。")
        return None, None, None

# ...(他の関数は変更なしなので省略)...
# (前回のコードから、run_content_plannerとrun_affiliate_botの関数をここにコピーしてください)
def run_content_planner(worksheet):
    # (省略)
    pass
def run_affiliate_bot(worksheet, rakuten_app_id, rakuten_affiliate_id):
    # (省略)
    pass


# ==============================================================================
# メインの実行ロジック
# ==============================================================================
if __name__ == "__main__":
    print("🚀 スケジュール実行を開始します。")
    sys.stdout.flush()
    
    gc, RAKUTEN_APP_ID, RAKUTEN_AFFILIATE_ID = setup_and_get_clients()

    if not gc:
        print("🛑 クライアントのセットアップに失敗したため、処理を終了します。")
        sys.stdout.flush()
        raise SystemExit()

    print("✅ APIクライアントとスプレッドシートクライアントの準備が完了しました。")
    sys.stdout.flush()

    # (この後の時刻チェックとタスク実行のロジックは変更なしなので省略)
    # (前回のコードから、main()関数内の時刻チェック以降のロジックをここにコピーしてください)
    
    print("🏁 処理を終了します。")
    sys.stdout.flush()
