import os
import sys
import random
import json
import time
import re
from datetime import datetime, date
import pytz

# --- 最初に最低限のライブラリのみをインポート ---
print("--- SCRIPT START ---")
sys.stdout.flush()

# --- 定数と設定 ---
SPREADSHEET_NAME = 'コスメ投稿案リスト'
SERVICE_ACCOUNT_FILE = 'google_credentials.json'
POSTING_SCHEDULE = {
    "21:00": "hybrid", "22:00": "hybrid", "22:30": "hybrid", "21:30": "hybrid", "14:00": "hybrid",
    "15:00": "hybrid", "12:30": "hybrid", "19:00": "hybrid", "11:00": "hybrid", "00:00": "hybrid"
}
SEASONAL_TOPICS = ["春の新作色っぽリップ", "夏の崩れない最強下地", "秋の抜け感ブラウンシャドウ", "冬の高保湿スキンケア", "紫外線対策 日焼け止め", "汗・皮脂に強いファンデーション"]
CONCERN_TOPICS = ["気になる毛穴の黒ずみ撃退法", "頑固なニキビ跡を隠すコンシーラー術", "敏感肌でも安心な低刺激コスメ", "ブルベ女子に似合う透明感チーク", "イエベ女子のための必勝アイシャドウ"]
TECHNIQUE_TOPICS = ["中顔面を短縮するメイクテクニック", "誰でも簡単！涙袋の作り方", "プロが教える眉毛の整え方", "チークをアイシャドウとして使う裏技", "証明写真 盛れるメイク術"]
ALL_TOPICS_SEED = SEASONAL_TOPICS + CONCERN_TOPICS + TECHNIQUE_TOPICS

# --- グローバル変数 ---
g_rakuten_app_id = None
g_rakuten_affiliate_id = None
g_amazon_access_key, g_amazon_secret_key, g_amazon_associate_tag = None, None, None
g_gemini_model = None

# --- 初期セットアップ ---
def setup_apis():
    global g_rakuten_app_id, g_rakuten_affiliate_id, g_amazon_access_key, g_amazon_secret_key, g_amazon_associate_tag, g_gemini_model
    print("デバッグ: setup_apis() 関数を開始します。")
    sys.stdout.flush()
    try:
        # ★★★ Geminiライブラリをここでインポート ★★★
        import google.generativeai as genai
        print("デバッグ: google.generativeai をインポートしました。")
        sys.stdout.flush()
        
        GEMINI_API_KEY = os.getenv('GEMINI_API_KEY2')
        g_rakuten_app_id = os.getenv('RAKUTEN_APP_ID')
        g_rakuten_affiliate_id = os.getenv('RAKUTEN_AFFILIATE_ID')
        g_amazon_access_key = os.getenv('AMAZON_ACCESS_KEY')
        g_amazon_secret_key = os.getenv('AMAZON_SECRET_KEY')
        g_amazon_associate_tag = os.getenv('AMAZON_ASSOCIATE_TAG')
        
        if not all([GEMINI_API_KEY, g_rakuten_app_id, g_amazon_access_key]):
            print("🛑 エラー: 必要なAPIキーが環境変数に設定されていません。")
            return False
            
        genai.configure(api_key=GEMINI_API_KEY)
        g_gemini_model = genai.GenerativeModel('gemini-1.5-flash')
        print("✅ APIキーとGeminiモデルの準備が完了しました。")
        sys.stdout.flush()
        return True
    except Exception as e:
        print(f"🛑 エラー: APIセットアップ中にエラー: {e}")
        sys.stdout.flush()
        return False

def get_gspread_client():
    print("デバッグ: get_gspread_client() 関数を開始します。")
    sys.stdout.flush()
    try:
        # ★★★ スプレッドシート関連ライブラリをここでインポート ★★★
        import gspread
        from google.oauth2.service_account import Credentials
        print("デバッグ: gspread と Credentials をインポートしました。")
        sys.stdout.flush()

        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        if os.path.exists(SERVICE_ACCOUNT_FILE):
            creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
            gc = gspread.authorize(creds)
            print("✅ gspreadクライアントの認証に成功しました。")
            sys.stdout.flush()
            return gc
        else:
            print(f"🛑 エラー: サービスアカウントのキーファイル '{SERVICE_ACCOUNT_FILE}' が見つかりません。")
            return None
    except Exception as e:
        print(f"🛑 エラー: gspreadクライアントの取得中にエラー: {e}")
    return None

def search_products(platform, keyword):
    """プラットフォームに応じて商品を検索する"""
    print(f"  - {platform.capitalize()}を検索中... (キーワード: '{keyword}')")
    sys.stdout.flush()
    try:
        import requests # ★★★ requestsをここでインポート ★★★
        if platform == "rakuten":
            params = {"applicationId": g_rakuten_app_id, "affiliateId": g_rakuten_affiliate_id, "keyword": keyword, "format": "json", "sort": "-reviewCount", "hits": 10}
            response = requests.get("https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601", params=params)
            response.raise_for_status()
            return [{"name": i['Item']['itemName'], "url": i['Item']['affiliateUrl']} for i in response.json().get("Items", [])]
        elif platform == "amazon":
            # ★★★ Amazon関連ライブラリをここでインポート ★★★
            from paapi5_python_sdk.api.default_api import DefaultApi
            from paapi5_python_sdk.models.partner_type import PartnerType
            from paapi5_python_sdk.models.search_items_request import SearchItemsRequest
            from paapi5_python_sdk.models.search_items_resource import SearchItemsResource
            from paapi5_python_sdk.rest import ApiException
            
            api_client = DefaultApi(access_key=g_amazon_access_key, secret_key=g_amazon_secret_key, host="webservices.amazon.co.jp", region="us-west-2")
            search_request = SearchItemsRequest(partner_tag=g_amazon_associate_tag, partner_type=PartnerType.ASSOCIATES, keywords=keyword, search_index="Beauty", resources=[SearchItemsResource.ITEMINFO_TITLE, SearchItemsResource.DETAILPAGEURL], item_count=10)
            response = api_client.search_items(search_request)
            return [{"name": i.item_info.title.display_value, "url": i.detail_page_url} for i in response.search_result.items] if response.search_result and response.search_result.items else []
    except Exception as e:
        print(f"  🛑 {platform} APIエラー: {e}")
    return []

def generate_hybrid_post(topic_seed):
    # (この関数のロジックは変更なし)
    print(f"  - テーマの切り口「{topic_seed}」で投稿案を生成中...")
    # ...
    # (前回と同じコード)
    # ...
    return {"type": "hybrid", "topic": topic, "content": final_content}

if __name__ == "__main__":
    print("--- メイン処理の開始 ---")
    sys.stdout.flush()
    if not setup_apis(): raise SystemExit()
    gc = get_gspread_client()
    if not gc: raise SystemExit()
    
    # (この後のメインロジックは変更なし)
    # ...
    print("🏁 コンテンツ一括生成プログラムを終了します。")
    sys.stdout.flush()
